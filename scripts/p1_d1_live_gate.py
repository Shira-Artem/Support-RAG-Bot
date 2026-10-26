"""Explicitly opt-in, bounded Groq + read-only Qdrant D1 live gate.

This script never imports bot.py and always uses a disposable SQLite database.
Run with --execute only after reviewing the gate protocol.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai_coordinator import coordinate
from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.embeddings import SentenceTransformerEmbedding
from app.retrieval import Retriever
from app.source_first_service import SourceFirstService
from app.vector_store import QdrantStore
from app.compat import RetrieverRAGAdapter
from qdrant_client import QdrantClient


QUESTIONS = ("Что такое ОФД?", "А зачем он нужен кассе?")
MAX_GROQ_CALLS = 2
DEFAULT_TRACE = ROOT / "experiments/architecture_recovery_audit/p1_d1_live_trace_20261026.json"


class GateBlocked(RuntimeError):
    def __init__(self, code: str, error_type: str | None = None):
        super().__init__(code)
        self.code = code
        self.error_type = error_type


class ReadOnlyQdrantClient:
    """Expose only the Qdrant calls needed by the retrieval pipeline.

    In particular, QdrantStore's legacy create-on-missing behavior cannot
    reach the wrapped client, even if the collection disappears after preflight.
    """

    def __init__(self, client: QdrantClient):
        self.__client = client

    def collection_exists(self, collection: str):
        return self.__client.collection_exists(collection)

    def get_collection(self, collection: str):
        return self.__client.get_collection(collection)

    def scroll(self, collection: str, **kwargs):
        return self.__client.scroll(collection, **kwargs)

    def query_points(self, collection: str, **kwargs):
        return self.__client.query_points(collection, **kwargs)


def _preflight(settings) -> list[str]:
    issues = []
    if settings.llm_provider != "groq":
        issues.append("LLM_PROVIDER must be groq")
    if not settings.groq_api_key:
        issues.append("GROQ_API_KEY is not configured")
    if settings.rag_engine != "source_first":
        issues.append("RAG_ENGINE must be source_first")
    if not settings.ai_coordinator_enabled:
        issues.append("AI_COORDINATOR_ENABLED must be true for this opt-in gate")
    if os.getenv("RAG_BACKEND", "qdrant").strip().lower() != "qdrant":
        issues.append("RAG_BACKEND must be qdrant")
    if os.getenv("RAG_DEMO_MODE", "0").strip().lower() in {"1", "true", "yes"}:
        issues.append("RAG_DEMO_MODE must be disabled so only approved evidence is retrieved")
    return issues


async def _run(settings) -> dict:
    # Mirror the bot's refusal to construct a missing/empty collection. Never
    # let QdrantStore's legacy constructor create a collection during this gate.
    qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    collection = os.getenv("QDRANT_COLLECTION")
    if not collection:
        raise GateBlocked("qdrant_collection_not_configured")
    try:
        exists = qdrant.collection_exists(collection)
        points_count = (qdrant.get_collection(collection).points_count or 0) if exists else 0
    except Exception as exc:
        raise GateBlocked("qdrant_read_only_preflight_failed", type(exc).__name__) from exc
    if not exists:
        raise GateBlocked("qdrant_collection_missing")
    if not points_count:
        raise GateBlocked("qdrant_collection_empty")
    embedding_name = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    # The gate is bounded to Groq and Qdrant; local embeddings must not trigger
    # an incidental Hugging Face Hub download or metadata request.
    os.environ["HF_HUB_OFFLINE"] = "1"
    embedding = SentenceTransformerEmbedding(embedding_name)
    # The wrapper permits only read methods. QdrantStore's constructor can
    # create a missing collection, but that call is intentionally unavailable.
    read_only_client = ReadOnlyQdrantClient(qdrant)
    store = QdrantStore(read_only_client, embedding, collection)
    rag = RetrieverRAGAdapter(Retriever(store, demo=False))
    service = SourceFirstService(rag, settings, settings.docs_dir.parent.parent)
    turns = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    calls = 0
    retrieval_turns = 0

    with tempfile.TemporaryDirectory(prefix="support-rag-p1-live-") as temp_dir:
        store = ConversationStore(Path(temp_dir) / "gate.sqlite3")
        conversation_id = store.new(1, 1)
        for text in QUESTIONS:
            if calls >= MAX_GROQ_CALLS:
                raise RuntimeError("Hard Groq call budget exhausted")
            before = store.dialogue_state(conversation_id)
            history = store.history(conversation_id)
            calls += 1  # understand_message has exactly one HTTP attempt and no retry loop.
            try:
                understanding = await understand_message(text, "current", history, before, settings)
            except UnderstandingError as exc:
                turns.append({"user_text": text, "status": "understanding_failed",
                              "error_code": exc.code, "http_status": exc.http_status})
                break
            for key in usage:
                value = (understanding.tokens or {}).get(key)
                if isinstance(value, int):
                    usage[key] += value
            message_id = store.begin(conversation_id, text, semantic_mode=True,
                                     understanding=understanding_to_dict(understanding))
            state = store.dialogue_state(conversation_id)
            event = next((item for item in reversed(store.history(conversation_id))
                          if item.get("role") == "user" and item.get("content") == text), {})
            decision = coordinate(event.get("understanding"), state)
            if decision.route != "grounded_information":
                turns.append({
                    "user_text": text,
                    "understanding_raw": understanding.structured_response,
                    "understanding_validated": understanding_to_dict(understanding),
                    "request_type": decision.request_type,
                    "route": decision.route,
                    "task_relation": decision.task_relation,
                    "current_subgoal": decision.current_subgoal,
                    "required_action": decision.required_action,
                    "rationale": decision.rationale,
                    "state_before": before.to_dict(),
                    "state_after_understanding": state.to_dict(),
                    "status": "stopped_route_outside_grounded_information",
                })
                break
            retrieval_turns += 1
            if retrieval_turns > 2:
                raise RuntimeError("Hard hybrid-retrieval-turn budget exhausted")
            answer_started_at = datetime.now(timezone.utc).isoformat()
            answer = await service.answer(text, state=state,
                history=store.history(conversation_id), coordinator_decision=decision)
            store.complete(message_id, answer)
            turns.append({
                "user_text": text,
                "request_type": decision.request_type,
                "route": decision.route,
                "task_relation": decision.task_relation,
                "current_subgoal": decision.current_subgoal,
                "required_action": decision.required_action,
                "rationale": decision.rationale,
                "understanding_raw": understanding.structured_response,
                "understanding_validated": understanding_to_dict(understanding),
                "state_before": before.to_dict(),
                "latency_ms": {
                    "understanding": understanding.duration_ms,
                    "answer_pipeline": answer.duration_ms,
                },
                "answer_started_at_utc": answer_started_at,
                "assistant_text": answer.text,
                "scenario": answer.scenario,
                "scenario_reason": answer.scenario_reason,
                "validation_status": answer.validation_status,
                "llm_call_attempted_after_understanding": answer.llm_call_attempted,
                "coordinator_evidence": (answer.retrieval_diagnostics or {}).get("coordinator_evidence"),
                "retrieval_diagnostics": answer.retrieval_diagnostics,
                "qdrant_candidates": [
                    {key: candidate.get(key) for key in
                     ("source", "document_id", "status", "metadata", "retrieval", "relevance", "reasons", "selected")}
                    for candidate in (answer.retrieval_diagnostics or {}).get("candidates", [])
                ],
                "safety": {
                    "validation_status": answer.validation_status,
                    "source_sha256_verified": bool((answer.retrieval_diagnostics or {})
                        .get("coordinator_evidence", {}).get("source_sha256_verified")),
                    "post_understanding_llm_call": answer.llm_call_attempted,
                    "approved_evidence_required": True,
                },
                "state_after_reopen": ConversationStore(Path(temp_dir) / "gate.sqlite3")
                    .dialogue_state(conversation_id).to_dict(),
            })

    useful = len(turns) == 2 and all(item.get("scenario") == "answer" for item in turns)
    distinct = useful and turns[0]["assistant_text"] != turns[1]["assistant_text"]
    safe = useful and all(
        item.get("validation_status") == "exact_approved_sentence"
        and item.get("coordinator_evidence", {}).get("source_sha256_verified") is True
        and not item.get("llm_call_attempted_after_understanding")
        for item in turns
    )
    return {
        "gate": "D1.2-D1.3 coordinator live gate",
        "provider": settings.llm_provider,
        "model": settings.groq_model,
        "qdrant_collection": collection,
        "qdrant_points_at_preflight": points_count,
        "qdrant_client_mode": "read_only_facade",
        "groq_calls": calls,
        "groq_call_limit": MAX_GROQ_CALLS,
        "hybrid_retrieval_turns": retrieval_turns,
        "hybrid_retrieval_turn_limit": 2,
        "composer_planner_calls": 0,
        "usage": usage,
        "turns": turns,
        "useful_answers_distinct": bool(distinct),
        "independent_safety_checks_passed": bool(safe),
        "gate_result": "PASS" if distinct and safe else "NO-GO",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="perform the explicitly bounded two-call Groq/Qdrant gate")
    parser.add_argument("--output", type=Path, default=DEFAULT_TRACE,
                        help="path for the sanitized JSON experiment trace")
    args = parser.parse_args()
    settings = get_settings()
    issues = _preflight(settings)
    if not args.execute:
        print(json.dumps({"mode": "preflight_only", "will_make_network_calls": False,
                          "configured": not issues, "issues": issues,
                          "groq_call_limit": MAX_GROQ_CALLS,
                          "questions": list(QUESTIONS)}, ensure_ascii=True, indent=2))
        return 0 if not issues else 2
    if issues:
        print(json.dumps({"gate_result": "BLOCKED", "issues": issues}, ensure_ascii=True, indent=2))
        return 2
    try:
        result = asyncio.run(_run(settings))
    except GateBlocked as exc:
        result = {
            "gate": "D1.2-D1.3 coordinator live gate",
            "gate_result": "BLOCKED",
            "blocked_at": "read_only_qdrant_collection_preflight",
            "failure_code": exc.code,
            "failure_type": exc.error_type,
            "qdrant_collection": os.getenv("QDRANT_COLLECTION"),
            "groq_calls": 0,
            "groq_call_limit": MAX_GROQ_CALLS,
            "hybrid_retrieval_turns": 0,
            "hybrid_retrieval_turn_limit": 2,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "turns": [],
            "raw_validated_understanding": "unavailable: stopped before Groq request",
            "chosen_evidence": "unavailable: stopped before Qdrant retrieval",
            "qdrant_writes": 0,
        }
    result["trace_created_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["trace_path"] = str(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
