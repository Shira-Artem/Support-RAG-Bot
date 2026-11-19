import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest

from app.network_transport import retry_connection
from app.telegram_transport import ConnectionRetryHTTPXRequest


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr("app.network_transport.asyncio.sleep", AsyncMock())


def test_connection_failures_recover_without_repeating_a_success(caplog):
    operation = AsyncMock(side_effect=[httpx.ConnectError("PRIVATE_TOKEN"),
                                      httpx.ConnectTimeout("PRIVATE_TOKEN"), "answer"])
    assert asyncio.run(retry_connection(operation, stage="understanding")) == "answer"
    assert operation.await_count == 3
    assert "PRIVATE_TOKEN" not in caplog.text


def test_connection_retries_are_bounded():
    operation = AsyncMock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(httpx.ConnectError):
        asyncio.run(retry_connection(operation, stage="generation"))
    assert operation.await_count == 3


@pytest.mark.parametrize("error", [httpx.ReadTimeout("ambiguous"),
    httpx.WriteTimeout("ambiguous"), httpx.RemoteProtocolError("already sent"),
    RuntimeError("application error")])
def test_ambiguous_delivery_and_application_errors_are_not_repeated(error):
    operation = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        asyncio.run(retry_connection(operation, stage="telegram"))
    assert operation.await_count == 1


def test_http_quota_response_is_not_retried_by_connection_recovery():
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.org"))
    operation = AsyncMock(return_value=response)
    assert asyncio.run(retry_connection(operation, stage="generation")) is response
    assert operation.await_count == 1


@pytest.mark.parametrize("cause,retries", [(httpx.ConnectError("TLS handshake"), 2),
                                          (httpx.ReadTimeout("unknown delivery"), 1)])
def test_native_telegram_error_chaining_controls_retry(monkeypatch, cause, retries):
    error = NetworkError("transport failed")
    error.__cause__ = cause
    native = AsyncMock(side_effect=[error, (200, b'{}')])
    monkeypatch.setattr(HTTPXRequest, "do_request", native)
    request = ConnectionRetryHTTPXRequest()
    async def run():
        try:
            return await request.do_request(url="https://example.org", method="POST")
        finally:
            await request.shutdown()
    if retries == 2:
        assert asyncio.run(run()) == (200, b'{}')
    else:
        with pytest.raises(NetworkError):
            asyncio.run(run())
    assert native.await_count == retries


def test_read_only_startup_can_recover_after_regular_delivery_budget(monkeypatch):
    error = NetworkError("TLS handshake")
    error.__cause__ = httpx.ConnectError("offline")
    native = AsyncMock(side_effect=[error, error, error, (200, b'{}')])
    monkeypatch.setattr(HTTPXRequest, "do_request", native)
    request = ConnectionRetryHTTPXRequest()
    async def run():
        try:
            return await request.do_request(url="https://example.org/getMe", method="POST")
        finally:
            await request.shutdown()
    assert asyncio.run(run()) == (200, b'{}')
    assert native.await_count == 4


def test_typing_timeout_does_not_discard_question_or_prevent_answer(monkeypatch, tmp_path):
    from app.answer_service import Answer
    from app.config import Settings
    from app.conversation_store import ConversationStore
    from app.expert_store import ExpertStore
    store = ConversationStore(tmp_path / "conversation.sqlite3")
    cid = store.new(42, 42)
    settings = Settings("offline", "", "offline", "test", "http://localhost", False,
                        Path(__file__).resolve().parents[1] / "data/docs")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.compat.build_answer_rag", lambda _: SimpleNamespace())
    monkeypatch.setattr("app.conversation_store.ConversationStore", lambda: store)
    monkeypatch.setattr("app.expert_store.ExpertStore", lambda: ExpertStore(tmp_path / "expert.sqlite3"))
    sys.modules.pop("bot", None)
    bot = importlib.import_module("bot")
    try:
        generate = AsyncMock(return_value=Answer("Онлайн-касса формирует фискальный чек."))
        monkeypatch.setattr(bot.answer_service, "answer", generate)
        message = SimpleNamespace(text="Как работают онлайн-кассы?", reply_text=AsyncMock(),
            chat=SimpleNamespace(send_action=AsyncMock(side_effect=TimedOut())))
        update = SimpleNamespace(message=message, effective_message=message,
            effective_user=SimpleNamespace(id=42), effective_chat=SimpleNamespace(id=42))
        asyncio.run(bot.handle_message(update, None))
        assert generate.await_count == 1
        assert message.reply_text.await_count == 1
        assert [m["content"] for m in store.history(cid)] == [message.text, "Онлайн-касса формирует фискальный чек."]
    finally:
        sys.modules.pop("bot", None)


def test_failed_delivery_retains_generated_answer_without_publishing_checks(tmp_path):
    from app.answer_service import Answer
    from app.conversation_store import ConversationStore
    store = ConversationStore(tmp_path / "conversation.sqlite3")
    cid = store.new(42, 42)
    message_id = store.begin(cid, "Вопрос", semantic_mode=True, understanding_error="offline")
    answer = Answer("Ответ уже сгенерирован", provider="hubris", generation_status="generated",
        prompt_tokens=123, progress_update={"shown_units": [{"unit_id": "not-delivered"}]})
    store.fail_delivery(message_id, answer)
    with store.connect() as db:
        row = db.execute("SELECT content,status,diagnostics_json FROM messages WHERE id=?", (message_id,)).fetchone()
    assert row[0] == answer.text and row[1] == "failed"
    diagnostics = json.loads(row[2])
    assert diagnostics["delivery_status"] == "failed" and diagnostics["prompt_tokens"] == 123
    assert not any(m["role"] == "assistant" for m in store.history(cid))
    assert store.dialogue_state(cid).task_context is None
