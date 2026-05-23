from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from handlers import inline_router


def _setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


async def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)

    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(inline_router)

    # Graceful shutdown on SIGINT / SIGTERM
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    logger.info("Starting Sylph bot (inline mode)")

    polling_task = asyncio.create_task(
        dp.start_polling(bot, handle_signals=False)
    )

    await shutdown_event.wait()

    logger.info("Stopping polling…")
    await dp.stop_polling()
    polling_task.cancel()

    await bot.session.close()
    logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
