from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from mistralai import Mistral
from mistralai import models as mistral_models

from config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_MESSAGE_LIMIT = 4096
_PREFIX_RESERVE = 200  # room for "Вопрос: ... Ответ: ..." wrapper


class LLMService:
    """Async client for the Mistral API with retry and rate-limit handling."""

    def __init__(self) -> None:
        self._model = settings.llm_model
        self._max_retries = settings.llm_max_retries
        self._system_prompt = settings.system_prompt
        self._max_len = min(
            settings.max_response_length,
            _TELEGRAM_MESSAGE_LIMIT - _PREFIX_RESERVE,
        )
        # Disable the SDK's built-in retries — we manage retries/backoff ourselves.
        self._client = Mistral(
            api_key=settings.mistral_api_key,
            timeout_ms=settings.llm_timeout * 1000,
            retry_config=None,
        )
        logger.info("LLMService initialized (model=%s)", self._model)

    async def generate(self, prompt: str) -> Optional[str]:
        """Send a prompt to the Mistral API and return the text response.

        Returns ``None`` when no usable answer could be obtained.
        """
        last_exc: Optional[Exception] = None
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.chat.complete_async(
                    model=self._model,
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.7,
                )

                if not response or not response.choices:
                    logger.warning("LLM returned no choices (attempt %d)", attempt)
                    return None

                text = (response.choices[0].message.content or "").strip()
                if not text:
                    logger.warning("LLM returned empty content (attempt %d)", attempt)
                    return None

                if len(text) > self._max_len:
                    text = text[: self._max_len - 3] + "..."

                return text

            except mistral_models.SDKError as exc:
                last_exc = exc
                status = getattr(exc, "status_code", 0) or 0
                if status == 429:
                    wait = 5 * attempt
                    logger.warning(
                        "Rate limit (429), backing off %ds (attempt %d/%d)",
                        wait, attempt, self._max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(
                    "Mistral API error %d (attempt %d/%d): %s",
                    status, attempt, self._max_retries, exc,
                )

            except mistral_models.HTTPValidationError as exc:
                # 422 — malformed request; retrying won't help.
                logger.error("Mistral request validation error: %s", exc)
                return None

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "LLM request timed out (attempt %d/%d)",
                    attempt, self._max_retries,
                )

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "LLM connection error (attempt %d/%d): %s",
                    attempt, self._max_retries, exc,
                )

            except Exception as exc:  # noqa: BLE001 - last-resort guard
                last_exc = exc
                logger.exception(
                    "Unexpected LLM error (attempt %d/%d)",
                    attempt, self._max_retries,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(3.0 * attempt)

        logger.error("All %d LLM attempts failed. Last error: %s", self._max_retries, last_exc)
        return None
