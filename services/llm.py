from __future__ import annotations

import asyncio
import logging
from typing import Optional

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from config import get_settings

logger = logging.getLogger(__name__)


class LLMService:
    """Async client for Mistral API (OpenAI-compatible) with retry and rate-limit handling."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.llm_model
        self._max_retries = settings.llm_max_retries
        self._system_prompt = settings.system_prompt
        self._max_len = settings.max_response_length
        self._max_tokens = settings.max_tokens
        self._client = AsyncOpenAI(
            api_key=settings.mistral_api_key,
            base_url="https://api.mistral.ai/v1",
            timeout=float(settings.llm_timeout),
        )
        logger.info("LLMService initialized (model=%s)", self._model)

    async def generate(self, prompt: str) -> Optional[str]:
        """Send a prompt to Mistral and return the text response.

        Returns ``None`` when no usable answer could be obtained.
        """
        last_exc: Optional[Exception] = None
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=0.7,
                )

                if not response.choices:
                    logger.warning("LLM returned no choices (attempt %d)", attempt)
                    return None

                text = (response.choices[0].message.content or "").strip()
                if not text:
                    logger.warning("LLM returned empty content (attempt %d)", attempt)
                    return None

                if len(text) > self._max_len:
                    text = text[: self._max_len - 3] + "..."

                return text

            except RateLimitError as exc:
                last_exc = exc
                wait = 5 * attempt
                logger.warning(
                    "Rate limit (429), backing off %ds (attempt %d/%d)",
                    wait, attempt, self._max_retries,
                )
                await asyncio.sleep(wait)
                continue

            except APITimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "LLM request timed out (attempt %d/%d)",
                    attempt, self._max_retries,
                )

            except APIConnectionError as exc:
                last_exc = exc
                logger.warning(
                    "LLM connection error (attempt %d/%d): %s",
                    attempt, self._max_retries, exc,
                )

            except APIError as exc:
                last_exc = exc
                logger.error(
                    "LLM API error %d (attempt %d/%d): %s",
                    getattr(exc, 'status_code', None) or 0, attempt, self._max_retries, exc,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(3.0 * attempt)

        logger.error("All %d LLM attempts failed. Last error: %s", self._max_retries, last_exc)
        return None
