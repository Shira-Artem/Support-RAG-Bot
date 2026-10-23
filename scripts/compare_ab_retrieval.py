"""Read-only replay of saved pilot retrieval against two Qdrant collections.

This script never constructs a writable QdrantStore, never calls an LLM, and
never changes the saved review batch.  It reuses the current DialogueState and
retrieval pipeline with only the collection binding varied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient, models  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.dialogue_state import DialogueState  # noqa: E402
from app.embeddings import SentenceTransformerEmbedding  # noqa: E402
from app.retrieval import Retriever  # noqa: E402
from app.retrieval_pipeline import _state_task_category  # noqa: E402
from app.compat import RetrieverRAGAdapter  # noqa: E402
from scripts import run_assistant_review as runner  # noqa: E402


def _norm_source(value: str | None) -> str:
    return str(value or "").replace("\\", "/").removeprefix("data/knowledge/")


class ReadOnlyQdrantStore:
    """Minimal store surface used by Retriever; exposes no write methods."""

    def __init__(self, client: QdrantClient, embedding, collection: str):
        self.client, self.embedding, self.collection = client, embedding, collection

    def all_points(self) -> list:
        points, offset = [], None
        while True:
            batch, offset = self.client.scroll(self.collection, offset=offset, limit=256,
                                               with_payload=True, with_vectors=False)
            points.extend(batch)
            if offset is None:
                return points

    def semantic(self, query: str, limit: int, query_filter: models.Filter | None = None) -> list:
        vector = self.embedding.embed([query])[0]
        return self.client.query_points(self.collection, query=vector, limit=limit,
                                        query_filter=query_filter, with_payload=True).points


def _points_for_source(client: QdrantClient, collection: str, source: str) -> list:
    return [point for point in _scroll(client, collection)
            if _norm_source(point.payload.get("source")) == source]


def _scroll(client: QdrantClient, collection: str) -> list:
    points, offset = [], None
    while True:
        batch, offset = client.scroll(collection, offset=offset, limit=256,
                                      with_payload=True, with_vectors=False)
        points.extend(batch)
        if offset is None:
            return points


def _document_snapshot(client: QdrantClient, collection: str, source: str) -> dict:
    points = _points_for_source(client, collection, source)
    payloads = [{k: v for k, v in point.payload.items() if k != "text"} for point in points]
    # Keep content hashing independent from stage-specific chunk metadata.  A
    # different chunk_index is a metadata difference, not a document-text
    # difference.
    text_chunks = sorted(str(point.payload.get("text", "")) for point in points)
    statuses = sorted({str(point.payload.get("status")) for point in points})
    return {
        "source": source,
        "present": bool(points),
        "chunks": len(points),
        "statuses": statuses,
        "approved_only": bool(points) and statuses == ["approved"],
        "document_ids": sorted({str(point.payload.get("document_id")) for point in points}),
        "metadata_sha256": hashlib.sha256(json.dumps(payloads, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "content_sha256": hashlib.sha256(json.dumps(text_chunks, ensure_ascii=False).encode()).hexdigest(),
        "metadata_sample": payloads[0] if payloads else None,
    }


def _expected_hit_rank(hits, source: str) -> tuple[int | None, bool, dict | None]:
    for rank, hit in enumerate(hits, 1):
        hit_source = _norm_source((hit.metadata or {}).get("source") or getattr(hit, "source", ""))
        if hit_source == source:
            return rank, True, {"score": hit.score, "metadata": hit.metadata}
    return None, False, None


def _diagnostics_for(collection: str, client: QdrantClient, embedding, state: DialogueState,
                     query: str, expected_source: str, saved_answer: dict) -> dict:
    store = ReadOnlyQdrantStore(client, embedding, collection)
    adapter = RetrieverRAGAdapter(Retriever(store, demo=False))
    raw_hits = adapter.retriever.search(query, top_k=100)
    retrieval = adapter.search_for_state(state, query)
    reasons = []
    for item in [*retrieval.candidates, *retrieval.rejected]:
        if _norm_source(item.source) == expected_source:
            reasons.extend(item.reasons)
    return {
        "collection": collection,
        "raw_rank": _expected_hit_rank(raw_hits, expected_source)[0],
        "in_top_100": _expected_hit_rank(raw_hits, expected_source)[1],
        "raw_target": _expected_hit_rank(raw_hits, expected_source)[2],
        "rejection_reasons": sorted(set(reasons)),
        "selected_documents": list(dict.fromkeys(item.source for item in retrieval.documents)),
        "selected_evaluated_documents": [item.source for item in retrieval.candidates if item.selected],
        "evidence_status": retrieval.evidence_status,
        "evidence_level": retrieval.evidence_level,
        "sufficient": retrieval.sufficient,
        "insufficiency_reason": retrieval.insufficiency_reason,
        "saved_generation_status": saved_answer.get("generation_status"),
        "saved_scenario": saved_answer.get("scenario"),
        "saved_generation_reason": saved_answer.get("generation_reason"),
    }


def run(batch: str, collections: list[str], output: Path) -> Path:
    settings = get_settings()
    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), timeout=15)
    for collection in collections:
        info = client.get_collection(collection)
        print("QDRANT", collection, info.points_count, info.status, flush=True)
    embedding = SentenceTransformerEmbedding(os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    with runner.connect() as db:
        attempts = db.execute("""SELECT case_id, turn_index, query, state_json, answer_json
            FROM assistant_review_attempts WHERE batch_id=? ORDER BY id""", (batch,)).fetchall()
        cases = {row["case_id"]: json.loads(row["case_json"]) for row in db.execute(
            "SELECT case_id, case_json FROM assistant_review_cases WHERE batch_id=?", (batch,))}
    if not attempts:
        raise ValueError(f"No attempts saved for {batch}")
    expected_documents = sorted({
        _norm_source(cases[row["case_id"]]["turns"][row["turn_index"]]["expected_document"])
        for row in attempts
    })
    document_snapshots = {
        source: {
            collection: _document_snapshot(client, collection, source)
            for collection in collections
        }
        for source in expected_documents
    }
    by_case = []
    for row in attempts:
        case = cases[row["case_id"]]
        turn = case["turns"][row["turn_index"]]
        state = DialogueState.from_dict(json.loads(row["state_json"]))
        answer = json.loads(row["answer_json"])
        expected = _norm_source(turn["expected_document"])
        by_collection = {
            collection: _diagnostics_for(collection, client, embedding, state,
                                         answer.get("rag_query") or row["query"], expected, answer)
            for collection in collections
        }
        by_case.append({"case_id": row["case_id"], "query": row["query"],
                        "expected_document": expected,
                        "state": {"intent": state.intent, "operation": state.operation,
                                  "task_category": _state_task_category(state, row["query"]),
                                  "service": state.routing_service or state.task_entity("ofd") or state.task_entity("software")},
                        "collections": by_collection})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"batch": batch, "collections": collections,
                                  "document_snapshots": document_snapshots,
                                  "cases": by_case}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--collections", nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.batch, args.collections, args.output))


if __name__ == "__main__":
    main()
