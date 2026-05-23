from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from config import settings
from services.gemini import GeminiService

logger = logging.getLogger(__name__)

router = Router(name="inline")

_gemini = GeminiService()

# user_id -> last request timestamp (simple anti-spam)
_cooldowns: Dict[int, float] = {}

# Telegram inline result ID must be ≤ 64 bytes
def _result_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _is_on_cooldown(user_id: int) -> bool:
    now = time.monotonic()
    last = _cooldowns.get(user_id, 0.0)
    if now - last < settings.cooldown_seconds:
        return True
    _cooldowns[user_id] = now
    return False


def _escape_markdown(text: str) -> str:
    """Minimal Markdown-safe escaping for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{ch}" if ch in special else ch for ch in text)


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

    # Anti-spam cooldown
    if _is_on_cooldown(user_id):
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id("cooldown"),
                    title="⏳ Подождите немного...",
                    description="Слишком частые запросы",
                    input_message_content=InputTextMessageContent(
                        message_text="Пожалуйста, подождите несколько секунд перед следующим запросом.",
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    logger.info("Inline query from user=%d: %s", user_id, query_text[:80])

    answer_text = await _gemini.generate(query_text)

    if not answer_text:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id("error"),
                    title="❌ Не удалось получить ответ",
                    description="Попробуйте позже или переформулируйте запрос",
                    input_message_content=InputTextMessageContent(
                        message_text="К сожалению, не удалось получить ответ от Gemini. Попробуйте позже.",
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    # Build the result
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
    logger.info("Inline answer sent for user=%d, length=%d", user_id, len(answer_text))
