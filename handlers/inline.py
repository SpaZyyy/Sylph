from __future__ import annotations

import html
import logging
import time
import uuid
from typing import Dict, Tuple

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from cachetools import TTLCache

from config import settings
from services.llm import LLMService

logger = logging.getLogger(__name__)

router = Router(name="inline")

_llm = LLMService()

# user_id -> last request monotonic timestamp; entries expire naturally
_cooldowns: TTLCache[int, float] = TTLCache(maxsize=10_000, ttl=settings.cooldown_seconds * 2)

# query_key -> answer_text with TTL
_cache: TTLCache[str, str] = TTLCache(maxsize=1000, ttl=settings.cache_ttl)


def _result_id() -> str:
    return uuid.uuid4().hex


def _cache_key(text: str) -> str:
    return text.strip().lower()


def _is_on_cooldown(user_id: int) -> bool:
    now = time.monotonic()
    last = _cooldowns.get(user_id)
    if last is not None and now - last < settings.cooldown_seconds:
        return True
    _cooldowns[user_id] = now
    return False


def _format_answer(query: str, answer: str) -> str:
    q = html.escape(query)
    a = html.escape(answer)
    return f"<b>Вопрос:</b> {q}\n\n<b>Ответ:</b> {a}"


@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    """Show a clickable button — no LLM call happens here."""
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id

    if not query_text:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id(),
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
                    id=_result_id(),
                    title="Запрос слишком длинный",
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

    if _is_on_cooldown(user_id):
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id(),
                    title="Подождите немного...",
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

    q_escaped = html.escape(query_text)
    await inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id=_result_id(),
                title=f"Получить ответ на: {query_text[:50]}",
                description="Нажмите, чтобы отправить запрос",
                input_message_content=InputTextMessageContent(
                    message_text=f"<b>Вопрос:</b> {q_escaped}\n\n<i>Генерирую ответ...</i>",
                    parse_mode="HTML",
                ),
            )
        ],
        cache_time=1,
        is_personal=True,
    )


@router.chosen_inline_result()
async def handle_chosen_result(chosen: ChosenInlineResult, bot: Bot) -> None:
    """Called when user clicks the button. Calls LLM and edits the posted message."""
    query_text = chosen.query.strip()
    user_id = chosen.from_user.id
    inline_message_id = chosen.inline_message_id

    if not query_text or not inline_message_id:
        return

    logger.info("User %d chose query: %s", user_id, query_text[:80])

    key = _cache_key(query_text)
    cached = _cache.get(key)
    if cached:
        logger.info("Cache hit for query: %s", query_text[:40])
        try:
            await bot.edit_message_text(
                text=_format_answer(query_text, cached),
                inline_message_id=inline_message_id,
                parse_mode="HTML",
            )
        except (TelegramBadRequest, TelegramAPIError) as exc:
            logger.warning("Failed to edit inline message: %s", exc)
        return

    answer_text = await _llm.generate(query_text)

    if not answer_text:
        try:
            await bot.edit_message_text(
                text=_format_answer(query_text, "Не удалось получить ответ. Попробуйте позже."),
                inline_message_id=inline_message_id,
                parse_mode="HTML",
            )
        except (TelegramBadRequest, TelegramAPIError) as exc:
            logger.warning("Failed to edit inline message: %s", exc)
        return

    _cache[key] = answer_text

    try:
        await bot.edit_message_text(
            text=_format_answer(query_text, answer_text),
            inline_message_id=inline_message_id,
            parse_mode="HTML",
        )
    except (TelegramBadRequest, TelegramAPIError) as exc:
        logger.warning("Failed to edit inline message: %s", exc)
        return

    logger.info("Answer sent for user=%d, length=%d", user_id, len(answer_text))
