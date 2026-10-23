"""Replay the same sequences through current production algorithm on isolated SQLite.

Only reads Stage3 Qdrant. No Telegram, worker, production SQLite, or index writes.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from qdrant_client import QdrantClient, models

import app.answer_service as answer_service
from app.compat import build_answer_rag
from app.config import get_settings
from app.conversation_store import ConversationStore

COLLECTION = "knowledge_stage3_retrieval_20261022"


async def run(args) -> None:
    env = dotenv_values(ROOT / ".env")
    os.environ["QDRANT_COLLECTION"] = COLLECTION  # this process only
    os.environ["RAG_DEMO_MODE"] = "0"
    url = os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333"
    client = QdrantClient(url=url, timeout=15)
    info = client.get_collection(COLLECTION)
    approved = client.count(COLLECTION, count_filter=models.Filter(must=[models.FieldCondition(
        key="status", match=models.MatchValue(value="approved"))]), exact=True).count
    if info.points_count != 934 or approved != 672:
        raise RuntimeError("Stage3 receipt differs")
    settings = get_settings()
    if (settings.llm_provider, settings.groq_model, settings.groq_reasoning_effort) != (
            "groq", "openai/gpt-oss-20b", "medium"):
        raise RuntimeError("Model configuration differs")
    service = answer_service.AnswerService(build_answer_rag(settings.docs_dir), settings)
    if service.rag.retriever.store.collection != COLLECTION or service.rag.retriever.demo:
        raise RuntimeError("Baseline retriever is not approved-only Stage3")
    db = args.sqlite.resolve()
    if db == (ROOT / "data" / "conversations.sqlite3").resolve():
        raise RuntimeError("Refusing production SQLite")
    if db.exists():
        raise FileExistsError(f"Isolated baseline DB already exists: {db}")
    db.parent.mkdir(parents=True, exist_ok=True)
    conversation_store = ConversationStore(db)
    original_generate = answer_service.generate
    calls = 0
    last_call_at = 0.0
    recent: list[tuple[float, int]] = []

    async def paced_generate(messages, configured_settings):
        nonlocal calls, last_call_at
        if calls >= args.max_groq_calls:
            raise RuntimeError("Baseline Groq call cap reached")
        estimate = min(5500, sum(len(m.get("content", "")) for m in messages)//3 + 512)
        while True:
            now = time.monotonic()
            recent[:] = [(t,n) for t,n in recent if now-t < 66]
            pause = max(0, 18.0 - (now-last_call_at))
            if recent and sum(n for _,n in recent) + estimate > 6000:
                pause = max(pause, 66 - (now-recent[0][0]))
            if pause <= 0:
                break
            await asyncio.sleep(min(pause, 20))
        calls += 1
        last_call_at = time.monotonic()
        answer = await original_generate(messages, configured_settings)
        recent.append((time.monotonic(), answer.total_tokens or estimate))
        return answer

    answer_service.generate = paced_generate
    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    results = {"config": {"collection": COLLECTION, "points": info.points_count,
                           "approved_points": approved, "model": settings.groq_model,
                           "reasoning_effort": settings.groq_reasoning_effort}, "scenarios": []}
    try:
        for number, scenario in enumerate(scenarios):
            cid = conversation_store.new(-10000-number, -10000-number)
            record = {"id": scenario["id"], "name": scenario["name"], "turns": []}
            results["scenarios"].append(record)
            for message in scenario["turns"]:
                pending = conversation_store.begin(cid, message)
                state = conversation_store.dialogue_state(cid)
                start = time.perf_counter()
                answer = await service.answer(message, state=state)
                conversation_store.complete(pending, answer)
                diagnostics = answer.retrieval_diagnostics or {}
                turn = {"user": message, "answer": answer.text,
                        "scenario": answer.scenario, "reason": answer.scenario_reason,
                        "generation_status": answer.generation_status,
                        "llm_used": answer.llm_call_attempted,
                        "tokens": answer.total_tokens,
                        "elapsed_ms": round((time.perf_counter()-start)*1000),
                        "active_request": answer.active_request,
                        "selected": diagnostics.get("selected", []),
                        "candidates": diagnostics.get("candidates", []),
                        "validation_reason": answer.validation_reason,
                        "dialogue_state": answer.dialogue_state}
                record["turns"].append(turn)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"scenario": scenario["id"], "turn": len(record["turns"]),
                                  "answer": answer.text, "llm_used": answer.llm_call_attempted,
                                  "elapsed_ms": turn["elapsed_ms"], "reason": answer.scenario_reason},
                                 ensure_ascii=False), flush=True)
    finally:
        answer_service.generate = original_generate
        print(f"Baseline Groq calls attempted: {calls}/{args.max_groq_calls}", flush=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=Path(__file__).with_name("scenarios.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("baseline-results.json"))
    parser.add_argument("--sqlite", type=Path, default=ROOT / ".local" / "vnext-baseline.sqlite3")
    parser.add_argument("--max-groq-calls", type=int, default=15)
    asyncio.run(run(parser.parse_args()))
