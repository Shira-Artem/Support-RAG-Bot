from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import app.llm_client as client
from app.groq_rate_limit import GroqRateLimiter


@pytest.fixture(autouse=True)
def isolated_groq_quota(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "groq_rate_limiter", GroqRateLimiter(minimum_interval=0, maximum_wait=0))
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "groq.jsonl")


class _Client:
    response = None
    responses = None
    requests = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        type(self).requests += 1
        if type(self).responses:
            return type(self).responses.pop(0)
        return type(self).response


def _settings():
    return SimpleNamespace(llm_provider="groq", groq_api_key="test-secret",
        groq_model="test-model", groq_reasoning_effort="low")


def _response(status: int, payload: dict, headers: dict | None = None):
    return httpx.Response(status, json=payload, headers=headers,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))


def test_success_reports_latency_and_actual_provider_usage(monkeypatch):
    _Client.requests = 0
    _Client.response = _response(200, {"model": "actual", "id": "call-1",
        "choices": [{"message": {"content": '{"mode":"no_evidence"}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    result = asyncio.run(client.generate([], _settings()))
    assert result.duration_ms is not None and result.duration_ms >= 0
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (11, 7, 18)
    assert _Client.requests == 1


def test_missing_headers_allow_one_bounded_generation_and_next_call(monkeypatch):
    _Client.requests = 0
    _Client.response = _response(200, {"choices": [{"message": {"content": "ok"}}],
                                 "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    asyncio.run(client.generate([], _settings()))
    asyncio.run(client.generate([], _settings()))
    assert _Client.requests == 2


def test_observed_tpm_blocks_next_call_without_http_retry(monkeypatch):
    _Client.requests = 0
    _Client.response = _response(200, {"choices": [{"message": {"content": "ok"}}],
                                 "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}},
                                {"x-ratelimit-remaining-tokens": "2",
                                 "x-ratelimit-reset-tokens": "30s"})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    asyncio.run(client.generate([], _settings()))
    with pytest.raises(client.GenerationError) as raised:
        asyncio.run(client.generate([], _settings()))
    assert raised.value.error_type == "GroqQuotaDeferred"
    assert raised.value.retry_after_seconds >= 20
    assert _Client.requests == 1


def test_rate_limit_diagnostics_are_bounded_and_retain_retry_and_usage(monkeypatch):
    _Client.requests = 0
    _Client.responses = [
      _response(429, {"error": {"message": "echoed secret prompt", "type": "tokens",
        "code": "rate_limit_exceeded", "param": None},
        "usage": {"prompt_tokens": 4, "completion_tokens": 0, "total_tokens": 4}},
        {"retry-after": "0.01", "x-request-id": "req-123"}),
      _response(200, {"model": "actual", "choices": [{"message": {"content": "safe"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}},
        {"x-ratelimit-remaining-requests": "10", "x-ratelimit-remaining-tokens": "7000"}),
    ]
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    result = asyncio.run(client.generate([], _settings()))
    assert result.retry_count == 1
    assert result.retry_wait_seconds == pytest.approx(0.01)
    assert result.total_tokens == 5
    assert _Client.requests == 2
    trace_path = __import__("app.groq_rate_limit", fromlist=["_TRACE"])._TRACE
    trace = [__import__("json").loads(line) for line in
             trace_path.read_text(encoding="utf-8").splitlines()]
    retry = next(item for item in trace if item.get("event") == "bounded_retry_scheduled")
    assert retry["http_status"] == 429 and retry["retry_after_seconds"] == pytest.approx(0.01)
    assert "echoed secret prompt" not in str(trace)


def test_429_without_short_retry_after_is_not_retried(monkeypatch):
    _Client.requests = 0
    _Client.responses = None
    _Client.response = _response(429, {"error": {"type": "tokens", "code": "rate_limit_exceeded"}},
                                 {"retry-after": "60"})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    with pytest.raises(client.GenerationError) as raised:
        asyncio.run(client.generate([], _settings()))
    assert raised.value.http_status == 429
    assert raised.value.retry_count == 0
    assert _Client.requests == 1


def test_provider_schema_rejection_is_classified_without_retaining_body(monkeypatch):
    _Client.requests = 0
    _Client.response = _response(400, {"error": {"message": "contains private request data",
        "type": "invalid_request_error", "code": "json_validate_failed", "param": "response_format"}})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    with pytest.raises(client.GenerationError) as raised:
        asyncio.run(client.generate([], _settings()))
    error = raised.value
    assert error.http_status == 400
    assert error.schema_error == "provider_rejected_request_schema"
    assert error.provider_error_param == "response_format"
    assert error.provider_usage is None
    assert "private request data" not in (error.cause_message or "")


def test_malformed_provider_payload_has_phase_specific_schema_error(monkeypatch):
    _Client.requests = 0
    _Client.response = httpx.Response(200, content=b"not-json",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    with pytest.raises(client.GenerationError) as raised:
        asyncio.run(client.generate([], _settings()))
    assert raised.value.stage == "decode_json"
    assert raised.value.schema_error == "invalid_provider_json"
    assert raised.value.duration_ms is not None
    assert _Client.requests == 1
