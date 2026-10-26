"""Bounded, process-local Groq pacing for every active chat completion path."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock
from time import monotonic


_HEADER_NAMES = (
    "retry-after", "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens",
)
_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$")
_TRACE = Path(__file__).resolve().parents[1] / ".local" / "groq-rate-limit.jsonl"


def _seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        match = _DURATION.fullmatch(value.strip())
        if not match or not any(match.groups()):
            return None
        number = sum(float(part or 0) * scale for part, scale in zip(match.groups(), (3600, 60, 1)))
    return number if 0 <= number <= 86400 else None


def _nonnegative_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def public_headers(headers) -> dict[str, str]:
    """Never persist arbitrary headers, authorization, or response bodies."""
    return {name: str(headers[name])[:40] for name in _HEADER_NAMES if name in headers}


def estimate_tokens(request: dict) -> int:
    # Conservative UTF-8 approximation plus full configured completion allowance.
    body = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
    return max(1, (len(body.encode("utf-8")) + 2) // 3) + int(
        request.get("max_completion_tokens") or request.get("max_tokens") or 0)


class GroqQuotaDeferred(RuntimeError):
    def __init__(self, retry_after_seconds: float | None, reason: str):
        super().__init__("Groq quota temporarily unavailable")
        self.retry_after_seconds = retry_after_seconds
        self.reason = reason


class GroqRateLimiter:
    """Use observed headers after the first bounded call; never probe GET /models."""

    def __init__(self, *, minimum_interval: float = 2.1, maximum_wait: float = 8.0):
        self.minimum_interval = minimum_interval
        self.maximum_wait = maximum_wait
        self._lock = Lock()
        self._last_attempt = 0.0
        self._remaining_tokens: int | None = None
        self._tokens_reset = 0.0
        self._remaining_requests: int | None = None
        self._requests_reset = 0.0
        self._cooldown_until = 0.0

    async def before_request(self, estimated_tokens: int) -> None:
        """Wait briefly for a known reset, otherwise defer without an HTTP retry."""
        while True:
            with self._lock:
                now = monotonic()
                if self._tokens_reset and now >= self._tokens_reset:
                    self._remaining_tokens, self._tokens_reset = None, 0.0
                if self._requests_reset and now >= self._requests_reset:
                    self._remaining_requests, self._requests_reset = None, 0.0
                wait = max(0.0, self._last_attempt + self.minimum_interval - now,
                           self._cooldown_until - now)
                reason = "request_pacing"
                if self._remaining_requests == 0:
                    wait = max(wait, self._requests_reset - now if self._requests_reset else 86400.0)
                    reason = "rpd_exhausted"
                if self._remaining_tokens is not None and estimated_tokens > self._remaining_tokens:
                    wait = max(wait, self._tokens_reset - now if self._tokens_reset else 60.0)
                    reason = "tpm_insufficient"
                if wait <= 0:
                    self._last_attempt = now
                    # Reserve once so concurrent calls cannot all spend the same observed quota.
                    if self._remaining_tokens is not None:
                        self._remaining_tokens = max(0, self._remaining_tokens - estimated_tokens)
                    if self._remaining_requests is not None:
                        self._remaining_requests = max(0, self._remaining_requests - 1)
                    return
                if wait > self.maximum_wait:
                    raise GroqQuotaDeferred(round(wait, 2), reason)
            await asyncio.sleep(wait)

    def observe(self, headers, *, status: int | None, usage: dict | None, stage: str,
                duration_ms: int | None = None) -> dict[str, str]:
        exposed = public_headers(headers or {})
        now = monotonic()
        with self._lock:
            tokens = _nonnegative_int(exposed.get("x-ratelimit-remaining-tokens"))
            requests = _nonnegative_int(exposed.get("x-ratelimit-remaining-requests"))
            if tokens is not None:
                self._remaining_tokens = tokens
                reset = _seconds(exposed.get("x-ratelimit-reset-tokens"))
                self._tokens_reset = now + reset if reset is not None else 0.0
            if requests is not None:
                self._remaining_requests = requests
                reset = _seconds(exposed.get("x-ratelimit-reset-requests"))
                self._requests_reset = now + reset if reset is not None else 0.0
            if status == 429:
                retry = _seconds(exposed.get("retry-after"))
                self._cooldown_until = now + (retry if retry is not None else 60.0)
        safe_usage = {key: _nonnegative_int((usage or {}).get(key)) for key in
                      ("prompt_tokens", "completion_tokens", "total_tokens")}
        record = {"at_utc": datetime.now(timezone.utc).isoformat(), "stage": stage,
                  "http_status": status, "duration_ms": duration_ms,
                  "rate_limit_headers": exposed, "usage": safe_usage}
        try:
            _TRACE.parent.mkdir(parents=True, exist_ok=True)
            with _TRACE.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return exposed


groq_rate_limiter = GroqRateLimiter()
