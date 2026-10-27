import asyncio

import pytest

from app.groq_rate_limit import (GroqQuotaDeferred, GroqRateLimiter, _seconds,
    allowlist_local_tpm_bypass, public_headers)


def test_official_reset_units_and_header_allowlist():
    assert _seconds("2m59.56s") == pytest.approx(179.56)
    assert _seconds("7.66s") == pytest.approx(7.66)
    assert _seconds("garbage") is None
    assert public_headers({"authorization": "secret", "x-ratelimit-remaining-tokens": "120"}) == {
        "x-ratelimit-remaining-tokens": "120"}


def test_first_unknown_quota_is_allowed_then_429_cools_down(monkeypatch, tmp_path):
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "quota.jsonl")
    limiter = GroqRateLimiter(minimum_interval=0, maximum_wait=0)
    asyncio.run(limiter.before_request(5000))
    limiter.observe({"retry-after": "12"}, status=429, usage=None, stage="understanding")
    with pytest.raises(GroqQuotaDeferred) as error:
        asyncio.run(limiter.before_request(5000))
    assert error.value.retry_after_seconds >= 11
    trace = (tmp_path / "quota.jsonl").read_text(encoding="utf-8")
    assert "understanding" in trace and "retry-after" in trace


def test_rpd_exhaustion_defers_without_generating(monkeypatch, tmp_path):
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "quota.jsonl")
    limiter = GroqRateLimiter(minimum_interval=0, maximum_wait=0)
    limiter.observe({"x-ratelimit-remaining-requests": "0",
                     "x-ratelimit-reset-requests": "1h"}, status=200, usage={}, stage="planner")
    with pytest.raises(GroqQuotaDeferred) as error:
        asyncio.run(limiter.before_request(10))
    assert error.value.reason == "rpd_exhausted"


def test_allowlist_bypasses_estimated_tpm_only_and_keeps_http_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "quota.jsonl")
    limiter = GroqRateLimiter(minimum_interval=0, maximum_wait=0)
    limiter.observe({"x-ratelimit-remaining-tokens": "5"}, status=200,
                    usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                    stage="understanding", attempt_number=0)
    with pytest.raises(GroqQuotaDeferred) as error:
        asyncio.run(limiter.before_request(100, stage="understanding"))
    assert error.value.reason == "tpm_insufficient"

    with allowlist_local_tpm_bypass(True):
        attempt = asyncio.run(limiter.before_request(100, stage="understanding"))
    assert attempt == 1
    limiter.observe({"x-ratelimit-remaining-tokens": "2"}, status=200,
        usage={"prompt_tokens": 7, "completion_tokens": 9, "total_tokens": 16},
        stage="understanding", attempt_number=attempt)
    rows = [__import__("json").loads(line) for line in
            (tmp_path / "quota.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["http_status"] == 200
    assert rows[-1]["llm_http_attempt"] == 1
    assert rows[-1]["usage"]["total_tokens"] == 16
    assert rows[-1]["rate_limit_headers"]["x-ratelimit-remaining-tokens"] == "2"


def test_allowlist_still_honors_provider_retry_after_without_retrying(monkeypatch, tmp_path):
    monkeypatch.setattr("app.groq_rate_limit._TRACE", tmp_path / "quota.jsonl")
    limiter = GroqRateLimiter(minimum_interval=0, maximum_wait=0)
    limiter.observe({"retry-after": "12"}, status=429, usage=None, stage="understanding",
                    attempt_number=1)
    with allowlist_local_tpm_bypass(True):
        with pytest.raises(GroqQuotaDeferred) as error:
            asyncio.run(limiter.before_request(100, stage="understanding"))
    assert error.value.reason == "provider_retry_after"
    assert error.value.retry_after_seconds == pytest.approx(12, abs=0.2)


def test_allowlist_waits_through_local_pacing_beyond_maximum_wait():
    limiter = GroqRateLimiter(minimum_interval=0.02, maximum_wait=0.005)
    first = asyncio.run(limiter.before_request(10))
    assert first == 1
    with allowlist_local_tpm_bypass(True):
        second = asyncio.run(limiter.before_request(10))
    assert second == 2
