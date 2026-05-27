from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class ConfigError(Exception):
    """Raised when a required config value is missing or invalid."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Environment variable {name} is not set")
    return value


def _int_env(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid integer") from exc


def _float_env(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid float") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    # Telegram
    telegram_token: str = field(default_factory=lambda: _require_env("TELEGRAM_BOT_TOKEN"))

    # AgentRouter
    agentrouter_api_key: str = field(default_factory=lambda: _require_env("AGENTROUTER_API_KEY"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-v4-pro"))

    # System prompt
    system_prompt: str = field(
        default_factory=lambda: os.getenv(
            "SYSTEM_PROMPT",
            "You are Sylph, a helpful and concise assistant. "
            "Answer in the same language the user writes in. "
            "Keep answers compact — they will be shown in a Telegram message.",
        )
    )

    # Limits
    max_query_length: int = field(default_factory=lambda: _int_env("MAX_QUERY_LENGTH", "500"))
    max_response_length: int = field(default_factory=lambda: _int_env("MAX_RESPONSE_LENGTH", "3800"))
    llm_timeout: int = field(default_factory=lambda: _int_env("LLM_TIMEOUT", "60"))
    llm_max_retries: int = field(default_factory=lambda: _int_env("LLM_MAX_RETRIES", "3"))

    # Anti-spam cooldown in seconds
    cooldown_seconds: float = field(default_factory=lambda: _float_env("COOLDOWN_SECONDS", "3.0"))

    # Inline cache time (Telegram caches the result for this many seconds)
    inline_cache_time: int = field(default_factory=lambda: _int_env("INLINE_CACHE_TIME", "5"))

    # Cache TTL in seconds
    cache_ttl: int = field(default_factory=lambda: _int_env("CACHE_TTL", "300"))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


settings = Settings()
