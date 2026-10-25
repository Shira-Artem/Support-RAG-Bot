"""Small, evidence-bound LLM contract for conversational understanding.

This module interprets the client's latest turn. It never plans or generates
technical instructions; every stored claim is reduced from exact client spans.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.dialogue_state import (ENTITY_NAMES, ENTITY_SLOTS, OBJECTS, OPERATIONS, RELATIONS,
                                DialogueState, Fact, Observation)
from app.config import Settings


TURN_TYPES = {"greeting", "information", "diagnosis", "instruction", "feedback", "escalation"}
UNKNOWN_SLOTS = ENTITY_SLOTS | {"goal", "details", "task"}
INTENTS = {name for name, _, _ in OBJECTS} | {"general", "unknown"}
OBJECT_VALUES = {obj for _, obj, _ in OBJECTS} | {"понятие"}
OPERATIONS_ALLOWED = ({name for name, _ in OPERATIONS} |
                      {"unknown", "explain", "diagnose", "status", "view_reports",
                       "change_permissions", "add_employee", "assign_role",
                       "create_role", "request_specialist"})

TURN_TYPE_ALIASES = {"information_request": "information", "informational_request": "information",
    "info_request": "information", "faq": "information", "troubleshooting": "diagnosis",
    "procedural_instruction": "instruction", "human_escalation": "escalation"}
INTENT_ALIASES = {"definition": "general", "concept": "general",
    "general_question": "general", "general_information": "general"}
OPERATION_ALIASES = {"explanation": "explain", "diagnosis": "diagnose", "status_check": "status"}
RELATION_ALIASES = {"new_topic": "new_task", "topic_change": "new_task",
    "continuation": "continue", "same_task": "continue",
    "clarification_answer": "answer_to_clarification", "parameter_change": "parameter_update",
    "constraint_change": "constraint_update", "conflict": "contradiction"}


class UnderstandingError(ValueError):
    """Provider or validation error; callers must not fall back to lexical state."""
    def __init__(self, message: str, *, tokens: dict[str, int | None] | None = None,
                 duration_ms: int | None = None, model: str | None = None,
                 http_status: int | None = None,
                 structured_response: dict[str, Any] | None = None,
                 field_diagnostics: list[dict[str, Any]] | None = None,
                 provider_error: str | None = None):
        super().__init__(message)
        self.tokens, self.duration_ms, self.model = tokens, duration_ms, model
        self.http_status = http_status
        self.structured_response = structured_response
        self.field_diagnostics = field_diagnostics or []
        self.provider_error = provider_error


@dataclass(frozen=True)
class Understanding:
    request_type: str
    specialist_requested: bool
    unknown_facts: tuple[str, ...]
    observation: Observation
    tokens: dict[str, int | None]
    model: str
    duration_ms: int
    structured_response: dict[str, Any] | None = None
    field_diagnostics: list[dict[str, Any]] | None = None


def _append_local_trace(*, model: str | None, status: str, structured_output: Any,
                        field_diagnostics: list[dict[str, Any]], tokens: dict[str, int | None] | None,
                        duration_ms: int | None, error: str | None = None,
                        provider_error: str | None = None,
                        request_payload: dict[str, Any] | None = None) -> None:
    """Persist provider output and field decisions locally; never include credentials."""
    from datetime import datetime, timezone
    from hashlib import sha256
    path = Path(__file__).resolve().parents[1] / ".local" / "conversational-understanding.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "model": model,
        "status": status, "structured_output": structured_output,
        "structured_output_sha256": sha256(json.dumps(structured_output, ensure_ascii=False,
            sort_keys=True, default=str).encode("utf-8")).hexdigest(),
        "request_payload": request_payload, "field_diagnostics": field_diagnostics, "tokens": tokens,
        "duration_ms": duration_ms, "error": error, "provider_error": provider_error}
    try:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            stream.flush()
    except OSError as exc:
        raise UnderstandingError("local Understanding diagnostic trace is unavailable") from exc


def _span_schema(nullable: bool = True) -> dict[str, Any]:
    schema = {"type": "object", "properties": {"quote": {"type": "string"}},
              "required": ["quote"], "additionalProperties": False}
    return {**schema, "type": ["object", "null"]} if nullable else schema


def response_schema() -> dict[str, Any]:
    fields = {
        # Keep provider constraints structural. Semantic vocabularies are
        # intentionally validated locally so a new grounded noun or one
        # malformed label cannot make the API reject the entire generation.
        "request_type": {"type": "string"},
        "relation": {"type": "string"},
        "intent": {"type": "string"},
        "operation": {"type": "string"},
        "object": {"type": ["string", "null"]},
        # intent/operation/relation are semantic classifications. Evidence is
        # required for client facts, not for these labels.
        "object_evidence": _span_schema(),
        "goal": _span_schema(), "symptom": _span_schema(),
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "slot": {"type": "string"},
            "value": {"type": "string"}, "evidence": _span_schema(False)},
            "required": ["slot", "value", "evidence"], "additionalProperties": False}},
        "unknown_facts": {"type": "array", "items": {"type": "object", "properties": {
            "slot": {"type": "string"},
            "evidence": _span_schema(False)}, "required": ["slot", "evidence"],
            "additionalProperties": False}},
        "specialist_requested": {"type": "boolean"},
        "specialist_evidence": _span_schema(),
        "confidence": {"type": "number"},
    }
    return {"name": "conversational_understanding", "strict": True,
            "schema": {"type": "object", "properties": fields,
                       "required": list(fields), "additionalProperties": False}}


def _find_span(text: str, quote: Any, message_id: int | str) -> Fact:
    if not isinstance(quote, str) or not quote.strip():
        raise UnderstandingError("evidence quote is empty")
    start = text.find(quote)
    if start < 0 or text.find(quote, start + 1) >= 0:
        raise UnderstandingError("evidence quote is not one exact unique span")
    return Fact.span(text, message_id, start, start + len(quote))


def _fact_or_none(text: str, raw: Any, message_id: int | str) -> Fact | None:
    if raw is None:
        return None
    quote = raw.get("quote") if isinstance(raw, dict) else None
    # Some strict-schema completions emit an empty optional span instead of
    # JSON null. Treat that as absent; required claims are rejected below.
    if quote == "":
        return None
    return _find_span(text, quote, message_id)


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip()


def _canonical_entity_from_quote(slot: str, quote: str) -> str | None:
    """Resolve a known client mention to one canonical name using its source span."""
    folded_quote = _fold(quote)
    found = [(candidate_slot, name, _fold(alias)) for candidate_slot, name, aliases in ENTITY_NAMES
             for alias in aliases if _fold(alias) in folded_quote]
    # A service name such as "АТОЛ Онлайн" contains a manufacturer alias.
    # Prefer the longer full name and never infer the shorter cross-slot name.
    matches = {name for candidate_slot, name, alias in found
               if candidate_slot == slot and not any(
                   other_slot != candidate_slot and len(other_alias) > len(alias)
                   and alias in other_alias and other_alias in folded_quote
                   for other_slot, _, other_alias in found)}
    return next(iter(matches)) if len(matches) == 1 else None


def _entity_mention_is_asserted(text: str, fact: Fact) -> bool:
    """Do not turn a negated or explicitly uncertain mention into a client fact."""
    aliases = {alias for _, _, values in ENTITY_NAMES for alias in values}
    folded_quote = _fold(fact.quote)
    positions = [(fact.start + match.start(), alias) for alias in aliases
                 if _fold(alias) in folded_quote
                 for match in re.finditer(re.escape(alias), text[fact.start:fact.end], re.I)]
    if not positions:
        return True
    # Check context immediately before the named mention. A symptom such as
    # "не отправляются чеки на Эвотор" is not a negation of the product fact.
    start, _ = max(positions, key=lambda item: len(item[1]))
    before = text[:start]
    clause_start = max((before.rfind(mark) + 1 for mark in ".,;!?\n"), default=0)
    prefix = before[clause_start:]
    if re.search(r"\bне\s+(?:используем|пользуемся|применяем|поддерживаем|работаем\s+с|наш\w*|этот|эта|это)\s*(?:[а-яa-z0-9-]+\s*){0,2}$|"
                 r"\b(?:нет|без)\s*(?:[а-яa-z0-9-]+\s*){0,1}$|\bне\s*$", prefix, re.I):
        return False
    if re.search(r"\b(?:возможно|кажется|наверное|сомневаюсь|не\s+уверен\w*|не\s+знаю)\b[^,;.!?\n]{0,30}$",
                 prefix, re.I):
        return False
    return True


def _entity_value_supported(slot: str, value: Any, quote: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if slot == "equipment":
        return value.casefold() in quote.casefold()
    return _canonical_entity_from_quote(slot, quote) == value


def _field_result(diagnostics: list[dict[str, Any]], field: str, status: str,
                  reason: str, **extra: Any) -> None:
    diagnostics.append({"field": field, "status": status, "reason": reason, **extra})


def _normalize_label(raw: Any, allowed: set[str], aliases: dict[str, str]) -> str:
    if not isinstance(raw, str):
        return "unknown"
    value = raw.strip().casefold().replace("-", "_").replace(" ", "_")
    value = aliases.get(value, value)
    return value if value in allowed else "unknown"


def _parse_optional_fact(text: str, raw: Any, message_id: int | str,
                         diagnostics: list[dict[str, Any]], field: str) -> Fact | None:
    if raw is None or raw == {"quote": ""}:
        _field_result(diagnostics, field, "omitted", "not_claimed")
        return None
    try:
        fact = _fact_or_none(text, raw, message_id)
    except (UnderstandingError, AttributeError, TypeError) as exc:
        _field_result(diagnostics, field, "rejected", str(exc))
        return None
    if fact is None:
        _field_result(diagnostics, field, "omitted", "not_claimed")
    else:
        _field_result(diagnostics, field, "accepted", "exact_current_message_span",
                      start=fact.start, end=fact.end)
    return fact


def validate_response(data: Any, text: str, message_id: int | str) -> tuple[str, bool, tuple[str, ...], Observation]:
    diagnostics: list[dict[str, Any]] = []
    schema_fields = set(response_schema()["schema"]["required"])
    if not isinstance(data, dict) or set(data) != schema_fields:
        raise UnderstandingError("structured response fields mismatch")
    raw_kind = data["request_type"]
    kind = _normalize_label(raw_kind, TURN_TYPES, TURN_TYPE_ALIASES)
    if kind == "unknown":
        raise UnderstandingError("invalid request_type; cannot safely route turn")
    raw_relation, raw_intent, raw_operation = data["relation"], data["intent"], data["operation"]
    relation = _normalize_label(raw_relation, RELATIONS, RELATION_ALIASES)
    intent = _normalize_label(raw_intent, INTENTS, INTENT_ALIASES)
    operation = _normalize_label(raw_operation, OPERATIONS_ALLOWED, OPERATION_ALIASES)
    for field_name, raw_value, value, aliases in (
            ("relation", raw_relation, relation, RELATION_ALIASES),
            ("intent", raw_intent, intent, INTENT_ALIASES),
            ("operation", raw_operation, operation, OPERATION_ALIASES)):
        normalized_input = raw_value.strip().casefold().replace("-", "_").replace(" ", "_") if isinstance(raw_value, str) else None
        valid_input = normalized_input in (RELATIONS if field_name == "relation" else
            INTENTS if field_name == "intent" else OPERATIONS_ALLOWED)
        status = "accepted" if valid_input or aliases.get(normalized_input) == value else "rejected"
        reason = ("valid_semantic_classification" if normalized_input == value else
                  "normalized_semantic_alias" if value != "unknown" and aliases.get(normalized_input) == value else
                  "unsupported_value_defaulted_to_unknown")
        _field_result(diagnostics, field_name, status, reason, value=value)
    raw_obj = data["object"]
    obj = raw_obj if raw_obj is None or (isinstance(raw_obj, str) and raw_obj in OBJECT_VALUES) else None
    if raw_obj is not None and obj is None:
        _field_result(diagnostics, "object", "rejected", "unsupported_object_value", claimed=str(raw_obj))
    if obj is not None and intent != "unknown" and (intent, obj) not in (
            {(i, o) for i, o, _ in OBJECTS} | {("general", "понятие")}):
        raise UnderstandingError("object is inconsistent with intent")
    if obj is not None and intent == "unknown":
        _field_result(diagnostics, "object", "rejected", "object_cannot_be_validated_without_intent", claimed=obj)
        obj = None
    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        confidence = 0.0
        _field_result(diagnostics, "confidence", "rejected", "invalid_confidence_defaulted_to_zero")
    else:
        _field_result(diagnostics, "confidence", "accepted", "valid_confidence", value=float(confidence))
    normalized_kind = raw_kind.strip().casefold().replace("-", "_").replace(" ", "_") if isinstance(raw_kind, str) else None
    _field_result(diagnostics, "request_type", "accepted",
        "valid_turn_classification" if normalized_kind == kind else "normalized_turn_type_alias", value=kind)
    if not isinstance(data["specialist_requested"], bool):
        specialist_requested = False
        _field_result(diagnostics, "specialist_requested", "rejected", "invalid_flag_type_defaulted_false")
    else:
        specialist_requested = data["specialist_requested"]
    unknown_raw = data["unknown_facts"]
    if not isinstance(unknown_raw, list):
        _field_result(diagnostics, "unknown_facts", "rejected", "expected_array")
        unknown_raw = []
    elif not unknown_raw:
        _field_result(diagnostics, "unknown_facts", "omitted", "no_unknown_slots_claimed")
    else:
        _field_result(diagnostics, "unknown_facts", "accepted", "valid_array", count=len(unknown_raw))
    unknown_evidence: dict[str, Fact] = {}
    for index, item in enumerate(unknown_raw):
        field = f"unknown_facts[{index}]"
        if not isinstance(item, dict) or set(item) != {"slot", "evidence"}:
            _field_result(diagnostics, field, "rejected", "invalid_unknown_fact_shape")
            continue
        slot = item["slot"]
        if not isinstance(slot, str) or slot not in UNKNOWN_SLOTS or slot in unknown_evidence:
            _field_result(diagnostics, field, "rejected", "invalid_or_duplicate_unknown_fact_slot")
            continue
        try:
            fact = _find_span(text, item["evidence"].get("quote"), message_id)
        except (UnderstandingError, AttributeError, TypeError) as exc:
            _field_result(diagnostics, field, "rejected", str(exc))
            continue
        unknown_evidence[slot] = fact
        _field_result(diagnostics, f"unknown_facts.{slot}", "accepted", "explicit_unknown_with_exact_span",
                      start=fact.start, end=fact.end)

    object_ev = _parse_optional_fact(text, data["object_evidence"], message_id, diagnostics, "object_evidence")
    if obj is not None and object_ev is None:
        _field_result(diagnostics, "object", "rejected", "object_claim_lacks_valid_source_span", claimed=obj)
        obj = None
    elif obj is not None:
        _field_result(diagnostics, "object", "accepted", "classification_and_source_span_valid", value=obj)
    elif raw_obj is None:
        _field_result(diagnostics, "object", "omitted", "no_object_claimed")
    specialist_ev = _parse_optional_fact(text, data["specialist_evidence"], message_id,
                                         diagnostics, "specialist_evidence")
    if specialist_requested and (specialist_ev is None
            or not re.search(r"специалист|живой человек|человек|сотрудник поддержки", specialist_ev.quote, re.I)
            or re.search(r"\bне\b.{0,28}\b(?:специалист\w*|человек\w*|сотрудник\w*)\b|"
                         r"\b(?:специалист\w*|человек\w*|сотрудник\w*)\b.{0,20}\bне\b",
                         specialist_ev.quote, re.I)):
        specialist_requested = False
        _field_result(diagnostics, "specialist_requested", "rejected", "no_direct_positive_user_evidence")
    elif specialist_requested:
        _field_result(diagnostics, "specialist_requested", "accepted", "direct_positive_user_evidence")
    else:
        _field_result(diagnostics, "specialist_requested", "accepted", "not_requested")

    entities: dict[str, list[Fact]] = {}
    entity_claims = data["entities"]
    if not isinstance(entity_claims, list):
        _field_result(diagnostics, "entities", "rejected", "expected_array")
        entity_claims = []
    elif not entity_claims:
        _field_result(diagnostics, "entities", "omitted", "no_entity_claims")
    else:
        _field_result(diagnostics, "entities", "accepted", "valid_array", count=len(entity_claims))
    for index, item in enumerate(entity_claims):
        field = f"entities[{index}]"
        if not isinstance(item, dict) or set(item) != {"slot", "value", "evidence"}:
            _field_result(diagnostics, field, "rejected", "invalid_entity_claim_shape")
            continue
        slot, value = item["slot"], item["value"]
        if not isinstance(slot, str) or slot not in ENTITY_SLOTS or not isinstance(value, str) or not value.strip():
            _field_result(diagnostics, field, "rejected", "invalid_entity_slot_or_value")
            continue
        try:
            evidence = _find_span(text, item["evidence"].get("quote"), message_id)
        except (UnderstandingError, AttributeError, TypeError) as exc:
            _field_result(diagnostics, field, "rejected", str(exc), slot=slot)
            continue
        if not _entity_mention_is_asserted(text, evidence):
            _field_result(diagnostics, field, "rejected", "entity_mention_is_negated_or_uncertain",
                          slot=slot, claimed=value, start=evidence.start, end=evidence.end)
            continue
        if slot == "equipment":
            canonical = evidence.quote if value.casefold() in evidence.quote.casefold() else None
        else:
            canonical = _canonical_entity_from_quote(slot, evidence.quote)
        if canonical is None:
            _field_result(diagnostics, field, "rejected", "entity_not_supported_by_source_alias",
                          slot=slot, claimed=value, start=evidence.start, end=evidence.end)
            continue
        reason = "exact_source_value" if canonical == value else "normalized_to_known_alias_from_source"
        entities.setdefault(slot, []).append(Fact.span(text, message_id, evidence.start, evidence.end,
                                                        value=canonical))
        _field_result(diagnostics, field, "accepted", reason, slot=slot,
                      value=canonical, start=evidence.start, end=evidence.end)

    goal = _parse_optional_fact(text, data["goal"], message_id, diagnostics, "goal")
    symptom = _parse_optional_fact(text, data["symptom"], message_id, diagnostics, "symptom")
    evidence = Fact.span(text, message_id)
    observation = Observation(entities=entities, unknown_facts=unknown_evidence,
        validation_diagnostics=diagnostics,
        intent=intent, operation=operation, object=obj, evidence=evidence,
        object_evidence=object_ev, symptom=symptom,
        goals=[goal] if goal else [], relation=relation, confidence=float(confidence),
        intent_confidence=float(confidence), operation_confidence=float(confidence),
        relation_confidence=float(confidence), feedback=kind == "feedback",
        question=kind == "information")
    if kind == "information" and operation not in {"unknown", "explain"}:
        raise UnderstandingError("information request conflicts with non-explanatory operation")
    return kind, specialist_requested, tuple(unknown_evidence), observation


def _state_summary(state: DialogueState) -> dict[str, Any]:
    task = state.active_task
    if task is None:
        return {"active_task": None, "expected_clarification": None}
    def facts(items):
        return [{"value": f.value, "source_message_id": f.message_id} for f in items]
    return {"active_task": {"task_id": state.task_id, "intent": state.intent,
            "operation": state.operation, "object": state.object,
            "entities": {k: facts(v) for k, v in task.entities.items()},
            "unknown_facts": list(task.unknown_facts),
            "symptom": facts([task.symptom]) if task.symptom else [],
            "goals": facts(task.goals), "constraints": facts(task.constraints),
            "details": facts(task.details)},
            "expected_clarification": ({"slot": state.expected.slot, "question": state.expected.question}
                                       if state.expected else None)}


async def understand_message(text: str, message_id: int | str, history: list[dict],
                             state: DialogueState, settings: Settings) -> Understanding:
    if settings.llm_provider != "groq" or not settings.groq_api_key:
        raise UnderstandingError("Source-first understanding requires configured Groq")
    from time import perf_counter
    started = perf_counter()
    safe_history = [{"role": item.get("role"), "content": item.get("content", "")}
                    for item in history[-12:] if item.get("role") in {"user", "assistant"}]
    payload = {"task": "Interpret the latest client turn. Return the requested structured JSON; do not answer or give technical steps.",
        "rules": ["Use recent conversation and active task only to resolve reference, continuity, new task, clarification answer, and missing information.",
            "Intent, operation, request type, and relation are semantic classifications. Infer them from meaning; do not require or invent quote evidence for these labels.",
            "Every concrete client fact must cite one exact unique substring of current_message: entities, object, goal, symptom, an explicit unknown fact, and a direct specialist request.",
            "Never turn facts stated by the assistant into client facts. If a client fact has no exact supporting quote, omit it or mark the needed slot unknown only when the client explicitly says they do not know/cannot provide it.",
            "Do not infer a cash-register manufacturer from an OFD operator or the reverse.",
            "Information requests ask for explain operation; diagnosis and instructions remain separate.",
            "Set specialist_requested only for a direct, positive request to speak with a human specialist.",
            "Use unknown and unknown_facts when the client cannot provide a detail. Never repeat a requested unknown fact.",
            "Choose relation new_task when the client changes topic; otherwise distinguish continuation from clarification answer."],
        "recent_history": safe_history, "active_task_state": _state_summary(state), "current_message": text}
    schema = response_schema()
    headers = {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}
    request = {"model": settings.groq_model, "reasoning_effort": settings.groq_reasoning_effort,
        "temperature": 0, "max_completion_tokens": 4096,
        "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        "response_format": {"type": "json_schema", "json_schema": schema}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=15)) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=request)
        if response.status_code >= 400:
            provider_error = response.text[:2000]
            diagnostics = [{"field": "$", "status": "rejected",
                            "reason": f"groq_http_{response.status_code}"}]
            _append_local_trace(model=settings.groq_model, status="provider_http_error",
                structured_output=None, field_diagnostics=diagnostics, tokens=None,
                duration_ms=round((perf_counter()-started)*1000),
                error=f"Groq HTTP {response.status_code}", provider_error=provider_error,
                request_payload=request)
            raise UnderstandingError(f"Groq HTTP {response.status_code}", duration_ms=round((perf_counter()-started)*1000),
                                     model=settings.groq_model, http_status=response.status_code,
                                     field_diagnostics=diagnostics, provider_error=provider_error)
        result = response.json()
        usage = result.get("usage") or {}
        tokens = {key: usage.get(source) for key, source in (("prompt_tokens", "prompt_tokens"),
                  ("completion_tokens", "completion_tokens"), ("total_tokens", "total_tokens"))}
        content = result["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            diagnostics = [{"field": "$", "status": "rejected", "reason": "invalid_json"}]
            _append_local_trace(model=result.get("model") or settings.groq_model,
                status="invalid_json", structured_output=content, field_diagnostics=diagnostics,
                tokens=tokens, duration_ms=round((perf_counter()-started)*1000), error=type(exc).__name__,
                request_payload=request)
            raise UnderstandingError("Groq returned invalid structured JSON", tokens=tokens,
                duration_ms=round((perf_counter()-started)*1000), model=result.get("model") or settings.groq_model,
                structured_response={"raw_content": content}, field_diagnostics=diagnostics) from exc
        try:
            kind, specialist, unknown, observation = validate_response(parsed, text, message_id)
        except UnderstandingError as exc:
            diagnostics = exc.field_diagnostics or [{"field": "$", "status": "rejected", "reason": str(exc)}]
            _append_local_trace(model=result.get("model") or settings.groq_model,
                status="rejected", structured_output=parsed, field_diagnostics=diagnostics,
                tokens=tokens, duration_ms=round((perf_counter()-started)*1000), error=str(exc),
                request_payload=request)
            raise UnderstandingError(str(exc), tokens=tokens,
                duration_ms=round((perf_counter()-started)*1000), model=result.get("model") or settings.groq_model,
                structured_response=parsed, field_diagnostics=diagnostics) from exc
        _append_local_trace(model=result.get("model") or settings.groq_model,
            status="validated_with_field_rejections" if any(d["status"] == "rejected" for d in observation.validation_diagnostics) else "validated",
            structured_output=parsed, field_diagnostics=observation.validation_diagnostics,
            tokens=tokens, duration_ms=round((perf_counter()-started)*1000), request_payload=request)
    except UnderstandingError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise UnderstandingError(f"understanding failed: {type(exc).__name__}",
            tokens=locals().get("tokens"), duration_ms=round((perf_counter()-started)*1000),
            model=locals().get("result", {}).get("model", settings.groq_model)) from exc
    return Understanding(kind, specialist, unknown, observation, tokens,
                         result.get("model") or settings.groq_model,
                         round((perf_counter() - started) * 1000), parsed,
                         observation.validation_diagnostics)


def understanding_to_dict(value: Understanding) -> dict[str, Any]:
    obs = value.observation
    def fact(f): return {"value": f.value, "message_id": f.message_id,
                        "quote": f.quote, "start": f.start, "end": f.end} if f else None
    return {"request_type": value.request_type, "specialist_requested": value.specialist_requested,
        "unknown_facts": list(value.unknown_facts), "tokens": value.tokens,
        "model": value.model, "duration_ms": value.duration_ms,
        "validation_diagnostics": value.field_diagnostics or [],
        "observation": {"intent": obs.intent, "operation": obs.operation, "object": obs.object,
            "relation": obs.relation, "confidence": obs.confidence,
            "intent_evidence": fact(obs.intent_evidence), "operation_evidence": fact(obs.operation_evidence),
            "object_evidence": fact(obs.object_evidence), "relation_evidence": fact(obs.relation_evidence),
            "symptom": fact(obs.symptom), "goals": [fact(x) for x in obs.goals],
            "unknown_facts": {slot: fact(span) for slot, span in obs.unknown_facts.items()},
            "entities": {slot: [fact(x) for x in values] for slot, values in obs.entities.items()}}}


def observation_from_dict(data: dict[str, Any], text: str, message_id: int | str) -> tuple[Observation, dict[str, Any]]:
    """Revalidate persisted spans before the deterministic reducer applies them."""
    raw = data.get("observation") or {}
    def parse(raw_fact):
        if raw_fact is None: return None
        fact = Fact(**raw_fact)
        if fact.message_id != message_id or fact.start < 0 or fact.end > len(text) or text[fact.start:fact.end] != fact.quote:
            raise UnderstandingError("persisted evidence span mismatch")
        return fact
    entities = {slot: [parse(item) for item in values] for slot, values in raw.get("entities", {}).items()}
    if set(entities) - ENTITY_SLOTS:
        raise UnderstandingError("persisted entity slot mismatch")
    raw_unknown = raw.get("unknown_facts", {})
    if not isinstance(raw_unknown, dict) or set(raw_unknown) - UNKNOWN_SLOTS:
        raise UnderstandingError("persisted unknown-fact slot mismatch")
    unknown_evidence = {slot: parse(span) for slot, span in raw_unknown.items()}
    observation = Observation(entities=entities, unknown_facts=unknown_evidence,
        intent=raw["intent"], operation=raw["operation"],
        object=raw.get("object"), evidence=Fact.span(text, message_id),
        intent_evidence=parse(raw.get("intent_evidence")), operation_evidence=parse(raw.get("operation_evidence")),
        object_evidence=parse(raw.get("object_evidence")), relation_evidence=parse(raw.get("relation_evidence")),
        symptom=parse(raw.get("symptom")), goals=[parse(item) for item in raw.get("goals", [])],
        relation=raw["relation"], confidence=float(raw["confidence"]),
        intent_confidence=float(raw["confidence"]), operation_confidence=float(raw["confidence"]),
        relation_confidence=float(raw["confidence"]), feedback=data.get("request_type") == "feedback",
        question=data.get("request_type") == "information")
    kind, specialist, unknown = data.get("request_type"), data.get("specialist_requested"), data.get("unknown_facts", [])
    if (kind not in TURN_TYPES or not isinstance(specialist, bool)
            or not isinstance(unknown, list) or any(x not in UNKNOWN_SLOTS for x in unknown)
            or set(unknown) != set(unknown_evidence)):
        raise UnderstandingError("persisted understanding contract mismatch")
    if (observation.intent not in INTENTS or observation.operation not in OPERATIONS_ALLOWED
            or observation.object is not None and observation.object not in OBJECT_VALUES
            or observation.relation not in RELATIONS):
        raise UnderstandingError("persisted task vocabulary mismatch")
    if observation.object is not None and observation.object_evidence is None:
        raise UnderstandingError("persisted object is missing evidence")
    for slot, values in entities.items():
        if any(not _entity_value_supported(slot, fact.value, fact.quote)
               or not _entity_mention_is_asserted(text, fact) for fact in values):
            raise UnderstandingError("persisted entity value is not grounded")
    if kind == "information" and (observation.intent != "general" or observation.operation != "explain"):
        raise UnderstandingError("persisted information intent mismatch")
    return observation, {"request_type": kind, "specialist_requested": specialist,
                         "unknown_facts": list(unknown), "tokens": data.get("tokens", {}),
                         "model": data.get("model"), "duration_ms": data.get("duration_ms")}
