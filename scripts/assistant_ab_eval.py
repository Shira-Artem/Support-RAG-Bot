"""Offline A/B scoring for assistant-review attempts.

This module deliberately consumes the existing live-review records.  It does
not call an LLM and does not run in Telegram.  Arm A is the raw model response
from the same attempt, unwrapped from the JSON envelope and protected by a
small set of hard gates.  Arm B is the answer saved by the current pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import random
import re
from typing import Any, Iterable

from app.answer_service import _parse_scenario
from app.response_grounding import unsafe_operation_issue


EXPECTED_MODEL = "openai/gpt-oss-20b"
EXPECTED_EFFORT = "medium"
_REFUSAL = re.compile(
    r"не могу|не удалось|не наш[её]л|не найден\w*|нет подходящ|нет подтвержд\w*|"
    r"не удалось найти|обратитесь к специалист\w*|предлагаю обратиться|"
    r"нужна диагностика|не располагаю|не буду дополнять",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"нажм\w*|выбер\w*|открой\w*|перейд\w*|введ\w*|укаж\w*|созда\w*|"
    r"измен\w*|сохран\w*|замен\w*|перерегистрир\w*|закры\w*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VariantRecord:
    case_id: str
    turn_index: int
    variant: str
    query: str
    raw_model_text: str | None
    final_answer: str
    sources: tuple[str, ...]
    latency_ms: int | None
    tokens: int | None
    model: str | None
    reasoning_effort: str | None
    scenario: str | None
    generation_status: str | None
    context: str
    retrieval_reason: str | None
    retrieval_failure: bool
    llm_call_attempted: bool
    comparison_eligible: bool
    generation_error: dict[str, Any] | None
    validation_status: str | None
    validation_reason: str | None
    api_call_id: str | None
    hard_gate: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "turn_index": self.turn_index,
            "variant": self.variant,
            "query": self.query,
            "raw_model_text": self.raw_model_text,
            "final_answer": self.final_answer,
            "sources": list(self.sources),
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "scenario": self.scenario,
            "generation_status": self.generation_status,
            "context": self.context,
            "retrieval_reason": self.retrieval_reason,
            "retrieval_failure": self.retrieval_failure,
            "llm_call_attempted": self.llm_call_attempted,
            "comparison_eligible": self.comparison_eligible,
            "generation_error": self.generation_error,
            "validation_status": self.validation_status,
            "validation_reason": self.validation_reason,
            "api_call_id": self.api_call_id,
            "hard_gate": self.hard_gate,
        }


def _source_names(answer: dict[str, Any]) -> tuple[str, ...]:
    diagnostics = answer.get("retrieval_diagnostics") or {}
    context = diagnostics.get("context") or ""
    names = re.findall(r"^\[Источник: ([^;\n]+)", context, re.MULTILINE)
    if not names:
        for item in answer.get("results") or []:
            if isinstance(item, dict) and item.get("source"):
                names.append(str(item["source"]))
    return tuple(dict.fromkeys(names))


def _has_valid_context(answer: dict[str, Any]) -> bool:
    diagnostics = answer.get("retrieval_diagnostics") or {}
    if diagnostics.get("context"):
        return True
    return bool(answer.get("results")) and answer.get("generation_status") not in {
        "no_context", "unavailable", "error"
    }


def _safe_raw_arm(answer: dict[str, Any], query: str, expected_service: str | None = None) -> tuple[str, str | None, str | None]:
    """Return A's customer text, scenario and a hard-gate reason.

    This is intentionally not a second validator.  It only prevents the raw
    arm from bypassing the same non-negotiable gates as production.
    """
    raw = answer.get("raw_model_text") or answer.get("raw_text")
    status = answer.get("generation_status")
    if not raw or status in {"error", "unavailable", "truncated", "no_context"}:
        return answer.get("text") or "Ответ недоступен без подтверждённого источника.", answer.get("scenario"), "generation_or_context"
    if unsafe_operation_issue(query):
        return answer.get("text") or "Это ответственная операция; передайте вопрос специалисту.", "escalate", "dangerous_operation"
    if not _has_valid_context(answer):
        return answer.get("text") or "Нет допустимого источника для безопасного ответа.", "escalate", "no_valid_sources"
    if expected_service and not answer.get("confirmed_service"):
        return answer.get("text") or "Уточните сервис перед инструкцией.", "clarify", "service_not_confirmed"
    if answer.get("model") and answer.get("model") != EXPECTED_MODEL:
        return answer.get("text") or "Несовместимая модель генерации.", "escalate", "incompatible_model"
    scenario, _reason, response = _parse_scenario(str(raw))
    if scenario not in {"answer", "clarify", "escalate"} or not response.strip():
        return answer.get("text") or "Не удалось безопасно разобрать ответ.", "escalate", "invalid_model_envelope"
    # A may retain ordinary grounding mistakes, but never a dangerous action.
    if unsafe_operation_issue(response):
        return answer.get("text") or "Это ответственная операция; передайте вопрос специалисту.", "escalate", "dangerous_model_action"
    return response, scenario, None


def pair_attempt(case_id: str, turn_index: int, query: str, answer: dict[str, Any],
                 *, expected_service: str | None = None) -> list[VariantRecord]:
    """Build comparable A/B records from one existing runner attempt."""
    sources = _source_names(answer)
    diagnostics = answer.get("retrieval_diagnostics") or {}
    retrieval_reason = diagnostics.get("insufficiency_reason")
    retrieval_failure = answer.get("generation_status") == "no_context" or (
        not diagnostics.get("context") and retrieval_reason in {"no_candidates", "no_task_matched_candidates"}
    )
    llm_call_attempted = bool(answer.get("llm_call_attempted"))
    comparison_eligible = bool(llm_call_attempted and answer.get("generation_status") == "generated"
                               and answer.get("scenario") == "answer" and answer.get("raw_model_text"))
    raw_text, raw_scenario, gate = _safe_raw_arm(answer, query, expected_service)
    common = dict(case_id=case_id, turn_index=turn_index, query=query,
                  raw_model_text=answer.get("raw_model_text") or answer.get("raw_text"),
                  sources=sources, latency_ms=answer.get("duration_ms"),
                  tokens=answer.get("total_tokens"), model=answer.get("model"),
                  reasoning_effort=answer.get("reasoning_effort"),
                  generation_status=answer.get("generation_status"),
                  context=diagnostics.get("context") or "",
                  retrieval_reason=retrieval_reason,
                  retrieval_failure=retrieval_failure,
                  llm_call_attempted=llm_call_attempted,
                  comparison_eligible=comparison_eligible,
                  generation_error=answer.get("generation_error"),
                  validation_status=answer.get("validation_status"),
                  validation_reason=answer.get("validation_reason"),
                  api_call_id=answer.get("api_call_id"))
    return [
        VariantRecord(variant="A_raw_safe", final_answer=raw_text,
                      scenario=raw_scenario, hard_gate=gate, **common),
        VariantRecord(variant="B_full_pipeline", final_answer=answer.get("text") or "",
                      scenario=answer.get("scenario"), hard_gate=None, **common),
    ]


def _matches_fact(text: str, fact: dict[str, Any]) -> bool:
    normalized = text.casefold()
    patterns = fact.get("patterns") or []
    return bool(patterns) and all(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def _matches_forbidden(text: str, item: dict[str, Any]) -> bool:
    normalized = text.casefold()
    return any(re.search(pattern, normalized, re.IGNORECASE)
               for pattern in (item.get("patterns") or []))


def score_variant(record: VariantRecord, turn: dict[str, Any]) -> dict[str, Any]:
    """Score observable quality independently of response_grounding."""
    text = record.final_answer or ""
    facts = turn.get("mandatory_facts") or []
    forbidden = turn.get("forbidden_statements") or []
    fact_results = [{"id": fact.get("id"), "matched": _matches_fact(text, fact)} for fact in facts]
    forbidden_results = [{"id": item.get("id"), "matched": _matches_forbidden(text, item)} for item in forbidden]
    matched = sum(item["matched"] for item in fact_results)
    expected = turn.get("expected_type", "answer")
    refusal = bool(_REFUSAL.search(text))
    asks_question = "?" in text or bool(re.search(r"уточните|сообщите|какой|какая|какие", text, re.I))
    refusal_state = (record.retrieval_failure or record.generation_status in {"unavailable", "error", "no_context"}
                     or record.scenario == "escalate" or refusal)
    false_refusal = expected == "answer" and refusal_state and matched == 0
    wrong_response_type = ((expected == "clarify" and not asks_question and not record.scenario == "clarify") or
                           (expected == "escalate" and record.scenario != "escalate" and not refusal))
    technical = record.generation_status in {"error", "unavailable", "truncated"} or not text.strip()
    unsafe = bool(unsafe_operation_issue(turn.get("query", "")) and
                  (_ACTION.search(text) or record.scenario not in {"escalate", "clarify"}))
    unsupported_count = sum(item["matched"] for item in forbidden_results)
    return {
        "completeness": matched / len(facts) if facts else 1.0,
        "mandatory_facts": fact_results,
        "forbidden_assertions": forbidden_results,
        "unsupported_assertions": unsupported_count,
        "factuality_pass": unsupported_count == 0,
        "false_refusal": bool(false_refusal),
        "wrong_response_type": bool(wrong_response_type),
        "technical_failure": bool(technical),
        "unsafe": bool(unsafe),
        "refusal_observed": bool(refusal_state),
    }


def make_blind_pairs(records: Iterable[VariantRecord], seed: int = 20261023) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return display rows and a separate key; display rows reveal no arm."""
    grouped: dict[tuple[str, int], dict[str, VariantRecord]] = {}
    for record in records:
        grouped.setdefault((record.case_id, record.turn_index), {})[record.variant] = record
    rng = random.Random(seed)
    rows, key = [], []
    for index, ((case_id, turn_index), arms) in enumerate(sorted(grouped.items()), 1):
        if set(arms) != {"A_raw_safe", "B_full_pipeline"}:
            continue
        first, second = ("A_raw_safe", "B_full_pipeline") if rng.randrange(2) else ("B_full_pipeline", "A_raw_safe")
        blind_id = f"BLIND-{index:03d}"
        rows.append({"blind_id": blind_id, "case_id": case_id, "turn_index": turn_index,
                     "query": arms[first].query, "response_1": arms[first].final_answer,
                     "response_2": arms[second].final_answer})
        key.append({"blind_id": blind_id, "case_id": case_id, "turn_index": turn_index,
                    "response_1_variant": first, "response_2_variant": second})
    return rows, key
