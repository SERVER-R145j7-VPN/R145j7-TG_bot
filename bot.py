"""
• Telegram-бот для управления и мониторинга
  - Запускается через aiogram.
  - Обрабатывает команды и callback-запросы.
  - Запускает мониторинг серверов и сайтов.
  - Ведёт собственный лог (bot.log) и access-лог (access.log).
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from contextlib import suppress

from config import BOT_TOKEN, SERVERS
from monitoring import monitor, monitor_sites, init_loggers
from handlers import handle_command_servers, handle_callback_server

# 🔧 Логирование
os.makedirs("logs/bot", exist_ok=True)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

file_handler = TimedRotatingFileHandler(
    filename="logs/bot/bot.log", when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

access_logger = logging.getLogger("access")
access_file_handler = TimedRotatingFileHandler(
    filename="logs/bot/access.log", when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
access_file_handler.setFormatter(log_formatter)
access_logger.setLevel(logging.WARNING)
access_logger.addHandler(access_file_handler)


async def handle_servers(message: Message):
    await handle_command_servers(message)

async def handle_callback(callback: CallbackQuery):
    await handle_callback_server(callback)

async def main():
    logger.info("Bot R145j7 is starting...")
    init_loggers()
    logger.info("Monitoring loggers initialized")

    async with Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="MarkdownV2")) as bot:
        dp = Dispatcher()

        # Регистрация хэндлеров (без декораторов)
        dp.message.register(handle_servers, Command("server"))
        dp.callback_query.register(handle_callback)

        # Фоновые задачи
        tasks = [asyncio.create_task(monitor(sid), name=f"monitor:{SERVERS[sid]['name']}") for sid in SERVERS.keys()]
        logger.info(f"Monitoring started for servers: {', '.join([cfg['name'] for cfg in SERVERS.values()])}")
        tasks.append(asyncio.create_task(monitor_sites(), name="monitor:sites"))
        logger.info("Monitoring of sites started")

        try:
            logger.info("Bot polling started")
            await dp.start_polling(bot)
        finally:
            # Корректное завершение фоновых задач
            for t in tasks:
                t.cancel()
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)

            logger.info("Bot stopped.")

if __name__ == "__main__":
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())