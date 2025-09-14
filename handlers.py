from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from config import TG_ID, SERVERS, SITES_MONITOR
from monitoring import (
    fetch_cpu_ram_data, send_cpu_ram_status,
    fetch_disk_data, send_disk_status,
    fetch_process_data, send_process_status,
    fetch_updates, send_update_status,
    check_single_site, send_site_status,
    escape_markdown
)

CATEGORIES = ["cpu_ram", "disk", "processes", "updates", "sites"]

def is_authorized(user_id: int) -> bool:
    return user_id == TG_ID

def get_server_by_name(name: str):
    return next((s for s in SERVERS if s["name"] == name), None)

def build_main_menu():
    buttons = [[InlineKeyboardButton(text=cat.upper(), callback_data=f"cat:{cat}")] for cat in CATEGORIES]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_servers_menu(category: str):
    if category == "sites":
        return None
    buttons = [[InlineKeyboardButton(text=s["name"], callback_data=f"{category}:{s['name']}")] for s in SERVERS]
    buttons.append([InlineKeyboardButton(text="Все", callback_data=f"{category}:all")])
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

    category, target = data.split(":")
    servers = SERVERS if target == "all" else [get_server_by_name(target)]

    for server in servers:
        if category == "cpu_ram":
            data = await fetch_cpu_ram_data(server)
            if data:
                await send_cpu_ram_status(server, data)

        elif category == "disk":
            percent = await fetch_disk_data(server)
            if percent is not None:
                await send_disk_status(server, percent)

        elif category == "processes":
            if "processes" in server and server["processes"].get("required"):
                running = await fetch_process_data(server)
                required = server["processes"]["required"]
                missing = [p for p in required if p not in running]
                await send_process_status(server, missing)

        elif category == "updates":
            if "updates" in server:
                updates = await fetch_updates(server)
                await send_update_status(server, updates)