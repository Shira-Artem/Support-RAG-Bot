"""Read-only raw dense vs current hybrid candidate positions for control documents."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from qdrant_client import QdrantClient, models

from app.embeddings import SentenceTransformerEmbedding
from app.retrieval import Retriever

COLLECTION = "knowledge_stage3_retrieval_20261022"


class ReadOnlyStore:
    def __init__(self, client, embedding):
        self.client, self.embedding, self.collection = client, embedding, COLLECTION

    def all_points(self):
        offset, points = None, []
        while True:
            batch, offset = self.client.scroll(COLLECTION, offset=offset, limit=256,
                                               with_payload=True, with_vectors=False)
            points.extend(batch)
            if offset is None:
                return points

    def semantic(self, query, limit, query_filter=None):
        vector = self.embedding.embed([query])[0]
        return self.client.query_points(COLLECTION, query=vector, limit=limit,
                                        query_filter=query_filter, with_payload=True).points


def main():
    env = dotenv_values(ROOT / ".env")
    client = QdrantClient(url=env.get("QDRANT_URL") or "http://127.0.0.1:6333", timeout=15)
    info = client.get_collection(COLLECTION)
    if info.points_count != 934:
        raise RuntimeError("Stage3 receipt differs")
    embedding = SentenceTransformerEmbedding(env.get("EMBEDDING_MODEL") or
                                             "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    store = ReadOnlyStore(client, embedding)
    hybrid = Retriever(store, demo=False)
    approved = models.Filter(must=[models.FieldCondition(
        key="status", match=models.MatchValue(value="approved"))])
    cases = [
        ("platforma_receipt", "Как найти чек по номеру ФД в Платформе ОФД?", "platformaofd-lkk-receipt-search"),
        ("aqsi_add_user", "Как добавить сотрудника в aQsi Online?", "aqsi-online-account-add-user"),
        ("directbank", "В 1С перестали загружаться банковские выписки. Как разобраться?", "batch-20261013-bank-directbank-all-accounts"),
    ]
    results = []
    for name, query, expected in cases:
        vector = embedding.embed([query])[0]
        dense = client.query_points(COLLECTION, query=vector, limit=100,
                                    query_filter=approved, with_payload=True).points
        raw = [str(p.payload.get("document_id")) for p in dense]
        hits = hybrid.search(query, top_k=30)
        ranked = [str(h.metadata.get("document_id")) for h in hits]
        results.append({"id": name, "document_id": expected,
                        "dense_rank_100": raw.index(expected)+1 if expected in raw else None,
                        "hybrid_rank_30": ranked.index(expected)+1 if expected in ranked else None})
    path = Path(__file__).with_name("retrieval-diagnostic.json")
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
