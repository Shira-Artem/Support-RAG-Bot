from __future__ import annotations

import argparse
import json

from app.runtime import build_retriever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    hits = build_retriever(demo=args.demo).search(args.query, args.top_k)
    print(json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
