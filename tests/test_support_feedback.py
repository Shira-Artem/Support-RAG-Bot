import asyncio
import importlib
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.answer_service import Answer, AnswerService
from app.config import Settings
from app.conversation_store import ConversationStore
from app.expert_store import ExpertStore
from app.dialogue_state import DialogueManager, DialogueState
from app.rag import SearchResult
from app.retrieval_pipeline import RetrievalResult
from scripts.support_report import summary
from scripts.support_queue import saved_requests


def test_telegram_buttons_comment_and_request_flow(monkeypatch, tmp_path):
    store = ConversationStore(tmp_path / 'free.sqlite3')
    expert_store = ExpertStore(tmp_path / 'expert.sqlite3')
    cid = store.new(42, 99)
    answer_id = store.begin(cid, 'Где отчёт?')
    store.complete(answer_id, Answer('В кабинете.'))
    monkeypatch.setattr('app.compat.build_answer_rag', lambda _: SimpleNamespace())
    monkeypatch.setattr('app.expert_store.ExpertStore', lambda: expert_store)
    monkeypatch.setattr('app.conversation_store.ConversationStore', lambda: store)
    sys.modules.pop('bot', None)
    bot = importlib.import_module('bot')
    try:
        labels = [button.text for row in bot.answer_buttons(answer_id).inline_keyboard
                  for button in row]
        assert labels == ['👍 Помогло', '👎 Не помогло', '👨‍💻 Позвать специалиста']
        message = SimpleNamespace(text='', reply_text=AsyncMock(),
                                  chat=SimpleNamespace(send_action=AsyncMock()))
        query = SimpleNamespace(data='', id='callback-1', message=message, answer=AsyncMock())
        update = SimpleNamespace(message=message, effective_message=message,
            callback_query=query, effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=99))
        async def run():
            query.data = f'fb:unhelpful:{answer_id}'
            await bot.free_callback(update, None)
            query.data = f'fb:comment:{answer_id}'
            await bot.free_callback(update, None)
            message.text = 'Не хватает ссылки'
            await bot.handle_message(update, None)
            query.data = f'sp:ask:{answer_id}'
            await bot.free_callback(update, None)
            query.data = f'sp:confirm:{answer_id}'
            await bot.free_callback(update, None)
            await bot.free_callback(update, None)
        asyncio.run(run())
        with sqlite3.connect(store.path) as db:
            assert db.execute('SELECT comment FROM feedback_events').fetchone()[0] == 'Не хватает ссылки'
            assert db.execute('SELECT COUNT(*) FROM support_requests').fetchone()[0] == 1
            assert db.execute('SELECT status FROM support_requests').fetchone()[0] == 'saved'
            assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 2
    finally:
        sys.modules.pop('bot', None)


def test_feedback_and_confirmed_local_request_are_bound_to_answer(tmp_path):
    store = ConversationStore(tmp_path / 'conversations.sqlite3')
    cid = store.new(42, 99)
    answer_id = store.begin(cid, 'Где посмотреть отчёты?')
    store.complete(answer_id, Answer('Подтверждённый ответ', generation_status='grounded',
                                   scenario='answer', scenario_reason='source_confirmed',
                                   retrieval_collection='test_collection',
                                   retrieval_diagnostics={'sufficient': True, 'selected': [
                                       {'document_id': 'atol-online-account-cash-reports'}]}))
    assert store.record_feedback(answer_id, 42, 99, 'unhelpful')
    assert not store.record_feedback(answer_id, 42, 99, 'unhelpful')
    assert store.record_feedback(answer_id, 42, 99, 'helpful')
    assert store.record_feedback(answer_id, 42, 99, 'unhelpful', 'callback-three')
    assert not store.record_feedback(answer_id, 42, 99, 'unhelpful', 'callback-three')
    with pytest.raises(ValueError):
        store.record_feedback(answer_id, 43, 99, 'helpful')
    with pytest.raises(ValueError):
        store.support_request(answer_id, 42, 99, 'confirm')
    assert store.support_request(answer_id, 42, 99, 'ask') == 'pending_confirmation'
    assert store.support_request(answer_id, 42, 99, 'confirm') == 'saved'
    assert store.support_request(answer_id, 42, 99, 'confirm') == 'saved'
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT COUNT(*) FROM support_requests').fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM escalation_events WHERE event_type='confirmed'").fetchone()[0] == 1
        assert db.execute('SELECT question_message_id,answer_message_id,status FROM support_requests').fetchone() == (answer_id-1, answer_id, 'saved')
    report = summary(store.path)
    assert report['helpful_answers'] == 0 and report['unhelpful_answers'] == 1
    assert report['users_requested_specialist'] == 1
    assert report['requests_delivered_to_specialist'] == 0
    queue = saved_requests(store.path)
    assert len(queue) == 1
    assert queue[0]['conversation_id'] == cid
    assert queue[0]['question'] == 'Где посмотреть отчёты?'
    assert queue[0]['answer'] == 'Подтверждённый ответ'


def test_cash_report_source_answer_uses_no_llm(monkeypatch, tmp_path):
    hit = SearchResult('atol_online/account/cash-reports.md',
        'Просмотр отчётов\nПосле замены ФН сервис направляет отчёты на регистрационную почту. '
        'Доступные отчёты можно посмотреть в разделе личного кабинета «Отчеты по кассам».', .05,
        metadata={'document_id': 'atol-online-account-cash-reports',
                  'source_url': 'https://help.atol.online/article/11069'})
    class Rag:
        def search_for_state(self, state, query):
            return RetrievalResult(query, [], [], [hit], True, None, hit.text)
    async def no_llm(*args, **kwargs):
        raise AssertionError('LLM call is unnecessary')
    monkeypatch.setattr('app.answer_service.generate', no_llm)
    settings = Settings('', '', '', '', '', False, tmp_path)
    state = DialogueManager().advance(DialogueState(),
        'Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн?', 1)
    answer = asyncio.run(AnswerService(Rag(), settings).answer(state.task.value, state=state))
    assert answer.scenario == 'answer' and answer.generation_status == 'partial'
    assert not answer.llm_call_attempted
    assert 'регистрационную почту' in answer.text and 'отчёты' in answer.text.casefold()
    assert answer.response_repair['mode'] == 'partial_answer'


def test_rephrased_unresolved_question_is_detected_by_facts_not_message_ids(tmp_path):
    store = ConversationStore(tmp_path / 'conversation.sqlite3')
    cid = store.new(42, 99)
    first = store.begin(cid, '1. Где посмотреть отчёты по кассам в АТОЛ Онлайн?')
    first_state = store.dialogue_state(cid)
    store.complete(first, Answer('Не нашёл инструкции.', generation_status='no_context',
                                 scenario='escalate', dialogue_state=first_state.to_dict()))
    second = store.begin(cid, '2. Где посмотреть отчёты по кассам в АТОЛ Онлайн?')
    assert store.previous_unresolved(cid, second, store.dialogue_state(cid))
