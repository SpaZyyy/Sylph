from __future__ import annotations

import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.critical("Environment variable %s is not set", name)
        sys.exit(1)
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    # Telegram
    telegram_token: str = field(default_factory=lambda: _require_env("TELEGRAM_BOT_TOKEN"))

    # AgentRouter
    agentrouter_api_key: str = field(default_factory=lambda: _require_env("AGENTROUTER_API_KEY"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-v4-pro"))

    # Limits
    max_query_length: int = field(default_factory=lambda: int(os.getenv("MAX_QUERY_LENGTH", "500")))
    max_response_length: int = field(default_factory=lambda: int(os.getenv("MAX_RESPONSE_LENGTH", "4000")))
    llm_timeout: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "60")))
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "3")))

    # Anti-spam cooldown in seconds
    cooldown_seconds: float = field(default_factory=lambda: float(os.getenv("COOLDOWN_SECONDS", "3.0")))

    # Inline cache time (Telegram caches the result for this many seconds)
    inline_cache_time: int = field(default_factory=lambda: int(os.getenv("INLINE_CACHE_TIME", "5")))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


settings = Settings()
