"""Readable, read-only diagnostics for recent Telegram free-chat turns."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# The viewer is a stdlib-only read tool: importing the application would require
# provider dependencies even though no provider is used here.
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/conversations.sqlite3"


def _one_turn(row, show_context: bool = False) -> None:
    data = json.loads(row["diagnostics_json"] or "{}")
    state = data.get("dialogue_state") or {}
    entities = state.get("entities") or {}
    entity_text = ", ".join(
        f"{slot}={', '.join(f.get('value', '') for f in facts)}"
        for slot, facts in entities.items() if facts
    ) or "—"
    print(f"\n[{row['created_at']}] {row['user_content'] or '(сообщение клиента не найдено)'}")
    print(f"  задача: {state.get('intent', '—')} / {state.get('operation', '—')} / {state.get('object') or '—'}")
    print(f"  сущности: {entity_text}")
    print(f"  RAG-запрос: {data.get('rag_query') or '—'}")
    retrieval = data.get("retrieval_diagnostics") or {}
    print(f"  доказательств достаточно: {retrieval.get('sufficient', '—')} ({retrieval.get('insufficiency_reason') or '—'})")
    for key, label in (("selected", "выбрано"), ("rejected", "отклонено")):
        docs = retrieval.get(key) or []
        print(f"  {label}: {len(docs)}")
        for item in docs[:12]:
            why = "; ".join(item.get("reasons") or [])
            score = item.get("relevance", {}).get("score")
            print(f"    - {item.get('source')} [{item.get('status')}; score={score}] {why}")
    attempted = data.get('llm_call_attempted')
    if attempted is None:
        attempted = data.get('used_model') or data.get('generation_reason') == 'llm_api_error'
    print(f"  LLM: {data.get('model') or '—'} / {data.get('generation_status') or '—'}; вызов: {attempted}")
    print(f"  reasoning effort: {data.get('reasoning_effort') or 'не сохранён'}")
    print("  токены: " + ", ".join(f"{key}={data.get(key)}" for key in (
        'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens')))
    if data.get('generation_error'):
        print(f"  ошибка API: {data['generation_error']}")
    print(f"  валидация: {data.get('validation_status') or '—'} {data.get('validation_reason') or ''}")
    print(f"  ответ бота: {data.get('text') or '—'}")
    if data.get("raw_model_text"):
        print(f"  исходный ответ LLM: {data['raw_model_text']}")
    repair = data.get('response_repair') or {}
    if repair:
        print(f"  обработка ответа: {repair.get('mode')}")
        for item in repair.get('removed', []):
            print(f"    удалено ({item.get('reason')}): {item.get('text')}")
        for item in repair.get('evidence', []):
            print(f"    подтверждение [{item.get('source')}]: {item.get('text')}")
    if show_context:
        print("  контекст для LLM:")
        print(retrieval.get("context") or "  (пусто)")


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--conversation", help="conversation ID; default is most recently updated")
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--context", action="store_true", help="also print the exact context sent to the LLM")
    args = parser.parse_args()
    # Open in read-only mode; the viewer never migrates or writes SQLite.
    db = sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        cid = args.conversation
        if not cid:
            row = db.execute("SELECT conversation_id FROM messages ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                print("История пока пуста.")
                return
            cid = row[0]
        rows = db.execute("""SELECT a.*,
            (SELECT u.content FROM messages u WHERE u.conversation_id=a.conversation_id
                AND u.role='user' AND u.id<a.id ORDER BY u.id DESC LIMIT 1) AS user_content
            FROM messages a WHERE a.conversation_id=?
            AND a.role='assistant' AND a.status='complete' ORDER BY a.id DESC LIMIT ?""",
            (cid, max(1, args.turns))).fetchall()[::-1]
        if not rows:
            print(f"Нет завершённых ответов для диалога {cid}.")
            return
        print(f"Диалог: {cid} | SQLite: {args.db}")
        for row in rows:
            _one_turn(row, args.context)
    finally:
        db.close()


if __name__ == "__main__":
    main()
