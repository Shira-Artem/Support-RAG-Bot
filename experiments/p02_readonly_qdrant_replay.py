"""Read-only Stage3 confirmation of P0.2 incident and negative controls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from qdrant_client import QdrantClient, models

from app.compat import RetrieverRAGAdapter
from app.dialogue_state import DialogueManager, DialogueState
from app.embeddings import SentenceTransformerEmbedding
from app.rag_query import build_rag_query
from app.retrieval import Retriever
from experiments.p02_directbank_replay import CASES
from experiments.vnext.stage3_retrieval import COLLECTION, ReadOnlyStore


def run():
    env = dotenv_values(ROOT / ".env")  # read only
    client = QdrantClient(url=os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or
                          "http://127.0.0.1:6333", timeout=15)
    info = client.get_collection(COLLECTION)
    approved_filter = models.Filter(must=[models.FieldCondition(
        key="status", match=models.MatchValue(value="approved"))])
    approved = client.count(COLLECTION, count_filter=approved_filter, exact=True).count
    if (info.points_count, approved, info.config.params.vectors.size) != (934, 672, 384):
        raise RuntimeError("Stage3 inventory differs from pinned receipt")
    embedding = SentenceTransformerEmbedding(os.getenv("EMBEDDING_MODEL") or
                                             env.get("EMBEDDING_MODEL") or
                                             "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    adapter = RetrieverRAGAdapter(Retriever(ReadOnlyStore(client, embedding), demo=False))
    rows = []
    for case_id, question in CASES:
        state = DialogueManager().advance(DialogueState(), question, 1)
        query = build_rag_query(state)
        result = adapter.search_for_state(state, query)
        rows.append({"id": case_id, "question": question, "rag_query": query,
                     "intent": state.intent, "operation": state.operation,
                     "candidate_documents": [x.document_id for x in result.candidates],
                     "rejected": [{"document_id": x.document_id, "reasons": x.reasons}
                                  for x in result.rejected],
                     "context_documents": list(dict.fromkeys(
                         str((x.metadata or {}).get("document_id")) for x in result.documents)),
                     "context_sections": [(x.metadata or {}).get("section") for x in result.documents],
                     "context": result.context, "supported_steps": result.supported_steps,
                     "evidence_level": result.evidence_level,
                     "insufficiency_reason": result.insufficiency_reason})
    return {"collection": COLLECTION, "points": info.points_count,
            "approved_points": approved, "llm_calls": 0, "writes": 0, "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in result["cases"]:
        print(json.dumps({key: row[key] for key in (
            "id", "intent", "operation", "context_documents", "context_sections",
            "evidence_level")}, ensure_ascii=False))
