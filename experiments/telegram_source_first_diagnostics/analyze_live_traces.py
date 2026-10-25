"""Read-only extraction of three reported Source-first turns from the existing SQLite DB."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.telegram_source_first_integration.export_anonymized import anonymize  # noqa: E402

DB = ROOT / "data/conversations.sqlite3"
OUT = Path(__file__).resolve().parent / "live_traces_anonymized.jsonl"
TARGETS = {
    "greeting_plus_ofd": "привет! помоги с офд",
    "ofd_definition": "что такое офд",
    "ofd_term": "офд как проверит срок",
}
PRIVATE_KEYS = {"conversation_id", "user_id", "chat_id", "message_id", "task_id",
                "topic_start_message_id", "api_call_id"}


def scrub_ids(value):
    if isinstance(value, dict):
        return {key: scrub_ids(item) for key, item in value.items() if key not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [scrub_ids(item) for item in value]
    return value


def main() -> int:
    uri = f"file:{DB.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id, conversation_id, role, content, diagnostics_json "
                          "FROM messages WHERE status='complete' ORDER BY conversation_id,id").fetchall()
    found = {}
    for index, row in enumerate(rows):
        if row["role"] != "user":
            continue
        folded = " ".join(row["content"].casefold().split())
        target = next((name for name, needle in TARGETS.items() if needle in folded), None)
        if target is None:
            continue
        assistant = next((item for item in rows[index + 1:]
                          if item["conversation_id"] == row["conversation_id"]
                          and item["role"] == "assistant"), None)
        if assistant is None:
            continue
        diagnostic = json.loads(assistant["diagnostics_json"] or "{}")
        if diagnostic.get("rag_engine") != "source_first":
            continue
        found[target] = anonymize(scrub_ids({
            "case": target,
            "user_message": row["content"],
            "final_answer": assistant["content"],
            "trace": diagnostic,
        }))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(found[key], ensure_ascii=False)
                             for key in TARGETS if key in found) + ("\n" if found else ""), encoding="utf-8")
    print(json.dumps({"matched_cases": sorted(found), "missing_cases": sorted(set(TARGETS) - set(found)),
                      "output": OUT.relative_to(ROOT).as_posix(), "db_mode": "read_only"}, ensure_ascii=False))
    return 0 if len(found) == len(TARGETS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
