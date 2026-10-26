import asyncio

import pytest

from app.groq_rate_limit import GroqQuotaDeferred, GroqRateLimiter, _seconds, public_headers


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
