"""Local support feedback and handoff summary. Read-only; no client text exported."""
from __future__ import annotations

from collections import Counter
import json
import sqlite3

from app.conversation_store import DEFAULT_DB


def summary(path=DEFAULT_DB) -> dict:
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        # One current rating per answer; absence of a click is never positive.
        ratings = db.execute('''SELECT rating, COUNT(*) AS n FROM feedback_events f
            WHERE id=(SELECT MAX(id) FROM feedback_events WHERE answer_message_id=f.answer_message_id)
            GROUP BY rating''').fetchall()
        requested = db.execute('''SELECT COUNT(DISTINCT c.user_id) FROM support_requests s
            JOIN conversations c ON c.id=s.conversation_id''').fetchone()[0]
        delivered = db.execute("SELECT COUNT(*) FROM support_requests WHERE status='delivered'").fetchone()[0]
        missing = db.execute('''SELECT COUNT(*) FROM messages WHERE role='assistant' AND status='complete'
            AND json_extract(diagnostics_json,'$.generation_status')='no_context' ''').fetchone()[0]
        topics = Counter()
        for row in db.execute('''SELECT m.diagnostics_json FROM support_requests s
            JOIN messages m ON m.id=s.answer_message_id'''):
            d = json.loads(row[0] or '{}')
            state = d.get('dialogue_state') or {}
            key = (state.get('intent') or 'unknown', state.get('operation') or 'unknown',
                   d.get('confirmed_service') or 'unspecified')
            topics[key] += 1
        return {'helpful_answers': dict(ratings).get('helpful', 0),
                'unhelpful_answers': dict(ratings).get('unhelpful', 0),
                'users_requested_specialist': requested,
                'requests_delivered_to_specialist': delivered,
                'answers_missing_confirmed_knowledge': missing,
                'top_escalation_topics': [{'intent': k[0], 'operation': k[1], 'service': k[2],
                                           'requests': n} for k,n in topics.most_common(10)]}
    finally:
        db.close()


if __name__ == '__main__':
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
