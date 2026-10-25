"""Read-only metadata and identity comparison of the two existing Qdrant collections."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "collection_comparison.json"
STAGE3 = "knowledge_stage3_retrieval_20261022"
FIELDS = ("document_id", "chunk_id", "source", "status", "category", "service", "software",
          "task_category", "operations", "manufacturer", "model", "procedure_service",
          "content_hash", "source_url", "source_checked_at", "verified_at", "section")


def load_points(client, collection):
    all_points = []
    offset = None
    while True:
        batch, offset = client.scroll(collection, offset=offset, limit=512,
                                      with_payload=True, with_vectors=False)
        all_points.extend(batch)
        if offset is None:
            return all_points


def inventory(client, name):
    info = client.get_collection(name)
    points = load_points(client, name)
    docs = defaultdict(list)
    ids = set()
    for point in points:
        payload = point.payload or {}
        ids.add(str(point.id))
        docs[str(payload.get("document_id") or "<missing>")].append(payload)
    signatures = {}
    for doc_id, chunks in docs.items():
        first = chunks[0]
        signatures[doc_id] = {field: first.get(field) for field in FIELDS if field in first}
        signatures[doc_id]["chunk_count"] = len(chunks)
        signatures[doc_id]["approved_chunk_count"] = sum(x.get("status") == "approved" for x in chunks)
        signatures[doc_id]["draft_chunk_count"] = sum(x.get("status") == "draft" for x in chunks)
    return {"name": name, "points": len(points), "server_points": info.points_count,
            "vector_size": info.config.params.vectors.size,
            "status_counts": dict(Counter(str((p.payload or {}).get("status") or "<missing>") for p in points)),
            "document_count": len(docs), "approved_document_count": sum(
                any(x.get("status") == "approved" for x in chunks) for chunks in docs.values()),
            "point_ids": ids, "documents": signatures}


def main():
    env = dotenv_values(ROOT / ".env")
    configured = os.getenv("QDRANT_COLLECTION") or env.get("QDRANT_COLLECTION") or "knowledge_v1"
    url = os.getenv("QDRANT_URL") or env.get("QDRANT_URL") or "http://127.0.0.1:6333"
    client = QdrantClient(url=url, timeout=20)
    try:
        a, b = inventory(client, configured), inventory(client, STAGE3)
    finally:
        client.close()
    a_docs, b_docs = a.pop("documents"), b.pop("documents")
    a_ids, b_ids = a.pop("point_ids"), b.pop("point_ids")
    common_docs = sorted(set(a_docs) & set(b_docs))
    document_diffs = []
    for doc_id in common_docs:
        left, right = a_docs[doc_id], b_docs[doc_id]
        fields = sorted(set(left) | set(right))
        changed = {field: {"configured": left.get(field), "stage3": right.get(field)}
                   for field in fields if left.get(field) != right.get(field)}
        if changed:
            document_diffs.append({"document_id": doc_id, "fields": changed})
    result = {
        "configured_by_dotenv": configured,
        "v1_2_b_collection_constant": STAGE3,
        "collections": [a, b],
        "point_identity": {"configured_points": len(a_ids), "stage3_points": len(b_ids),
                           "same_qdrant_point_id_count": len(a_ids & b_ids),
                           "configured_only_point_ids": len(a_ids - b_ids),
                           "stage3_only_point_ids": len(b_ids - a_ids)},
        "document_identity": {"configured_document_count": len(a_docs), "stage3_document_count": len(b_docs),
                              "same_document_id_count": len(set(a_docs) & set(b_docs)),
                              "configured_only_document_ids": sorted(set(a_docs) - set(b_docs)),
                              "stage3_only_document_ids": sorted(set(b_docs) - set(a_docs)),
                              "documents_with_metadata_or_chunk_count_differences": document_diffs},
    }
    result["snapshot_sha256"] = sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"configured_collection": configured, "stage3_collection": STAGE3,
                      "configured_points": len(a_ids), "stage3_points": len(b_ids),
                      "same_point_ids": len(a_ids & b_ids),
                      "common_document_ids": len(set(a_docs) & set(b_docs)),
                      "metadata_different_documents": len(document_diffs),
                      "output": OUT.relative_to(ROOT).as_posix(), "qdrant_writes": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
