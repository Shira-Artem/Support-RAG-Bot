"""Read-only, answer-level export for later RAG quality analysis."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.conversation_store import DEFAULT_DB


def _details(row: sqlite3.Row) -> dict:
    diagnostics = json.loads(row['diagnostics_json'] or '{}')
    retrieval = diagnostics.get('retrieval_diagnostics') or {}
    selected = retrieval.get('selected') or []
    document_ids = list(dict.fromkeys(
        item.get('document_id') for item in selected if item.get('document_id')))
    return {
        'conversation_id': row['conversation_id'],
        'question_message_id': row['question_message_id'],
        'answer_message_id': row['answer_message_id'],
        'question': row['question'],
        'final_answer': row['answer'],
        'raw_model_answer': diagnostics.get('raw_model_text'),
        'found_document_ids': document_ids,
        'found_documents': selected,
        'retrieval_collection': diagnostics.get('retrieval_collection'),
        'scenario': diagnostics.get('scenario'),
        'scenario_reason': diagnostics.get('scenario_reason'),
        'generation_status': diagnostics.get('generation_status'),
        'generation_reason': diagnostics.get('generation_reason'),
        'validation_reason': diagnostics.get('validation_reason'),
    }


def export(path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN')
        answers = db.execute('''SELECT a.conversation_id, a.id AS answer_message_id,
            a.content AS answer, a.diagnostics_json, q.id AS question_message_id,
            q.content AS question, s.id AS support_request_id,
            s.status AS support_request_status, s.basis AS support_request_basis
            FROM messages a JOIN messages q ON q.id=(
                SELECT MAX(id) FROM messages WHERE conversation_id=a.conversation_id
                AND role='user' AND id<a.id)
            LEFT JOIN support_requests s ON s.answer_message_id=a.id
            WHERE a.role='assistant' AND a.status='complete' ORDER BY a.id''').fetchall()
        feedback = db.execute('SELECT * FROM feedback_events ORDER BY id').fetchall()
        db.execute('COMMIT')
    finally:
        db.close()

    by_answer = {row['answer_message_id']: row for row in answers}
    latest = {}
    for row in feedback:
        latest[row['answer_message_id']] = row['id']
    ratings = []
    for row in feedback:
        answer = by_answer.get(row['answer_message_id'])
        if not answer:
            continue
        ratings.append({**_details(answer), 'feedback_event_id': row['id'],
            'rating': row['rating'], 'rated_at': row['created_at'],
            'comment': row['comment'], 'comment_created_at': row['comment_created_at'],
            'latest_rating_for_answer': row['id'] == latest[row['answer_message_id']],
            'support_request_id': answer['support_request_id'],
            'support_request_status': answer['support_request_status'],
            'support_request_basis': answer['support_request_basis']})

    bad_statuses = {'no_context', 'rejected', 'error', 'unavailable', 'truncated'}
    latest_rating = {row['answer_message_id']: row['rating'] for row in feedback}
    problems = []
    for row in answers:
        details = _details(row)
        rating = latest_rating.get(row['answer_message_id'])
        if (rating == 'unhelpful' or row['support_request_id'] is not None
                or details['generation_status'] in bad_statuses):
            problems.append({**details, 'latest_rating': rating,
                'support_request_id': row['support_request_id'],
                'support_request_status': row['support_request_status'],
                'support_request_basis': row['support_request_basis']})

    ratings_jsonl = output_dir / 'feedback_events.jsonl'
    problems_jsonl = output_dir / 'problem_dialogues.jsonl'
    ratings_csv = output_dir / 'feedback_events.csv'
    for file, records in ((ratings_jsonl, ratings), (problems_jsonl, problems)):
        file.write_text(''.join(json.dumps(record, ensure_ascii=False) + '\n'
                                for record in records), encoding='utf-8')
    fields = ['feedback_event_id', 'conversation_id', 'question_message_id',
              'answer_message_id', 'rating', 'rated_at', 'comment',
              'latest_rating_for_answer', 'found_document_ids',
              'generation_status', 'generation_reason', 'support_request_status']
    with ratings_csv.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in ratings:
            writer.writerow({key: (json.dumps(record[key], ensure_ascii=False)
                                   if key == 'found_document_ids' else record.get(key))
                             for key in fields})
    return ratings_jsonl, problems_jsonl, ratings_csv


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--output-dir', type=Path, default=Path('.local/exports') /
                        ('support-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    args = parser.parse_args()
    for result in export(args.database, args.output_dir):
        print(result)
