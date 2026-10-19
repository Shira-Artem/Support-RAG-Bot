from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openrouter_api_key: str
    openrouter_model: str
    app_name: str
    app_url: str
    show_sources: bool
    docs_dir: Path
    llm_provider: str = "openrouter"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_reasoning_effort: str = "low"
    expert_telegram_ids: frozenset[int] = frozenset()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "да"}


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
    if provider not in {"openrouter", "groq"}:
        raise ValueError("LLM_PROVIDER must be openrouter or groq")
    ids = frozenset(int(item.strip()) for item in os.getenv("EXPERT_TELEGRAM_IDS", "").split(",") if item.strip())
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip(),
        app_name=os.getenv("APP_NAME", "Support RAG Bot").strip(),
        app_url=os.getenv("APP_URL", "http://localhost").strip(),
        show_sources=_bool_env("SHOW_SOURCES", True),
        docs_dir=ROOT_DIR / "data" / "docs",
        llm_provider=provider,
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        groq_reasoning_effort=os.getenv("GROQ_REASONING_EFFORT", "low").strip().lower(),
        expert_telegram_ids=ids,
    )
