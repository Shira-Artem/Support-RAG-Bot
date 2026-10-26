import asyncio
from hashlib import sha256
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
    assert bundle['ticket_id'].startswith('SR-0000001-')
    expected_binding = sha256(f"{bundle['conversation_id']}\0{bundle['task']['task_id']}".encode()).hexdigest()[:8].upper()
    assert bundle['ticket_id'] == f"SR-{bundle['request_id']:07d}-{expected_binding}"
    assert bundle['task']['operation'] == 'send_receipt'
    assert {'scope': 'task', 'slot': 'manufacturer', 'value': 'Эвотор', 'quote': 'Эвотор'} in bundle['confirmed_facts']
    assert bundle['escalation_reason'] == 'insufficient_knowledge'
    assert [item['text'] for item in bundle['messages']][-2:] == [
        'Эвотор не отправляет чеки в ОФД', 'Проверьте статус связи в кабинете.']


def test_handoff_history_excludes_messages_from_a_later_task(tmp_path):
    store, answer_id, bundle = _confirmed_bundle(tmp_path)
    next_id = store.begin(bundle['conversation_id'], 'Другой вопрос: личный адрес 12 Лесная улица')
    store.complete(next_id, Answer('Пример ответа по другой задаче.', dialogue_state={
        'task_id': 'task-2', 'task_context': {'task_id': 'task-2', 'intent': 'other'},
    }))
    scoped = store.handoff_bundle(answer_id, 42, 99)
    rendered = HandoffService(HandoffSettings(state_path=tmp_path / 'outbox.json')).prepare(scoped)
    assert 'личный адрес' not in rendered and 'Лесная улица' not in rendered
    assert 'Эвотор' in rendered and 'Не отправляются чеки' in rendered


def test_transport_is_disabled_by_default_and_requires_an_explicit_chat(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'configured-bot-token')
    monkeypatch.delenv('HANDOFF_ENABLED', raising=False)
    settings = HandoffSettings.from_env()
    assert not settings.enabled and not settings.ready
    assert not HandoffSettings(enabled=True, bot_token='token').ready


