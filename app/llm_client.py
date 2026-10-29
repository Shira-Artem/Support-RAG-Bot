"""One chat-completions interface for the two configured providers."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
import traceback

import httpx

from app.config import Settings
from app.groq_rate_limit import (GroqQuotaDeferred, estimate_tokens, groq_rate_limiter,
                                 retry_after_seconds)


class GenerationError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None,
                 error_type: str | None = None, retry_after_seconds: float | None = None,
                 stage: str | None = None, cause_message: str | None = None,
                 traceback_text: str | None = None, duration_ms: int | None = None,
                 provider_error_code: str | None = None,
                 provider_error_param: str | None = None,
                 provider_usage: dict | None = None, request_id: str | None = None,
                 schema_error: str | None = None, rate_limit_headers: dict | None = None,
                 retry_count: int = 0, retry_wait_seconds: float = 0.0):
        super().__init__(message)
        self.http_status = http_status
        self.error_type = error_type
        self.retry_after_seconds = retry_after_seconds
        self.stage = stage
        self.cause_message = cause_message
        self.traceback_text = traceback_text
        self.duration_ms = duration_ms
        self.provider_error_code = provider_error_code
        self.provider_error_param = provider_error_param
        self.provider_usage = provider_usage
        self.request_id = request_id
        self.schema_error = schema_error
        self.rate_limit_headers = rate_limit_headers
        self.retry_count = retry_count
        self.retry_wait_seconds = retry_wait_seconds


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    api_call_id: str | None = None
    finish_reason: str | None = None
    duration_ms: int | None = None
    rate_limit_headers: dict | None = None
    retry_count: int = 0
    retry_wait_seconds: float = 0.0


def _optional_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


async def _generate_once(messages: list[dict], settings: Settings, *, call_stage: str = "generation") -> Generation:
    if settings.llm_provider == "groq":
        key, model = settings.groq_api_key, settings.groq_model
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {}
        # GPT-OSS reasoning tokens use the same completion budget as visible output.
        # 2048 leaves room for reasoning while comfortably exceeding short support answers.
        # Routine support answers and planner decisions are short. Reserving
        # 2048 output tokens per request unnecessarily trips provider TPM when
        # less than that reserve remains, even when the actual answer is small.
        token_limit = {"max_completion_tokens": 1024,
                       "reasoning_effort": settings.groq_reasoning_effort or "low"}
    elif settings.llm_provider == "openrouter":
        key, model = settings.openrouter_api_key, settings.openrouter_model
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"HTTP-Referer": settings.app_url, "X-OpenRouter-Title": settings.app_name}
        token_limit = {"max_tokens": 900}
    else:
        raise GenerationError("Unsupported LLM provider")
    if not key:
        raise GenerationError("LLM API key is not configured")
    headers["Authorization"] = f"Bearer {key}"
    request = {"model": model, "messages": messages, "temperature": 0.2, **token_limit}
    if call_stage == "planner" and settings.llm_provider == "groq":
        request["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "source_section_plan", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                "properties": {
                    "mode": {"type": "string", "enum": ["select", "clarify", "escalate"]},
                    "section_id": {"type": "string"},
                    "applicability_confirmed": {"type": "boolean"},
                    "order_confirmed": {"type": "boolean"},
                    "reason": {"type": "string"}},
                "required": ["mode", "section_id", "applicability_confirmed", "order_confirmed", "reason"]}}}
    attempt_number = None
    if settings.llm_provider == "groq":
        try:
            attempt_number = await groq_rate_limiter.before_request(
                estimate_tokens(request), stage=call_stage)
        except GroqQuotaDeferred as exc:
            raise GenerationError("Groq quota temporarily unavailable", error_type=type(exc).__name__,
                                  retry_after_seconds=exc.retry_after_seconds, stage=call_stage,
                                  cause_message=exc.reason) from exc
    stage = "provider_request"
    started = perf_counter()
    response = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            response = await client.post(url, headers=headers, json=request)
        stage = "http_status"
        response.raise_for_status()
        stage = "decode_json"
        data = response.json()
        stage = "validate_payload"
        if not isinstance(data, dict):
            raise ValueError("Unexpected completion response")
        stage = "extract_choice"
        choice = data["choices"][0]
        content = choice["message"]["content"]
        stage = "validate_content"
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty completion")
        stage = "extract_usage"
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        if not isinstance(prompt_details, dict):
            prompt_details = {}
        if not isinstance(completion_details, dict):
            completion_details = {}
        rate_headers = (groq_rate_limiter.observe(getattr(response, "headers", {}),
                        status=getattr(response, "status_code", None),
                        usage=usage, stage=call_stage,
                        duration_ms=round((perf_counter() - started) * 1000),
                        attempt_number=attempt_number)
                        if settings.llm_provider == "groq" else None)
        return Generation(
            text=content.strip(), model=data.get("model") or model,
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
            reasoning_tokens=_optional_int(completion_details.get("reasoning_tokens")),
            cached_tokens=_optional_int(prompt_details.get("cached_tokens")),
            api_call_id=data.get("id") if isinstance(data.get("id"), str) else None,
            finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
            duration_ms=round((perf_counter() - started) * 1000),
            rate_limit_headers=rate_headers,
        )
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        # Provider response bodies may contain sensitive data; never expose them.
        response = exc.response if isinstance(exc, httpx.HTTPStatusError) else response
        status = getattr(response, "status_code", None) if response is not None else None
        response_headers = getattr(response, "headers", {}) if response is not None else {}
        rate_headers = (groq_rate_limiter.observe(response_headers, status=status,
                        usage=None,
                        stage=call_stage, duration_ms=round((perf_counter() - started) * 1000),
                        attempt_number=attempt_number)
                        if settings.llm_provider == "groq" else None)
        retry_after = retry_after_seconds(response_headers)
        provider_error_code = provider_error_param = provider_error_type = None
        provider_usage = None
        schema_error = None
        if response is not None and callable(getattr(response, "json", None)):
            # Keep only bounded, typed diagnostics. Never retain the provider body,
            # which can echo prompts or other user supplied data.
            try:
                payload = response.json()
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    for name, value in (("code", "provider_error_code"),
                                        ("param", "provider_error_param"),
                                        ("type", "provider_error_type")):
                        field = error.get(name)
                        if isinstance(field, str) and len(field) <= 100:
                            if name == "code": provider_error_code = field
                            elif name == "param": provider_error_param = field
                            else: provider_error_type = field
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    provider_usage = {key: _optional_int(usage.get(key)) for key in
                                      ("prompt_tokens", "completion_tokens", "total_tokens")}
            if status == 400 and (provider_error_code == "json_validate_failed"
                                  or provider_error_param in {"response_format", "messages"}):
                schema_error = "provider_rejected_request_schema"
        # Parsing/shape failures are distinguished from transport and HTTP failures.
        if not isinstance(exc, httpx.HTTPError):
            schema_error = schema_error or {
                "decode_json": "invalid_provider_json",
                "validate_payload": "invalid_provider_payload",
                "extract_choice": "missing_or_invalid_choice",
                "validate_content": "empty_or_invalid_content",
                "extract_usage": "invalid_provider_usage",
            }.get(stage)
        raise GenerationError(
            "LLM request failed", http_status=status,
            error_type=provider_error_type or type(exc).__name__, retry_after_seconds=retry_after,
            stage=stage, cause_message=(type(exc).__name__ if isinstance(exc, httpx.HTTPStatusError)
                                        else str(exc)[:160]),
            traceback_text=traceback.format_exc(), duration_ms=round((perf_counter() - started) * 1000),
            provider_error_code=provider_error_code, provider_error_param=provider_error_param,
            provider_usage=provider_usage,
            request_id=(response_headers.get("x-request-id") or response_headers.get("request-id")) if response_headers else None,
            schema_error=schema_error,
            rate_limit_headers=rate_headers,
        ) from exc


_MAX_GROQ_429_RETRIES = 1
_MAX_GROQ_RETRY_AFTER_SECONDS = 15.0


async def generate(messages: list[dict], settings: Settings, *, call_stage: str = "generation") -> Generation:
    """Retry one short, provider-directed 429 cooldown; never retry local defers."""
    retries = 0
    waited = 0.0
    while True:
        try:
            result = await _generate_once(messages, settings, call_stage=call_stage)
            return Generation(**{**result.__dict__, "retry_count": retries,
                                 "retry_wait_seconds": round(waited, 2)})
        except GenerationError as exc:
            delay = exc.retry_after_seconds
            retryable = (settings.llm_provider == "groq"
                         and exc.http_status == 429
                         and retries < _MAX_GROQ_429_RETRIES
                         and delay is not None and 0 < delay <= _MAX_GROQ_RETRY_AFTER_SECONDS)
            if not retryable:
                exc.retry_count = retries
                exc.retry_wait_seconds = round(waited, 2)
                raise
            groq_rate_limiter.record_bounded_retry(
                stage=call_stage, retry_number=retries + 1, retry_after_seconds=delay,
                provider_error_type=exc.error_type)
            await asyncio.sleep(delay)
            retries += 1
            waited += delay
