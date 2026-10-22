import json
import sqlite3
from pathlib import Path

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.expert_store import ExpertStore, load_questions
from scripts.export_support_feedback import export


def test_100_questions_are_grounded_and_session_order_is_durable(tmp_path):
    questions = load_questions()
    assert len(questions) == 100
    assert len({q['id'] for q in questions}) == 100
    assert sum(q['source_status'] == 'approved' for q in questions) == 84
    assert sum(q['source_status'] == 'draft' for q in questions) == 12
    assert all(q['expected_result'] and q['evaluation_criterion'] and q['difficulty']
               for q in questions)
    assert all(Path(q['expected_document']).is_file() for q in questions
               if q['expected_document'])
    assert all('отказ' in q['evaluation_criterion'] for q in questions
               if q['source_status'] == 'draft')

    store = ExpertStore(tmp_path / 'expert.sqlite3')
    old = store.start(42, [questions[0]])
    first = store.start(42, questions, shuffle=True)
    second = store.start(43, questions, shuffle=True)
    reopened = ExpertStore(store.path)
    first_order = [row['question_id'] for row in reopened.questions(first, 42)]
    second_order = [row['question_id'] for row in reopened.questions(second, 43)]
    assert len(first_order) == len(second_order) == 100
    assert first_order != second_order
    assert first_order == [row['question_id'] for row in ExpertStore(store.path).questions(first, 42)]
    assert reopened.session(old, 42)['finished_at'] is None
    assert reopened.questions(old, 42)[0]['question_id'] == questions[0]['id']
    assert reopened.questions(first, 42)[0]['expected_result']


def test_answer_feedback_comment_and_lossless_export(tmp_path):
    store = ConversationStore(tmp_path / 'conversations.sqlite3')
    cid = store.new(42, 99)
    answer_id = store.begin(cid, 'Где отчёты АТОЛ Онлайн?')
    store.complete(answer_id, Answer('Отчёты находятся в кабинете.',
        generation_status='partial', scenario='answer',
        raw_model_text='Черновой ответ модели',
        retrieval_collection='knowledge_organized_stage2_20261022',
        retrieval_diagnostics={'selected': [{'document_id': 'atol-online-account-cash-reports'}]}))
    assert store.record_feedback(answer_id, 42, 99, 'unhelpful', 'callback-1')
    assert not store.record_feedback(answer_id, 42, 99, 'unhelpful', 'callback-2')
    assert store.request_feedback_comment(answer_id, 42, 99)
    assert store.save_feedback_comment(42, 99, 'Нужна ссылка на отчёт')
    assert not store.save_feedback_comment(42, 99, 'Повтор')
    assert store.support_request(answer_id, 42, 99, 'ask') == 'pending_confirmation'
    assert store.support_request(answer_id, 42, 99, 'confirm') == 'saved'
    assert store.support_request(answer_id, 42, 99, 'confirm') == 'saved'
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM support_requests').fetchone()[0] == 1
    ratings, problems, csv_file = export(store.path, tmp_path / 'export')
    rating = json.loads(ratings.read_text(encoding='utf-8').strip())
    problem = json.loads(problems.read_text(encoding='utf-8').strip())
    assert rating['conversation_id'] == cid
    assert rating['question_message_id'] == answer_id - 1
    assert rating['answer_message_id'] == answer_id
    assert rating['question'] == 'Где отчёты АТОЛ Онлайн?'
    assert rating['final_answer'] == 'Отчёты находятся в кабинете.'
    assert rating['raw_model_answer'] == 'Черновой ответ модели'
    assert rating['found_document_ids'] == ['atol-online-account-cash-reports']
    assert rating['comment'] == 'Нужна ссылка на отчёт'
    assert rating['rated_at'] and rating['comment_created_at']
    assert problem['support_request_status'] == 'saved'
    assert csv_file.is_file()
