"""Read-only preflight for the existing Telegram bot's Source-first route."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.runtime import build_retriever  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("FAIL telegram_token=missing")
        return 2
    if settings.llm_provider != "groq" or not settings.groq_api_key:
        print("FAIL llm_provider_or_key=missing_or_unexpected")
        return 2
    rag = build_retriever(demo=False)
    store = rag.store
    if not store.client.collection_exists(store.collection):
        print("FAIL qdrant_collection=missing")
        return 2
    collection = store.client.get_collection(store.collection)
    points = store.all_points()
    statuses = Counter(str(point.payload.get("status") or "<missing>") for point in points)
    if not points or not statuses.get("approved"):
        print("FAIL approved_points=missing")
        return 2
    # Retrieval-only smoke: approved Qdrant points; embedding + dense and BM25/RRF
    # paths execute; no scoring assertion and no LLM request.
    hits = rag.search("проверить соединение и передачу данных", top_k=5)
    if any((hit.metadata or {}).get("status") != "approved" for hit in hits):
        print("FAIL retrieval_status_filter=violated")
        return 2
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    files = [ROOT / "bot.py", ROOT / "app/config.py", ROOT / "app/source_first_service.py",
             ROOT / "app/bot_runtime.py"]
    hashes = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in files}
    print(json.dumps({
        "status": "PASS",
        "telegram_token_present": True,
        "groq_key_present": True,
        "provider": settings.llm_provider,
        "model": settings.groq_model,
        "collection": store.collection,
        "collection_points": collection.points_count,
        "approved_points": statuses["approved"],
        "other_status_counts": {key: value for key, value in statuses.items() if key != "approved"},
        "embedding_model": os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        "query_vector_dimension": store.embedding.dimension,
        "retrieval_smoke_hits": len(hits),
        "retrieval_smoke_all_approved": all((hit.metadata or {}).get("status") == "approved" for hit in hits),
        "llm_calls": 0,
        "qdrant_writes": 0,
        "commit": head,
        "code_sha256": hashes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
