"""Export Source-first turns from the existing conversation DB with basic PII masking."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data/conversations.sqlite3"
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s()\-]*\d{2}[\s()\-]*\d{2}(?!\w)")
LABELED_PII = re.compile(r"(?im)\b(?:фио|ф\.\s*и\.\s*о\.|имя|адрес|телефон|почта|email)\s*[:=]\s*[^\n,;]+")
INTRODUCED_NAME = re.compile(r"(?i)\b(?:меня зовут|мо[её] имя|зовут)\s+[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+){0,2}")


def mask_text(value: str) -> str:
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    value = LABELED_PII.sub(lambda match: match.group(0).split(":", 1)[0].split("=", 1)[0] + ": [REDACTED]", value)
    return INTRODUCED_NAME.sub("[NAME]", value)


def anonymize(value):
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [anonymize(item) for item in value]
    if isinstance(value, dict):
        return {key: anonymize(item) for key, item in value.items()}
    return value


def export(db_path: Path, output: Path) -> int:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT conversation_id, role, content, diagnostics_json FROM messages "
                          "WHERE status='complete' ORDER BY conversation_id, id").fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["conversation_id"], []).append(row)
    records = []
    for conversation_number, (conversation_id, messages) in enumerate(grouped.items(), 1):
        latest_user = None
        turn_number = 0
        for row in messages:
            if row["role"] == "user":
                latest_user = row["content"]
                continue
            try:
                diagnostic = json.loads(row["diagnostics_json"] or "{}")
            except (ValueError, TypeError):
                diagnostic = {}
            if diagnostic.get("rag_engine") != "source_first" or latest_user is None:
                continue
            turn_number += 1
            records.append({"conversation": f"conversation-{conversation_number}",
                            "turn": turn_number, "user_message": latest_user,
                            "assistant_answer": row["content"], "trace": diagnostic})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(anonymize(record), ensure_ascii=False) for record in records)
                      + ("\n" if records else ""), encoding="utf-8")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.db.exists():
        print("Conversation database not found", file=sys.stderr)
        return 2
    count = export(args.db, args.output)
    print(f"Exported {count} Source-first turns to {args.output}; Telegram user/chat IDs omitted; common email/phone and labeled PII patterns masked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
