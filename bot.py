"""
• Telegram-бот для мониторинга и управления серверами
  - Работает на основе библиотеки aiogram.
  - Использует централизованную систему логирования из utils.setup_loggers().
  - Запускает фоновые задачи мониторинга серверов и сайтов.
  - Обрабатывает команды, кнопки и запросы пользователей.
  - Ведёт системный лог (bot.log) и лог доступа (access.log).
"""

import time
import asyncio
from typing import Union
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from contextlib import suppress
from config import BOT_TOKEN, SERVERS, TG_ID
from utils import setup_loggers
from monitoring import monitor, monitor_sites, set_bot
from handlers import handle_command_servers, handle_callback_server
from logs_report import handle_logs_command

BOT_VERSION = "2.3.0"
start_time = time.time()

# === Логгеры проекта ===
loggers = setup_loggers(SERVERS)
bot_logger = loggers["bot"]
access_logger = loggers["access"]

# ===== 🛠️ Функции и хэндлеры =====
# Форматирование времени работы бота
def format_uptime(seconds: int) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    months, days = divmod(days, 30)
    return f"{months}м. {days}д. {hours:02}:{minutes:02}:{seconds:02}"

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
    try:
        await message.delete()
    except Exception:
        pass
    uptime = format_uptime(time.time() - start_time)
    safe_version = BOT_VERSION.replace('.', '\\.')
    safe_uptime = uptime.replace('.', '\\.')
    await message.answer(
        f"🤖 Bot version: {safe_version}\n"
        f"⏳ Uptime: {safe_uptime}"
    )

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