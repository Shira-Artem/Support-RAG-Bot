"""Deterministic B1 replay on saved raw Understanding and fixed read-only hits."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response
from app.embeddings import SentenceTransformerEmbedding
from app.rag_query import build_rag_query
from app.retrieval import Retriever
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category
from app.vector_store import QdrantStore

HERE = Path(__file__).resolve().parent
GOLD = "evotor/ofd/evotor-7-3-ofd-connection.md"


class FixedSource:
    def __init__(self, hits, adapter):
        self.hits, self.adapter = hits, adapter

    def search(self, query, top_k=5):
        return self.hits[:top_k]

    def article(self, document_id):
        return self.adapter.article(document_id)


def main():
    trace = {row["question_message_id"]: row for row in json.loads(
        (HERE / "production_trace_redacted.json").read_text(encoding="utf-8"))}
    baseline = {row["message_id"]: row["baseline"] for row in json.loads(
        (HERE / "causal_replay.json").read_text(encoding="utf-8"))["cases"]}
    client = QdrantClient(url="http://127.0.0.1:6333", timeout=15)
    info = client.get_collection("knowledge_stage3_retrieval_20261022")
    assert info.status.value == "green" and info.points_count == 934
    store = object.__new__(QdrantStore)
    store.client, store.embedding, store.collection = (
        client, SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        "knowledge_stage3_retrieval_20261022")
    adapter = RetrieverRAGAdapter(Retriever(store, demo=False))
    rows = []
    for sequence in ((557, 559), (561,), (563, 565), (569,)):
        state = DialogueState()
        for mid in sequence:
            row = trace[mid]
            kind, _, _, observation = validate_response(row["raw_understanding"], row["question"], mid)
            state = DialogueManager().advance(state, row["question"], mid, observation=observation)
            query = build_rag_query(state)
            frame = state.task_frame
            output = {
                "message_id": mid, "baseline": baseline.get(mid),
                "task_frame": asdict(frame),
                "query": query, "task_category": _state_task_category(state, query),
            }
            if mid in (557, 559, 561, 565):
                original_query = row["rag_query"]
                hits = adapter.search(original_query, top_k=100)
                retrieval = RetrievalPipeline(FixedSource(hits, adapter)).search(state, original_query)
                gold = next((item for item in retrieval.diagnostics()["candidates"]
                             if item["source"].endswith(GOLD)), None)
                output["same_original_query_fixed_hits"] = {
                    "raw_hits": len(hits), "gold_selected": gold["selected"] if gold else None,
                    "gold_reasons": gold["reasons"] if gold else None,
                    "evidence_status": retrieval.evidence_status,
                    "sufficient": retrieval.sufficient,
                    "selected_sources": [item.source for item in retrieval.candidates if item.selected],
                }
            rows.append(output)
    result = {"method": "saved raw Understanding -> current validator/reducer/query; read-only Stage3 fixed original query hits; no Groq, Planner, production writes",
              "collection_points": info.points_count, "cases": rows}
    (HERE / "stage_b1_production_replay.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: row.get(k) for k in ("message_id", "task_category", "same_original_query_fixed_hits")}
                      for row in rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
