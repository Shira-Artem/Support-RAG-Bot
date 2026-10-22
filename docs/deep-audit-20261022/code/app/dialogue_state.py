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


SCHEMA_VERSION = 1
ENTITY_SLOTS = {"service", "manufacturer", "equipment", "ofd", "software"}
CLARIFICATION_SLOTS = ENTITY_SLOTS | {"goal", "details", "task"}


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
class DialogueState:
    schema_version: int = SCHEMA_VERSION
    revision: int = 0
    task_id: str | None = None
    topic_start_message_id: int | str | None = None
    intent: str = "unknown"
    operation: str = "unknown"
    object: str | None = None
    entities: dict[str, list[Fact]] = field(default_factory=dict)
    # entities are session facts; requirements/parameters reset on a new task.
    # routing_slot binds this task to a session entity without erasing others.
    routing_slot: str | None = None
    parameters: list[Fact] = field(default_factory=list)
    object_reference: Fact | None = None
    task: Fact | None = None
    operation_evidence: Fact | None = None
    goals: list[Fact] = field(default_factory=list)
    constraints: list[Fact] = field(default_factory=list)
    details: list[Fact] = field(default_factory=list)
    error: Fact | None = None
    expected: ExpectedClarification | None = None
    transition: str = "new_task"
    analysis_required: bool = False
    unresolved: Fact | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DialogueState:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported dialogue state schema; preserve the snapshot and migrate explicitly")
        data = deepcopy(data)
        data["entities"] = {k: [Fact(**v) for v in values] for k, values in data.get("entities", {}).items()}
        for key in ("task", "operation_evidence", "error", "unresolved", "object_reference"):
            if data.get(key):
                data[key] = Fact(**data[key])
        for key in ("goals", "constraints", "details", "parameters"):
            data[key] = [Fact(**v) for v in data.get(key, [])]
        if data.get("expected"):
            data["expected"] = ExpectedClarification(**data["expected"])
        return cls(**data)

    def entity(self, slot: str) -> str | None:
        values = self.entities.get(slot, [])
        return values[0].value if len(values) == 1 else None

    @property
    def task_entities(self) -> dict[str, list[Fact]]:
        # A general definition need not be narrowed to a previously used vendor.
        if self.operation == 'explain' and self.routing_slot is None:
            return {}
        cabinet_task = self.intent in {'access', 'credentials', 'receipt', 'report'} or (
            self.intent == 'device' and self.operation == 'list' and not self.error)
        if cabinet_task and self.routing_slot in self.entities:
            active = {self.routing_slot: self.entities[self.routing_slot]}
            if self.routing_slot == 'manufacturer' and 'equipment' in self.entities:
                active['equipment'] = self.entities['equipment']
            return active
        return self.entities

    @property
    def routing_service(self) -> str | None:
        # Routing is a view of distinct entities, never their concatenation.
        # An access task belongs to the cabinet; receipt delivery belongs to OFD
        # when no cloud cabinet was named. Hardware is retained independently.
        if not self.task_entities:
            return None
        hardware_task = self.intent == 'fiscal_drive' or (
            self.intent == 'device' and (self.operation != 'list' or self.error))
        slots = (("service", "manufacturer") if hardware_task else
                 ("service", "software", "manufacturer", "ofd")
                 if self.intent in {"access", "credentials"} else
                 ("service", "ofd", "manufacturer", "software"))
        if self.routing_slot in slots and self.routing_slot in self.entities:
            return self.entity(self.routing_slot)
        for slot in slots:
            if slot in self.entities:
                return self.entity(slot)  # multiple values in one slot require clarification
        return None


@dataclass
class Observation:
    """Typed patch produced solely from the current client message."""
    entities: dict[str, list[Fact]] = field(default_factory=dict)
    intent: str = "unknown"
    operation: str = "unknown"
    object: str | None = None
    evidence: Fact | None = None
    goals: list[Fact] = field(default_factory=list)
    constraints: list[Fact] = field(default_factory=list)
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


class MessageAnalyzer(Protocol):
    def analyze(self, text: str, message_id: int | str, state: DialogueState) -> Observation: ...


