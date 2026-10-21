"""One chat-completions interface for the two configured providers."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings


class GenerationError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None,
                 error_type: str | None = None, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.error_type = error_type
        self.retry_after_seconds = retry_after_seconds


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


def _optional_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


async def generate(messages: list[dict], settings: Settings) -> Generation:
    if settings.llm_provider == "groq":
        key, model = settings.groq_api_key, settings.groq_model
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {}
        # GPT-OSS reasoning tokens use the same completion budget as visible output.
        # 2048 leaves room for reasoning while comfortably exceeding short support answers.
        token_limit = {"max_completion_tokens": 2048,
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
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            response = await client.post(url, headers=headers, json={
                "model": model, "messages": messages, "temperature": 0.2, **token_limit,
            })
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected completion response")
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty completion")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        if not isinstance(prompt_details, dict):
            prompt_details = {}
        if not isinstance(completion_details, dict):
            completion_details = {}
        return Generation(
            text=content.strip(), model=data.get("model") or model,
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            total_tokens=_optional_int(usage.get("total_tokens")),
            reasoning_tokens=_optional_int(completion_details.get("reasoning_tokens")),
            cached_tokens=_optional_int(prompt_details.get("cached_tokens")),
            api_call_id=data.get("id") if isinstance(data.get("id"), str) else None,
            finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
        )
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        # Provider response bodies may contain sensitive data; never expose them.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        retry_after = None
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                value = float(exc.response.headers.get('retry-after', ''))
                if 0 <= value <= 86400:
                    retry_after = value
            except ValueError:
                pass
        raise GenerationError("LLM request failed", http_status=status,
                              error_type=type(exc).__name__, retry_after_seconds=retry_after) from exc
