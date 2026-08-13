from __future__ import annotations

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


async def ask_openrouter(
    *,
    api_key: str,
    model: str,
    app_name: str,
    app_url: str,
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> str:
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is empty")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": app_url or "http://localhost",
        "X-OpenRouter-Title": app_name or "Support RAG Bot",
    }

    payload = {
        "model": model or "openrouter/auto",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    timeout = httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        raise OpenRouterError(f"OpenRouter HTTP {response.status_code}: {response.text[:1000]}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response: {data}") from exc
