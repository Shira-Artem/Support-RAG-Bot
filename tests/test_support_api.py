"""Offline durability/security contracts; fake generation is never LIVE evidence."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.answer_service import Answer
from app.support_api import SupportGateway


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('RAG_SERVICE_TOKEN', 's' * 40)
    gateway = SupportGateway(tmp_path / 'state.sqlite3', lambda store: SimpleNamespace(conversations=store))
    calls = []
    async def turn(runtime, conversation, text, user_id, **kwargs):
        calls.append(text)
        mid = runtime.conversations.begin(conversation, text)
        return mid, Answer('Сохранённый ответ', generation_status='generated', scenario='answer', provider='offline-fixture')
    with patch('app.support_api.run_turn', turn):
        with TestClient(create_app(retriever=object(), support_factory=lambda: gateway)) as client:
            client.headers['Authorization'] = 'Bearer ' + 's' * 40
            yield client, gateway, calls


def request(**changes):
    return dict(ticket_id='test:case:1', message_id='msg:1', text='Что такое ОФД?', expected_revision=0,
                context={'channel': 'test'}, **changes)


def test_auth_and_extra_context_are_rejected(api):
    client, _, calls = api
    assert client.post('/v1/support/reply', json=request(), headers={'Authorization': 'Bearer wrong'}).status_code == 401
    value = request(); value['context']['customer_phone'] = '+70001234567'
    assert client.post('/v1/support/reply', json=value).status_code == 422
    assert not calls


def test_idempotency_revision_and_ack_are_durable(api):
    client, gateway, calls = api
    payload = request()
    first = client.post('/v1/support/reply', json=payload).json()
    assert first['status'] == 'answered' and first['revision'] == 1
    assert client.post('/v1/support/reply', json=payload).json() == first
    payload['text'] = 'Другое сообщение'
    assert client.post('/v1/support/reply', json=payload).status_code == 409
    payload = request(); payload.update(message_id='msg:2', expected_revision=1)
    assert client.post('/v1/support/reply', json=payload).status_code == 409
    reopened = SupportGateway(gateway.store.path)
    assert reopened.state('test:case:1')['revision'] == 1
    with reopened.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages WHERE status='pending'").fetchone()[0] == 1
    ack = {'reply_id': first['reply_id']}
    assert client.post('/v1/support/ack/test:case:1', json=ack).json() == {'state': 'accepted'}
    assert client.post('/v1/support/ack/test:case:1', json=ack).status_code == 200
    assert client.post('/v1/support/reply', json=payload).status_code == 200
    assert len(calls) == 2


def test_revision_conflict_and_pii_boundary(api):
    client, gateway, calls = api
    payload = request(); payload['expected_revision'] = 4
    assert client.post('/v1/support/reply', json=payload).status_code == 409
    payload['expected_revision'] = 0
    payload['text'] = 'Email me test@example.com +7 (999) 123-45-67 password=secretvalue'
    assert client.post('/v1/support/reply', json=payload).status_code == 200
    assert 'secretvalue' not in calls[0] and 'example.com' not in calls[0] and '999' not in calls[0]


def test_concurrent_input_is_fenced_and_discard_preserves_user(api):
    client, gateway, _ = api
    first = client.post('/v1/support/reply', json=request()).json()
    assert client.post('/v1/support/ack/another-ticket', json={'reply_id': first['reply_id']}).status_code == 404
    assert client.post('/v1/support/ack/test:case:1', json={'reply_id': first['reply_id'], 'accepted': False}).status_code == 200
    assert client.post('/v1/support/ack/test:case:1', json={'reply_id': first['reply_id']}).status_code == 409
    with gateway.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages WHERE role='user'").fetchone()[0] == 1
        assert db.execute("SELECT status FROM messages WHERE role='assistant'").fetchone()[0] == 'failed'


def test_interrupted_generation_is_not_regenerated(api):
    client, gateway, calls = api
    first = client.post('/v1/support/reply', json=request()).json()
    with gateway.store.connect() as db:
        db.execute("UPDATE crm_replies SET state='processing',response=NULL,started=0,assistant_id=NULL,answer_json=NULL")
    recovered = client.post('/v1/support/reply', json=request()).json()
    assert recovered['status'] == 'error' and recovered['escalation_reason'] == 'interrupted_generation'
    assert len(calls) == 1
    assert client.post('/v1/support/reply', json=request()).json() == recovered


def test_timeout_retains_user_and_returns_cached_error(api):
    client, gateway, _ = api
    gateway.timeout = .01
    calls = []
    async def slow(runtime, conversation, text, user_id, **kwargs):
        calls.append(text)
        runtime.conversations.begin(conversation, text)
        await asyncio.sleep(2)
    with patch('app.support_api.run_turn', slow):
        result = client.post('/v1/support/reply', json=request()).json()
        assert result['status'] == 'error'
        assert client.post('/v1/support/reply', json=request()).json() == result
        assert len(calls) == 1
    with gateway.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages WHERE role='user'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM messages WHERE status='pending'").fetchone()[0] == 0


def test_second_inflight_request_cannot_generate(api):
    from app.support_contract import ReplyRequest
    client, gateway, _ = api
    async def run():
        entered = asyncio.Event()
        resume = asyncio.Event()
        async def slow(runtime, conversation, text, user_id, **kwargs):
            entered.set()
            await resume.wait()
            mid = runtime.conversations.begin(conversation, text)
            return mid, Answer('Ответ', generation_status='generated', scenario='answer')
        with patch('app.support_api.run_turn', slow):
            first = asyncio.create_task(gateway.reply(ReplyRequest(**request())))
            await entered.wait()
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                await gateway.reply(ReplyRequest(**request()))
            assert exc.value.detail == 'request_in_progress'
            second = request(); second['message_id'] = 'm2'
            with pytest.raises(HTTPException):
                await gateway.reply(ReplyRequest(**second))
            resume.set()
            await first
    asyncio.run(run())


def test_sources_only_contain_final_cited_approved_document(api):
    from app.rag import SearchResult
    client, gateway, _ = api
    async def turn(runtime, conversation, text, user_id, **kwargs):
        mid = runtime.conversations.begin(conversation, text)
        return mid, Answer('Ответ. Источник: data/approved.md', generation_status='generated', scenario='answer',
            validation_status='exact_source_copy', results=[
                SearchResult('data/approved.md', 'fact', 1, metadata={'document_id': 'approved', 'status': 'approved'}),
                SearchResult('data/approved.md', 'other chunk', 1, metadata={'document_id': 'approved', 'status': 'approved'}),
                SearchResult('data/unselected.md', 'irrelevant', 1, metadata={'document_id': 'unselected', 'status': 'approved'}),
                SearchResult('data/draft.md', 'draft', 1, metadata={'document_id': 'draft', 'status': 'draft'}),
            ])
    with patch('app.support_api.run_turn', turn):
        response = client.post('/v1/support/reply', json=request()).json()
    assert response['sources'] == [{'id': 'approved', 'title': None}]
