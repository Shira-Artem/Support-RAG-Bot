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


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "да"}


def get_settings() -> Settings:
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip(),
        app_name=os.getenv("APP_NAME", "Support RAG Bot").strip(),
        app_url=os.getenv("APP_URL", "http://localhost").strip(),
        show_sources=_bool_env("SHOW_SOURCES", True),
        docs_dir=ROOT_DIR / "data" / "docs",
    )
