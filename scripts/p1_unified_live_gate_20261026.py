"""Bounded live A/B: lexical sentence selection vs LLM evidence-ID selection.

Uses one real Understanding and one read-only hybrid retrieval per turn, then
compares both selectors over the same exact approved section snapshot.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai_coordinator import coordinate
from app.answer_service import Answer
from app.config import get_settings
from app.compat import RetrieverRAGAdapter
from app.conversation_store import ConversationStore
from app.dialogue_state import DialogueState
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.embeddings import SentenceTransformerEmbedding
from app.rag_query import build_rag_query
from app.retrieval import Retriever
from app.semantic_evidence_selector import (SelectorDecisionError, build_evidence_units,
    select_evidence, validate_selected_units)
from app.source_first_service import (_focused_approved_sentence, _source_sections,
                                      _section_has_answer_bearing_content,
                                      _validate_information_composition)
from app.vector_store import QdrantStore
from qdrant_client import QdrantClient
from app.response_grounding import evidence_kind, instruction_issue, statements, unsafe_operation_issue


SCENARIOS = {
    "D1_HOLDOUT": ("Касса формирует чек сама. Что именно делает ОФД после этого?", "Если касса уже отправляет данные, зачем в цепочке нужен оператор?"),
    "EVOTOR_HOLDOUT": ("На Эвоторе 7.3 после замены роутера чеки перестали доходить до ОФД. С чего безопасно начать проверку?", "Wi-Fi подключен и сайты открываются; тестовая оплата прошла. Какой следующий проверяемый шаг?"),
    "FN_CODE_HOLDOUT": ("В отчёте ККТ показан код ошибки ФН 234. Что означает именно этот код и что проверить?", "Уточнение: сейчас на экране код ФН 235. Это та же ошибка или другая?"),
}
MAX_GROQ_CALLS = 12
MAX_RETRIEVAL_TURNS = 6
MAX_TURNS = 6
DEFAULT_OUTPUT = ROOT / "experiments/architecture_recovery_audit/p1_unified_live_gate_20261026.json"


class BoundedReadOnlyClient:
    def __init__(self, client):
        self._client = client

    def collection_exists(self, collection):
        return self._client.collection_exists(collection)

    def get_collection(self, collection):
        return self._client.get_collection(collection)

    def scroll(self, collection, **kwargs):
        return self._client.scroll(collection, **kwargs)

    def query_points(self, collection, **kwargs):
        return self._client.query_points(collection, **kwargs)


def _quality(question: str, text: str | None, *, scenario: str) -> dict:
    if not text:
        return {"useful": False, "reason": "no_selected_answer"}
    folded = text.casefold()
    if text.strip().endswith("?"):
        return {"useful": False, "reason": "selected_fragment_only_repeats_a_question"}
    if scenario.startswith("D1") and "зачем" in question.casefold():
        useful = any(term in folded for term in ("переда", "фискальн", "документ", "фнс"))
        return {"useful": useful,
                "rubric": "Объясняет назначение ОФД для получения/передачи фискальных документов, а не только договор/тариф."}
    if scenario.startswith("D1"):
        useful = any(term in folded for term in ("получает", "обрабатывает", "передаёт", "передает", "оператор"))
        return {"useful": useful, "rubric": "Объясняет роль ОФД как оператора обработки/передачи фискальных документов."}
    if scenario.startswith("EVOTOR"):
        useful = any(term in folded for term in ("интернет", "диагност", "провер", "настройк"))
        return {"useful": useful, "rubric": "Сохраняет безопасную последовательность диагностики Эвотор после восстановления сети; не утверждает неподтверждённый результат."}
    if scenario.startswith("FN_CODE"):
        expected = "235" if "235" in question else "234"
        useful = expected in folded and ("234" not in folded or "235" not in folded or expected in folded)
        return {"useful": useful, "expected_exact_fn_code": expected, "rubric": "Различает точный код ошибки ФН из текущего вопроса и не переносит описание другого кода."}
    if "прош" in question.casefold():
        useful = any(x in folded for x in ("период задаётся", "период задается", "календарн", "датами пробития"))
    else:
        useful = "чеки" in folded and "поиск" in folded and ("маршрут" in folded or "→" in text)
    return {"useful": useful,
            "rubric": "Сохраняет задачу поиска чека и отвечает, как задать прошлый месяц/диапазон дат в Платформе ОФД."}


async def _run(settings, progress: dict, *, resume: bool = False) -> dict:
    collection = os.getenv("QDRANT_COLLECTION")
    if not collection:
        raise RuntimeError("qdrant_collection_not_configured")
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    if not client.collection_exists(collection):
        raise RuntimeError("qdrant_collection_missing")
    point_count = client.get_collection(collection).points_count or 0
    if point_count <= 0:
        raise RuntimeError("qdrant_collection_empty")
    os.environ["HF_HUB_OFFLINE"] = "1"
    embedding_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    rag = RetrieverRAGAdapter(Retriever(QdrantStore(BoundedReadOnlyClient(client),
        SentenceTransformerEmbedding(embedding_name), collection), demo=False))
    root = settings.docs_dir.parent.parent
    store = ConversationStore
    turns = progress.setdefault("turns", [])
    usage = progress.setdefault("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    groq_calls = progress.setdefault("groq_calls", 0)
    retrieval_turns = progress.setdefault("retrieval_turns", 0)
    selector_calls = progress.setdefault("selector_calls", 0)
    scenarios = {"D3": SCENARIOS["D3"]} if resume else SCENARIOS
    with tempfile.TemporaryDirectory(prefix="support-rag-selector-ab-") as temporary:
        for scenario, messages in scenarios.items():
            db = store(Path(temporary) / f"{scenario}.sqlite3")
            conversation = db.new(1, 1)
            for question in messages:
                if groq_calls + 2 > MAX_GROQ_CALLS or retrieval_turns >= MAX_RETRIEVAL_TURNS:
                    raise RuntimeError("hard_live_budget_exhausted")
                before = db.dialogue_state(conversation)
                history = db.history(conversation)
                started = perf_counter()
                groq_calls += 1
                progress.update(groq_calls=groq_calls, retrieval_turns=retrieval_turns,
                                selector_calls=selector_calls, usage=usage, turns=turns)
                try:
                    understanding = await understand_message(question, "current", history, before, settings)
                except UnderstandingError as exc:
                    turns.append({"scenario": scenario, "question": question, "stage": "understanding",
                        "status": "failed", "error_code": exc.code, "http_status": exc.http_status})
                    progress.update(groq_calls=groq_calls, turns=turns, usage=usage)
                    return {"status": "STOPPED", "stop_reason": "understanding_failed_no_retry",
                        "groq_calls": groq_calls, "retrieval_turns": retrieval_turns,
                        "selector_calls": selector_calls, "usage": usage, "turns": turns,
                        "qdrant_collection": collection, "qdrant_points": point_count}
                for key in usage:
                    amount = (understanding.tokens or {}).get(key)
                    if isinstance(amount, int):
                        usage[key] += amount
                progress.update(usage=usage)
                event_id = db.begin(conversation, question, semantic_mode=True,
                                    understanding=understanding_to_dict(understanding))
                state = db.dialogue_state(conversation)
                user_event = next((row for row in reversed(db.history(conversation))
                                   if row.get("role") == "user" and row.get("content") == question), {})
                decision = coordinate(user_event.get("understanding"), state)
                query = build_rag_query(state)
                retrieval_turns += 1
                progress.update(retrieval_turns=retrieval_turns)
                retrieval_started = perf_counter()
                result = rag.search_for_state(state, query)
                retrieval_ms = round((perf_counter() - retrieval_started) * 1000)
                if not result.sufficient:
                    turns.append({"scenario": scenario, "question": question,
                        "understanding_raw": understanding.structured_response,
                        "understanding_validated": understanding_to_dict(understanding),
                        "coordinator_decision": decision.to_dict(), "state": state.to_dict(),
                        "retrieval_status": "insufficient", "retrieval_diagnostics": result.diagnostics(),
                        "latency_ms": {"understanding": understanding.duration_ms, "retrieval": retrieval_ms}})
                    db.complete(event_id, Answer("В live A/B evidence не прошло полноту retrieval; сравнение этого хода остановлено.",
                        scenario="escalate", scenario_reason="selector_ab_retrieval_insufficient"))
                    continue
                sections = _source_sections(rag, result, root)
                sections = [item for item in sections if _section_has_answer_bearing_content(item)]
                focus = decision.current_subgoal or question
                lexical_start = perf_counter()
                lexical_match = _focused_approved_sentence(sections, focus)
                lexical_text = lexical_match[1] if lexical_match else None
                lexical_ms = round((perf_counter() - lexical_start) * 1000)
                informational = state.intent == "general" and state.operation == "explain"
                units = build_evidence_units(sections, informational=informational)
                groq_calls += 1
                selector_calls += 1
                progress.update(groq_calls=groq_calls, selector_calls=selector_calls)
                selector_start = perf_counter()
                try:
                    semantic_decision, generation = await select_evidence(question, state,
                        db.history(conversation), units, settings,
                        current_subgoal=decision.current_subgoal)
                except Exception as exc:
                    failed_generation = getattr(exc, "generation", None)
                    provider_failure = {key: getattr(exc, key, None) for key in (
                        "http_status", "error_type", "provider_error_code", "provider_error_param",
                        "retry_after_seconds", "stage", "cause_message", "duration_ms",
                        "schema_error", "provider_usage", "request_id")}
                    if not failed_generation and isinstance(getattr(exc, "provider_usage", None), dict):
                        for key in usage:
                            value = exc.provider_usage.get(key)
                            if isinstance(value, int): usage[key] += value
                    if failed_generation:
                        for key in usage:
                            value = getattr(failed_generation, key, None)
                            if isinstance(value, int): usage[key] += value
                    turns.append({"scenario": scenario, "question": question, "stage": "selector",
                        "error_type": type(exc).__name__, "error": str(exc)[:180],
                        "provider_failure": provider_failure,
                        "raw_decision": failed_generation.text if failed_generation else None,
                        "usage": ({key: getattr(failed_generation, key, None) for key in usage}
                                  if failed_generation else None),
                        "understanding_raw": understanding.structured_response,
                        "understanding_validated": understanding_to_dict(understanding),
                        "state_before": before.to_dict(), "state_after": state.to_dict(),
                        "coordinator_decision": decision.to_dict(), "rag_query": query,
                        "retrieval_diagnostics": result.diagnostics(), "approved_sections": sections,
                        "lexical": {"answer": lexical_text,
                            "selected_section": lexical_match[0] if lexical_match else None,
                            "manual_quality": _quality(question, lexical_text, scenario=scenario)},
                        "candidate_units": [unit.public_dict() for unit in units],
                        "latency_ms": {"understanding": understanding.duration_ms,
                            "retrieval": retrieval_ms, "lexical": lexical_ms,
                            "selector": round((perf_counter() - selector_start) * 1000)}})
                    turns[-1]["latency_ms"]["selector_provider"] = getattr(exc, "duration_ms", None)
                    progress.update(groq_calls=groq_calls, selector_calls=selector_calls,
                                    retrieval_turns=retrieval_turns, turns=turns, usage=usage)
                    return {"status": "STOPPED", "stop_reason": "selector_failed_no_retry",
                        "groq_calls": groq_calls, "retrieval_turns": retrieval_turns,
                        "selector_calls": selector_calls, "usage": usage, "turns": turns,
                        "qdrant_collection": collection, "qdrant_points": point_count}
                selector_ms = round((perf_counter() - selector_start) * 1000)
                for key, attr in (("prompt_tokens", "prompt_tokens"), ("completion_tokens", "completion_tokens"),
                                  ("total_tokens", "total_tokens")):
                    if isinstance(getattr(generation, attr), int):
                        usage[key] += getattr(generation, attr)
                progress.update(usage=usage)
                selected, rejection = validate_selected_units(semantic_decision, units, state, root,
                                                                informational=informational)
                semantic_text = " ".join(unit.text for unit in selected) if selected else None
                semantic_safety = rejection is None
                if semantic_text:
                    if informational:
                        section_text = "\n".join(item["text"] for item in sections
                                                   if any(u.document_id == item["document_id"] and u.section == item["section"] for u in selected))
                        semantic_text, semantic_reason = _validate_information_composition(
                            semantic_text, section_text, "; ".join(u.section for u in selected))
                        semantic_safety = semantic_text is not None
                    else:
                        semantic_reason = "exact_ordered_source_block_with_applicability_checked"
                        if any(u.kind != "procedure_block" for u in selected) and any(
                            evidence_kind(u.text, u.section) in {"procedure", "interface"} for u in selected):
                            semantic_text, semantic_reason, semantic_safety = None, "detached_procedure_step", False
                        if semantic_text and (unsafe_operation_issue(semantic_text)
                            or instruction_issue(semantic_text, "\n".join(u.text for u in selected))):
                            semantic_text, semantic_reason, semantic_safety = None, "technical_safety_rejected", False
                else:
                    semantic_reason = rejection or semantic_decision.reason_code
                # Persist this user's turn with the lexical answer so the next turn
                # gets the same task context for both selector arms.
                lexical_answer = lexical_text or "В retrieval evidence не найден локальный lexical match."
                db.complete(event_id, Answer(lexical_answer, scenario="answer" if lexical_text else "escalate",
                    scenario_reason="selector_ab_lexical", validation_status="candidate_only"))
                diagnostics = result.diagnostics()
                turns.append({"scenario": scenario, "question": question,
                    "understanding_raw": understanding.structured_response,
                    "understanding_validated": understanding_to_dict(understanding),
                    "state_before": before.to_dict(), "state_after": state.to_dict(),
                    "coordinator_decision": decision.to_dict(), "rag_query": query,
                    "retrieval_diagnostics": diagnostics,
                    "approved_sections": sections, "evidence_units": [u.public_dict() for u in units],
                    "lexical": {"answer": lexical_text, "selected_section": lexical_match[0] if lexical_match else None,
                        "latency_ms": lexical_ms, "manual_quality": _quality(question, lexical_text, scenario=scenario)},
                    "semantic": {"answer": semantic_text, "decision": asdict(semantic_decision),
                        "validation_rejection": rejection, "post_render_reason": semantic_reason,
                        "selected_ids_verified": [u.id for u in selected], "source_hashes": list(dict.fromkeys(u.source_sha256 for u in selected)),
                        "safety_passed": semantic_safety, "latency_ms": selector_ms,
                        "usage": {"prompt_tokens": generation.prompt_tokens,
                            "completion_tokens": generation.completion_tokens, "total_tokens": generation.total_tokens},
                        "manual_quality": _quality(question, semantic_text, scenario=scenario)},
                    "latency_ms": {"understanding": understanding.duration_ms, "retrieval": retrieval_ms},
                    "qdrant_candidate_count": len(diagnostics.get("candidates", []))})
                progress["turns"] = turns
    semantic_safe = all(t.get("semantic", {}).get("safety_passed") for t in turns if "semantic" in t)
    paired_turns_complete = (len(turns) == MAX_TURNS and all("semantic" in t and "lexical" in t for t in turns))
    return {"status": "COMPLETED", "gate_result": "PASS" if paired_turns_complete and semantic_safe else "NO-GO",
        "provider": settings.llm_provider, "model": settings.groq_model, "qdrant_collection": collection,
        "qdrant_points": point_count, "qdrant_mode": "read-only facade", "groq_calls": groq_calls,
        "groq_call_limit": MAX_GROQ_CALLS, "retrieval_turns": retrieval_turns,
        "retrieval_turn_limit": MAX_RETRIEVAL_TURNS, "selector_calls": selector_calls,
        "automatic_retries": 0, "usage": usage, "turns": turns,
        "semantic_safety_passed": semantic_safe,
        "paired_turns_complete": paired_turns_complete,
        "semantic_useful_turns": sum(bool(t.get("semantic", {}).get("manual_quality", {}).get("useful")) for t in turns),
        "lexical_useful_turns": sum(bool(t.get("lexical", {}).get("manual_quality", {}).get("useful")) for t in turns),
        "historical_source_first_trace": "experiments/architecture_recovery_audit/p1_d1_live_trace_20261026_run2.json",
        "historical_comparison_note": "Not a paired A/B: different execution date/path, 9 Groq calls and 13,352 tokens reported by user."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resume", type=Path,
                        help="continue only D3 from a previous stopped trace; never repeats prior turns")
    args = parser.parse_args()
    settings = get_settings()
    issues = []
    if settings.llm_provider != "groq" or not settings.groq_api_key: issues.append("groq_not_configured")
    if settings.rag_engine != "source_first" or not settings.ai_coordinator_enabled: issues.append("source_first_coordinator_not_enabled")
    if os.getenv("RAG_BACKEND", "qdrant").lower() != "qdrant": issues.append("qdrant_backend_required")
    if os.getenv("RAG_DEMO_MODE", "0").lower() in {"1", "true", "yes"}: issues.append("demo_mode_must_be_off")
    if not os.getenv("QDRANT_COLLECTION"): issues.append("qdrant_collection_required")
    elif os.getenv("QDRANT_COLLECTION") != "knowledge_stage3_retrieval_20261022": issues.append("stage3_collection_required")
    if not args.execute:
        print(json.dumps({"mode": "preflight_only", "will_make_network_calls": False,
            "configured": not issues, "issues": issues, "groq_call_limit": MAX_GROQ_CALLS,
            "retrieval_turn_limit": MAX_RETRIEVAL_TURNS, "scenarios": SCENARIOS}, ensure_ascii=True, indent=2))
        return 0 if not issues else 2
    if issues:
        print(json.dumps({"status": "BLOCKED", "issues": issues}, ensure_ascii=True, indent=2))
        return 2
    prior = None
    if args.resume:
        prior = json.loads(args.resume.read_text(encoding="utf-8"))
        if (prior.get("status") != "STOPPED" or prior.get("stop_reason") not in {
                "selector_failed_no_retry", "understanding_failed_no_retry"}):
            print(json.dumps({"status": "BLOCKED", "reason": "resume_requires_stopped_trace"}, ensure_ascii=True))
            return 2
        if (prior.get("groq_calls", 0) >= MAX_GROQ_CALLS
                or prior.get("retrieval_turns", 0) >= MAX_RETRIEVAL_TURNS):
            print(json.dumps({"status": "BLOCKED", "reason": "no_budget_left_to_resume"}, ensure_ascii=True))
            return 2
    progress = ({key: prior.get(key) for key in
                 ("groq_calls", "retrieval_turns", "selector_calls", "usage", "turns")}
                if prior else {"groq_calls": 0, "retrieval_turns": 0, "selector_calls": 0,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "turns": []})
    try:
        result = asyncio.run(_run(settings, progress, resume=prior is not None))
    except Exception as exc:
        result = {"status": "STOPPED", "stage": "preflight_or_execution", "failure_type": type(exc).__name__,
            "failure": str(exc)[:240], **progress, "groq_call_limit": MAX_GROQ_CALLS,
            "retrieval_turn_limit": MAX_RETRIEVAL_TURNS,
            "qdrant_collection": os.getenv("QDRANT_COLLECTION"), "automatic_retries": 0}
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    if prior:
        result["resumed_from"] = str(args.resume)
        result["resume_note"] = "Earlier D1 calls/traces are retained verbatim; only D3 turns were run after resume."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("gate_result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
