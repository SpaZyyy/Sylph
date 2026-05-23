from __future__ import annotations

import asyncio
import logging
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig

from config import settings

logger = logging.getLogger(__name__)


class GeminiService:
    """Async wrapper around Google Gemini generative AI API with retry and rate-limit handling."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model
        self._timeout = settings.gemini_timeout
        self._max_retries = settings.gemini_max_retries
        logger.info("GeminiService initialized (model=%s)", self._model)

    async def generate(self, prompt: str) -> Optional[str]:
        """Send a prompt to Gemini and return the text response.

        Implements retry logic with exponential backoff for transient / rate-limit errors.
        Returns ``None`` when no usable answer could be obtained.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._client.models.generate_content,
                        model=self._model,
                        contents=prompt,
                        config=GenerateContentConfig(
                            max_output_tokens=2048,
                            temperature=0.7,
                        ),
                    ),
                    timeout=self._timeout,
                )

                if not response or not response.text:
                    logger.warning("Gemini returned an empty response (attempt %d)", attempt)
                    return None

                text = response.text.strip()
                if len(text) > settings.max_response_length:
                    text = text[: settings.max_response_length - 3] + "..."

                return text

            except asyncio.TimeoutError:
                logger.warning("Gemini request timed out (attempt %d/%d)", attempt, self._max_retries)
                last_exc = asyncio.TimeoutError()

            except Exception as exc:
                last_exc = exc
                is_rate_limit = "429" in str(exc) or "resource_exhausted" in str(exc).lower()

                if is_rate_limit:
                    wait = 2 ** attempt
                    logger.warning("Rate limit hit, backing off %ds (attempt %d/%d)", wait, attempt, self._max_retries)
                    await asyncio.sleep(wait)
                    continue

                logger.error("Gemini API error (attempt %d/%d): %s", attempt, self._max_retries, exc)

            if attempt < self._max_retries:
                await asyncio.sleep(1.5 * attempt)

        logger.error("All %d Gemini attempts failed. Last error: %s", self._max_retries, last_exc)
        return None
