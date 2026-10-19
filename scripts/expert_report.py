"""Print expert statistics and optionally export complete attempts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.expert_report import export, statistics
from app.expert_store import DEFAULT_DB, ExpertStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--expert-id", type=int)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DB.parent / "exports")
    args = parser.parse_args()
    store = ExpertStore(args.db)
    rows = store.rows(args.expert_id)
    report = statistics(rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.export:
        for path in export(store, args.output_dir, args.expert_id):
            print(path)


if __name__ == "__main__":
    main()
