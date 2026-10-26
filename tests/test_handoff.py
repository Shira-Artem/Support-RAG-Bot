import asyncio
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.answer_service import Answer
from app.conversation_store import ConversationStore
from app.handoff import (HandoffService, HandoffSettings, specialist_request)


class FakeTransport:
    def __init__(self, *, receipt=None, error=None):
        self.receipt = receipt or SimpleNamespace(message_id=51, chat_id=-100123)
        self.error = error
        self.calls = []

    async def send_message(self, chat_id, text):
        self.calls.append((chat_id, text))
        if self.error:
            raise self.error
        return self.receipt


def _confirmed_bundle(tmp_path: Path):
    store = ConversationStore(tmp_path / 'support.sqlite3')
    cid = store.new(42, 99)
    answer_id = store.begin(cid, 'Эвотор не отправляет чеки в ОФД')
    store.complete(answer_id, Answer('Проверьте статус связи в кабинете.',
        scenario='escalate', scenario_reason='no_approved_procedure',
        generation_status='no_context', dialogue_state={
            'task_id': 'task-1', 'intent': 'diagnose', 'operation': 'send_receipt',
            'task_context': {
                'task_id': 'task-1', 'intent': 'diagnose', 'operation': 'send_receipt',
                'object': 'чеки', 'task_fact': {'value': 'Не отправляются чеки', 'quote': 'не отправляет чеки'},
                'entities': {'manufacturer': [{'value': 'Эвотор', 'quote': 'Эвотор'}]},
                'parameters': [], 'goals': [], 'constraints': [], 'details': [],
            }, 'session': {'entities': {}}
        }))
    store.support_request(answer_id, 42, 99, 'ask')
    store.support_request(answer_id, 42, 99, 'confirm')
    return store, answer_id, store.handoff_bundle(answer_id, 42, 99)


def test_handoff_bundle_uses_confirmed_ticket_and_client_fact_evidence(tmp_path):
    store, answer_id, bundle = _confirmed_bundle(tmp_path)
    assert bundle['ticket_id'] == 'SR-0000001'
    assert bundle['task']['operation'] == 'send_receipt'
    assert {'scope': 'task', 'slot': 'manufacturer', 'value': 'Эвотор', 'quote': 'Эвотор'} in bundle['confirmed_facts']
    assert bundle['escalation_reason'] == 'insufficient_knowledge'
    assert [item['text'] for item in bundle['messages']][-2:] == [
        'Эвотор не отправляет чеки в ОФД', 'Проверьте статус связи в кабинете.']


def test_transport_is_disabled_by_default_and_requires_an_explicit_chat(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'configured-bot-token')
    monkeypatch.delenv('HANDOFF_ENABLED', raising=False)
    settings = HandoffSettings.from_env()
    assert not settings.enabled and not settings.ready
    assert not HandoffSettings(enabled=True, bot_token='token').ready


def test_delivery_is_confirmed_and_duplicate_click_does_not_send_twice(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport()
    service = HandoffService(HandoffSettings(True, 'fake-token', '-100123', tmp_path / 'outbox.json'), transport)
    async def run():
        first, second = await asyncio.gather(service.deliver(bundle), service.deliver(bundle))
        return first, second
    first, second = asyncio.run(run())
    assert first['status'] == second['status'] == 'delivered'
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == '-100123'
    assert 'Telegram' not in transport.calls[0][1]
    assert json.loads((tmp_path / 'outbox.json').read_text())['SR-0000001']['status'] == 'delivered'


def test_api_error_is_failed_and_only_explicit_retry_resends(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    path = tmp_path / 'outbox.json'
    failed_transport = FakeTransport(error=TimeoutError('network timeout'))
    settings = HandoffSettings(True, 'fake-token', '-100123', path)
    async def run():
        service = HandoffService(settings, failed_transport)
        first = await service.deliver(bundle)
        duplicate = await service.deliver(bundle)
        retry_transport = FakeTransport()
        retried = await HandoffService(settings, retry_transport).deliver(bundle, retry=True)
        return first, duplicate, retry_transport, retried
    first, duplicate, retry_transport, retried = asyncio.run(run())
    assert first['status'] == duplicate['status'] == 'failed'
    assert len(failed_transport.calls) == 1
    assert len(retry_transport.calls) == 1
    assert retried['status'] == 'delivered'


def test_unverified_transport_receipt_never_claims_delivery(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport(receipt=SimpleNamespace(message_id=51, chat_id=-123))
    service = HandoffService(HandoffSettings(True, 'fake-token', '-100123', tmp_path / 'outbox.json'), transport)
    result = asyncio.run(service.deliver(bundle))
    assert result['status'] == 'failed'


def test_progress_provider_is_included_in_prepared_message(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    service = HandoffService(HandoffSettings(state_path=tmp_path / 'outbox.json'),
        progress_provider=lambda conversation_id, task_id: {'checked': ['network'], 'result': 'not verified'})
    payload = service.prepare(bundle)
    assert 'Результаты проверок' in payload and 'not verified' in payload


def test_direct_specialist_request_is_confirmed_without_calling_llm(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    store, answer_id, _ = _confirmed_bundle(tmp_path)
    with store.connect() as db:
        db.execute('DELETE FROM escalation_events WHERE answer_message_id=?', (answer_id,))
        db.execute('DELETE FROM support_requests WHERE answer_message_id=?', (answer_id,))
    monkeypatch.setattr('app.compat.build_answer_rag', lambda _: SimpleNamespace())
    monkeypatch.setattr('app.expert_store.ExpertStore', lambda: SimpleNamespace())
    monkeypatch.setattr('app.conversation_store.ConversationStore', lambda: store)
    monkeypatch.delenv('HANDOFF_ENABLED', raising=False)
    sys.modules.pop('bot', None)
    bot = importlib.import_module('bot')
    try:
        bot.settings = SimpleNamespace(docs_dir=tmp_path)
        bot.handoff_settings = HandoffSettings(state_path=tmp_path / 'unused-outbox.json')
        bot.understand_message = AsyncMock(side_effect=AssertionError('LLM must not be called'))
        reply_text = AsyncMock()
        message = SimpleNamespace(text='Позови специалиста', reply_text=reply_text,
                                  chat=SimpleNamespace(send_action=AsyncMock()))
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=42),
                                  effective_chat=SimpleNamespace(id=99))
        asyncio.run(bot.handle_message(update, None))
        reply_text.assert_awaited_once()
        assert 'Сохранить заявку специалисту' in reply_text.await_args.args[0]
        assert bot.understand_message.await_count == 0
    finally:
        sys.modules.pop('bot', None)


@pytest.mark.parametrize('text,expected', [
    ('Позови специалиста, пожалуйста', True),
    ('Хочу поговорить со специалистом', True),
    ('Специалист не нужен', False),
    ('Не позови специалиста', False),
])
def test_model_free_direct_specialist_request(text, expected):
    assert specialist_request(text) is expected
