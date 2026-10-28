"""Read-only replay of the seven saved 28 October Telegram turns.

Uses recorded DialogueState/Coordinator decisions, live Stage3 retrieval and a
deterministic local section-ID planner. No Groq, Telegram or SQLite writes.
The private output intentionally omits identifiers and raw diagnostic payloads.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
STAGE3 = "knowledge_stage3_retrieval_20261022"
os.environ.update({
    "RAG_BACKEND": "qdrant", "QDRANT_COLLECTION": STAGE3, "RAG_DEMO_MODE": "0",
    "RAG_ENGINE": "source_first", "AI_COORDINATOR_ENABLED": "1",
    "SEMANTIC_EVIDENCE_SELECTOR_ENABLED": "0", "HF_HUB_OFFLINE": "1",
})

from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.config import get_settings
from app.dialogue_state import DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.llm_client import Generation
from app.retrieval import Retriever
import app.source_first_service as source_first_module
from app.source_first_service import SourceFirstService
from app.vector_store import QdrantStore
from scripts.source_scope_offline_e2e import ReadOnlyQdrant

PREFERRED = (
    "Проверенная информация и первичная диагностика",
    "Что можно объяснить и проверить",
    "Подтверждённые сведения",
    "Проверка без изменения регистрации",
    "Результат контроля",
    "Безопасная диагностика",
    "",
)


def recorded_turns() -> list[tuple[str, dict, str]]:
    db_path = (ROOT / "data/conversations.sqlite3").resolve()
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT role, content, diagnostics_json FROM messages "
                          "WHERE created_at LIKE '2026-10-28%' ORDER BY id").fetchall()
    turns = []
    previous_user = None
    for row in rows:
        if row["role"] == "user":
            previous_user = row["content"]
        elif row["role"] == "assistant" and previous_user and row["diagnostics_json"]:
            diagnostics = json.loads(row["diagnostics_json"])
            if diagnostics.get("dialogue_state") and diagnostics.get("coordinator_decision"):
                turns.append((previous_user, diagnostics, row["content"]))
            previous_user = None
    if len(turns) != 7:
        raise RuntimeError(f"Expected seven saved turns, got {len(turns)}")
    return turns


async def run() -> list[dict]:
    turns = recorded_turns()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    info = client.get_collection(STAGE3)
    if not info.points_count or str(info.status) != "green":
        raise RuntimeError("Stage3 unavailable or non-green")
    embedding = SentenceTransformerEmbedding(os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    rag = RetrieverRAGAdapter(Retriever(QdrantStore(ReadOnlyQdrant(client), embedding, STAGE3), demo=False))
    service = SourceFirstService(rag, replace(get_settings(), rag_engine="source_first"), ROOT)
    results = []
    original = source_first_module.generate
    try:
        for index, (question, diagnostics, baseline) in enumerate(turns):
            fixture_calls = 0
            preferred = PREFERRED[index]

            async def offline_plan(messages, _settings, *, call_stage="generation"):
                nonlocal fixture_calls
                fixture_calls += 1
                if call_stage == "general_knowledge":
                    return Generation("ОФД получает фискальные документы от кассы и передаёт их в ФНС.",
                                      "offline-general-fixture")
                payload = json.loads(messages[-1]["content"])
                sections = payload.get("candidate_sections") or []
                selected = next((item for item in sections
                                 if preferred and preferred.casefold() in item["section"].casefold()), None)
                if selected is None and sections:
                    selected = sections[0]
                plan = {"mode": "select" if selected else "escalate",
                        "section_id": selected["id"] if selected else "",
                        "applicability_confirmed": bool(selected),
                        "order_confirmed": bool(selected) and index != 4,
                        "reason": "deterministic local section-ID fixture"}
                return Generation(json.dumps(plan, ensure_ascii=False), "offline-planner-fixture")

            source_first_module.generate = offline_plan
            state = DialogueState.from_dict(diagnostics["dialogue_state"])
            started = perf_counter()
            answer = await service.answer(question, state=state,
                history=[{"role": "user", "content": question,
                          "understanding": diagnostics.get("dialogue_understanding"),
                          "semantic_mode": True}],
                coordinator_decision=diagnostics["coordinator_decision"])
            rd = answer.retrieval_diagnostics or {}
            results.append({
                "case": index + 1,
                "question": question,
                "state": {"intent": state.intent, "operation": state.operation,
                          "object": state.object,
                          "symptom": state.symptom.value if state.symptom else None,
                          "entities": {key: [fact.value for fact in facts]
                                       for key, facts in state.entities.items()}},
                "baseline_answer": baseline,
                "answer": answer.text,
                "scenario": answer.scenario,
                "reason": answer.scenario_reason,
                "validation_status": answer.validation_status,
                "rag_query": answer.rag_query,
                "selected_documents": [{"document_id": item.get("document_id"),
                                        "source": item.get("source")}
                                       for item in rd.get("selected") or []],
                "rejected_documents": [{"document_id": item.get("document_id"),
                                        "source": item.get("source"),
                                        "reasons": item.get("reasons")}
                                       for item in rd.get("rejected") or []][:12],
                "source_scope_gate": rd.get("source_scope_gate"),
                "planner": rd.get("planner"),
                "planner_reselection": rd.get("planner_reselection"),
                "progress_update": answer.progress_update,
                "composer": rd.get("answer_composer"),
                "fixture_calls": fixture_calls,
                "actual_provider_calls": 0,
                "duration_ms": round((perf_counter() - started) * 1000),
            })
            print(index + 1, answer.scenario, answer.scenario_reason,
                  answer.validation_status, answer.text[:100].replace("\n", " "))
    finally:
        source_first_module.generate = original
        client.close()
    return results


def assert_quality(results: list[dict]) -> None:
    if len(results) != 7:
        raise AssertionError("seven recorded turns required")
    a = [item["answer"].casefold() for item in results]
    assert results[0]["scenario"] == "answer" and "сканер" in a[0]
    assert results[1]["scenario"] == "answer" and "возврат" in a[1]
    assert results[2]["scenario"] == "clarify" and "статус" in a[2] and "журнал" in a[2]
    assert "версии api" not in a[2] and "ффд" not in a[2]
    assert results[3]["scenario"] == "answer" and "итог регистрации" in a[3]
    assert "замените" not in a[3] and "перерегистрируйте" not in a[3]
    assert results[4]["scenario"] == "answer" and "успешный приём" in a[4]
    assert "карантин" in a[4] and "уточните точную надпись статуса" in a[4]
    assert results[4]["planner"]["order_confirmed"] is False
    assert results[5]["scenario"] == "answer" and "версию" in a[5]
    assert "директбанк" in a[5] and "банк" in a[5]
    assert results[6]["scenario"] == "answer" and "офд получает" in a[6]
    assert "передаёт их в фнс" in a[6] and "перенос" not in a[6]
    assert all(item["actual_provider_calls"] == 0 for item in results)
    assert all(item["fixture_calls"] <= 1 for item in results)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = asyncio.run(run())
    assert_quality(result)
    output = ROOT / ".local/telegram-quality-replay-20261028.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "recorded state and coordinator; read-only Stage3; local planner; no Groq",
        "results": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved", output)
