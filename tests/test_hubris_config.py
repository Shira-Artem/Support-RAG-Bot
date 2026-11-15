from __future__ import annotations

import pytest

from app import config


def test_hubris_settings_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", " Hubris ")
    monkeypatch.setenv("HUBRIS_API_KEY", " local-test-key ")
    monkeypatch.setenv("HUBRIS_BASE_URL", "https://api.hubris.pw/v1/ ")
    monkeypatch.setenv("HUBRIS_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("HUBRIS_REASONING_EFFORT", "MEDIUM")

    settings = config.get_settings()
    assert settings.llm_provider == "hubris"
    assert settings.hubris_api_key == "local-test-key"
    assert settings.hubris_base_url == "https://api.hubris.pw/v1"
    assert settings.hubris_model == "openai/gpt-oss-20b"
    assert settings.hubris_reasoning_effort == "medium"


def test_groq_provider_remains_supported(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-local-test")
    settings = config.get_settings()
    assert settings.llm_provider == "groq"
    assert settings.groq_api_key == "groq-local-test"
    assert settings.groq_model == "openai/gpt-oss-20b"


def test_unknown_provider_has_updated_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="openrouter, groq or hubris"):
        config.get_settings()
