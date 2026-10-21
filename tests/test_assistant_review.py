"""Persistence/export checks only: no model or Qdrant access."""
from dataclasses import asdict
import json
import sqlite3

import pytest

from app.answer_service import Answer
from app.dialogue_state import DialogueState
from scripts import run_assistant_review as runner


def test_additive_storage_and_reviews_preserve_human_data(tmp_path, monkeypatch):
    path = tmp_path / 'reviews.sqlite3'
    monkeypatch.setattr(runner, 'DB', path)
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    # connect's default path is bound at definition, so explicitly replace it.
    monkeypatch.setattr(runner, 'connect', lambda: _connect(path))
    with runner.connect() as db:
        db.execute('CREATE TABLE reviews(id INTEGER PRIMARY KEY, score INTEGER, comment TEXT)')
        db.execute("INSERT INTO reviews VALUES(1,9,'человеческая оценка')")
        runner.prepare(db)
        db.execute("INSERT INTO assistant_review_batches VALUES('b','now','running','{}','{}')")
        case = {'turns': [{'reference_answer': 'Проверить по карточке'}]}
        db.execute('INSERT INTO assistant_review_cases VALUES(?,?,?,?)', ('b','SYN-001',json.dumps(case),'cid'))
        answer = Answer('Нужен сервис', generation_status='clarification', llm_call_attempted=False)
        db.execute('''INSERT INTO assistant_review_attempts(batch_id,case_id,turn_index,created_at,
            query,state_json,answer_json) VALUES(?,?,?,?,?,?,?)''',
            ('b','SYN-001',0,'now','Вопрос',json.dumps(DialogueState().to_dict()),json.dumps(asdict(answer))))
    review = tmp_path / 'grades.jsonl'
    review.write_text(json.dumps(dict(case_id='SYN-001',turn_index=0,score=8,verdict='pass',
                                     comment='Обоснованное уточнение',corrected_answer='Уточнить сервис')), encoding='utf-8')
    output = runner.import_reviews('b', review)
    assert 'Оценка помощника' in (output / 'report.md').read_text(encoding='utf-8')
    with runner.connect() as db:
        assert tuple(db.execute('SELECT * FROM reviews').fetchone()) == (1,9,'человеческая оценка')
        row = db.execute('SELECT * FROM assistant_review_grades').fetchone()
        assert row['reviewer_kind'] == 'assistant' and row['human_approved'] == 0
    # A bad import rolls back and cannot manufacture an unexecuted answer.
    review.write_text(json.dumps(dict(case_id='absent',turn_index=0)), encoding='utf-8')
    with pytest.raises(ValueError, match='absent attempt'):
        runner.import_reviews('b', review)


def _connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db
