from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from time import monotonic

import httpx
import pytest

import app.llm_client as llm
from app.groq_rate_limit import GroqRateLimiter, retry_after_seconds

spec = importlib.util.spec_from_file_location("b1_live_harness", Path(__file__).resolve().parents[1] / "reports/architecture_audit_20261101/run_b1_memory_live.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def response(status, headers=None):
    payload = ({"error": {"type": "tokens", "code": "rate_limit_exceeded"}} if status == 429 else
               {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}})
    return httpx.Response(status, json=payload, headers=headers,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))


def test_runtime_short_retry_is_observed_once_after_wait(monkeypatch, tmp_path):
    guard = harness.RetryCaptureGuard()
    scope = object()
    calls = []
    responses = [response(429, {"retry-after": "0.05"}), response(200)]
    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            now = monotonic()
            retry = guard.before_request(scope, "planner", kwargs["json"], now)
            result = responses.pop(0)
            guard.observe(scope, "planner", kwargs["json"], result.status_code,
                          retry_after_seconds(result.headers), monotonic(), retry)
            calls.append((result.status_code, now, retry))
            return result
    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)
    # The provider-directed delay is 50ms. Leave a small local wait budget so
    # timer scheduling jitter after asyncio.sleep does not turn the intended
    # single retry into a false quota defer.
    monkeypatch.setattr(llm, "groq_rate_limiter", GroqRateLimiter(minimum_interval=0, maximum_wait=0.1))
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "trace.jsonl")
    settings = SimpleNamespace(llm_provider="groq", groq_api_key="test", groq_model="test", groq_reasoning_effort="low")
    result = asyncio.run(llm.generate([], settings, call_stage="planner"))
    assert [x[0] for x in calls] == [429, 200]
    assert calls[1][1] - calls[0][1] >= 0.05
    assert result.retry_count == 1 and not guard.stopped_on_429
    with pytest.raises(RuntimeError):
        guard.before_request(scope, "planner", {}, monotonic())


def test_retry_guard_rejects_early_different_and_forbidden_retries():
    scope = object()
    request = {"model": "m"}
    guard = harness.RetryCaptureGuard()
    guard.observe(scope, "planner", request, 429, 2, 10, False)
    for other_scope, stage, body, now in [(scope, "planner", request, 11),
            (object(), "planner", request, 12), (scope, "understanding", request, 12),
            (scope, "planner", {"model": "other"}, 12)]:
        with pytest.raises(RuntimeError):
            guard.before_request(other_scope, stage, body, now)
    assert guard.before_request(scope, "planner", request, 12)
    guard.observe(scope, "planner", request, 429, 2, 12, True)
    with pytest.raises(RuntimeError):
        guard.before_request(scope, "planner", request, 14)
    assert guard.stop_reason == "provider_429_after_retry"
    guard = harness.RetryCaptureGuard()
    guard.observe(scope, "planner", request, 429, 16, 10, False)
    with pytest.raises(RuntimeError):
        guard.before_request(scope, "planner", request, 30)
