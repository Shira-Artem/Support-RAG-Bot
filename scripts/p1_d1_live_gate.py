"""Explicitly opt-in, bounded Groq + read-only Qdrant D1 live gate.

This script never imports bot.py and always uses a disposable SQLite database.
Run with --execute only after reviewing the gate protocol.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai_coordinator import coordinate
from app.compat import build_answer_rag
from app.config import get_settings
from app.conversation_store import ConversationStore
from app.dialogue_understanding import UnderstandingError, understand_message, understanding_to_dict
from app.source_first_service import SourceFirstService
from qdrant_client import QdrantClient


QUESTIONS = ("Что такое ОФД?", "А зачем он нужен кассе?")
MAX_GROQ_CALLS = 2
MAX_COMPLETION_TOKENS_PER_CALL = 4096  # Existing Understanding request cap.


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
    return issues


async def _run(settings) -> dict:
    # Mirror the bot's refusal to construct a missing/empty collection. Never
    # let QdrantStore's legacy constructor create a collection during this gate.
    qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    collection = os.getenv("QDRANT_COLLECTION", "knowledge_v1")
    if not qdrant.collection_exists(collection):
        raise RuntimeError("Configured Qdrant collection is missing; gate stopped before retrieval")
    if not (qdrant.get_collection(collection).points_count or 0):
        raise RuntimeError("Configured Qdrant collection is empty; gate stopped before retrieval")
    rag = build_answer_rag(settings.docs_dir)
    service = SourceFirstService(rag, settings, settings.docs_dir.parent.parent)
    turns = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    calls = 0

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
                "assistant_text": answer.text,
                "scenario": answer.scenario,
                "scenario_reason": answer.scenario_reason,
                "validation_status": answer.validation_status,
                "llm_call_attempted_after_understanding": answer.llm_call_attempted,
                "coordinator_evidence": (answer.retrieval_diagnostics or {}).get("coordinator_evidence"),
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
        "groq_calls": calls,
        "groq_call_limit": MAX_GROQ_CALLS,
        "hybrid_retrieval_turns": sum(bool(item.get("coordinator_evidence")) for item in turns),
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
    args = parser.parse_args()
    settings = get_settings()
    issues = _preflight(settings)
    if not args.execute:
        print(json.dumps({"mode": "preflight_only", "will_make_network_calls": False,
                          "configured": not issues, "issues": issues,
                          "groq_call_limit": MAX_GROQ_CALLS,
                          "questions": list(QUESTIONS)}, ensure_ascii=False, indent=2))
        return 0 if not issues else 2
    if issues:
        print(json.dumps({"gate_result": "BLOCKED", "issues": issues}, ensure_ascii=False, indent=2))
        return 2
    result = asyncio.run(_run(settings))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