def test_missing_approved_chat_id_never_calls_transport(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport()
    service = HandoffService(HandoffSettings(True, 'fake-token', '', tmp_path / 'outbox.json'), transport)
    result = asyncio.run(service.deliver(bundle))
    assert result['status'] == 'failed'
    assert result['error'] == 'specialist_chat_not_configured'
    assert transport.calls == []


def test_unapproved_configured_chat_never_calls_transport(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport()
    settings = HandoffSettings(True, 'fake-token', '-100123', tmp_path / 'outbox.json',
                               approved_chat_id='-100999')
    assert not settings.ready
    result = asyncio.run(HandoffService(settings, transport).deliver(bundle))
    assert result['status'] == 'failed'
    assert result['error'] == 'specialist_chat_not_approved'
    assert transport.calls == []


def test_delivery_is_confirmed_and_duplicate_click_does_not_send_twice(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport()
    service = HandoffService(HandoffSettings(True, 'fake-token', '-100123', tmp_path / 'outbox.json',
                                             approved_chat_id='-100123'), transport)
    async def run():
        first, second = await asyncio.gather(service.deliver(bundle), service.deliver(bundle))
        return first, second
    first, second = asyncio.run(run())
    assert first['status'] == second['status'] == 'delivered'
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == '-100123'
    assert 'Telegram' not in transport.calls[0][1]
    outbox = json.loads((tmp_path / 'outbox.json').read_text())
    assert outbox[bundle['ticket_id']]['status'] == 'delivered'
    assert 'conversation_id' not in outbox[bundle['ticket_id']]['payload']
    assert 'task_id' not in outbox[bundle['ticket_id']]['payload']


def test_api_error_is_failed_and_only_explicit_retry_resends(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    path = tmp_path / 'outbox.json'
    failed_transport = FakeTransport(error=TimeoutError('network timeout'))
    settings = HandoffSettings(True, 'fake-token', '-100123', path, approved_chat_id='-100123')
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


def test_pending_sidecar_survives_crash_and_requires_explicit_retry(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    path = tmp_path / 'outbox.json'

    class ProcessCrash(BaseException):
        pass

    class CrashAfterSendAccepted:
        def __init__(self):
            self.calls = []

        async def send_message(self, chat_id, text):
            self.calls.append((chat_id, text))
            # Models Telegram accepting the message followed by process death before
            # the client receives the receipt. The remote outcome is now ambiguous.
            raise ProcessCrash()

    settings = HandoffSettings(True, 'fake-token', '-100123', path, approved_chat_id='-100123')
    crash_transport = CrashAfterSendAccepted()
    with pytest.raises(ProcessCrash):
        asyncio.run(HandoffService(settings, crash_transport).deliver(bundle))
    pending = json.loads(path.read_text())[bundle['ticket_id']]
    assert pending['status'] == 'pending'
    assert 'task_id' not in pending['payload'] and 'conversation_id' not in pending['payload']

    after_restart = FakeTransport()
    service = HandoffService(settings, after_restart)
    remains_pending = asyncio.run(service.deliver(bundle))
    assert remains_pending['status'] == 'pending'
    assert after_restart.calls == []
    retried = asyncio.run(service.deliver(bundle, retry=True))
    assert retried['status'] == 'delivered'
    assert len(after_restart.calls) == 1


def test_unverified_transport_receipt_never_claims_delivery(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    transport = FakeTransport(receipt=SimpleNamespace(message_id=51, chat_id=-123))
    service = HandoffService(HandoffSettings(True, 'fake-token', '-100123', tmp_path / 'outbox.json',
                                             approved_chat_id='-100123'), transport)
    result = asyncio.run(service.deliver(bundle))
    assert result['status'] == 'failed'


def test_progress_provider_is_included_in_prepared_message(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    service = HandoffService(HandoffSettings(state_path=tmp_path / 'outbox.json'),
        progress_provider=lambda conversation_id, task_id: {'checked': ['network'], 'result': 'not verified'})
    payload = service.prepare(bundle)
    assert 'Результаты проверок' in payload and 'not verified' in payload


def test_handoff_payload_redacts_contact_data_from_facts_messages_and_progress(tmp_path):
    _, _, bundle = _confirmed_bundle(tmp_path)
    bundle['task']['task'] = 'Кассовая система не отправляет чеки, клиент +7 (999) 123-45-67'
    bundle['confirmed_facts'].append({'slot': 'details', 'value': 'user@example.com',
                                      'quote': 'позвоните +7 999 123 45 67'})
    bundle['messages'] = [{'role': 'user', 'text': 'Почта user@example.com, телефон +7 (999) 123-45-67'}]
    service = HandoffService(HandoffSettings(state_path=tmp_path / 'outbox.json'),
        progress_provider=lambda *_: {'checks': [{'status': 'unknown', 'client_quote': 'user@example.com'}]})
    payload = service.prepare(bundle)
    assert 'Кассовая система не отправляет чеки' in payload
    assert 'user@example.com' not in payload
    assert '+7 999' not in payload and '+7 (' not in payload
    assert '[email скрыт]' in payload and '[телефон скрыт]' in payload


def test_progress_provider_reads_only_matching_task_snapshot_without_mutating_it(tmp_path):
    store = ConversationStore(tmp_path / 'progress.sqlite3')
    cid = store.new(17, 18)
    store.dialogue_state(cid)  # create the versioned snapshot table/row through the store API
    with store.connect() as db:
        state = {'task_context': {'task_id': 'task-1', 'procedure_id': 'approved-doc',
            'entities': {'equipment': [{'value': 'Эвотор X500'}]},
            'eligible_units': [{'unit_id': 'unit-1', 'label': 'Проверить интернет'},
                {'unit_id': 'old-model-unit', 'label': 'Открыть модельное меню',
                 'model_scope': ['5i'], 'model_value': '5i'}],
            'checks': [{'unit_id': 'unit-1', 'status': 'unknown',
                        'result_span': {'quote': 'Интернет проверил, результата не знаю'}},
                {'unit_id': 'old-model-unit', 'status': 'passed',
                 'result_span': {'quote': 'На 5i открыл меню'}}]}}
        db.execute('UPDATE dialogue_states_v2 SET state_json=? WHERE conversation_id=?',
                   (json.dumps(state), cid))
    before = (tmp_path / 'progress.sqlite3').read_bytes()
    summary = store.progress_summary(cid, 'task-1')
    assert summary == {'procedure_id': 'approved-doc', 'checks': [
        {'step': 'Проверить интернет', 'status': 'unknown',
         'client_quote': 'Интернет проверил, результата не знаю'}]}
    assert store.progress_summary(cid, 'other-task') is None
    assert (tmp_path / 'progress.sqlite3').read_bytes() == before