def words(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[-.,][\w]+)*", text.casefold().replace("ё", "е"))


def has(tokens: list[str], stems: tuple[str, ...]) -> bool:
    return any(token.startswith(stems) for token in tokens)


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
    ("ofd", "Платформа ОФД", ("платформа офд", "платформе офд", "платформы офд")),
    ("ofd", "Первый ОФД", ("первый офд", "первом офд")),
    ("ofd", "Такском", ("такском",)),
    ("ofd", "Астрал", ("астрал",)),
    ("software", "1С", ("1с", "1c", "один эс")),
    ("service", "ТС ПиОТ", ("тс пиот", "тспиот")),
    ("service", "Честный ЗНАК", ("честный знак", "честном знаке")),
    ("manufacturer", "Эвотор", ("эвотор", "evotor")),
    ("manufacturer", "aQsi", ("aqsi", "акси")),
    ("manufacturer", "АТОЛ", ("атол", "atol")),
    ("manufacturer", "Штрих-М", ("штрих-м", "штрих")),
)
OBJECTS = (
    ("credentials", "учётная запись", ("парол", "авторизац")),
    ("access", "сотрудник", ("сотрудник", "коллег", "пользовател", "учетн", "учетк", "аккаунт", "доступ", "роль", "роли", "ролей", "прав", "полномоч")),
    ("report", "отчёт", ("отчет",)),
    ("fiscal_drive", "ФН", ("фн", "накопител")),
    ("receipt", "чек", ("чек", "квитанц")),
    ("network", "соединение", ("интернет", "связь", "сети", "подключен")),
    ("marking", "маркировка", ("маркиров", "gtin")),
    ("tax", "налогообложение", ("налог", "ндс", "усн", "псн")),
    ("device", "касса", ("касс", "ккт", "принтер")),
)
OPERATIONS = (
    ("reset_password", ("восстанов", "сброс", "забыл")),
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
        obs.new_topic = any(tuple(tokens[:len(prefix)]) == prefix for prefix in NEW_TOPIC)
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
        obs.operation = commands[0] if commands else actions[0][0] if actions else 'unknown'
        subject_tokens = tokens[:parameter_at] if search_request else tokens
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
        if (search_request and parameter_at < len(tokens) and obs.intent == 'unknown'
                and (obs.reference or elliptical_search) and state.operation == 'search' and not obs.new_topic):
            obs.intent, obs.object = state.intent, state.object
            obs.binds_object = True
        if search_request and parameter_at < len(tokens):
            spans = list(re.finditer(r"[\w]+(?:[-.,][\w]+)*", text))
            obs.parameters.append(Fact.span(text, message_id, spans[parameter_at].start(),
                                            len(text.rstrip(' .?!'))))
        # Restrictions describe the desired result, not a new operation. A
        # participle ("созданному") likewise must not outrank a command.
        if elliptical_search:
            obs.operation = 'search'
        if obs.intent == 'device' and obs.operation == 'check' and has(tokens, ('список', 'перечень')):
            obs.operation = 'list'
        if obs.question and len(set(commands)) > 1:
            obs.uncertain = True  # several requested operations need disambiguation
        if obs.intent == "access":
            role_stems = ("роль", "роли", "ролей", "ролю")
            user_stems = ("сотрудник", "пользовател", "коллег", "учетн", "учетк", "аккаунт")
            target = next(("role" if token.startswith(role_stems) else "user"
                           for token in subject_tokens if token.startswith(role_stems + user_stems)), None)
            if obs.operation == 'add' and target == 'role':
                obs.operation, obs.object = 'create_role', 'роль'
            elif obs.operation in {"change", "configure"}:
                obs.operation = "change_permissions"
            elif obs.operation == 'add':
                obs.operation = "add_employee"
            elif has(tokens, role_stems):
                obs.operation = "assign_role"
            elif obs.operation == 'assign':
                obs.operation = "change_permissions"
        if obs.intent == 'report' and obs.operation in {'check', 'search', 'list'}:
            obs.operation = 'view_reports'
        if obs.intent in {"device", "fiscal_drive", "network", "receipt"} and has(tokens, ("ошиб", "неисправ", "перестал", "печата", "отправля")):
            obs.operation = "diagnose"
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
        # Requirements are source clauses, not inferred permissions. In
        # particular a job title is never converted into a product role.
        awaiting_goal = bool(state.expected and state.expected.slot == 'goal')
        if (obs.requirement or awaiting_goal or set(tokens) & {'без', 'нельзя', 'только', 'запрещено'}
                or (state.intent == "access" and obs.reference and not obs.question)):
            for start, end in client_clauses(text):
                clause = text[start:end]
                if not clause or clause.casefold() in {"мне нужно", "я хочу"}:
                    continue
                fact = Fact.span(text, message_id, start, end)
                if set(words(clause)) & {"не", "без", "нельзя", "запрещено", "только"}:
                    obs.constraints.append(fact)
                elif has(words(clause), ("мог", "просмотр", "просматр", "смотр", "читать", "чтени", "доступ", "работ")):
                    obs.goals.append(fact)
        if awaiting_goal and not obs.goals and not obs.constraints and not obs.feedback and not obs.entities:
            obs.goals.append(Fact.span(text, message_id))
        if any(len(values) > 1 for values in obs.entities.values()):
            obs.uncertain = True
        return obs


def _append_unique(target: list[Fact], additions: list[Fact]) -> None:
    for fact in additions:
        if fact.value.casefold() not in {f.value.casefold() for f in target}:
            target.append(fact)


class DialogueManager:
    def __init__(self, analyzer: MessageAnalyzer | None = None):
        self.analyzer = analyzer or LexicalAnalyzer()

    def advance(self, previous: DialogueState, text: str, message_id: int | str) -> DialogueState:
        obs = self.analyzer.analyze(text, message_id, deepcopy(previous))
        # Enforce the boundary even for a future model-backed analyser.
        facts = [f for values in obs.entities.values() for f in values]
        facts += [*obs.goals, *obs.constraints, *obs.parameters, *([obs.evidence] if obs.evidence else []), *([obs.error] if obs.error else [])]
        valid_operations = {name for name, _ in OPERATIONS} | {'unknown', 'explain', 'add_employee', 'assign_role', 'create_role', 'view_reports', 'change_permissions', 'diagnose', 'status'}
        if obs.operation not in valid_operations or obs.intent not in {name for name, _, _ in OBJECTS} | {'unknown', 'general'}:
            raise ValueError('Unsupported analyser task; extend the typed vocabulary explicitly')
        if obs.evidence is None or set(obs.entities) - ENTITY_SLOTS or any(
            f.message_id != message_id or f.start < 0 or f.end > len(text)
            or f.start >= f.end or text[f.start:f.end] != f.quote for f in facts
        ):
            raise ValueError("Analyser facts must cite spans of the current client message")
        known_task = obs.intent != "unknown" and obs.operation != "unknown"
        different_task = known_task and (obs.intent != previous.intent or obs.operation == "explain"
                         or (obs.intent not in {'access', 'credentials'} and previous.operation != 'unknown'
                             and obs.operation != previous.operation))
        refinement = bool(previous.task_id and not obs.question and (obs.requirement or obs.goals or obs.constraints)
                          and (obs.reference or not known_task))
        new = not previous.task_id or obs.new_topic or (different_task and not refinement and not obs.entity_only)
        summarizing = bool(previous.expected and previous.expected.reason == 'query_budget_exceeded'
                           and not obs.feedback and not obs.entity_only)
        new |= summarizing
        state = DialogueState(revision=previous.revision) if new else deepcopy(previous)
        if new:
            state.entities = deepcopy(previous.entities)
            state.routing_slot = None if obs.operation == 'explain' else previous.routing_slot
        state.revision += 1
        state.transition = "new_task" if new else "continue_task"
        state.analysis_required = False
        state.unresolved = None
        if new:
            state.task_id = f"task:{message_id}"
            state.topic_start_message_id = message_id
            state.task = Fact.span(text, message_id)
        changed_entity = any([f.value for f in values] != [f.value for f in state.entities.get(slot, [])]
                             for slot, values in obs.entities.items())
        for slot, values in obs.entities.items():
            state.entities[slot] = values
        explicit_routing = [slot for slot in ('service', 'ofd', 'software', 'manufacturer') if slot in obs.entities]
        equipment_only_update = (explicit_routing == ['manufacturer'] and not new
                                 and state.routing_slot in {'service', 'ofd', 'software'}
                                 and state.intent in {'access', 'credentials', 'receipt'})
        if explicit_routing and not equipment_only_update:
            state.routing_slot = explicit_routing[0]
        manufacturer_changed = ([f.value for f in obs.entities.get('manufacturer', [])]
                                != [f.value for f in previous.entities.get('manufacturer', [])])
        if "manufacturer" in obs.entities and "equipment" not in obs.entities and manufacturer_changed:
            state.entities.pop("equipment", None)
        # A requirement may contain an explicit replacement operation on the
        # same object ("мне нужно изменить ему права"). Keep only capability
        # refinements from changing the task to the objects they mention.
        if (not refinement and (new or (known_task and obs.intent == state.intent))) or (
                known_task and obs.intent == previous.intent and not obs.goals and not obs.constraints):
            state.intent, state.operation, state.object = obs.intent, obs.operation, obs.object
            state.operation_evidence = obs.evidence
        if obs.binds_object:
            state.object_reference = obs.evidence
        if any(words(f.value)[:1] == ['за'] for f in obs.parameters):
            state.parameters = [f for f in state.parameters if words(f.value)[:1] != ['за']]
        _append_unique(state.parameters, obs.parameters)
        if obs.error:
            state.error = obs.error
        if not new:
            if previous.expected:
                state.transition = "clarification"
                slot = previous.expected.slot
                # Entity slots remain pending until a matching client fact was
                # extracted. Generic short replies cannot confirm a service.
                if slot in ENTITY_SLOTS:
                    if slot in obs.entities or (slot == "service" and obs.entities):
                        state.expected = None
                elif known_task or obs.goals or obs.constraints or obs.entities:
                    state.expected = None
            if changed_entity and obs.entities and not (previous.expected and state.expected is None):
                state.transition = "change_service" if "service" in obs.entities else "change_parameter"
            elif obs.error and previous.error and obs.error.value != previous.error.value:
                state.transition = 'change_parameter'
            elif obs.goals or obs.constraints or refinement:
                state.transition = "refine_requirements"
        _append_unique(state.goals, obs.goals)
        _append_unique(state.constraints, obs.constraints)
        ambiguous = bool(not new and not known_task and not obs.entities and not refinement and not obs.feedback
                         and not obs.reference and not previous.expected and not obs.goals and not obs.constraints)
        if ambiguous or obs.uncertain:
            state.analysis_required = True
            state.unresolved = Fact.span(text, message_id)
        if previous.analysis_required and not (new or known_task or obs.entities or obs.goals or obs.constraints):
            state.analysis_required = True
            state.unresolved = previous.unresolved
        if not new and previous.expected and previous.expected.slot not in ENTITY_SLOTS and not known_task and not obs.entities:
            _append_unique(state.details, [Fact.span(text, message_id)])
        elif not new and obs.feedback:
            _append_unique(state.details, [Fact.span(text, message_id)])
        return state

    def observe_answer(self, previous: DialogueState, *, scenario: str | None,
                       reason: str | None, question: str, message_id: int | str | None = None,
                       slot: str | None = None) -> DialogueState:
        """An assistant can open an expected slot, never write client facts."""
        state = deepcopy(previous)
        if scenario == "clarify":
            if slot not in CLARIFICATION_SLOTS:
                slot = ("service" if reason in {"service_not_confirmed", "service_unknown", "service_ambiguous", "missing_service"}
                        else "equipment" if reason == "error_product_missing" else "details")
            state.expected = ExpectedClarification(slot, question, message_id, reason)
        else:
            state.expected = None
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
