"""Index reviewed local documents. Run with python -m scripts.index_documents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.knowledge import DocumentLoader
from app.runtime import build_store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--demo", action="store_true", help="Index unverified data/docs into the same collection for explicit demo use")
    args = parser.parse_args()
    docs_dir = Path("data/docs") if args.demo else args.docs_dir
    documents = DocumentLoader(docs_dir).load_all()
    store = build_store(demo=args.demo)
    stats = store.index(documents, remove_missing=True)
    print(json.dumps({"documents": len(documents), **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
