"""Index reviewed local documents. Run with python -m scripts.index_documents."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from qdrant_client import QdrantClient

from app.embeddings import SentenceTransformerEmbedding
from app.knowledge import DocumentLoader
from app.runtime import build_store
from app.vector_store import QdrantStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--demo", action="store_true", help="Index unverified data/docs into the same collection for explicit demo use")
    parser.add_argument("--draft-collection", help="Explicit isolated collection for draft documents")
    parser.add_argument("--local-qdrant-path", type=Path, help="Embedded local Qdrant path for draft review")
    args = parser.parse_args()
    docs_dir = Path("data/docs") if args.demo else args.docs_dir
    documents = DocumentLoader(docs_dir).load_all()
    if args.demo and (args.draft_collection or args.local_qdrant_path):
        parser.error("--demo cannot be combined with draft collection options")
    if any(document.status != "approved" for document in documents) and not args.demo and not args.draft_collection:
        parser.error("Draft documents require --draft-collection")
    if args.local_qdrant_path and not args.draft_collection:
        parser.error("--local-qdrant-path requires --draft-collection")
    if args.draft_collection and args.draft_collection == os.getenv("QDRANT_COLLECTION", "knowledge_v1"):
        parser.error("Draft collection must differ from the client collection")
    if args.local_qdrant_path:
        model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        store = QdrantStore(QdrantClient(path=str(args.local_qdrant_path)),
                            SentenceTransformerEmbedding(model), args.draft_collection)
    else:
        store = build_store(demo=args.demo, collection=args.draft_collection)
    stats = store.index(documents, remove_missing=True)
    print(json.dumps({"documents": len(documents), **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
