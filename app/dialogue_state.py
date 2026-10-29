"""Incremental dialogue state. Only client spans may establish facts.

The lexical analyser is deliberately bounded: a declarative support vocabulary,
not an NLP claim. Unknown relationships require clarification. A future analyser
can implement MessageAnalyzer; it must return grounded observations, not prose.
Neither the reducer nor the query builder performs I/O or calls a model.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import re
from typing import Protocol


SCHEMA_VERSION = 2
ENTITY_SLOTS = {"service", "manufacturer", "equipment", "ofd", "software", "integration", "component"}
CLARIFICATION_SLOTS = ENTITY_SLOTS | {"goal", "details", "task"}
RELATIONS = {"new_task", "continue", "parameter_update", "constraint_update",
             "contradiction", "answer_to_clarification", "unknown"}
NON_TASK_TURN_KINDS = {"greeting", "thanks", "capabilities", "vague_help"}
NON_TASK_SCENARIO_REASONS = {
    "pre_retrieval_greeting", "pre_retrieval_thanks",
    "pre_retrieval_capabilities", "task_not_specified",
}


@dataclass(frozen=True)
class Fact:
    value: str
    message_id: int | str
    quote: str
    start: int
    end: int

    @classmethod
    def span(cls, text: str, message_id: int | str, start: int = 0,
             end: int | None = None, *, value: str | None = None) -> Fact:
        end = len(text) if end is None else end
        return cls(value if value is not None else text[start:end].strip(),
                   message_id, text[start:end], start, end)


@dataclass
class ExpectedClarification:
    slot: str
    question: str
    message_id: int | str | None = None
    reason: str | None = None


@dataclass
class SessionContext:
    """Confirmed conversation facts; never imply that a new task uses them."""
    entities: dict[str, list[Fact]] = field(default_factory=dict)
    active_route: ActiveRoute | None = None


@dataclass
class ActiveRoute:
    slot: str
    fact: Fact

    @property
    def value(self) -> str:
        return self.fact.value


@dataclass
class TaskContext:
    task_id: str | None = None
    topic_start_message_id: int | str | None = None
    intent: str = "unknown"
    operation: str = "unknown"
    object: str | None = None
    entities: dict[str, list[Fact]] = field(default_factory=dict)
    active_route: ActiveRoute | None = None
    parameters: list[Fact] = field(default_factory=list)
    object_reference: Fact | None = None
    task_fact: Fact | None = None
    operation_evidence: Fact | None = None
    operation_confidence: float = 0.0
    symptom: Fact | None = None
    superseded_facts: list[Fact] = field(default_factory=list)
    goals: list[Fact] = field(default_factory=list)
    constraints: list[Fact] = field(default_factory=list)
    details: list[Fact] = field(default_factory=list)
    error: Fact | None = None
    expected: ExpectedClarification | None = None
    relation: str = "new_task"
    confidence: float = 1.0
    transition: str = "new_task"
    analysis_required: bool = False
    unresolved: Fact | None = None
    unknown_facts: list[str] = field(default_factory=list)
    # Additive ProgressLedger. Units are copied only from a verified approved
    # answer; outcomes are written only by DialogueManager from client spans.
    procedure_id: str | None = None
    shown_units: list[dict] = field(default_factory=list)
    eligible_units: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    open_question: str | None = None
    current_subgoal: Fact | None = None
    clarification_repeats: dict[str, int] = field(default_factory=dict)
    closed: bool = False


def _fact(value):
    if value is None or isinstance(value, Fact):
        return value
    return Fact(**value)


def _facts_by_slot(values: dict[str, list[Fact | dict]]) -> dict[str, list[Fact]]:
    return {slot: [_fact(f) for f in facts] for slot, facts in (values or {}).items()}


def _session_from(value: SessionContext | dict) -> SessionContext:
    if isinstance(value, SessionContext):
        return value
    route = value.get("active_route")
    if route and not isinstance(route, ActiveRoute):
        route = ActiveRoute(route["slot"], _fact(route["fact"]))
    return SessionContext(_facts_by_slot(value.get("entities", {})), route)


def _task_from(value: TaskContext | dict) -> TaskContext:
    if isinstance(value, TaskContext):
        return value
    raw = deepcopy(value)
    raw["entities"] = _facts_by_slot(raw.get("entities", {}))
    for key in ("parameters", "goals", "constraints", "details", "superseded_facts"):
        raw[key] = [_fact(f) for f in raw.get(key, [])]
    for key in ("object_reference", "task_fact", "operation_evidence", "symptom", "error", "unresolved", "current_subgoal"):
        raw[key] = _fact(raw.get(key))
    if raw.get("expected") and not isinstance(raw["expected"], ExpectedClarification):
        raw["expected"] = ExpectedClarification(**raw["expected"])
    route = raw.get("active_route")
    if route and not isinstance(route, ActiveRoute):
        raw["active_route"] = ActiveRoute(route["slot"], _fact(route["fact"]))
    return TaskContext(**raw)


class DialogueState:
    """Versioned state with real session/task ownership and a v1 facade.

    Existing callers can continue reading and assigning the old flat property
    names. The serialized source of truth is SessionContext plus TaskContext.
    """
    def __init__(self, schema_version: int = SCHEMA_VERSION, revision: int = 0,
                 task_id: str | None = None, topic_start_message_id: int | str | None = None,
                 intent: str = "unknown", operation: str = "unknown", object: str | None = None,
                 entities: dict[str, list[Fact]] | None = None, routing_slot: str | None = None,
                 parameters: list[Fact] | None = None, object_reference: Fact | None = None,
                 task: Fact | None = None, operation_evidence: Fact | None = None,
                 goals: list[Fact] | None = None, constraints: list[Fact] | None = None,
                 details: list[Fact] | None = None, error: Fact | None = None,
                 expected: ExpectedClarification | None = None, transition: str = "new_task",
                 analysis_required: bool = False, unresolved: Fact | None = None,
                 *, session: SessionContext | dict | None = None,
                 task_context: TaskContext | dict | None = None,
                 relation: str | None = None, confidence: float = 1.0):
        if schema_version not in {1, SCHEMA_VERSION}:
            raise ValueError("Unsupported dialogue state schema; preserve the snapshot and migrate explicitly")
        self.schema_version = SCHEMA_VERSION
        self.revision = revision
        self.session = _session_from(session) if session is not None else SessionContext(entities or {})
        task_supplied = task_context is not None
        self.task_context = _task_from(task_context) if task_supplied else None
        has_task = bool(task_id or intent != "unknown" or operation != "unknown" or task or
                        parameters or goals or constraints or details or expected or
                        analysis_required or routing_slot)
        if self.task_context is None and has_task:
            self.task_context = TaskContext()
        if self.task_context is not None and not task_supplied:
            self.task_context.task_id = task_id or self.task_context.task_id
            self.task_context.topic_start_message_id = topic_start_message_id or self.task_context.topic_start_message_id
            self.task_context.intent = intent
            self.task_context.operation = operation
            self.task_context.object = object
            self.task_context.parameters = parameters or []
            self.task_context.object_reference = object_reference
            self.task_context.task_fact = task
            self.task_context.operation_evidence = operation_evidence
            self.task_context.goals = goals or []
            self.task_context.constraints = constraints or []
            self.task_context.details = details or []
            self.task_context.error = error
            self.task_context.expected = expected
            self.task_context.transition = transition
            self.task_context.analysis_required = analysis_required
            self.task_context.unresolved = unresolved
            if relation:
                self.task_context.relation = relation
            if routing_slot and routing_slot in self.task_context.entities:
                facts = self.task_context.entities[routing_slot]
                if len(facts) == 1:
                    self.task_context.active_route = ActiveRoute(routing_slot, facts[0])

    def _ensure_task(self) -> TaskContext:
        if self.task_context is None:
            self.task_context = TaskContext()
        return self.task_context

    @property
    def active_task(self) -> TaskContext | None:
        return self.task_context

    @active_task.setter
    def active_task(self, value: TaskContext | None) -> None:
        self.task_context = value

    @property
    def task_id(self): return self.task_context.task_id if self.task_context else None
    @task_id.setter
    def task_id(self, value): self._ensure_task().task_id = value
    @property
    def topic_start_message_id(self): return self.task_context.topic_start_message_id if self.task_context else None
    @topic_start_message_id.setter
    def topic_start_message_id(self, value): self._ensure_task().topic_start_message_id = value
    @property
    def intent(self): return self.task_context.intent if self.task_context else "unknown"
    @intent.setter
    def intent(self, value): self._ensure_task().intent = value
    @property
    def operation(self): return self.task_context.operation if self.task_context else "unknown"
    @operation.setter
    def operation(self, value): self._ensure_task().operation = value
    @property
    def object(self): return self.task_context.object if self.task_context else None
    @object.setter
    def object(self, value): self._ensure_task().object = value
    @property
    def entities(self): return self.session.entities
    @entities.setter
    def entities(self, value): self.session.entities = value
    @property
    def routing_slot(self): return self.task_context.active_route.slot if self.task_context and self.task_context.active_route else None
    @routing_slot.setter
    def routing_slot(self, value):
        task = self._ensure_task()
        facts = task.entities.get(value, []) if value else []
        task.active_route = ActiveRoute(value, facts[0]) if value and len(facts) == 1 else None
    @property
    def parameters(self): return self.task_context.parameters if self.task_context else []
    @parameters.setter
    def parameters(self, value): self._ensure_task().parameters = value
    @property
    def object_reference(self): return self.task_context.object_reference if self.task_context else None
    @object_reference.setter
    def object_reference(self, value): self._ensure_task().object_reference = value
    @property
    def task(self): return self.task_context.task_fact if self.task_context else None
    @task.setter
    def task(self, value): self._ensure_task().task_fact = value
    @property
    def operation_evidence(self): return self.task_context.operation_evidence if self.task_context else None
    @operation_evidence.setter
    def operation_evidence(self, value): self._ensure_task().operation_evidence = value
    @property
    def operation_confidence(self): return self.task_context.operation_confidence if self.task_context else 0.0
    @operation_confidence.setter
    def operation_confidence(self, value): self._ensure_task().operation_confidence = float(value)
    @property
    def symptom(self): return self.task_context.symptom if self.task_context else None
    @symptom.setter
    def symptom(self, value): self._ensure_task().symptom = value
    @property
    def superseded_facts(self): return self.task_context.superseded_facts if self.task_context else []
    @property
    def goals(self): return self.task_context.goals if self.task_context else []
    @goals.setter
    def goals(self, value): self._ensure_task().goals = value
    @property
    def constraints(self): return self.task_context.constraints if self.task_context else []
    @constraints.setter
    def constraints(self, value): self._ensure_task().constraints = value
    @property
    def details(self): return self.task_context.details if self.task_context else []
    @details.setter
    def details(self, value): self._ensure_task().details = value
    @property
    def error(self): return self.task_context.error if self.task_context else None
    @error.setter
    def error(self, value): self._ensure_task().error = value
    @property
    def expected(self): return self.task_context.expected if self.task_context else None
    @expected.setter
    def expected(self, value): self._ensure_task().expected = value
    @property
    def transition(self): return self.task_context.transition if self.task_context else "new_task"
    @transition.setter
    def transition(self, value): self._ensure_task().transition = value
    @property
    def relation(self): return self.task_context.relation if self.task_context else "new_task"
    @relation.setter
    def relation(self, value):
        if value not in RELATIONS: raise ValueError(f"Unsupported dialogue relation: {value}")
        self._ensure_task().relation = value
    @property
    def confidence(self): return self.task_context.confidence if self.task_context else 1.0
    @confidence.setter
    def confidence(self, value): self._ensure_task().confidence = float(value)
    @property
    def analysis_required(self): return self.task_context.analysis_required if self.task_context else False
    @analysis_required.setter
    def analysis_required(self, value): self._ensure_task().analysis_required = value
    @property
    def unresolved(self): return self.task_context.unresolved if self.task_context else None
    @unresolved.setter
    def unresolved(self, value): self._ensure_task().unresolved = value

    def _legacy_route_entities(self) -> dict[str, list[Fact]]:
        if not self.task_context:
            return {}
        route = self.task_context.active_route
        if not route:
            return {}
        active = {route.slot: [route.fact]}
        if route.slot == "manufacturer" and "equipment" in self.task_context.entities:
            active["equipment"] = self.task_context.entities["equipment"]
        return active

    @property
    def task_entities(self) -> dict[str, list[Fact]]:
        if not self.task_context:
            return {}
        if self.operation == "explain" and self.routing_slot is None:
            return {}
        cabinet_task = self.intent in {"access", "credentials", "receipt", "report"} or (
            self.intent == "device" and self.operation == "list" and not self.error)
        if cabinet_task:
            return self._legacy_route_entities()
        return self.task_context.entities

    def entity(self, slot: str) -> str | None:
        values = self.session.entities.get(slot, [])
        return values[0].value if len(values) == 1 else None

    def task_entity(self, slot: str) -> str | None:
        values = (self.task_context.entities.get(slot, []) if self.task_context else [])
        return values[0].value if len(values) == 1 else None

    def reusable_session_route(self, intent: str) -> ActiveRoute | None:
        route = self.session.active_route
        if not route:
            return None
        if intent in {"access", "credentials", "report"} and route.slot in {"service", "software"}:
            return route
        if intent in {"receipt", "fiscal_drive"}:
            if route.slot == "ofd" or (route.slot == "service" and route.value != "ТС ПиОТ"):
                return route
            if intent == "fiscal_drive" and route.slot == "manufacturer":
                return route
        if intent == "bank_statement" and route.slot == "software":
            return route
        if intent == "device" and route.slot == "manufacturer":
            return route
        return None

    @property
    def routing_service(self) -> str | None:
        if not self.task_context or not self.task_context.active_route:
            return None
        return self.task_context.active_route.value

    def to_dict(self) -> dict:
        session = {"entities": {k: [asdict(f) for f in values]
                                for k, values in self.session.entities.items()},
                   "active_route": ({"slot": self.session.active_route.slot,
                                     "fact": asdict(self.session.active_route.fact)}
                                    if self.session.active_route else None)}
        task = None
        if self.task_context:
            t = self.task_context
            task = {
                "task_id": t.task_id, "topic_start_message_id": t.topic_start_message_id,
                "intent": t.intent, "operation": t.operation, "object": t.object,
                "entities": {k: [asdict(f) for f in values] for k, values in t.entities.items()},
                "active_route": ({"slot": t.active_route.slot, "fact": asdict(t.active_route.fact)}
                                 if t.active_route else None),
                "parameters": [asdict(f) for f in t.parameters],
                "object_reference": asdict(t.object_reference) if t.object_reference else None,
                "task_fact": asdict(t.task_fact) if t.task_fact else None,
                "operation_evidence": asdict(t.operation_evidence) if t.operation_evidence else None,
                "operation_confidence": t.operation_confidence,
                "symptom": asdict(t.symptom) if t.symptom else None,
                "superseded_facts": [asdict(f) for f in t.superseded_facts],
                "goals": [asdict(f) for f in t.goals], "constraints": [asdict(f) for f in t.constraints],
                "details": [asdict(f) for f in t.details], "error": asdict(t.error) if t.error else None,
                "expected": asdict(t.expected) if t.expected else None, "relation": t.relation,
                "confidence": t.confidence, "transition": t.transition,
                "analysis_required": t.analysis_required, "unresolved": asdict(t.unresolved) if t.unresolved else None,
                "unknown_facts": list(t.unknown_facts),
                "procedure_id": t.procedure_id, "shown_units": deepcopy(t.shown_units),
                "eligible_units": deepcopy(t.eligible_units),
                "checks": deepcopy(t.checks), "open_question": t.open_question,
                "current_subgoal": asdict(t.current_subgoal) if t.current_subgoal else None,
                "clarification_repeats": dict(t.clarification_repeats), "closed": t.closed,
            }
        # Top-level compatibility projection remains available to existing consumers.
        return {
            "schema_version": SCHEMA_VERSION, "revision": self.revision,
            "session": session, "task_context": task,
            "task_id": self.task_id, "topic_start_message_id": self.topic_start_message_id,
            "intent": self.intent, "operation": self.operation, "object": self.object,
            "entities": session["entities"], "routing_slot": self.routing_slot,
            "parameters": [asdict(f) for f in self.parameters],
            "object_reference": asdict(self.object_reference) if self.object_reference else None,
            "task": asdict(self.task) if self.task else None,
            "operation_evidence": asdict(self.operation_evidence) if self.operation_evidence else None,
            "goals": [asdict(f) for f in self.goals], "constraints": [asdict(f) for f in self.constraints],
            "details": [asdict(f) for f in self.details], "error": asdict(self.error) if self.error else None,
            "expected": asdict(self.expected) if self.expected else None, "relation": self.relation,
            "confidence": self.confidence, "transition": self.transition,
            "analysis_required": self.analysis_required,
            "unresolved": asdict(self.unresolved) if self.unresolved else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DialogueState:
        version = data.get("schema_version")
        if version not in {1, SCHEMA_VERSION}:
            raise ValueError("Unsupported dialogue state schema; preserve the snapshot and migrate explicitly")
        if version == SCHEMA_VERSION and "session" in data:
            session_raw = data.get("session") or {}
            task_raw = data.get("task_context")
            return cls(schema_version=SCHEMA_VERSION, revision=data.get("revision", 0),
                       session=session_raw, task_context=task_raw,
                       relation=(task_raw or {}).get("relation"),
                       confidence=(task_raw or {}).get("confidence", 1.0))
        raw = deepcopy(data)
        entities = _facts_by_slot(raw.get("entities", {}))
        intent, operation = raw.get("intent", "unknown"), raw.get("operation", "unknown")
        routing_slot = raw.get("routing_slot")
        task_entities = {}
        if routing_slot in entities:
            task_entities[routing_slot] = entities[routing_slot]
            if routing_slot == "manufacturer" and "equipment" in entities:
                task_entities["equipment"] = entities["equipment"]
        task_raw = {
            "task_id": raw.get("task_id"), "topic_start_message_id": raw.get("topic_start_message_id"),
            "intent": intent, "operation": operation, "object": raw.get("object"),
            "entities": {k: [asdict(f) for f in v] for k, v in task_entities.items()},
            "active_route": ({"slot": routing_slot, "fact": asdict(task_entities[routing_slot][0])}
                             if routing_slot in task_entities and len(task_entities[routing_slot]) == 1 else None),
            "parameters": raw.get("parameters", []), "object_reference": raw.get("object_reference"),
            "task_fact": raw.get("task"), "operation_evidence": raw.get("operation_evidence"),
            "operation_confidence": raw.get("operation_confidence", 0.0), "symptom": raw.get("symptom"),
            "superseded_facts": raw.get("superseded_facts", []),
            "goals": raw.get("goals", []), "constraints": raw.get("constraints", []),
            "details": raw.get("details", []), "error": raw.get("error"), "expected": raw.get("expected"),
            "relation": "new_task" if raw.get("transition", "new_task") == "new_task" else "continue",
            "confidence": 0.7, "transition": raw.get("transition", "new_task"),
            "analysis_required": raw.get("analysis_required", False), "unresolved": raw.get("unresolved"),
            "unknown_facts": raw.get("unknown_facts", []),
        }
        legacy_route = task_raw.get("active_route")
        return cls(revision=raw.get("revision", 0), session={
            "entities": {k: [asdict(f) for f in v] for k, v in entities.items()},
            "active_route": legacy_route}, task_context=task_raw)


@dataclass
class Observation:
    """Typed patch produced solely from the current client message.

    This is the stable boundary for a future semantic analyzer: each typed
    claim may carry its own confidence and source span, and relation must be
    one of RELATIONS. The reducer validates every span before applying it.
    """
    entities: dict[str, list[Fact]] = field(default_factory=dict)
    # Explicit statements that the client does not know a requested value are
    # facts too; each slot must point to an exact span in the current message.
    unknown_facts: dict[str, Fact] = field(default_factory=dict)
    # Per-field diagnostics from typed Understanding; informational only and
    # never used as facts by the reducer.
    validation_diagnostics: list[dict] = field(default_factory=list)
    intent: str = "unknown"
    operation: str = "unknown"
    object: str | None = None
    evidence: Fact | None = None
    intent_evidence: Fact | None = None
    object_evidence: Fact | None = None
    operation_evidence: Fact | None = None
    relation_evidence: Fact | None = None
    symptom: Fact | None = None
    goals: list[Fact] = field(default_factory=list)
    constraints: list[Fact] = field(default_factory=list)
    details: list[Fact] = field(default_factory=list)
    error: Fact | None = None
    new_topic: bool = False
    reference: bool = False
    question: bool = False
    requirement: bool = False
    entity_only: bool = False
    feedback: bool = False
    uncertain: bool = False
    parameters: list[Fact] = field(default_factory=list)
    binds_object: bool = False
    relation: str = "unknown"
    confidence: float = 0.5
    intent_confidence: float = 0.0
    operation_confidence: float = 0.0
    relation_confidence: float = 0.0


class MessageAnalyzer(Protocol):
    def analyze(self, text: str, message_id: int | str, state: DialogueState) -> Observation: ...


def words(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[-.,][\w]+)*", text.casefold().replace("ё", "е"))


_SOCIAL_PREFIXES = (
    ("добрый", "день"), ("доброе", "утро"), ("добрый", "вечер"),
    ("доброго", "дня"), ("доброго", "вечера"),
    ("здравствуйте",), ("здравствуй",), ("привет",),
)
_THANKS_PREFIXES = (("большое", "спасибо"), ("спасибо",), ("благодарю",))
_COURTESY = {"пожалуйста", "бот", "тебя", "вас"}


def _remove_turn_prefixes(tokens: list[str], prefixes: tuple[tuple[str, ...], ...]) -> tuple[list[str], bool]:
    remaining, removed = list(tokens), False
    changed = True
    while changed:
        changed = False
        while remaining and remaining[0] in _COURTESY:
            remaining.pop(0)
        for prefix in prefixes:
            if tuple(remaining[:len(prefix)]) == prefix:
                remaining = remaining[len(prefix):]
                removed = changed = True
                break
    while remaining and remaining[-1] in _COURTESY:
        remaining.pop()
    return remaining, removed


def is_resolution_turn(text: str) -> bool:
    """Recognize a conversational close from ordinary completion language."""
    normalized = " ".join(words(text))
    if not normalized:
        return False
    completion = r"(?:решен\w*|помог\w*|получил\w*|получилось|сработал\w*|готов\w*|вопрос\s+закрыт\w*)"
    gratitude = r"(?:спасибо|благодарю|благодарность)"
    return bool(re.search(gratitude + r".*\b" + completion + r"\b", normalized)
                or re.search(r"\b" + completion + r"\b.*" + gratitude, normalized)
                or re.fullmatch(gratitude + r" (?:пока )?(?:все|на сегодня все)", normalized))


def classify_user_turn(text: str) -> str:
    """Classify only turns that are safe to answer without retrieval.

    The allow-list is intentionally narrow. Greetings or courtesy words are
    stripped only at the edges, so a concrete request such as
    ``привет, как найти чек?`` remains a normal task.
    """
    if is_resolution_turn(text):
        return "resolved"
    tokens = words(text)
    if not tokens:
        return "vague_help"
    remaining, greeted = _remove_turn_prefixes(tokens, _SOCIAL_PREFIXES)
    remaining, thanked = _remove_turn_prefixes(remaining, _THANKS_PREFIXES)
    phrase = " ".join(remaining)
    if not remaining:
        return "thanks" if thanked else "greeting" if greeted else "vague_help"
    if re.fullmatch(
        r"что ты умеешь|"
        r"что вы умеете|"
        r"чем (?:ты |вы )?можешь помочь|"
        r"как (?:ты |вы )?можешь помочь|"
        r"какие (?:вопросы|задачи) (?:ты |вы )?(?:решаешь|решаете)",
        phrase,
    ):
        return "capabilities"
    if re.fullmatch(
        r"(?:помоги|помогите)(?: мне)?|"
        r"(?:мне )?(?:нужна|требуется) помощь|"
        r"(?:у меня (?:есть )?)?(?:вопрос|проблема|трудность)|"
        r"(?:не знаю )?что делать|"
        r"как быть|(?:подскажи|подскажите)",
        phrase,
    ):
        return "vague_help"
    return "task"


def has(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(token.startswith(stems) for token in tokens)


_FAILURE_STEMS = ("сбо", "ошиб", "неисправ", "перестал", "прекрат", "непроход", "незагруж")
_NEGATED_ACTION_STEMS = ("работ", "загруж", "проход", "отправ", "печат", "подключ", "приним")
_DESCRIPTIVE_ACTION_ENDINGS = ("ен", "ена", "ено", "ены", "ён", "ёна", "ёно", "ёны",
                               "анный", "енный", "авший", "ивший", "уемый", "имая", "имое")


def _failure_span(text: str) -> tuple[int, int] | None:
    """Return an evidence span for explicit failure language, not its cause."""
    tokens = list(re.finditer(r"[\w]+(?:[-.,][\w]+)*", text.casefold().replace("ё", "е")))
    for index, token in enumerate(tokens):
        word = token.group()
        if word.startswith(_FAILURE_STEMS):
            prefix = [t.group() for t in tokens[max(0, index - 2):index]]
            if word.startswith(("перестал", "прекрат")) and "не" in prefix:
                continue
            return token.start(), token.end()
        if word == "не" and index + 1 < len(tokens) and tokens[index + 1].group().startswith(_NEGATED_ACTION_STEMS):
            return token.start(), tokens[index + 1].end()
    return None


def client_clauses(text: str):
    """Source spans separated by punctuation and restriction operators."""
    boundaries = {0, len(text)}
    boundaries.update(m.start() for m in re.finditer(r'[,;.!?]', text))
    boundaries.update(m.start() for m in re.finditer(r'\b(?:но|без|нельзя|только|запрещено)\b', text, re.I))
    ordered = sorted(boundaries)
    for left, right in zip(ordered, ordered[1:]):
        raw = text[left:right]
        start = left + len(raw) - len(raw.lstrip(' ,;.!?'))
        end = right - (len(raw) - len(raw.rstrip(' ,;.!?')))
        if start < end:
            yield start, end


# This is a vocabulary of entities, objects and operations. Transition decisions
# live in the reducer and do not depend on a particular test sentence.
ENTITY_NAMES = (
    ("service", "aQsi Online", ("aqsi online", "акси онлайн")),
    ("service", "АТОЛ Онлайн", ("атол онлайн", "atol online")),
    ("service", "Saby", ("saby", "саби", "сбис")),
    ("service", "Диадок", ("диадок", "диадоке", "диадока", "диадоком")),
    ("service", "БИФИТ Касса", ("бифит касса", "bifit kassa")),
    # БИФИТ is retained as the explicitly named service/vendor route. It is
    # not expanded to a product, software, manufacturer or model here.
    ("service", "БИФИТ", ("бифит", "bifit")),
    ("ofd", "Платформа ОФД", ("платформа офд", "платформе офд", "платформы офд", "платформу офд")),
    ("ofd", "Первый ОФД", ("первый офд", "первом офд")),
    ("ofd", "Такском", ("такском",)),
    ("ofd", "Астрал", ("астрал",)),
    ("software", "1С", ("1с", "1c", "один эс")),
    ("component", "ТС ПиОТ", ("тс пиот", "тспиот")),
    ("integration", "DirectBank", ("directbank", "директбанк")),
    ("service", "Честный ЗНАК", ("честный знак", "честном знаке")),
    ("manufacturer", "Эвотор", ("эвотор", "evotor")),
    ("manufacturer", "aQsi", ("aqsi", "акси")),
    ("manufacturer", "АТОЛ", ("атол", "atol")),
    ("manufacturer", "Штрих-М", ("штрих-м", "штрих")),
)
OBJECTS = (
    ("bank_statement", "банковская выписка", ("выпис",)),
    ("billing", "договор", ("договор", "срок договора", "срок действия")),
    ("billing", "тариф", ("тариф", "продлен", "продл")),
    ("billing", "оплата", ("оплата",)),
    ("delivery_document", "УПД", ("упд", "накладн", "поставк")),
    ("credentials", "учётная запись", ("парол", "авторизац")),
    ("access", "сотрудник", ("сотрудник", "коллег", "пользовател", "учетн", "учетк", "аккаунт", "доступ", "роль", "роли", "ролей", "прав", "полномоч")),
    ("report", "отчёт", ("отчет",)),
    ("fiscal_drive", "ФН", ("фн", "накопител")),
    ("receipt", "чек", ("чек", "квитанц", "оператор")),
    ("general", "ОФД", ("офд", "оператор фискальных данных")),
    ("network", "соединение", ("интернет", "связь", "сети", "подключен")),
    ("marking", "маркировка", ("маркиров", "gtin")),
    ("tax", "налогообложение", ("налог", "ндс", "усн", "псн")),
    ("device", "касса", ("касс", "ккт", "принтер")),
)
OPERATIONS = (
    ("repeat_print", ("распечат", "напечат", "перепечат", "повторн")),
    ("reset_password", ("восстанов", "сброс", "забыл")),
    ("correct", ("исправ", "корректир", "скоррект")),
    ("reconcile", ("расхожд", "недостач", "свер", "прием", "приём", "подпис")),
    ("replace", ("замен",)),
    ("close", ("закры", "закрой", "заверш")),
    ("add", ("добав", "созда", "приглас", "завести")),
    ("change", ("измен", "менять", "помен", "смен", "редактир", "отредактир")),
    ("assign", ("назнач", "присво", "выда", "огранич", "надел", "предостав", "дать")),
    ("search", ("найти", "найт", "искать", "отыск", "поиск")),
    ("list", ("перечисл",)),
    ("transmit", ("переда", "отправ")),
    ("check", ("провер", "посмотр", "смотр", "увид", "узна")),
    ("connect", ("подключ", "соедин")),
    ("configure", ("настро",)),
    ("return", ("вернут", "возврат")),
)
REFERENCES = {"он", "она", "оно", "ему", "ей", "его", "ее", "им", "этот", "эти", "эту", "это", "там", "так", "дальше", "тоже", "также"}
NEW_TOPIC = (("другой", "вопрос"), ("новый", "вопрос"), ("новая", "тема"), ("еще", "вопрос"), ("кстати",))


class LexicalAnalyzer:
    def analyze(self, text: str, message_id: int | str, state: DialogueState) -> Observation:
        tokens = words(text)
        obs = Observation(evidence=Fact.span(text, message_id))
        obs.new_topic = any(
            tuple(tokens[index:index + len(prefix)]) == prefix
            for prefix in NEW_TOPIC
            for index in range(max(1, min(len(tokens), 8)))
        )
        obs.reference = bool(set(tokens) & REFERENCES)
        obs.feedback = bool(tokens and (tokens[0] in {"да", "нет", "понятно", "спасибо"}
                            or (tokens[0] == 'не' and has(tokens[1:], ('помог', 'получил', 'сработа')))))
        question_tokens = tokens[1:] if tokens[:1] == ['а'] else tokens
        obs.question = bool(question_tokens and question_tokens[0] in {
            'как', 'где', 'куда', 'почему', 'что', 'когда', 'зачем', 'какую', 'какие', 'какой', 'сколько', 'чем'})
        obs.requirement = has(tokens, ("хоч", "нуж", "требу", "мог", "должен", "должна", "пусть"))
        obs.requirement |= bool(state.task_id and has(tokens, ('просмотр', 'чтение')) and not obs.question)
        occupied: list[tuple[int, int]] = []
        for slot, name, aliases in ENTITY_NAMES:
            # Word boundaries prevent a brand inside another name from matching.
            for alias in aliases:
                pattern = r"(?<!\w)" + r"\s*".join(re.escape(w) for w in alias.split()) + r"\w*(?!\w)"
                for match in re.finditer(pattern, text, re.I):
                    start, end = match.span()
                    if any(start < b and end > a for a, b in occupied):
                        continue
                    occupied.append((start, end))
                    prefix = words(text[:start])
                    if prefix and prefix[-1] in {'не', 'вместо'}:
                        continue  # excluded old value, not a competing current entity
                    values = obs.entities.setdefault(slot, [])
                    fact = Fact.span(text, message_id, start, end, value=name)
                    if name not in [v.value for v in values]:
                        values.append(fact)
                    if slot == "manufacturer":
                        # A model is accepted only if explicitly adjacent to its
                        # manufacturer; do not invent a model from a product page.
                        model = re.match(r"\s+\d+(?:[.,]\d+)?(?:\s*lite|[фФ])?(?!\w)", text[end:], re.I)
                        if model:
                            obs.entities.setdefault("equipment", []).append(Fact.span(
                                text, message_id, start, end + model.end()))
        covered = text
        for start, end in sorted(occupied, reverse=True):
            covered = covered[:start] + ' ' + covered[end:]
        if (state.expected and state.expected.slot == 'equipment' and state.entity('manufacturer')
                and re.fullmatch(r'\d+(?:[.,]\d+)?(?:\s*lite|[фФ])?', text.strip(), re.I)):
            obs.entities['equipment'] = [Fact.span(text, message_id, value=state.entity('manufacturer') + ' ' + text.strip())]
            covered = ''
        obs.entity_only = bool(obs.entities) and not any(
            w not in {"в", "у", "на", "я", "мой", "моя", "это", "использую", "работаю", "с", "а", "если", "тогда", "там", "так", "же", "делается", "тоже", "касса", "офд", "оборудование"}
            and not w[0].isdigit() for w in words(covered))
        # Search arguments are not search objects. Resolve the direct object
        # before a parameter preposition; bind an anaphoric object to the task.
        # This applies to any search object/argument, not a special FN sentence.
        search_request = has(tokens, next(stems for name, stems in OPERATIONS if name == 'search'))
        # Elliptical follow-ups can omit both the verb and pronoun ("А по ...?").
        substantive = [token for token in tokens if token not in {'а', 'и', 'можно', 'ли'}]
        elliptical_search = (state.operation == 'search' and substantive[:1] in [['по'], ['за']]
                             and not obs.new_topic)
        search_request |= elliptical_search
        parameter_at = next((i for i, token in enumerate(tokens) if token in {'по', 'за'}), len(tokens))
        # Bind the object to the requested action, before contextual modifiers.
        # An action noun in «после замены ...» is background, not a new command.
        boundary = next((i for i, token in enumerate(tokens) if token in {'но', 'без', 'нельзя'}), len(tokens))
        actions = [(name, token) for name, stems in OPERATIONS for token in tokens[:boundary] if token.startswith(stems)]
        commands = [name for name, token in actions if token.endswith(('ть', 'ти', 'йте'))]
        nominal_or_action = [(name, token) for name, token in actions
                             if not token.endswith(_DESCRIPTIVE_ACTION_ENDINGS)]
        obs.operation = (commands[0] if commands else
                         nominal_or_action[0][0] if nominal_or_action else 'unknown')
        subject_tokens = tokens[:parameter_at] if search_request else tokens
        if search_request:
            # In a multi-clause follow-up («есть только номер ФН. Получится
            # найти чек ...») bind the requested object after the last action,
            # while retaining the earlier FN phrase as its search parameter.
            action_indices = [i for i, token in enumerate(tokens)
                              if any(token.startswith(stems) for name, stems in OPERATIONS if name == 'search')]
            if action_indices:
                subject_tokens = tokens[action_indices[-1] + 1:parameter_at]
        if not search_request:
            stems = next((stems for name, stems in OPERATIONS if name == obs.operation), ())
            action_at = next((i for i, token in enumerate(tokens) if token.startswith(stems)), None) if stems else None
            after_action = tokens[action_at + 1:] if action_at is not None else tokens
            # Also support a fronted object: «Отчёты ... где посмотреть?».
            if any(has(after_action, object_stems) for _, _, object_stems in OBJECTS):
                subject_tokens = after_action
            modifier_at = next((i for i, token in enumerate(subject_tokens)
                                if token in {'после', 'до', 'при'}), len(subject_tokens))
            if modifier_at:
                subject_tokens = subject_tokens[:modifier_at]
        for intent, obj, stems in OBJECTS:
            if has(subject_tokens, stems):
                obs.intent, obs.object = intent, obj
                break
        if (obs.intent == "unknown" and has(tokens, ("оплат",))
                and not has(tokens, ("способ",))):
            obs.intent, obs.object = "billing", "оплата"
        if obs.intent != "unknown":
            obs.intent_evidence = obs.evidence
            obs.object_evidence = obs.evidence
            obs.intent_confidence = 0.9
        if obs.intent == "receipt" and obs.operation == "reconcile":
            # "Сверить адрес/порт передачи" is a technical check. Reconcile
            # remains reserved for inventory/accounting discrepancies.
            obs.operation = "check"
        if (search_request and parameter_at < len(tokens) and obs.intent == 'unknown'
                and (obs.reference or elliptical_search) and state.operation == 'search' and not obs.new_topic):
            obs.intent, obs.object = state.intent, state.object
            obs.binds_object = True
        if search_request and parameter_at < len(tokens):
            spans = list(re.finditer(r"[\w]+(?:[-.,][\w]+)*", text))
            obs.parameters.append(Fact.span(text, message_id, spans[parameter_at].start(),
                                            len(text.rstrip(' .?!'))))
        if search_request and has(tokens, ('фн',)):
            fn = re.search(r"(?:по\s+)?(?:номер\w*\s+)?(?:ФН(?:\s+касс\w*)?|фискальн\w+\s+накопител\w*)(?:\s+\d+)?", text, re.I)
            if fn:
                obs.parameters = [Fact.span(text, message_id, *fn.span())]
        elif search_request and re.search(r"фискальн\w+\s+накопител\w*", text, re.I):
            fn = re.search(r"(?:по\s+)?(?:номер\w*\s+)?фискальн\w+\s+накопител\w*(?:\s+\d+)?", text, re.I)
            if fn:
                obs.parameters = [Fact.span(text, message_id, *fn.span())]
        if obs.intent == 'receipt' and obs.operation == 'repeat_print' and has(tokens, ('фд',)):
            fd = re.search(r"(?:номер\w*\s+)?ФД(?:\s+\d+)?", text, re.I)
            if fd:
                obs.parameters.append(Fact.span(text, message_id, *fd.span()))
        # Restrictions describe the desired result, not a new operation. A
        # participle ("созданному") likewise must not outrank a command.
        if elliptical_search:
            obs.operation = 'search'
        if obs.operation == 'check' and has(tokens, ('список', 'перечень')):
            obs.operation = 'list'
        if obs.question and len(set(commands)) > 1:
            obs.uncertain = True  # several requested operations need disambiguation
        if obs.intent == "access":
            role_stems = ("роль", "роли", "ролей", "ролю")
            user_stems = ("сотрудник", "пользовател", "коллег", "учетн", "учетк", "аккаунт")
            target = next(("role" if token.startswith(role_stems) else "user"
                           for token in subject_tokens if token.startswith(role_stems + user_stems)), None)
            new_user_target = bool(re.search(
                r"\b(?:нов\w*|добав\w*|созданн\w*|приглаш\w*)\s+"
                r"(?:сотрудник\w*|пользовател\w*|коллег\w*|учетн\w*|учетк\w*|аккаунт\w*)\b",
                text, re.I))
            existing_user_target = bool(re.search(
                r"\b(?:существующ\w*|текущ\w*|уже\s+(?:создан\w*|есть))\s+"
                r"(?:сотрудник\w*|пользовател\w*|коллег\w*|учетн\w*|учетк\w*|аккаунт\w*)\b",
                text, re.I))
            if obs.operation == 'add' and target == 'role':
                obs.operation, obs.object = 'create_role', 'роль'
            elif obs.operation in {"change", "configure"}:
                obs.operation = "change_permissions"
            elif obs.operation == 'add':
                obs.operation = "add_employee"
            elif has(tokens, role_stems):
                obs.operation = "assign_role"
            elif obs.operation == 'assign':
                if (target == "user" and new_user_target and not existing_user_target
                        and has(tokens, ("доступ", "прав", "полномоч", "предостав"))):
                    obs.operation = "add_employee"
                elif (target == "user" and existing_user_target
                      and has(tokens, ("доступ", "прав", "полномоч", "предостав"))):
                    obs.operation = "change_permissions"
                elif (target == "user"
                      and has(tokens, ("доступ", "прав", "полномоч", "предостав"))):
                    obs.operation = "unknown"
                    obs.uncertain = True
                else:
                    obs.operation = "change_permissions"
        if (obs.intent == "fiscal_drive" and obs.operation == "unknown"
                and any(token.startswith(("понят", "прослуж", "заполн", "срок", "состояни", "ресурс"))
                        for token in tokens)):
            # Informational state questions are safe inspection requests, not
            # replacement/closure commands and do not require a service guess.
            obs.operation = "check"
        if obs.intent == 'report' and obs.operation in {'check', 'search', 'list'}:
            obs.operation = 'view_reports'
        if obs.intent == 'bank_statement' and has(tokens, ('список', 'перечень')):
            obs.operation = 'list'
        if obs.intent == 'receipt' and has(tokens, ('отправ', 'переда')) and has(tokens, ('документ',)):
            obs.operation = 'transmit'
            if has(tokens, ('не', 'нет', 'неотправ')):
                obs.details.append(obs.evidence)
        # A client's own mistake in an already issued receipt is a correction
        # request, not a device/OFD failure. Diagnostic routing remains for an
        # error code or a malfunction that prevents printing/transmission.
        failure = _failure_span(text)
        if failure:
            obs.symptom = Fact.span(text, message_id, *failure)
            if obs.intent in {"device", "fiscal_drive", "network", "receipt", "bank_statement"}:
                if obs.operation == "unknown":
                    obs.operation = "diagnose"
            elif obs.intent == "billing":
                # A payment/contract symptom does not establish whether the
                # customer needs status, renewal, or troubleshooting.
                obs.operation = "unknown"
                obs.uncertain = True
        elif obs.intent == "billing" and obs.operation == "unknown":
            # Contract/tariff lifecycle statements without an explicit request
            # are not enough to route to payment, renewal, or status procedure.
            obs.uncertain = True
        if (obs.intent == "delivery_document" and obs.operation == "unknown"
                and (len(re.findall(r"\b\d+\b", text)) >= 2
                     or has(tokens, ("привез", "получ", "количеств", "нехват")))):
            obs.operation = "reconcile"
        if obs.intent == "receipt" and has(tokens, ("статус", "дошел", "дошли", "передан")):
            obs.operation = "status"
        code = re.search(r"(?:\bфн|ошибк\w*|код)\s*[:№#-]?\s*(-?\d{2,5})\b", text, re.I)
        if code and not (search_request and obs.parameters):
            obs.error = Fact.span(text, message_id, *code.span(1))
            obs.operation = 'diagnose'
        if question_tokens[:2] == ["что", "такое"]:
            obs.operation = "explain"
            if obs.intent == "unknown":
                obs.intent, obs.object = "general", "понятие"
        if (state.task_id and state.intent == 'credentials' and state.operation == 'reset_password'
                and has(tokens, ('почт', 'телефон', 'номер', 'доступ', 'войти', 'вход'))):
            # Elliptical contact-method turns inherit the password task when
            # they discuss an unavailable recovery channel.
            obs.intent, obs.operation, obs.object = state.intent, state.operation, state.object
        # Requirements are source clauses, not inferred permissions. In
        # particular a job title is never converted into a product role.
        awaiting_goal = bool(state.expected and state.expected.slot == 'goal')
        if (obs.requirement or awaiting_goal or set(tokens) & {'без', 'нет', 'нельзя', 'только', 'запрещено'}
                or (state.intent == "access" and obs.reference and not obs.question)):
            for start, end in client_clauses(text):
                clause = text[start:end]
                if not clause or clause.casefold() in {"мне нужно", "я хочу"}:
                    continue
                fact = Fact.span(text, message_id, start, end)
                if set(words(clause)) & {"не", "нет", "без", "нельзя", "запрещено", "только"}:
                    obs.constraints.append(fact)
                elif has(words(clause), ("мог", "просмотр", "просматр", "смотр", "читать", "чтени", "доступ", "работ")):
                    obs.goals.append(fact)
        if awaiting_goal and not obs.goals and not obs.constraints and not obs.feedback and not obs.entities:
            obs.goals.append(Fact.span(text, message_id))
        if state.task_id and re.search(r"нет\s+(?:доступа|такого)|не\s+(?:вижу|отобража|могу\s+войти)|отсутств\w*", text, re.I):
            fact = Fact.span(text, message_id)
            if fact.value.casefold() not in {f.value.casefold() for f in obs.constraints}:
                obs.constraints.append(fact)
        if (state.intent == 'credentials' and has(tokens, ('почт', 'телефон', 'номер', 'смс', 'email'))
                and state.operation == 'reset_password'):
            obs.details.append(obs.evidence)
        if any(len(values) > 1 for values in obs.entities.values()):
            obs.uncertain = True
        contradiction = bool(state.task_id and re.search(
            r"(?:этого|такого|нужного|указанного).{0,32}(?:нет|отсутств)|(?:нет|отсутств\w*).{0,24}(?:раздел|кнопк|пункт)",
            text, re.I))
        contradiction |= bool(state.task_id and state.intent == 'report'
                              and has(tokens, ('кабинет', 'раздел', 'пункт', 'отчет'))
                              and re.search(r"\bнет\b|отсутств\w*|не\s+(?:вижу|отобража\w*)", text, re.I))
        # A short free-form answer to a requested detail belongs to the active
        # task. Explicit topic switches and a newly recognized different object
        # are handled below and must not be swallowed as clarification text.
        detail_reply = bool(state.expected and state.expected.slot == 'details'
                            and not obs.new_topic
                            and (obs.intent == 'unknown' or obs.intent == state.intent
                                 or obs.entities or obs.parameters or obs.constraints or obs.goals
                                 or (not obs.question and not obs.symptom)))
        if detail_reply and obs.evidence:
            obs.details.append(obs.evidence)
        elif (state.task_id and state.operation == "search" and obs.reference
              and obs.intent == "unknown" and not obs.parameters and obs.evidence):
            # A referential follow-up can add search context without declaring
            # a new standalone operation or an unverified structured filter.
            obs.details.append(obs.evidence)
        clarification_matches = bool(state.expected and (
            state.expected.slot in obs.entities
            or state.expected.slot == 'service' and obs.entities
            or state.expected.slot == 'goal' and (obs.goals or obs.constraints)
            or state.expected.slot == 'details' and detail_reply
            or state.expected.slot == 'task' and (obs.intent != 'unknown' or obs.entities or obs.constraints)))
        if contradiction:
            obs.relation = 'contradiction'
            obs.constraints = []
        elif obs.new_topic:
            obs.relation = 'new_task'
        elif (state.task_id and obs.entities and not obs.symptom and not obs.error
              and not obs.question and "?" not in text and not obs.requirement
              and not ((commands or re.search(r"\b\w+(?:йте|ьте|ите)\b", text, re.I))
                       and obs.intent not in {'unknown', state.intent})):
            # A declarative service/equipment/integration update is context
            # for the active task. Nominal actions inside it ("подключение к
            # банку") are not commands to start another workflow. The new
            # fact remains in the task query without replacing its problem.
            obs.relation = 'answer_to_clarification' if clarification_matches else 'continue'
            if not obs.entity_only:
                obs.details.append(obs.evidence)
        elif clarification_matches:
            obs.relation = 'answer_to_clarification'
        elif (state.task_id and obs.symptom
              and (obs.intent != state.intent or obs.operation != state.operation)):
            # A new failure mode is a new task boundary when it changes the
            # diagnosed object/action; do not carry the old operation into it.
            obs.relation = 'new_task'
        elif state.expected and obs.intent != 'unknown' and obs.intent != state.intent:
            obs.relation = 'new_task'
        elif state.task_id and obs.intent != 'unknown' and obs.intent != state.intent and not obs.entity_only:
            obs.relation = 'new_task'
        elif obs.parameters:
            obs.relation = 'parameter_update'
        elif obs.constraints:
            obs.relation = 'constraint_update'
        elif state.task_id and (obs.intent == state.intent or obs.reference or obs.entity_only or obs.feedback):
            obs.relation = 'continue'
        elif not state.task_id or obs.intent != 'unknown' or obs.operation != 'unknown':
            obs.relation = 'new_task'
        if obs.uncertain:
            obs.relation = 'unknown'
            obs.confidence = 0.3
        elif obs.operation == 'explain':
            obs.relation = 'new_task'
        elif state.expected and state.expected.slot in {'task', 'details'} and obs.feedback:
            obs.relation = 'unknown'
            obs.confidence = 0.35
        elif (obs.relation != 'answer_to_clarification' and state.task_id and state.intent == 'access'
              and (obs.requirement or obs.goals or obs.constraints)
              and (obs.reference or not obs.question)):
            obs.relation = 'constraint_update'
        elif obs.relation != 'unknown':
            obs.confidence = 0.9 if obs.intent != 'unknown' or obs.entities else 0.75
        if obs.operation != "unknown":
            action = next((token for name, stems in OPERATIONS if name == obs.operation
                           for token in tokens if token.startswith(stems)), None)
            operation_has_local_evidence = bool(action or obs.symptom)
            if action:
                match = re.search(re.escape(action), text, re.I)
                if match:
                    obs.operation_evidence = Fact.span(text, message_id, *match.span())
            elif obs.symptom:
                obs.operation_evidence = obs.symptom
            if obs.operation_evidence is None:
                # Composite operations (add_employee, view_reports, etc.) are
                # derived from a typed action rule; retain the full current
                # utterance as their grounded evidence span.
                obs.operation_evidence = obs.evidence
            obs.operation_confidence = 0.9 if operation_has_local_evidence else 0.7
        else:
            obs.operation_confidence = 0.3 if obs.uncertain else 0.0
        obs.relation_confidence = obs.confidence
        obs.relation_evidence = obs.evidence
        return obs


def _append_unique(target: list[Fact], additions: list[Fact]) -> None:
    for fact in additions:
        if fact.value.casefold() not in {f.value.casefold() for f in target}:
            target.append(fact)


class DialogueManager:
    def __init__(self, analyzer: MessageAnalyzer | None = None):
        self.analyzer = analyzer or LexicalAnalyzer()

    def advance(self, previous: DialogueState, text: str, message_id: int | str, *,
                observation: Observation | None = None,
                unknown_facts: list[str] | None = None) -> DialogueState:
        # Social/meta turns and requests without a task never establish task
        # facts. On an existing conversation they also leave the real task and
        # any pending clarification intact.
        if is_resolution_turn(text):
            state = deepcopy(previous)
            if state.task_context:
                state.task_context.closed = True
                state.task_context.open_question = None
            state.revision = previous.revision + 1
            return state
        if observation is None and classify_user_turn(text) in NON_TASK_TURN_KINDS:
            state = deepcopy(previous)
            state.revision = previous.revision + 1
            return state
        # Semantic callers supply a validated observation. Do not run a second,
        # lexical interpretation that could override the model's turn decision.
        obs = observation if observation is not None else self.analyzer.analyze(text, message_id, deepcopy(previous))
        # Enforce the boundary even for a future model-backed analyser.
        facts = [f for values in obs.entities.values() for f in values]
        facts += list(obs.unknown_facts.values())
        facts += [*obs.goals, *obs.constraints, *obs.details, *obs.parameters,
                  *([obs.intent_evidence] if obs.intent_evidence else []),
                  *([obs.object_evidence] if obs.object_evidence else []),
                  *([obs.operation_evidence] if obs.operation_evidence else []),
                  *([obs.relation_evidence] if obs.relation_evidence else []),
                  *([obs.symptom] if obs.symptom else []),
                  *([obs.evidence] if obs.evidence else []), *([obs.error] if obs.error else [])]
        valid_operations = {name for name, _ in OPERATIONS} | {'unknown', 'explain', 'add_employee', 'assign_role', 'create_role', 'view_reports', 'change_permissions', 'diagnose', 'status', 'fiscalize'}
        if obs.operation not in valid_operations or obs.intent not in {name for name, _, _ in OBJECTS} | {'unknown', 'general'}:
            raise ValueError('Unsupported analyser task; extend the typed vocabulary explicitly')
        if obs.evidence is None or set(obs.entities) - ENTITY_SLOTS or any(
            f.message_id != message_id or f.start < 0 or f.end > len(text)
            or f.start >= f.end or text[f.start:f.end] != f.quote for f in facts
        ):
            raise ValueError("Analyser facts must cite spans of the current client message")
        if obs.relation not in RELATIONS:
            raise ValueError("Analyser returned an unsupported message relation")
        known_task = obs.intent != "unknown" and obs.operation != "unknown"
        relation = obs.relation
        if not previous.task_id or (previous.task_context and previous.task_context.closed):
            relation = "new_task"
        # A model may label any follow-up as an answer to the last question.
        # Keep a slot clarification active until the client supplies that
        # slot (or explicitly says they do not know it); this lets new symptoms
        # and constraints accumulate without silently clearing the blocker.
        elif relation == "answer_to_clarification" and previous.expected is None:
            relation = "continue"
        elif (relation == "answer_to_clarification" and previous.expected
              and previous.expected.slot in ENTITY_SLOTS
              and not (obs.entities.keys() & {
                  "service": {"service", "ofd", "software", "integration"},
                  "ofd": {"ofd", "service"},
                  "manufacturer": {"manufacturer"}, "equipment": {"equipment"},
                  "model": {"equipment"}, "software": {"software"},
                  "integration": {"integration"},
              }.get(previous.expected.slot, {previous.expected.slot}))
              and previous.expected.slot not in obs.unknown_facts):
            relation = "continue"
        elif (relation == "new_task" and previous.expected
              and previous.expected.slot in ENTITY_SLOTS
              and obs.operation == "unknown" and not obs.new_topic
              and not obs.symptom and not obs.error and not obs.question):
            # A short ambiguous reply to a route/model question supplies no
            # new task and cannot close the outstanding slot.
            relation = "continue"
        elif (relation == "new_task" and previous.task_id and not obs.new_topic
              and not obs.symptom and not obs.error and bool(obs.entities)
              and (obs.object in {None, previous.object}
                   or (obs.intent == "general" and obs.object == "ОФД" and not obs.question))
              and obs.operation in {"unknown", previous.operation}
              and obs.intent in {"unknown", "general", previous.intent}):
            # A newly supplied route plus elaboration of the same action is
            # context for the active task, even when the route's generic noun
            # gave the lexical analyser a coarse intent label.
            relation = "continue"
        elif relation == "unknown" and (obs.intent != "unknown" and obs.intent != previous.intent
                                         or obs.operation == "explain"):
            relation = "new_task"
        elif relation == "unknown" and previous.expected and previous.expected.slot in {"task", "details"} and obs.feedback:
            relation = "unknown"
        elif relation == "unknown" and (obs.entities or obs.goals or obs.constraints or obs.parameters
                                         or obs.feedback or obs.reference):
            relation = "parameter_update" if obs.parameters else (
                "constraint_update" if obs.constraints else "continue")
        if (relation == "unknown" and previous.task_id and obs.symptom
                and (obs.intent != previous.intent or obs.operation != previous.operation)):
            relation = "new_task"

        if relation == "new_task":
            state = DialogueState(revision=previous.revision, session=deepcopy(previous.session))
            state.task_id = f"task:{message_id}"
            state.topic_start_message_id = message_id
            state.task = obs.evidence
            state.intent = obs.intent
            state.operation = obs.operation
            state.object = obs.object
            state.operation_evidence = obs.operation_evidence if known_task else None
            state.operation_confidence = obs.operation_confidence
            state.symptom = obs.symptom
            state.task_context.entities = deepcopy(obs.entities)
            tokens = words(text)
            explicit_reset = any(
                tuple(tokens[index:index + len(prefix)]) == prefix
                for prefix in NEW_TOPIC if prefix != ("кстати",)
                for index in range(max(1, min(len(tokens), 8)))
            )
            if observation is None and not explicit_reset and obs.operation != "explain" and not obs.entities:
                inherited_route = state.reusable_session_route(obs.intent)
                if inherited_route:
                    state.task_context.active_route = deepcopy(inherited_route)
                    state.task_context.entities[inherited_route.slot] = [inherited_route.fact]
            state.expected = None
            state.transition = "new_task"
        else:
            state = deepcopy(previous)
            state.transition = "continue_task"
            if relation == "answer_to_clarification":
                state.transition = "clarification"
                state.expected = None
                if previous.expected and previous.expected.reason == "query_budget_exceeded":
                    state.goals = []
                    state.constraints = []
                    state.details = []
                    state.parameters = []
            elif relation == "contradiction":
                state.transition = "contradiction"
            elif relation in {"parameter_update", "constraint_update"}:
                state.transition = "refine_requirements" if relation == "constraint_update" else "change_parameter"
            if obs.intent != "unknown" and (obs.intent == state.intent or state.intent == "unknown"):
                state.intent = obs.intent
                # Words inside a requested detail (for example «чек уже
                # выдан») describe the active correction case; they are not a
                # new command and must not replace the operation being refined.
                preserves_operation = (relation == "answer_to_clarification"
                                       and previous.expected
                                       and previous.expected.slot in {"service", "ofd", "software", "manufacturer",
                                                                      "equipment", "details", "goal"})
                if obs.operation != "unknown" and not preserves_operation:
                    if (obs.operation != previous.operation and previous.operation_evidence):
                        _append_unique(state.superseded_facts, [previous.operation_evidence])
                    state.operation = obs.operation
                if obs.object:
                    state.object = obs.object
                if known_task:
                    state.operation_evidence = obs.operation_evidence
                    state.operation_confidence = obs.operation_confidence

        # Symptoms are independently validated exact-span facts. A rejected or
        # task-mode intent label must not discard a confirmed symptom.
        if obs.symptom and relation != "contradiction":
            state.symptom = obs.symptom

        state.revision = previous.revision + 1
        state.relation = relation
        state.confidence = obs.confidence if relation != "unknown" else min(obs.confidence, 0.4)
        state.analysis_required = relation == "unknown" or obs.uncertain
        if previous.expected and previous.expected.slot == "service" and relation == "unknown":
            # The task itself is known; ask for the missing/ambiguous route.
            state.analysis_required = False
        state.unresolved = obs.evidence if state.analysis_required else None

        # Session records confirmed mentions; TaskContext owns only facts from
        # this task's actual turns. A prior session product never auto-routes.
        changed_entity = False
        for slot, values in obs.entities.items():
            old = state.session.entities.get(slot, [])
            changed_entity |= [f.value for f in old] != [f.value for f in values]
            for old_fact in state.task_context.entities.get(slot, []):
                if old_fact.value not in {fact.value for fact in values}:
                    _append_unique(state.superseded_facts, [old_fact])
            state.session.entities[slot] = values
            state.task_context.entities[slot] = values
        explicit_routes = [slot for slot in ("service", "ofd", "software", "manufacturer")
                           if slot in obs.entities]
        equipment_only_update = (explicit_routes == ["manufacturer"] and relation != "new_task"
                                 and state.routing_slot in {"service", "ofd", "software"}
                                 and state.intent in {"access", "credentials", "receipt"})
        route_candidates = explicit_routes
        if state.intent == "fiscal_drive" and "ofd" in route_candidates:
            route_candidates = [slot for slot in route_candidates if slot != "ofd"]
        if route_candidates and not equipment_only_update:
            slot = route_candidates[0]
            values = obs.entities[slot]
            route_changed = (previous.routing_slot != slot or previous.routing_service != values[0].value)
            old_route = previous.task_context.active_route if previous.task_context else None
            state.task_context.active_route = ActiveRoute(slot, values[0]) if len(values) == 1 else None
            if route_changed and old_route and relation != "new_task":
                current_values = {fact.value for values in state.task_entities.values() for fact in values}
                if old_route.value not in current_values:
                    _append_unique(state.superseded_facts, [old_route.fact])
                if old_route.slot == "manufacturer":
                    for equipment_fact in state.task_context.entities.get("equipment", []):
                        if equipment_fact.value not in current_values:
                            _append_unique(state.superseded_facts, [equipment_fact])
            if len(values) == 1:
                state.session.active_route = state.task_context.active_route
            if len(values) != 1:
                state.analysis_required = True
                state.relation = "unknown"
            elif route_changed and relation not in {"new_task", "answer_to_clarification"}:
                state.relation = "parameter_update"
        if "manufacturer" in obs.entities and "equipment" not in obs.entities:
            before_manufacturer = previous.entity("manufacturer")
            after_manufacturer = obs.entities["manufacturer"][0].value
            if before_manufacturer != after_manufacturer:
                _append_unique(state.superseded_facts, state.task_context.entities.get("equipment", []))
                state.session.entities.pop("equipment", None)
                state.task_context.entities.pop("equipment", None)
        if obs.binds_object:
            state.object_reference = obs.evidence
        if any(words(f.value)[:1] == ["за"] for f in obs.parameters):
            replaced_parameters = [f for f in state.parameters if words(f.value)[:1] == ["за"]]
            _append_unique(state.superseded_facts, replaced_parameters)
            state.parameters = [f for f in state.parameters if words(f.value)[:1] != ["за"]]
        _append_unique(state.parameters, obs.parameters)
        _append_unique(state.goals, obs.goals)
        _append_unique(state.constraints, obs.constraints)
        _append_unique(state.details, obs.details)
        if relation != "new_task" and (obs.goals or obs.symptom) and not obs.details:
            # A provider goal can cover only the question at the end of a
            # message. Retain any separate client statement as an exact span.
            # This preserves newly reported conditions without treating them
            # as a confirmed route, model, or inferred diagnosis.
            remaining = list(text)
            claimed = [*obs.goals, *obs.constraints, *obs.parameters,
                       *([obs.symptom] if obs.symptom else []),
                       *(fact for values in obs.entities.values() for fact in values)]
            for fact in claimed:
                for index in range(fact.start, fact.end):
                    remaining[index] = " "
            for match in re.finditer(r"[^.!?]+", "".join(remaining)):
                raw = match.group()
                leading = len(raw) - len(raw.lstrip(" ,:;—–\t\n"))
                trailing = len(raw.rstrip(" ,:;—–\t\n"))
                start, end = match.start() + leading, match.start() + trailing
                if end > start and len(words(text[start:end])) >= 2:
                    _append_unique(state.details, [Fact.span(text, message_id, start, end)])
        if obs.error:
            if previous.error and previous.error.value != obs.error.value:
                _append_unique(state.superseded_facts, [previous.error])
            state.error = obs.error
        if relation == "contradiction":
            _append_unique(state.details, [obs.evidence])
        elif (obs.feedback
              or (previous.expected and relation == "continue"
                  and (obs.entities or obs.goals or obs.constraints or obs.parameters
                       or obs.symptom or obs.unknown_facts))
              or (relation == "continue" and obs.relation == "new_task" and obs.entities)):
            _append_unique(state.details, [obs.evidence])
        if previous.expected and relation != "contradiction" and relation != "new_task":
            expected_slot = previous.expected.slot
            if expected_slot == "details":
                supplied = bool(obs.details or obs.goals or obs.constraints or obs.parameters or obs.symptom)
            elif expected_slot == "goal":
                supplied = bool(obs.goals or obs.constraints)
            elif expected_slot == "task":
                supplied = bool(obs.intent != "unknown" or obs.operation != "unknown" or obs.entities)
            else:
                equivalent_slots = {
                    "service": {"service", "ofd", "software", "integration"},
                    "ofd": {"ofd", "service"},
                    "model": {"equipment"}, "equipment": {"equipment"},
                    "software": {"software"}, "integration": {"integration"},
                }.get(expected_slot, {expected_slot})
                supplied = bool(equivalent_slots.intersection(obs.entities))
            supplied |= expected_slot in obs.unknown_facts
            if supplied:
                state.expected = None
                state.task_context.open_question = None
        if changed_entity and explicit_routes and relation not in {"new_task", "answer_to_clarification"}:
            state.transition = "change_service" if "service" in explicit_routes else "change_parameter"
        elif obs.error and previous.error and obs.error.value != previous.error.value:
            state.transition = "change_parameter"
        if not state.analysis_required:
            state.unresolved = None
        valid_unknown = ENTITY_SLOTS | {"goal", "details", "task"}
        if unknown_facts is not None:
            if any(slot not in valid_unknown for slot in unknown_facts):
                raise ValueError("Unsupported unknown-fact slot")
            if relation == "new_task":
                state.task_context.unknown_facts = list(dict.fromkeys(unknown_facts))
            else:
                state.task_context.unknown_facts = list(dict.fromkeys(
                    [*state.task_context.unknown_facts, *unknown_facts]))
        for slot in obs.entities:
            state.task_context.unknown_facts = [item for item in state.task_context.unknown_facts if item != slot]
        state.task_context.closed = False
        progress_changed = self._reduce_progress(state, text, message_id)
        if progress_changed and state.expected and state.expected.slot in {"details", "goal"}:
            state.expected = None
            state.task_context.open_question = None
        if obs.goals:
            state.task_context.current_subgoal = obs.goals[-1]
        return state

    @staticmethod
    def _reduce_progress(state: DialogueState, text: str, message_id: int | str) -> bool:
        """Apply only explicitly reported client outcomes to shown checks."""
        task = state.task_context
        if not task or not (task.eligible_units or task.shown_units):
            return False
        changed = False
        normalized = text.casefold().replace("ё", "е")
        for unit in (task.eligible_units or task.shown_units):
            model_value = unit.get("model_value")
            if model_value:
                equipment = " ".join(fact.value for fact in task.entities.get("equipment", []))
                if not re.search(r"(?<!\w)" + re.escape(model_value) + r"(?!\w)",
                                 equipment.casefold().replace("ё", "е")):
                    # A result for a model-scoped step belongs only to the
                    # model value confirmed when this unit became eligible.
                    continue
            label = str(unit.get("label") or "")
            # Content terms are derived from the exact approved unit, with a
            # bounded prefix form to tolerate Russian inflection.
            action_roots = ("провер", "откр", "закр", "напеч", "распеч", "посмотр", "уточн", "выбер",
                            "выполн", "сопостав", "свер", "переда", "следу", "подтверд")
            terms = [token for token in re.findall(r"[а-яa-z0-9]+", label.casefold().replace("ё", "е"))
                     if len(token) >= 4 and not token.startswith(action_roots)]
            # Match the actual client sentence to this check. Previously a
            # match anywhere in the reply attached its FIRST comma-clause to
            # every check, losing results and creating false successes.
            matches = [m for m in re.finditer(r"[^;.!?]+", text)
                       if any(re.search(r"(?<!\w)" + re.escape(term[:4]) + r"\w*",
                                        m.group().casefold().replace("ё", "е")) for term in terms)]
            if not matches:
                continue
            matched = max(matches, key=lambda m: sum(
                bool(re.search(r"(?<!\w)" + re.escape(term[:4]) + r"\w*",
                               m.group().casefold().replace("ё", "е"))) for term in terms))
            quote = matched.group().strip()
            start = text.find(quote)
            quote_normalized = quote.casefold().replace("ё", "е")
            if re.search(r"\b(?:не\s+(?:знаю|уверен\w*|понятно)|не\s+провер\w*|пока\s+не\s+провер\w*)\b", quote_normalized):
                status = "unknown" if re.search(r"\bне\s+(?:знаю|уверен\w*|понятно)\b", quote_normalized) else "not_done"
            elif re.search(r"\b(?:не\s+работ\w*|не\s+прош\w*|не\s+оплач\w*|не\s+подключ\w*|не\s+отправля\w*|не\s+уменьш\w*|истек\w*|законч\w*)\b", quote_normalized):
                status = "failed"
            elif re.search(r"\b(?:работа\w*|успешн\w*|прошл\w*|оплачен\w*|действу\w*|подключен\w*|исправлен\w*|уменьш\w*|подтвержден\w*|напечатал\w*|распечатал\w*|напечатан\w*|распечатан\w*)\b", quote_normalized):
                status = "passed"
            elif re.search(r"\b(?:провер\w*|посмотр\w*|свер\w*|узнал\w*)\b", quote_normalized):
                status = "unknown"
            else:
                continue
            # A single positive result cannot complete a whole conditional
            # procedure block (e.g. internet + settings + queue checks).
            instruction_sentences = [sentence for sentence in re.split(r"[.!?]", label)
                if re.search(r"\b(?:проверьте|откройте|напечатайте|выясните|сопоставьте|"
                             r"посмотрите|восстановите|передайте|уточните)\b", sentence, re.I)]
            if status == "passed" and len(instruction_sentences) > 1:
                status = "unknown"
            check = next((item for item in task.checks if item.get("unit_id") == unit.get("unit_id")), None)
            if check is None:
                check = {"unit_id": unit.get("unit_id"), "status": status,
                    "result_span": {"message_id": message_id, "quote": quote,
                                    "start": start, "end": start + len(quote)}}
                task.checks.append(check)
            else:
                previous_status = check.get("status")
                if {previous_status, status} == {"passed", "failed"}:
                    check["contradictions"] = [check.get("result_span"),
                        {"message_id": message_id, "quote": quote,
                         "start": start, "end": start + len(quote)}]
                    check["status"] = "unknown"
                else:
                    check["status"] = status
                    check["result_span"] = {"message_id": message_id, "quote": quote,
                                            "start": start, "end": start + len(quote)}
            if check.get("status") != "unknown" or "contradictions" not in check:
                check["result_span"] = {"message_id": message_id, "quote": quote,
                                        "start": start, "end": start + len(quote)}
            changed = True
        return changed

    def observe_answer(self, previous: DialogueState, *, scenario: str | None,
                       reason: str | None, question: str, message_id: int | str | None = None,
                       slot: str | None = None, progress_update: dict | None = None) -> DialogueState:
        """An assistant can open an expected slot, never write client facts."""
        state = deepcopy(previous)
        # Provider failure and an explicit request for a human must not erase
        # the customer's active task or unresolved clarification.
        if reason in {"understanding_error", "client_requested_specialist"}:
            return state
        if reason in NON_TASK_SCENARIO_REASONS and previous.task_id:
            return state
        if progress_update and state.task_context:
            if isinstance(progress_update.get("procedure_id"), str):
                state.task_context.procedure_id = progress_update["procedure_id"]
            for unit in progress_update.get("shown_units", []):
                if (isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
                        and isinstance(unit.get("label"), str) and unit.get("unit_id")
                        and unit.get("source_verified") is True):
                    if unit["unit_id"] not in {item.get("unit_id") for item in state.task_context.shown_units}:
                        state.task_context.shown_units.append({k: unit[k] for k in
                            ("unit_id", "label", "source", "section", "model_scope", "model_value", "source_order")
                            if k in unit})
                    if unit["unit_id"] not in {item.get("unit_id") for item in state.task_context.checks}:
                        state.task_context.checks.append({"unit_id": unit["unit_id"], "status": "asked"})
            for unit in progress_update.get("eligible_units", []):
                if (isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
                        and isinstance(unit.get("label"), str) and unit.get("source_verified") is True
                        and unit["unit_id"] not in {item.get("unit_id") for item in state.task_context.eligible_units}):
                    state.task_context.eligible_units.append({k: unit[k] for k in
                        ("unit_id", "label", "source", "section", "model_scope", "model_value", "source_order")
                        if k in unit})
            if isinstance(progress_update.get("open_question"), str):
                key = progress_update["open_question"]
                if key == state.task_context.open_question:
                    state.task_context.clarification_repeats[key] = state.task_context.clarification_repeats.get(key, 0) + 1
                else:
                    state.task_context.open_question = key
                    state.task_context.clarification_repeats[key] = 1
        elif scenario == "clarify" and slot and state.task_context:
            if state.task_context.open_question == slot:
                state.task_context.clarification_repeats[slot] = state.task_context.clarification_repeats.get(slot, 0) + 1
            else:
                state.task_context.open_question = slot
                state.task_context.clarification_repeats[slot] = 1
        if scenario == "clarify":
            if slot not in CLARIFICATION_SLOTS:
                slot = ("service" if reason in {"service_not_confirmed", "service_unknown", "service_ambiguous", "missing_service"}
                        else "equipment" if reason == "error_product_missing" else "details")
            state.expected = ExpectedClarification(slot, question, message_id, reason)
        else:
            pending = previous.expected
            supplied = bool(pending and (
                pending.slot in state.task_context.entities and state.task_context.entities[pending.slot]
                or pending.slot in state.task_context.unknown_facts)) if state.task_context else False
            state.expected = pending if pending and pending.slot in ENTITY_SLOTS and not supplied else None
        return state


def state_from_history(history: list[dict] | None) -> DialogueState:
    """Compatibility for stateless callers; persisted chats use incremental SQL state."""
    manager, state = DialogueManager(), DialogueState()
    for i, item in enumerate(history or []):
        mid = item.get("message_id", f"legacy:{i}")
        if item.get("role") == "user":
            state = manager.advance(state, item["content"], mid)
        elif item.get("role") == "assistant":
            state = manager.observe_answer(state, scenario=item.get("scenario"), reason=item.get("scenario_reason"),
                                           question=item.get("content", ""), message_id=mid,
                                           slot=item.get("clarification_slot"))
    return state
