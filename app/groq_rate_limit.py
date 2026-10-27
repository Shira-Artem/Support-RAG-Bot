"""Bounded, process-local Groq pacing for every active chat completion path."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
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
_ALLOWLIST_LOCAL_TPM_BYPASS: ContextVar[bool] = ContextVar(
    "groq_allowlist_local_tpm_bypass", default=False)


@contextmanager
def allowlist_local_tpm_bypass(enabled: bool):
    """Bypass only estimate-based local TPM holds inside an allowlisted turn."""
    token = _ALLOWLIST_LOCAL_TPM_BYPASS.set(bool(enabled))
    try:
        yield
    finally:
        _ALLOWLIST_LOCAL_TPM_BYPASS.reset(token)


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


def retry_after_seconds(headers) -> float | None:
    return _seconds(public_headers(headers or {}).get("retry-after"))


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
        self._http_attempts = 0

    async def before_request(self, estimated_tokens: int, *, stage: str = "unknown") -> int:
        """Pace calls, but don't pre-block allowlisted turns on estimated TPM."""
        bypass_local_tpm = _ALLOWLIST_LOCAL_TPM_BYPASS.get()
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
                if self._cooldown_until > now:
                    reason = "provider_retry_after"
                if self._remaining_requests == 0:
                    wait = max(wait, self._requests_reset - now if self._requests_reset else 86400.0)
                    reason = "rpd_exhausted"
                if (not bypass_local_tpm and self._remaining_tokens is not None
                        and estimated_tokens > self._remaining_tokens):
                    wait = max(wait, self._tokens_reset - now if self._tokens_reset else 60.0)
                    reason = "tpm_insufficient"
                if wait <= 0:
                    self._last_attempt = now
                    # Reserve once so concurrent calls cannot all spend the same observed quota.
                    if self._remaining_tokens is not None:
                        self._remaining_tokens = max(0, self._remaining_tokens - estimated_tokens)
                    if self._remaining_requests is not None:
                        self._remaining_requests = max(0, self._remaining_requests - 1)
                    self._http_attempts += 1
                    return self._http_attempts
                if wait > self.maximum_wait:
                    # Allowlisted manual-testing turns may wait through ordinary
                    # local pacing. Provider 429 cooldowns and request quotas stay
                    # hard gates because those limits came from Groq itself.
                    provider_limit = reason in {"provider_retry_after", "rpd_exhausted"}
                    if not bypass_local_tpm or provider_limit:
                        self._record_deferred(stage, estimated_tokens, reason, round(wait, 2),
                                              bypass_local_tpm)
                        raise GroqQuotaDeferred(round(wait, 2), reason)
            await asyncio.sleep(wait)

    def observe(self, headers, *, status: int | None, usage: dict | None, stage: str,
                duration_ms: int | None = None,
                attempt_number: int | None = None) -> dict[str, str]:
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
                  "rate_limit_headers": exposed, "usage": safe_usage,
                  "llm_http_attempt": attempt_number}
        self._write_trace(record)
        return exposed

    @staticmethod
    def _write_trace(record: dict) -> None:
        try:
            _TRACE.parent.mkdir(parents=True, exist_ok=True)
            with _TRACE.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def record_bounded_retry(self, *, stage: str, retry_number: int,
                             retry_after_seconds: float,
                             provider_error_type: str | None) -> None:
        """Record a single bounded provider-directed retry without response body."""
        self._write_trace({
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "event": "bounded_retry_scheduled",
            "http_status": 429,
            "retry_number": retry_number,
            "retry_after_seconds": round(retry_after_seconds, 2),
            "provider_error_type": provider_error_type,
            "usage": {"prompt_tokens": None, "completion_tokens": None,
                      "total_tokens": None},
        })

    def _record_deferred(self, stage: str, estimated_tokens: int, reason: str,
                         retry_after_seconds: float, bypass_local_tpm: bool) -> None:
        self._write_trace({"at_utc": datetime.now(timezone.utc).isoformat(),
            "stage": stage, "event": "local_deferred", "http_status": None,
            "duration_ms": None, "estimated_tokens": estimated_tokens,
            "defer_reason": reason, "retry_after_seconds": retry_after_seconds,
            "allowlist_local_tpm_bypass": bypass_local_tpm,
            "provider_limits": {"remaining_tokens": self._remaining_tokens,
                                "remaining_requests": self._remaining_requests},
            "usage": {"prompt_tokens": None, "completion_tokens": None,
                      "total_tokens": None}, "llm_http_attempt": None})


groq_rate_limiter = GroqRateLimiter()
