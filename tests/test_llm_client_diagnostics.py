from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import app.llm_client as client


class _Client:
    response = None
    requests = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        type(self).requests += 1
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


def test_rate_limit_diagnostics_are_bounded_and_retain_retry_and_usage(monkeypatch):
    _Client.requests = 0
    _Client.response = _response(429, {"error": {"message": "echoed secret prompt", "type": "rate_limit_error",
        "code": "rate_limit_exceeded", "param": None},
        "usage": {"prompt_tokens": 4, "completion_tokens": 0, "total_tokens": 4}},
        {"retry-after": "12", "x-request-id": "req-123"})
    monkeypatch.setattr(client.httpx, "AsyncClient", _Client)
    with pytest.raises(client.GenerationError) as raised:
        asyncio.run(client.generate([], _settings()))
    error = raised.value
    assert error.http_status == 429
    assert error.error_type == "rate_limit_error"
    assert error.provider_error_code == "rate_limit_exceeded"
    assert error.retry_after_seconds == 12
    assert error.duration_ms is not None
    assert error.provider_usage == {"prompt_tokens": 4, "completion_tokens": 0, "total_tokens": 4}
    assert error.request_id == "req-123"
    assert "echoed secret prompt" not in str(error.__dict__)
    assert "echoed secret prompt" not in (error.cause_message or "")
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
