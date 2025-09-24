"""
Данный файл содержит хэндлеры для работы с кнопками Telegram-бота.
Реализует доступ к категориям мониторинга (CPU/RAM, диск, процессы, обновления, бэкапы, сайты)
и ручные запросы по серверам и сайтам через Telegram-интерфейс.
"""
import logging
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from config import CATEGORIES, SERVERS, SITES_MONITOR
from monitoring import (
    cpu_ram__manual_button,
    disk__manual_button,
    processes__manual_button,
    updates__manual_button,
    backups__manual_button,
    check_single_site, send_site_status,
    escape_markdown
)

logger = logging.getLogger('bot')

def build_main_menu():
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"cat:{cat}")] for cat, name in CATEGORIES.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_servers_menu(category: str):
    if category == "sites":
        return None
    # show server names, but callback carries server_id (sid)
    buttons = [
        [InlineKeyboardButton(text=cfg["name"], callback_data=f"{category}:{sid}")]
        for sid, cfg in SERVERS.items()
    ]
    buttons.append([InlineKeyboardButton(text="Все", callback_data=f"{category}:ALL")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def handle_command_servers(message: Message):

    try:
        await message.delete()
    except Exception as e:
        logger.warning('handle_command_servers: delete failed: %s', e)

    try:
        await message.answer("📂 Выберите категорию:", reply_markup=build_main_menu())
    except Exception as e:
        logger.error('handle_command_servers: answer failed: %s', e)

async def handle_callback_server(callback: CallbackQuery):

    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning('handle_callback_server: delete failed: %s', e)
    data = callback.data

    if not data:
        logger.warning('handle_callback_server: empty callback.data')
        return

    if data.startswith("cat:"):
        category = data.split(":")[1]
        
        if category == "sites":
            try:
                urls = SITES_MONITOR.get('urls', [])
                if not isinstance(urls, list):
                    raise ValueError('SITES_MONITOR["urls"] must be a list')
                results = []
                for url in urls:
                    try:
                        status = await check_single_site(url)
                        emoji = "✅" if status else "❌"
                        results.append(f"{emoji} {url}")
                    except Exception as e:
                        logger.error('handle_callback_server: site check failed for %s: %s', url, e)
                        results.append(f"❌ {url}")
                await send_site_status("request", "\n".join(results))
            except Exception as e:
                logger.error('handle_callback_server: sites block failed: %s', e)
        else:
            try:
                label = CATEGORIES.get(category, category.upper())
                await callback.message.answer(
                    f"📡 Выберите сервер для {escape_markdown(label)}:",
                    reply_markup=build_servers_menu(category)
                )
            except Exception as e:
                logger.error('handle_callback_server: answer failed: %s', e)
        return

    try:
        category, target = data.split(":", 1)
    except Exception as e:
        logger.warning('handle_callback_server: bad callback data: %r (%s)', data, e)
        return

    arg = "ALL" if target == "ALL" else target

    if category == "cpu_ram":
        try:
            await cpu_ram__manual_button(arg)
        except Exception as e:
            logger.error('cpu_ram__manual_button failed: %s', e)
    elif category == "disk":
        try:
            await disk__manual_button(arg)
        except Exception as e:
            logger.error('disk__manual_button failed: %s', e)
    elif category == "processes":
        try:
            await processes__manual_button(arg)
        except Exception as e:
            logger.error('processes__manual_button failed: %s', e)
    elif category == "updates":
        try:
            await updates__manual_button(arg)
        except Exception as e:
            logger.error('updates__manual_button failed: %s', e)
    elif category == "backups":
        try:
            await backups__manual_button(arg)
        except Exception as e:
            logger.error('backups__manual_button failed: %s', e)