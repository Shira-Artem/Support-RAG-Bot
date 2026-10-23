#!/usr/bin/env python
"""Interactive, isolated A/B comparison of dialogue analyzers (no RAG/Telegram)."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.dialogue_state import (  # noqa: E402
    ENTITY_NAMES, ENTITY_SLOTS, OBJECTS, OPERATIONS, RELATIONS, DialogueManager, DialogueState,
    Fact, LexicalAnalyzer, Observation,
)

MODEL = "openai/gpt-oss-20b"
EFFORT = "medium"
ENTITY_VALUES = sorted({name for _, name, _ in ENTITY_NAMES})
INTENTS = sorted({name for name, _, _ in OBJECTS} | {"unknown", "general"})
OBJECT_VALUES = sorted({obj for _, obj, _ in OBJECTS} | {"понятие"})
OPERATIONS_ALLOWED = sorted(
    {name for name, _ in OPERATIONS}
    | {"unknown", "explain", "add_employee", "assign_role", "create_role",
       "view_reports", "change_permissions", "diagnose", "status"}
)
INTENT_OBJECT_PAIRS = {(intent, obj) for intent, obj, _ in OBJECTS} | {("general", "понятие")}


class SemanticResponseError(ValueError):
    def __init__(self, message: str, usage: dict[str, int | None]):
        super().__init__(message)
        self.usage = usage


def _span_schema() -> dict[str, Any]:
    return {"type": ["object", "null"], "properties": {
        "quote": {"type": "string"}}, "required": ["quote"], "additionalProperties": False}


def _span_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object", "properties": {
        "quote": {"type": "string"}}, "required": ["quote"], "additionalProperties": False}}


def build_schema() -> dict[str, Any]:
    """Strict schema derived from the live v2.1 vocabularies."""
    properties: dict[str, Any] = {
        "intent": {"type": "string", "enum": INTENTS},
        "operation": {"type": "string", "enum": OPERATIONS_ALLOWED},
        "object": {"type": ["string", "null"], "enum": [*OBJECT_VALUES, None]},
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "slot": {"type": "string", "enum": sorted(ENTITY_SLOTS)},
            "value": {"type": "string"},
            "evidence": {"type": "object", "properties": {"quote": {"type": "string"}},
                         "required": ["quote"], "additionalProperties": False}},
            "required": ["slot", "value", "evidence"], "additionalProperties": False}},
        "symptom": _span_schema(), "error": _span_schema(),
        "goals": _span_array_schema(), "constraints": _span_array_schema(),
        "details": _span_array_schema(), "parameters": _span_array_schema(),
        "relation": {"type": "string", "enum": sorted(RELATIONS)},
        "new_topic": {"type": "boolean"}, "reference": {"type": "boolean"},
        "question": {"type": "boolean"}, "requirement": {"type": "boolean"},
        "entity_only": {"type": "boolean"}, "feedback": {"type": "boolean"},
        "uncertain": {"type": "boolean"}, "binds_object": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "intent_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "operation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "relation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "intent_evidence": _span_schema(), "object_evidence": _span_schema(),
        "operation_evidence": _span_schema(), "relation_evidence": _span_schema(),
    }
    return {"name": "dialogue_observation", "strict": True, "schema": {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False}}


def _find_span(text: str, quote: str, message_id: int | str) -> Fact:
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError("evidence quote is empty")
    start = text.find(quote)
    if start < 0:
        raise ValueError(f"evidence quote is not an exact substring: {quote!r}")
    if text.find(quote, start + 1) >= 0:
        raise ValueError(f"evidence quote is not unique: {quote!r}")
    return Fact.span(text, message_id, start, start + len(quote))


def _entity_quote_supports(slot: str, value: str, quote: str) -> bool:
    aliases = next((aliases for candidate_slot, name, aliases in ENTITY_NAMES
                    if candidate_slot == slot and name == value), ())
    folded = quote.casefold().replace("ё", "е")
    return any(alias.casefold().replace("ё", "е") in folded for alias in aliases)


def validate_payload(payload: Any, text: str, message_id: int | str) -> Observation:
    """Validate vocabulary, confidence, exact evidence and entity grounding."""
    if not isinstance(payload, dict):
        raise ValueError("response must be a JSON object")
    required = set(build_schema()["schema"]["required"])
    if set(payload) != required:
        raise ValueError("response fields do not match the required schema")
    if payload["intent"] not in INTENTS or payload["operation"] not in OPERATIONS_ALLOWED:
        raise ValueError("unsupported intent or operation")
    if payload["object"] is not None and payload["object"] not in OBJECT_VALUES:
        raise ValueError("unsupported object")
    if payload["object"] is not None and (payload["intent"], payload["object"]) not in INTENT_OBJECT_PAIRS:
        raise ValueError("object does not belong to the selected intent")
    if payload["relation"] not in RELATIONS:
        raise ValueError("unsupported relation")
    for key in ("confidence", "intent_confidence", "operation_confidence", "relation_confidence"):
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    for key in ("new_topic", "reference", "question", "requirement", "entity_only",
                "feedback", "uncertain", "binds_object"):
        if not isinstance(payload[key], bool):
            raise ValueError(f"{key} must be boolean")
    if payload["new_topic"] and payload["relation"] != "new_task":
        raise ValueError("new_topic requires relation=new_task")

    def span(value: Any) -> Fact | None:
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"quote"}:
            raise ValueError("malformed evidence span")
        return _find_span(text, value["quote"], message_id)

    evidence = Fact.span(text, message_id)
    entities: dict[str, list[Fact]] = {}
    if not isinstance(payload["entities"], list):
        raise ValueError("entities must be a list")
    for item in payload["entities"]:
        if not isinstance(item, dict) or set(item) != {"slot", "value", "evidence"}:
            raise ValueError("malformed entity claim")
        slot, value = item["slot"], item["value"]
        if slot not in ENTITY_SLOTS or not isinstance(value, str) or not value.strip():
            raise ValueError("unsupported entity slot/value")
        ev = span(item["evidence"])
        grounded = (value.casefold() in ev.quote.casefold()) if slot == "equipment" and ev else (
            bool(ev and value in ENTITY_VALUES and _entity_quote_supports(slot, value, ev.quote)))
        if ev is None or not grounded:
            raise ValueError("entity value is not grounded by its evidence span")
        entities.setdefault(slot, []).append(Fact.span(text, message_id, ev.start, ev.end, value=value))

    def span_list(key: str) -> list[Fact]:
        values = payload[key]
        if not isinstance(values, list):
            raise ValueError(f"{key} must be a list")
        result = []
        for item in values:
            if not isinstance(item, dict) or set(item) != {"quote"}:
                raise ValueError(f"malformed {key} evidence")
            fact = span(item)
            assert fact is not None
            result.append(fact)
        return result

    spans = {key: span(payload[key]) for key in
             ("symptom", "error", "intent_evidence", "object_evidence", "operation_evidence", "relation_evidence")}
    # Claims without evidence are rejected, rather than being silently downgraded or
    # replaced by lexical output. Unknown values can remain unknown without a span.
    for key, value_key in (("intent_evidence", "intent"), ("object_evidence", "object"),
                           ("operation_evidence", "operation")):
        has_claim = payload[value_key] not in (None, "unknown")
        if has_claim and spans[key] is None:
            raise ValueError(f"{value_key} claim has no evidence")
    if payload["relation"] != "unknown" and spans["relation_evidence"] is None:
        raise ValueError("relation claim has no evidence")

    return Observation(
        entities=entities, intent=payload["intent"], operation=payload["operation"], object=payload["object"],
        evidence=evidence, intent_evidence=spans["intent_evidence"],
        object_evidence=spans["object_evidence"], operation_evidence=spans["operation_evidence"],
        relation_evidence=spans["relation_evidence"], symptom=spans["symptom"], error=spans["error"],
        goals=span_list("goals"), constraints=span_list("constraints"), details=span_list("details"),
        parameters=span_list("parameters"), relation=payload["relation"],
        new_topic=payload["new_topic"], reference=payload["reference"], question=payload["question"],
        requirement=payload["requirement"], entity_only=payload["entity_only"],
        feedback=payload["feedback"], uncertain=payload["uncertain"], binds_object=payload["binds_object"],
        confidence=float(payload["confidence"]), intent_confidence=float(payload["intent_confidence"]),
        operation_confidence=float(payload["operation_confidence"]),
        relation_confidence=float(payload["relation_confidence"]),
    )


def _confirmed_state(state: DialogueState) -> dict[str, Any]:
    """Only explicitly stored facts, retaining provenance; no full transcript."""
    task = state.task_context
    if not task:
        return {"active_task": None, "session_facts": {}}
    def facts(items: list[Fact]) -> list[dict[str, str]]:
        return [{"value": f.value, "source": f.quote} for f in items]
    return {
        "active_task": {"intent": task.intent, "operation": task.operation, "object": task.object,
            "routing_service": state.routing_service, "entities": {k: facts(v) for k, v in task.entities.items()},
            "symptom": asdict(task.symptom) if task.symptom else None,
            "goals": facts(task.goals), "constraints": facts(task.constraints),
            "details": facts(task.details), "expected_clarification": asdict(task.expected) if task.expected else None,
            "operation_evidence": asdict(task.operation_evidence) if task.operation_evidence else None},
        "session_facts": {k: facts(v) for k, v in state.session.entities.items()},
    }


class _PendingObservationAnalyzer:
    """Lets DialogueManager reduce a precomputed remote Observation once."""
    def __init__(self):
        self.current: tuple[str, Observation] | None = None

    def analyze(self, text: str, message_id: int | str, state: DialogueState) -> Observation:
        if self.current is None or self.current[0] != str(message_id):
            raise RuntimeError("no validated semantic observation for this message")
        return self.current[1]


def build_messages(text: str, state: DialogueState) -> list[dict[str, str]]:
    """Prompt contains schema and state, never benchmark questions/expected answers."""
    prompt = {
        "task": "Analyze one current Russian support message as a typed dialogue observation.",
        "rules": [
            "Use only the allowed vocabulary implied by the JSON schema.",
            "Separate the mentioned object, requested operation, and failure symptom.",
            "A noun or a descriptive participle alone is not a requested operation.",
            "Use relation answer_to_clarification only when the current text answers the stored expected slot.",
            "A new explicit topic is new_task. Do not merge distinct tasks.",
            "Only facts stated in the current text may have evidence spans. Previously confirmed facts are context, not new evidence.",
            "Never infer service, equipment, cause, or other facts. Use unknown/null and lower confidence when unsure.",
            "Every asserted intent/object/operation/relation and every entity must cite an exact, unique substring of current_message.",
            "Return only the schema object. Do not answer the support question.",
        ],
        "previous_confirmed_state": _confirmed_state(state),
        "current_message": text,
    }
    return [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]


async def groq_observation(text: str, message_id: int | str, state: DialogueState,
                           api_key: str) -> tuple[Observation, dict[str, int | None]]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    request = {"model": MODEL, "reasoning_effort": EFFORT, "temperature": 0,
        # GPT-OSS medium reasoning shares this cap with the visible JSON body.
        "max_completion_tokens": 4096, "messages": build_messages(text, state),
        "response_format": {"type": "json_schema", "json_schema": build_schema()}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15)) as client:
        response = await client.post("https://api.groq.com/openai/v1/chat/completions",
                                     headers=headers, json=request)
    if response.status_code >= 400:
        # Provider errors can clarify unsupported schema features. Expose only
        # the short error message (never response headers or request payload).
        try:
            detail = response.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        raise RuntimeError(f"Groq HTTP {response.status_code}: {str(detail)[:240]}")
    data = response.json()
    usage = data.get("usage") or {}
    tokens = {"prompt_tokens": usage.get("prompt_tokens"),
              "completion_tokens": usage.get("completion_tokens"),
              "total_tokens": usage.get("total_tokens")}
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("missing JSON content")
        payload = json.loads(content)
        observation = validate_payload(payload, text, message_id)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise SemanticResponseError(f"invalid semantic analyzer response ({type(exc).__name__}: {exc})",
                                    tokens) from exc
    return observation, tokens


def _fact_value(fact: Fact | None) -> str | None:
    return fact.value if fact else None


def _facts(items: list[Fact]) -> list[str]:
    return [fact.value for fact in items]


def state_view(state: DialogueState) -> dict[str, Any]:
    task = state.task_context
    return {"task_id": state.task_id, "intent": state.intent, "operation": state.operation,
        "object": state.object, "symptom": _fact_value(task.symptom) if task else None,
        "service/equipment": {k: _facts(v) for k, v in (task.entities.items() if task else [])},
        "relation": state.relation, "confidence": state.confidence,
        "goals": _facts(state.goals), "constraints": _facts(state.constraints),
        "details": _facts(state.details), "expected_clarification": asdict(state.expected) if state.expected else None,
        "operation_evidence": _fact_value(state.operation_evidence)}


def _observation_view(obs: Observation) -> dict[str, Any]:
    return {"intent": obs.intent, "operation": obs.operation, "object": obs.object,
        "symptom": obs.symptom.quote if obs.symptom else None,
        "service/equipment": {k: [{"value": f.value, "evidence": f.quote} for f in vals]
                              for k, vals in obs.entities.items()},
        "relation": obs.relation, "confidence": obs.confidence,
        "field_confidence": {"intent": obs.intent_confidence, "operation": obs.operation_confidence,
                             "relation": obs.relation_confidence},
        "evidence_spans": {"intent": obs.intent_evidence.quote if obs.intent_evidence else None,
            "object": obs.object_evidence.quote if obs.object_evidence else None,
            "operation": obs.operation_evidence.quote if obs.operation_evidence else None,
            "relation": obs.relation_evidence.quote if obs.relation_evidence else None}}


def _fact_classification(state: DialogueState, obs: Observation | None) -> dict[str, Any]:
    if obs is None:
        return {"confirmed": [], "assumptions": [], "uncertainty": ["analyzer error; no patch applied"]}
    confirmed = []
    assumptions = []
    for name, value, evidence, confidence in (
        ("intent", obs.intent, obs.intent_evidence, obs.intent_confidence),
        ("object", obs.object, obs.object_evidence, obs.intent_confidence),
        ("operation", obs.operation, obs.operation_evidence, obs.operation_confidence),
        ("relation", obs.relation, obs.relation_evidence, obs.relation_confidence),
    ):
        if value not in (None, "unknown"):
            target = confirmed if evidence and confidence >= 0.65 else assumptions
            target.append({"field": name, "value": value, "evidence": evidence.quote if evidence else None,
                           "confidence": confidence})
    for slot, items in obs.entities.items():
        confirmed.extend({"field": f"entity:{slot}", "value": fact.value,
                          "evidence": fact.quote, "confidence": 1.0} for fact in items)
    for name, fact in (("symptom", obs.symptom), ("error", obs.error)):
        if fact:
            confirmed.append({"field": name, "value": fact.value,
                              "evidence": fact.quote, "confidence": obs.confidence})
    for name, items in (("goal", obs.goals), ("constraint", obs.constraints),
                        ("detail", obs.details), ("parameter", obs.parameters)):
        confirmed.extend({"field": name, "value": fact.value,
                          "evidence": fact.quote, "confidence": 1.0} for fact in items)
    return {"confirmed": confirmed, "assumptions": assumptions,
        "uncertainty": ["unresolved/low confidence"] if obs.uncertain or obs.confidence < .65 else []}


def _safe_fact(fact: Fact | None) -> dict[str, Any] | None:
    if not fact:
        return None
    return {"value": "[redacted evidence text]", "message_id": fact.message_id,
            "start": fact.start, "end": fact.end}


def _safe_error(error: str | None) -> str | None:
    if not error:
        return None
    match = re.match(r"RuntimeError: Groq HTTP (\d+)", error)
    if match:
        return f"Groq HTTP {match.group(1)}"
    if "invalid semantic analyzer response" in error:
        return "Invalid semantic response (validation failed)"
    return error.split(":", 1)[0] + ": analyzer failed"


def _safe_state(state: DialogueState) -> dict[str, Any]:
    task = state.task_context
    def safe_values(items: list[Fact]) -> list[dict[str, Any]]:
        return [{**_safe_fact(fact), "value": "[redacted evidence text]"} for fact in items]
    return {
        "task_id": state.task_id, "revision": state.revision, "intent": state.intent,
        "operation": state.operation, "object": state.object, "relation": state.relation,
        "confidence": state.confidence, "analysis_required": state.analysis_required,
        "symptom": _safe_fact(task.symptom) if task else None,
        "entities": {slot: safe_values(facts) for slot, facts in (task.entities.items() if task else [])},
        "goals": safe_values(state.goals), "constraints": safe_values(state.constraints),
        "details": safe_values(state.details),
        "expected_clarification": ({"slot": state.expected.slot} if state.expected else None),
        "session_entity_slots": sorted(state.session.entities),
    }


def render(label: str, obs: Observation | None, previous: DialogueState,
           state: DialogueState, error: str | None) -> dict[str, Any]:
    return {"analyzer": label, "error": error, "observation": _observation_view(obs) if obs else None,
            "classification": _fact_classification(state, obs),
            "state_change": {"task_id_before": previous.task_id, "task_id_after": state.task_id,
                "previous_operation": previous.operation,
                "operation_after": state.operation,
                "previous_operation_preserved": previous.operation == state.operation,
                "task_changed": previous.task_id != state.task_id},
            "state_after": state_view(state)}


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.groq_api_key:
        print("GROQ_API_KEY is not configured; B cannot run.", file=sys.stderr)
        return 2
    manager_a = DialogueManager(LexicalAnalyzer())
    pending_b = _PendingObservationAnalyzer()
    manager_b = DialogueManager(pending_b)
    state_a = DialogueState()
    state_b = DialogueState()
    turns = 0
    session = 0
    call_count = 0
    output_path = Path(args.output) if args.output else None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    print("A/B dialogue analyzer stand. Commands: /new, /quit. A and B keep separate reducer states.")
    input_stream = Path(args.input_file).open("r", encoding="utf-8-sig") if args.input_file else None
    while True:
        try:
            line = (input_stream.readline().rstrip("\r\n") if input_stream else input("user> ")).strip()
            if input_stream and not line:
                break
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/new":
            session += 1
            turns = 0
            state_a, state_b = DialogueState(), DialogueState()
            print(f"--- new dialogue #{session}; both state histories reset ---")
            continue
        if line.startswith("/expect "):
            parts = line.split(maxsplit=2)
            slot = parts[1] if len(parts) > 1 else ""
            question = parts[2] if len(parts) > 2 else f"(simulated assistant clarification: {slot})"
            if slot not in {"service", "equipment", "manufacturer", "software", "ofd", "goal", "details", "task"}:
                print("Usage: /expect service|equipment|manufacturer|software|ofd|goal|details|task [question]")
                continue
            state_a = manager_a.observe_answer(state_a, scenario="clarify", reason=f"{slot}_not_confirmed",
                question=question, message_id=f"assistant:{session}:{turns}", slot=slot)
            state_b = manager_b.observe_answer(state_b, scenario="clarify", reason=f"{slot}_not_confirmed",
                question=question, message_id=f"assistant:{session}:{turns}", slot=slot)
            print(json.dumps({"event": "assistant_clarification", "slot": slot,
                              "A_expected": asdict(state_a.expected) if state_a.expected else None,
                              "B_expected": asdict(state_b.expected) if state_b.expected else None},
                             ensure_ascii=False, indent=2))
            continue

        turns += 1
        message_id = f"ab:{session}:{turns}"
        pre_a, pre_b = state_a, state_b
        err_a = err_b = None
        obs_a: Observation | None = None
        obs_b: Observation | None = None
        try:
            obs_a = manager_a.analyzer.analyze(line, message_id, pre_a)
            state_a = manager_a.advance(pre_a, line, message_id)
        except Exception as exc:  # preserve and report analyzer errors per variant
            err_a = f"{type(exc).__name__}: {exc}"
        tokens: dict[str, int | None] = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        try:
            if call_count and args.request_delay > 0:
                await asyncio.sleep(args.request_delay)
            call_count += 1
            obs_b, tokens = await groq_observation(line, message_id, pre_b, settings.groq_api_key)
            pending_b.current = (str(message_id), obs_b)
            state_b = manager_b.advance(pre_b, line, message_id)
        except Exception as exc:
            err_b = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, SemanticResponseError):
                tokens = exc.usage
        result = {"dialogue": session, "turn": turns, "message_id": message_id,
            "message_text": line, "A": render("LexicalAnalyzer", obs_a, pre_a, state_a, err_a),
            "B": render("Groq semantic", obs_b, pre_b, state_b, err_b), "B_tokens": tokens}
        print(json.dumps({"A": result["A"], "B": result["B"], "B_tokens": tokens},
                         ensure_ascii=False, indent=2))
        if output_path:
            safe_result = {"dialogue": session, "turn": turns,
                "A": {"error": _safe_error(err_a), "observation": _observation_view(obs_a) if obs_a else None,
                      "state_change": {"previous_operation": pre_a.operation,
                          "operation_after": state_a.operation,
                          "previous_operation_preserved": pre_a.operation == state_a.operation,
                          "task_changed": pre_a.task_id != state_a.task_id},
                      "state_after": _safe_state(state_a)},
                "B": {"error": _safe_error(err_b), "observation": _observation_view(obs_b) if obs_b else None,
                      "state_change": {"previous_operation": pre_b.operation,
                          "operation_after": state_b.operation,
                          "previous_operation_preserved": pre_b.operation == state_b.operation,
                          "task_changed": pre_b.task_id != state_b.task_id},
                      "state_after": _safe_state(state_b)}, "B_tokens": tokens}
            # Observation views contain exact spans, so remove span quotes before persistence.
            for variant in (safe_result["A"], safe_result["B"]):
                ob = variant.get("observation") or {}
                ob["evidence_spans"] = {k: ("[redacted]" if v else None)
                                        for k, v in ob.get("evidence_spans", {}).items()}
                if ob.get("symptom"):
                    ob["symptom"] = "[redacted evidence text]"
                for slot, vals in ob.get("service/equipment", {}).items():
                    for item in vals:
                        item["evidence"] = "[redacted]"
                        if slot == "equipment":
                            item["value"] = "[redacted evidence text]"
            with output_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(safe_result, ensure_ascii=False) + "\n")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/experiments/dialogue_analyzer_ab_2026-10-23.jsonl",
                        help="sanitized JSONL result file (default: docs/experiments/...jsonl)")
    parser.add_argument("--input-file", help="UTF-8 transcript with one user message/command per line")
    parser.add_argument("--request-delay", type=float, default=0,
                        help="seconds between Groq requests (useful under account rate limits)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
