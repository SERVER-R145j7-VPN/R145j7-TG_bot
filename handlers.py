"""
Данный файл содержит хэндлеры для работы с кнопками Telegram-бота.
Реализует доступ к категориям мониторинга (CPU/RAM, диск, процессы, обновления, бэкапы, сайты)
и ручные запросы по серверам и сайтам через Telegram-интерфейс.
"""
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from config import TG_ID, SERVERS, SITES_MONITOR
from monitoring import (
    cpu_ram__manual_button,
    disk__manual_button,
    processes__manual_button,
    updates__manual_button,
    backups__manual_button,
    check_single_site, send_site_status,
    escape_markdown
)

CATEGORIES = ["cpu_ram", "disk", "processes", "updates", "backups", "sites"]

def is_authorized(user_id: int) -> bool:
    return user_id == TG_ID

def build_main_menu():
    buttons = [[InlineKeyboardButton(text=cat.upper(), callback_data=f"cat:{cat}")] for cat in CATEGORIES]
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
    if not is_authorized(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    try:
        await message.delete()
    except Exception:
        pass

    await message.answer("📂 Выберите категорию:", reply_markup=build_main_menu())

async def handle_callback_server(callback: CallbackQuery):
    if not is_authorized(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await callback.message.delete()
    data = callback.data

    if data.startswith("cat:"):
        category = data.split(":")[1]
        
        if category == "sites":
            results = []
            for url in SITES_MONITOR["urls"]:
                status = await check_single_site(url)
                emoji = "✅" if status else "❌"
                results.append(f"{emoji} {url}")
            await send_site_status("request", "\n".join(results))
        else:
            await callback.message.answer(
                f"📡 Выберите сервер для {escape_markdown(category.upper())}:",
                reply_markup=build_servers_menu(category)
            )
        return

    category, target = data.split(":", 1)

    arg = "ALL" if target == "ALL" else target

    if category == "cpu_ram":
        await cpu_ram__manual_button(arg)
    elif category == "disk":
        await disk__manual_button(arg)
    elif category == "processes":
        await processes__manual_button(arg)
    elif category == "updates":
        await updates__manual_button(arg)
    elif category == "backups":
        await backups__manual_button(arg)