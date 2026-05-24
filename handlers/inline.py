from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Dict, Optional, Tuple

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from config import settings
from services.gemini import LLMService

logger = logging.getLogger(__name__)

router = Router(name="inline")

_llm = LLMService()

# user_id -> last request timestamp (simple anti-spam)
_cooldowns: Dict[int, float] = {}

# Debounce: user_id -> (query_text, asyncio.Task)
_pending: Dict[int, Tuple[str, asyncio.Task[None]]] = {}

# Simple response cache: (user_id, query_text) -> answer_text
_cache: Dict[Tuple[int, str], str] = {}

_DEBOUNCE_SECONDS = 1.5


def _result_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _is_on_cooldown(user_id: int) -> bool:
    now = time.monotonic()
    last = _cooldowns.get(user_id, 0.0)
    if now - last < settings.cooldown_seconds:
        return True
    _cooldowns[user_id] = now
    return False


@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id

    # Empty query — show a hint
    if not query_text:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id("hint"),
                    title="Задайте вопрос",
                    description="Введите текст запроса после @имя_бота",
                    input_message_content=InputTextMessageContent(
                        message_text="Пожалуйста, введите запрос после @имя_бота",
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    # Query too long
    if len(query_text) > settings.max_query_length:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id("too_long"),
                    title="⚠️ Запрос слишком длинный",
                    description=f"Максимум {settings.max_query_length} символов",
                    input_message_content=InputTextMessageContent(
                        message_text=f"Запрос слишком длинный (макс. {settings.max_query_length} символов).",
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    # Check cache first — if we already have an answer for this exact query, return it
    cache_key = (user_id, query_text)
    cached = _cache.get(cache_key)
    if cached:
        logger.info("Cache hit for user=%d query=%s", user_id, query_text[:40])
        await _send_answer(inline_query, query_text, cached)
        return

    # Cancel any pending debounce task for this user
    if user_id in _pending:
        old_query, old_task = _pending[user_id]
        if not old_task.done():
            old_task.cancel()

    # Show "typing" placeholder while waiting for debounce
    await inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id=_result_id("loading_" + query_text[:32]),
                title="⏳ Печатаю ответ...",
                description="Подождите, пока я закончу думать",
                input_message_content=InputTextMessageContent(
                    message_text=f"**Вопрос:** {query_text}\n\n_Генерирую ответ..._",
                    parse_mode="Markdown",
                ),
            )
        ],
        cache_time=1,
        is_personal=True,
    )

    # Schedule debounced LLM call
    task = asyncio.create_task(_debounced_generate(user_id, query_text))
    _pending[user_id] = (query_text, task)


async def _debounced_generate(user_id: int, query_text: str) -> None:
    """Wait for debounce period, then call LLM and cache the result."""
    try:
        await asyncio.sleep(_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return

    # After debounce, check if this is still the latest query for this user
    if user_id in _pending:
        current_query, _ = _pending[user_id]
        if current_query != query_text:
            return

    if _is_on_cooldown(user_id):
        return

    logger.info("Generating answer for user=%d: %s", user_id, query_text[:80])

    answer_text = await _llm.generate(query_text)
    if answer_text:
        _cache[(user_id, query_text)] = answer_text
        # Limit cache size
        if len(_cache) > 500:
            oldest = next(iter(_cache))
            del _cache[oldest]

    # Clean up pending
    _pending.pop(user_id, None)


async def _send_answer(
    inline_query: InlineQuery,
    query_text: str,
    answer_text: str,
) -> None:
    short_desc = answer_text[:100] + ("..." if len(answer_text) > 100 else "")

    results = [
        InlineQueryResultArticle(
            id=_result_id(query_text + answer_text[:64]),
            title=f"Ответ на: {query_text[:50]}",
            description=short_desc,
            input_message_content=InputTextMessageContent(
                message_text=f"**Вопрос:** {query_text}\n\n**Ответ:** {answer_text}",
                parse_mode="Markdown",
            ),
        ),
    ]

    await inline_query.answer(
        results=results,
        cache_time=settings.inline_cache_time,
        is_personal=True,
    )
    logger.info("Inline answer sent for user=%d, length=%d", inline_query.from_user.id, len(answer_text))
