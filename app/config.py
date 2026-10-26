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
    rag_engine: str = "legacy"
    source_first_telegram_ids: frozenset[int] = frozenset()
    ai_coordinator_enabled: bool = False


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
    engine = os.getenv("RAG_ENGINE", "legacy").strip().lower()
    if engine not in {"legacy", "source_first"}:
        raise ValueError("RAG_ENGINE must be legacy or source_first")
    configured_source_ids = os.getenv("SOURCE_FIRST_TELEGRAM_IDS")
    # User explicitly authorized reusing the existing Telegram ID list. The
    # process can opt into it with only RAG_ENGINE=source_first; no ID is copied
    # into code, documentation, or logs.
    source_id_value = configured_source_ids if configured_source_ids is not None else (
        os.getenv("EXPERT_TELEGRAM_IDS", "") if engine == "source_first" else "")
    source_first_ids = frozenset(int(item.strip()) for item in source_id_value.split(",") if item.strip())
    if engine == "source_first" and not source_first_ids:
        raise ValueError("SOURCE_FIRST_TELEGRAM_IDS is required when RAG_ENGINE=source_first")
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
        rag_engine=engine,
        source_first_telegram_ids=source_first_ids,
        ai_coordinator_enabled=_bool_env("AI_COORDINATOR_ENABLED", False),
    )


def should_use_source_first(settings: Settings, telegram_user_id: int) -> bool:
    """The opt-in engine and explicit Telegram allowlist are both required."""
    return settings.rag_engine == "source_first" and telegram_user_id in settings.source_first_telegram_ids


def should_use_ai_coordinator(settings: Settings, telegram_user_id: int) -> bool:
    """Coordinator is an opt-in variant of the existing Source-first route."""
    return bool(settings.ai_coordinator_enabled and should_use_source_first(settings, telegram_user_id))
