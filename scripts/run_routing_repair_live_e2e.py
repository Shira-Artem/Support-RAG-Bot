"""Small synthetic Groq E2E; approved KB and Qdrant are used read-only/in-memory."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from app.answer_service import AnswerService
from app.compat import RetrieverRAGAdapter
from app.config import get_settings
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import understand_message, understanding_to_dict
from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.retrieval import Retriever
from app.retrieval_pipeline import _state_task_category
from app.groq_rate_limit import groq_rate_limiter
import app.dialogue_understanding as understanding_module
from app.vector_store import QdrantStore


PROMPTS = [
    "В Saby не могу найти входящий документ. Где безопасно проверить его статус?",
    "Эвотор 6: как распечатать копию чека по ФД 123?",
]


def _state_summary(state):
    return {"intent": state.intent, "object": state.object, "operation": state.operation,
            "relation": state.relation, "active_route": state.routing_slot,
            "routing_service": state.routing_service, "analysis_required": state.analysis_required,
            "entities": {slot: [fact.value for fact in values]
                         for slot, values in state.task_entities.items()}}


async def run(output_path: str):
    settings = get_settings()
    if settings.llm_provider != "groq" or not settings.groq_api_key:
        raise RuntimeError("Groq provider/key is unavailable; no live request was sent")
    loader = DocumentLoader(ROOT / "data/knowledge")
    approved = [doc for doc in loader.load_all() if doc.status == "approved"]
    client = QdrantClient(":memory:")
    embedding = SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    store = QdrantStore(client, embedding, "routing_repair_live_e2e")
    store.index(approved, remove_missing=True)
    rag = RetrieverRAGAdapter(Retriever(store, demo=False))
    service = AnswerService(rag, settings)
    results = []
    trace_rows = []
    old_trace = understanding_module._append_local_trace
    import app.groq_rate_limit as rate_module
    previous_rate_path = rate_module._TRACE
    try:
        # Keep diagnostic output local to a temporary directory. The only
        # durable artifact is the final, synthetic-only result requested here.
        with tempfile.TemporaryDirectory(prefix="routing-repair-live-") as tmp:
            rate_module._TRACE = Path(tmp) / "rate.jsonl"
            understanding_module._append_local_trace = lambda **row: trace_rows.append(row)
            for index, prompt in enumerate(PROMPTS, 1):
                understanding = await understand_message(prompt, f"synthetic:{index}", [],
                                                          DialogueState(), settings)
                state = DialogueManager().advance(DialogueState(), prompt,
                    f"synthetic:{index}", observation=understanding.observation)
                answer = await service.answer(prompt, state=state)
                diagnostics = answer.retrieval_diagnostics or {}
                results.append({
                    "prompt": prompt,
                    "understanding_raw": understanding.structured_response,
                    "understanding_validated": understanding_to_dict(understanding),
                    "state": _state_summary(state),
                    "rag_query": answer.rag_query,
                    "expected_task": (_state_task_category(state, answer.rag_query)
                                      if answer.rag_query else None),
                    "final_evidence": list(dict.fromkeys(
                        (item.metadata or {}).get("document_id") for item in answer.results
                        if (item.metadata or {}).get("document_id"))),
                    "rejected_reasons": [{"document_id": item.get("document_id"),
                        "reasons": item.get("reasons", [])}
                        for item in diagnostics.get("rejected", [])[:12]],
                    "sufficient": diagnostics.get("sufficient"),
                    "evidence_status": diagnostics.get("evidence_status"),
                    "generation_status": answer.generation_status,
                    "scenario": answer.scenario,
                    "scenario_reason": answer.scenario_reason,
                    "answer": answer.text,
                    "answer_generation_used_model": answer.used_model,
                    "llm_call_attempted": answer.llm_call_attempted,
                    "usage": {"understanding": understanding.tokens,
                              "answer_prompt_tokens": answer.prompt_tokens,
                              "answer_completion_tokens": answer.completion_tokens,
                              "answer_total_tokens": answer.total_tokens},
                    "duration_ms": {"understanding": understanding.duration_ms,
                                    "answer": answer.duration_ms},
                })
    finally:
        understanding_module._append_local_trace = old_trace
        rate_module._TRACE = previous_rate_path
    payload = {"mode": "live_groq_synthetic_e2e", "model": settings.groq_model,
        "approved_documents": len(approved), "production_qdrant_access": False,
        "production_kb_write": False, "sqlite_access": False, "telegram": False,
        "cases": results}
    destination = ROOT / output_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": payload["model"], "cases": len(results),
        "generation_calls": sum(item["answer_generation_used_model"] for item in results),
        "result_path": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/kb_quality_sprint_20261028/routing_repair_live_e2e.json")
    asyncio.run(run(parser.parse_args().output))
