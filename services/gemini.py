from __future__ import annotations

import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Async client for AgentRouter (OpenAI-compatible) with retry and rate-limit handling."""

    def __init__(self) -> None:
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout
        self._max_retries = settings.llm_max_retries
        self._client = AsyncOpenAI(
            api_key=settings.agentrouter_api_key,
            base_url="https://agentrouter.org/v1",
            timeout=float(self._timeout),
        )
        logger.info("LLMService initialized (model=%s)", self._model)

    async def generate(self, prompt: str) -> Optional[str]:
        """Send a prompt to AgentRouter and return the text response.

        Implements retry logic with exponential backoff for transient / rate-limit errors.
        Returns ``None`` when no usable answer could be obtained.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=2048,
                        temperature=0.7,
                    ),
                    timeout=self._timeout,
                )

                if not response.choices:
                    logger.warning("LLM returned no choices (attempt %d)", attempt)
                    return None

                text = (response.choices[0].message.content or "").strip()
                if not text:
                    logger.warning("LLM returned empty content (attempt %d)", attempt)
                    return None

                if len(text) > settings.max_response_length:
                    text = text[: settings.max_response_length - 3] + "..."

                return text

            except asyncio.TimeoutError:
                logger.warning("LLM request timed out (attempt %d/%d)", attempt, self._max_retries)
                last_exc = TimeoutError()

            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_rate_limit = "429" in str(exc) or "rate" in err_str or "resource_exhausted" in err_str

                if is_rate_limit:
                    wait = 5 * attempt
                    logger.warning("Rate limit hit, backing off %ds (attempt %d/%d)", wait, attempt, self._max_retries)
                    await asyncio.sleep(wait)
                    continue

                logger.error("LLM API error (attempt %d/%d): %s", attempt, self._max_retries, exc)

            if attempt < self._max_retries:
                await asyncio.sleep(3.0 * attempt)

        logger.error("All %d LLM attempts failed. Last error: %s", self._max_retries, last_exc)
        return None
