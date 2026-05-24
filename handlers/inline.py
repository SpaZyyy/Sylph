from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, Tuple

from aiogram import Bot, Router
from aiogram.types import (
    ChosenInlineResult,
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

# Simple response cache: query_text -> answer_text
_cache: Dict[str, str] = {}


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
    """Show a clickable button — no LLM call happens here."""
    query_text = inline_query.query.strip()

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

    await inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id=_result_id("ask_" + query_text),
                title=f"🔍 Получить ответ на: {query_text[:50]}",
                description="Нажмите, чтобы отправить запрос",
                input_message_content=InputTextMessageContent(
                    message_text=f"**Вопрос:** {query_text}\n\n⏳ _Генерирую ответ..._",
                    parse_mode="Markdown",
                ),
            )
        ],
        cache_time=1,
        is_personal=True,
    )


@router.chosen_inline_result()
async def handle_chosen_result(chosen: ChosenInlineResult, bot: Bot) -> None:
    """Called when user clicks the button. Now we call the LLM and edit the message."""
    query_text = chosen.query.strip()
    user_id = chosen.from_user.id
    inline_message_id = chosen.inline_message_id

    if not query_text or not inline_message_id:
        return

    if _is_on_cooldown(user_id):
        await bot.edit_message_text(
            text="⏳ Слишком частые запросы. Подождите несколько секунд.",
            inline_message_id=inline_message_id,
        )
        return

    logger.info("User %d chose query: %s", user_id, query_text[:80])

    # Check cache
    cached = _cache.get(query_text)
    if cached:
        logger.info("Cache hit for query: %s", query_text[:40])
        await bot.edit_message_text(
            text=f"**Вопрос:** {query_text}\n\n**Ответ:** {cached}",
            inline_message_id=inline_message_id,
            parse_mode="Markdown",
        )
        return

    answer_text = await _llm.generate(query_text)

    if not answer_text:
        await bot.edit_message_text(
            text=f"**Вопрос:** {query_text}\n\n❌ Не удалось получить ответ. Попробуйте позже.",
            inline_message_id=inline_message_id,
            parse_mode="Markdown",
        )
        return

    # Cache the answer
    _cache[query_text] = answer_text
    if len(_cache) > 500:
        oldest = next(iter(_cache))
        del _cache[oldest]

    await bot.edit_message_text(
        text=f"**Вопрос:** {query_text}\n\n**Ответ:** {answer_text}",
        inline_message_id=inline_message_id,
        parse_mode="Markdown",
    )
    logger.info("Answer sent for user=%d, length=%d", user_id, len(answer_text))
