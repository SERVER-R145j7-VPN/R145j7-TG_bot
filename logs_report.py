import logging
from aiogram.types import Message

async def handle_logs_command(message: Message, logger: logging.Logger):
    # здесь позже будет логика анализа логов
    # используем logger для записи инцидентов в logs/bot/bot.log
    try:
        # временная заглушка
        await message.answer("🗂 Логи: заглушка. Скоро будет отчёт.")
    except Exception as e:
        logger.error(f"/logs handler failed: {e}")