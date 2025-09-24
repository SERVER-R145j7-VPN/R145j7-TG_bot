"""
• Telegram-бот для управления и мониторинга
  - Запускается через aiogram.
  - Обрабатывает команды и callback-запросы.
  - Запускает мониторинг серверов и сайтов.
  - Ведёт собственный лог (bot.log) и access-лог (access.log).
"""

import os
import asyncio
import logging
from typing import Union
from logging.handlers import TimedRotatingFileHandler
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from contextlib import suppress
from config import BOT_TOKEN, SERVERS, TG_ID
from monitoring import monitor, monitor_sites, set_bot
from handlers import handle_command_servers, handle_callback_server
from logs_report import handle_logs_command

BOT_VERSION = "2.1.0"

# ===== 🔧 Логирование =====
# Создание папок для логов
os.makedirs("logs/bot", exist_ok=True)
os.makedirs("logs/monitoring", exist_ok=True)

log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Общий консольный вывод
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# --- Логгер бота ---
bot_logger = logging.getLogger("bot")
bot_logger.setLevel(logging.INFO)
bot_logger.propagate = False
_bot_path = os.path.abspath("logs/bot/bot.log")
if not any(getattr(h, "baseFilename", None) == _bot_path for h in bot_logger.handlers):
    bot_file_handler = TimedRotatingFileHandler(
        filename=_bot_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    bot_file_handler.setFormatter(log_formatter)
    bot_logger.addHandler(bot_file_handler)
if console_handler not in bot_logger.handlers:
    bot_logger.addHandler(console_handler)

# --- Логгер доступа ---
access_logger = logging.getLogger("access")
access_logger.setLevel(logging.WARNING)
access_logger.propagate = False
_access_path = os.path.abspath("logs/bot/access.log")
if not any(getattr(h, "baseFilename", None) == _access_path for h in access_logger.handlers):
    access_file_handler = TimedRotatingFileHandler(
        filename=_access_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    access_file_handler.setFormatter(log_formatter)
    access_logger.addHandler(access_file_handler)
if console_handler not in access_logger.handlers:
    access_logger.addHandler(console_handler)

# --- Логгер глобального мониторинга ---
global_logger = logging.getLogger("global_monitoring")
global_logger.setLevel(logging.INFO)
global_logger.propagate = False
_global_path = os.path.abspath("logs/monitoring/global_monitoring.log")
if not any(getattr(h, "baseFilename", None) == _global_path for h in global_logger.handlers):
    global_file_handler = TimedRotatingFileHandler(
        filename=_global_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    global_file_handler.setFormatter(log_formatter)
    global_logger.addHandler(global_file_handler)
if console_handler not in global_logger.handlers:
    global_logger.addHandler(console_handler)

# --- Логгер сайтов ---
sites_logger = logging.getLogger("sites_monitoring")
sites_logger.setLevel(logging.INFO)
sites_logger.propagate = False
_sites_path = os.path.abspath("logs/monitoring/sites_monitoring.log")
if not any(getattr(h, "baseFilename", None) == _sites_path for h in sites_logger.handlers):
    sites_file_handler = TimedRotatingFileHandler(
        filename=_sites_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    sites_file_handler.setFormatter(log_formatter)
    sites_logger.addHandler(sites_file_handler)
if console_handler not in sites_logger.handlers:
    sites_logger.addHandler(console_handler)

# --- Логгеры серверов из конфига ---
for sid, cfg in SERVERS.items():
    srv_logger = logging.getLogger(sid)
    srv_logger.setLevel(logging.INFO)
    srv_logger.propagate = False
    _srv_path = os.path.abspath(f"logs/monitoring/{sid}.log")
    if not any(getattr(h, "baseFilename", None) == _srv_path for h in srv_logger.handlers):
        srv_file_handler = TimedRotatingFileHandler(
            filename=_srv_path,
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8",
        )
        srv_file_handler.setFormatter(log_formatter)
        srv_logger.addHandler(srv_file_handler)
    if console_handler not in srv_logger.handlers:
        srv_logger.addHandler(console_handler)

# --- Проверка доступа ---
async def deny_if_unauthorized(obj: Union[Message, CallbackQuery]) -> bool:
    user = obj.from_user
    uid = getattr(user, "id", None)
    if uid == TG_ID:
        return False

    uname = f"@{getattr(user, 'username', '')}" if getattr(user, "username", None) else "-"
    fname = getattr(user, "first_name", "-")

    # --- что именно сделал пользователь ---
    if isinstance(obj, Message):
        action = obj.text or "<non-text message>"
    else:  # CallbackQuery
        action = obj.data or "<no callback data>"

    access_logger.warning("DENY: uid=%s user=%s %s action=%r", uid, uname, fname, action)

    try:
        if isinstance(obj, Message):
            await obj.answer("⛔ ДОСТУП ЗАБЛОКИРОВАН ⛔")
        else:
            await obj.answer("⛔ ДОСТУП ЗАБЛОКИРОВАН ⛔", show_alert=True)
    except Exception as e:
        access_logger.error("deny_if_unauthorized: notify failed: %s", e)
    return True

# Хэндлер команд
async def handle_version(message: Message):
    if await deny_if_unauthorized(message):
        return
    await message.answer(f"🤖 Bot R145j7 version {BOT_VERSION}")

async def handle_servers(message: Message):
    if await deny_if_unauthorized(message):
        return
    await handle_command_servers(message)

async def handle_logs(message: Message):
    if await deny_if_unauthorized(message):
        return
    await handle_logs_command(message)

# Хэндлер callback-запросов
async def handle_callback(callback: CallbackQuery):
    if await deny_if_unauthorized(callback):
        return
    await handle_callback_server(callback)

async def main():
    bot_logger.info(f"Bot R145j7 v{BOT_VERSION} is starting...")

    async with Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="MarkdownV2")) as bot:
        set_bot(bot)
        dp = Dispatcher()

        # Регистрация хэндлеров (без декораторов)
        dp.message.register(handle_version, Command("version"))
        dp.message.register(handle_servers, Command("server"))
        dp.message.register(handle_logs, Command("logs"))
        dp.callback_query.register(handle_callback)

        # Фоновые задачи
        tasks = [asyncio.create_task(monitor(sid), name=f"monitor:{SERVERS[sid]['name']}") for sid in SERVERS.keys()]
        bot_logger.info(f"Monitoring started for servers: {', '.join([cfg['name'] for cfg in SERVERS.values()])}")
        tasks.append(asyncio.create_task(monitor_sites(), name="monitor:sites"))
        bot_logger.info("Monitoring of sites started")

        try:
            bot_logger.info("Bot polling started")
            await dp.start_polling(bot)
        finally:
            # Корректное завершение фоновых задач
            for t in tasks:
                t.cancel()
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)

            bot_logger.info("Bot stopped.")

if __name__ == "__main__":
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())