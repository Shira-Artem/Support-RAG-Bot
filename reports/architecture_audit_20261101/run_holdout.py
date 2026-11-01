"""Read-only lexical-state and Stage3 retrieval probe of the prelabelled holdout.

This is deliberately not a full Telegram or Groq quality measurement. It
isolates task-state and evidence selection on new natural utterances.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import yaml
from qdrant_client import QdrantClient
from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.rag_query import build_rag_query
from app.retrieval import Retriever
from app.retrieval_pipeline import RetrievalPipeline, _state_task_category
from app.vector_store import QdrantStore

HERE = Path(__file__).resolve().parent
CASES = HERE / "holdout_cases.jsonl"
COLLECTION = "knowledge_stage3_retrieval_20261022"


class FixedSource:
    def __init__(self, hits, adapter):
        self.hits, self.adapter = hits, adapter

    def search(self, query, top_k=5):
        return self.hits[:top_k]

    def article(self, document_id):
        return self.adapter.article(document_id)


def main():
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 48 and len({x["id"] for x in rows}) == 48
    assert Counter(x["family"] for x in rows) == {k: 6 for k in
        ("evotor_ofd", "fn", "atol", "aqsi", "directbank", "saby", "diadoc", "bifit")}
    for row in rows:
        if not row["source"]:
            continue
        path = ROOT / "data/knowledge" / row["source"]
        assert path.is_file(), row["id"]
        meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
        assert meta["status"] == "approved", row["id"]
    client = QdrantClient(url="http://127.0.0.1:6333", timeout=15)
    info = client.get_collection(COLLECTION)
    assert info.status.value == "green" and info.points_count == 934
    store = object.__new__(QdrantStore)
    store.client = client
    store.embedding = SentenceTransformerEmbedding("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    store.collection = COLLECTION
    adapter = RetrieverRAGAdapter(Retriever(store, demo=False))
    results = []
    for row in rows:
        manager = DialogueManager()
        state = DialogueState()
        if row.get("prior"):
            state = manager.advance(state, row["prior"], "prior")
        state = manager.advance(state, row["question"], "current")
        result = {**row,
                  "state": {"intent": state.intent, "operation": state.operation,
                            "relation": state.relation, "task_start": state.topic_start_message_id,
                            "routing_service": state.routing_service,
                            "equipment": state.task_entity("equipment")},
                  "actual_user_answer": None,
                  "answer_status": "not_run_retrieval_only"}
        try:
            query = build_rag_query(state)
        except Exception as exc:
            result.update(query=None, query_error=type(exc).__name__, raw_gold=False,
                          selected_gold=False, selected_sources=[], raw_top5=[])
            results.append(result)
            continue
        hits = adapter.search(query, top_k=100)
        retrieval = RetrievalPipeline(FixedSource(hits, adapter)).search(state, query)
        raw_sources = [x.source for x in hits]
        selected_sources = [x.source for x in retrieval.candidates if x.selected]
        diagnostics = retrieval.diagnostics()
        gold = row["source"]
        gold_rejection = next((x["reasons"] for x in diagnostics["rejected"]
                               if gold and x["source"].endswith(gold)), [])
        raw_gold_rank = next((i + 1 for i, x in enumerate(hits)
                              if gold and x.source.endswith(gold)), None)
        result.update(
            query=query,
            expected_task_category=_state_task_category(state, query),
            raw_gold=bool(gold and any(x.endswith(gold) for x in raw_sources)),
            raw_gold_rank=raw_gold_rank,
            selected_gold=bool(gold and any(x.endswith(gold) for x in selected_sources)),
            gold_rejection=gold_rejection,
            raw_top5=[{"source": x.source, "score": x.score} for x in hits[:5]],
            selected_sources=selected_sources,
            selected_candidates=[{"source": x["source"], "metadata": x["metadata"],
                                  "relevance": x["relevance"]} for x in diagnostics["selected"]],
            evidence_status=retrieval.evidence_status,
            sufficient=retrieval.sufficient,
            insufficiency_reason=retrieval.insufficiency_reason,
            supported_steps=retrieval.supported_steps[:2],
        )
        results.append(result)
        print(row["id"], result["state"]["intent"], result["state"]["operation"],
              result["selected_gold"], len(selected_sources), flush=True)
    positive = [x for x in results if x["source"]]
    negative = [x for x in results if not x["source"]]
    metrics = {
        "head_sha256": hashlib.sha256((ROOT / "app/retrieval_pipeline.py").read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "collection": COLLECTION, "collection_points": info.points_count,
        "method": "lexical DialogueManager state plus frozen read-only Stage3 retrieval; no Groq/Planner/user response",
        "total": len(results), "positive": len(positive), "negative": len(negative),
        "query_built": sum(bool(x.get("query")) for x in results),
        "positive_raw_gold": sum(x["raw_gold"] for x in positive),
        "positive_selected_gold": sum(x["selected_gold"] for x in positive),
        "positive_raw_hit_filtered": sum(x["raw_gold"] and not x["selected_gold"] for x in positive),
        "negative_any_selected": sum(bool(x["selected_sources"]) for x in negative),
        "answer_quality_measured": False,
        "by_family": {family: {
            "positive": sum(bool(x["source"]) for x in results if x["family"] == family),
            "selected_gold": sum(x["selected_gold"] for x in results if x["family"] == family),
            "negative_any_selected": sum(bool(x["selected_sources"]) for x in results
                                         if x["family"] == family and not x["source"]),
        } for family in sorted({x["family"] for x in results})},
    }
    (HERE / "holdout_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "holdout_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
