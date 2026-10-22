"""Inspect saved local requests before any future support-channel integration."""
from __future__ import annotations

import json
import sqlite3

from app.conversation_store import DEFAULT_DB


def saved_requests(path=DEFAULT_DB) -> list[dict]:
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute('''SELECT s.id,s.conversation_id,s.question_message_id,
            s.answer_message_id,s.status,s.basis,s.confirmed_at,c.chat_id,
            q.content AS question,a.content AS answer,a.diagnostics_json
            FROM support_requests s JOIN conversations c ON c.id=s.conversation_id
            JOIN messages q ON q.id=s.question_message_id
            JOIN messages a ON a.id=s.answer_message_id
            WHERE s.status IN ('saved','delivered') ORDER BY s.id''').fetchall()
        result = []
        for row in rows:
            d = json.loads(row['diagnostics_json'] or '{}')
            retrieval = d.get('retrieval_diagnostics') or {}
            result.append({**{key: row[key] for key in ('id','conversation_id','question_message_id',
                'answer_message_id','status','basis','confirmed_at','chat_id','question','answer')},
                'diagnostics': {key: d.get(key) for key in ('scenario','generation_status',
                    'generation_reason','retrieval_collection')},
                'retrieval': {key: retrieval.get(key) for key in ('evidence_status','sufficient',
                    'missing_evidence','insufficiency_reason')}})
        return result
    finally:
        db.close()


if __name__ == '__main__':
    print(json.dumps(saved_requests(), ensure_ascii=False, indent=2))
