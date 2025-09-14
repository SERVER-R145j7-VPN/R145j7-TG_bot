import psutil
import asyncio
import aiohttp
import datetime
from aiogram.client.default import DefaultBotProperties
from config import TG_ID, BOT_TOKEN, SERVERS, SITES_MONITOR, MINER_SCAN
from aiogram import Bot
import os
import re
import ssl
import logging
from logging.handlers import TimedRotatingFileHandler

def get_server_logger(name):
    os.makedirs("logs/monitoring", exist_ok=True)
    logger = logging.getLogger(f"monitoring.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = TimedRotatingFileHandler(
        filename=f"logs/monitoring/{name}.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="MarkdownV2"))

# Правка сообщений для Телеграм
def escape_markdown(text: str) -> str:
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', str(text))

# 🔁 Мониторинг сайтов
async def send_site_status(type, msg: str):
    if type == "problem":
        message = f"🌐 *Проблема с сайтом:*\n\n{escape_markdown(msg)}"
    elif type == "request":
        message = f"🌐 *Результат опроса сайтов:*\n\n{escape_markdown(msg)}"
    try:
        await bot.send_message(
            chat_id=TG_ID,
            text=message,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        print(f"Ошибка при отправке отчета: {e}")

async def check_single_site(url):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, ssl=ssl_context) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"❌ Ошибка при обращении к {url}: {e}")
        return False

# async def monitor_sites():
#     os.makedirs("logs/sites", exist_ok=True)
#     logger = logging.getLogger("monitoring.sites")
#     logger.setLevel(logging.INFO)

#     file_handler = logging.FileHandler("logs/sites/sites.log", encoding="utf-8")
#     formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
#     file_handler.setFormatter(formatter)
#     logger.addHandler(file_handler)

#     hour, minute = map(int, SITES_MONITOR["time"].split(":"))

#     while True:
#         now = datetime.datetime.now()
#         target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

#         if now >= target_time:
#             logger.info("⏰ Запускаем проверку сайтов")
#             for url in SITES_MONITOR["urls"]:
#                 result = await check_single_site(url)
#                 if result:
#                     logger.info(f"✅ {url} — доступен.")
#                 else:
#                     logger.warning(f"❌ {url} — не доступен")
#                     await send_site_status("problem", url)

#             tomorrow = now + datetime.timedelta(days=1)
#             next_run = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
#         else:
#             next_run = target_time

#         seconds_until_next_run = (next_run - datetime.datetime.now()).total_seconds()
#         await asyncio.sleep(seconds_until_next_run)

async def monitor_sites():
    os.makedirs("logs/sites", exist_ok=True)
    logger = logging.getLogger("monitoring.sites")
    logger.setLevel(logging.INFO)

    # не плодим хендлеры при повторных импортах
    if not logger.handlers:
        file_handler = logging.FileHandler("logs/sites/sites.log", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    interval = int(SITES_MONITOR.get("interval", 3600))
    interval = max(30, interval)  # safety: минимум 30 сек
    urls = SITES_MONITOR.get("urls", [])

    # помним предыдущее состояние, чтобы не спамить одинаковыми уведомлениями
    last_status: dict[str, bool] = {}

    while True:
        for url in urls:
            is_ok = await check_single_site(url)

            # лог в файл
            if is_ok:
                logger.info(f"✅ {url} — доступен")
            else:
                logger.warning(f"❌ {url} — недоступен")

            # уведомления только при смене состояния
            prev = last_status.get(url)
            if prev is None:
                # первое наблюдение — шлём только если плохо
                if not is_ok:
                    await send_site_status("problem", url)
            else:
                if prev and not is_ok:
                    # было ок -> стало плохо
                    await send_site_status("problem", url)
                elif (not prev) and is_ok:
                    # было плохо -> стало ок (уведомим о восстановлении)
                    try:
                        await bot.send_message(
                            chat_id=TG_ID,
                            text=f"🌐 *Сайт восстановился:*\n\n{escape_markdown(url)}",
                            parse_mode="MarkdownV2",
                        )
                    except Exception as e:
                        print(f"Ошибка при отправке отчёта о восстановлении: {e}")

            last_status[url] = is_ok

        await asyncio.sleep(interval)

# Информация о процессоре и оперативной памяти
async def send_cpu_ram_status(server, data):
    cpu = data["cpu"]
    ram = data["ram"]
    load = data.get("load", {})

    name = escape_markdown(server["name"])
    cpu_val = escape_markdown(f"{cpu:.1f}%")
    ram_val = escape_markdown(f"{ram:.1f}%")
    load_1 = escape_markdown(f"{load.get('1min', 0):.2f}")
    load_5 = escape_markdown(f"{load.get('5min', 0):.2f}")
    load_15 = escape_markdown(f"{load.get('15min', 0):.2f}")

    status = "🚨 *ПЕРЕГРУЗКА* 🚨" if cpu > server["cpu_ram"]["cpu_high"] or ram > server["cpu_ram"]["ram_high"] else "✅ *НОРМА* ✅"

    message = (
        f"*{name}*\n"
        f"{status}\n\n"
        f"🖥 *CPU*: `{cpu_val}`\n"
        f"💻 *RAM*: `{ram_val}`\n"
        f"📈 *Load Avg*: `{load_1}`, `{load_5}`, `{load_15}`"
    )

    try:
        await bot.send_message(
            chat_id=TG_ID,
            text=message,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        print(f"[{server['name']}] ❌ Ошибка при отправке сообщения: {e}")

async def fetch_cpu_ram_data(server):
    if server["type"] == "local":
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        load1, load5, load15 = psutil.getloadavg()
        return {
            "cpu": cpu,
            "ram": ram,
            "load": {
                "1min": load1,
                "5min": load5,
                "15min": load15
            }
        }

    elif server["type"] == "remote":
        url = f"{server['base_url']}{server['cpu_ram']['url']}?token={server['token']}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            return None

    return None

async def monitor_cpu_ram(server, logger):
    if "cpu_ram" not in server:
        logger.warning(f"[{server['name']}] ⚠️ Отсутствует конфигурация CPU/RAM.")
        return

    cfg = server["cpu_ram"]
    interval = cfg["interval"]["normal"]
    alert = False
    alert_level = 0

    while True:
        data = await fetch_cpu_ram_data(server)

        if not data:
            logger.warning(f"[{server['name']}] ❌ Нет данных от CPU/RAM.")
            await asyncio.sleep(interval)
            continue

        cpu = data["cpu"]
        ram = data["ram"]
        load = data.get("load", {})

        logger.info(
            f"[{server['name']}] CPU={cpu:.1f}% | RAM={ram:.1f}% | "
            f"Load: {load.get('1min', 0):.2f}, {load.get('5min', 0):.2f}, {load.get('15min', 0):.2f}"
        )

        if (cfg["cpu_low"] < cpu < cfg["cpu_high"]) or (cfg["ram_low"] < ram < cfg["ram_high"]):
            interval = cfg["interval"]["warning"]
            # logger.debug(f"[{server['name']}] ⚠️ Состояние WARNING: интервал {interval}")
            alert_level = 0

        if cpu > cfg["cpu_high"] or ram > cfg["ram_high"]:
            interval = cfg["interval"]["critical"]
            # logger.debug(f"[{server['name']}] 🔥 Состояние CRITICAL: интервал {interval}")
            if not alert:
                alert_level += 1
                # logger.debug(f"[{server['name']}] 🚨 Увеличен alert_level: {alert_level}")
            if alert_level >= 3:
                # logger.warning(f"[{server['name']}] 🚨 Превышение порогов 3 раза подряд. Отправка уведомления.")
                await send_cpu_ram_status(server, data)
                alert = True
                alert_level = 0

        if cpu < cfg["cpu_low"] and ram < cfg["ram_low"]:
            interval = cfg["interval"]["normal"]
            alert_level = 0
            if alert:
                # logger.info(f"[{server['name']}] 🔔 Восстановление состояния. CPU/RAM в норме.")
                await send_cpu_ram_status(server, data)
                alert = False

        await asyncio.sleep(interval)

# Информация о дисках
async def send_disk_status(server, percent):
    name = server["name"]
    threshold = server["disk"]["threshold"]

    if percent >= threshold:
        msg = (
            f"💽 *{escape_markdown(name)}*\n"
            f"⚠️ Заполнение диска превысило порог\n"
            f"`{percent:.1f}%` / `{threshold}%`"
        )
    else:
        msg = (
            f"💽 *{escape_markdown(name)}*\n"
            f"✅ С диском всё в порядке\n"
            f"Текущее заполнение: `{percent:.1f}%`"
        )

    try:
        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения о диске: {e}")

async def fetch_disk_data(server):
    if server["type"] == "local":
        usage = psutil.disk_usage('/')
        return usage.percent

    elif server["type"] == "remote":
        try:
            url = f'{server["base_url"]}{server["disk"]["url"]}?token={server["token"]}'
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("disk_percent")
        except Exception as e:
            print(f"[{server['name']}] ❌ Ошибка при получении данных о диске: {e}")
            return None

    return None

async def monitor_disks(server, logger):
    if "disk" not in server:
        return

    alert = False
    interval = server["disk"]["interval"]

    while True:
        try:
            usage = await fetch_disk_data(server)
            if usage is None:
                logger.warning(f"[{server['name']}] ❌ Не удалось получить данные о диске.")
            else:
                logger.info(f"[{server['name']}] 💽 Использование диска: {usage:.1f}%")
                threshold = server["disk"]["threshold"]

                if usage > threshold and not alert:
                    await send_disk_status(server, usage)
                    alert = True

                elif usage <= threshold and alert:
                    await send_disk_status(server, usage)
                    alert = False

        except Exception as e:
            logger.error(f"[{server['name']}] ❌ Ошибка при мониторинге диска: {e}")

        await asyncio.sleep(interval)

# Информация о процессах
async def send_process_status(server, missing=None):
    name = server["name"]
    if missing:
        msg = (
            f"🧩 *{escape_markdown(name)}*\n"
            f"❌ Не запущены процессы:\n"
            + "\n".join(f"• `{escape_markdown(proc)}`" for proc in missing)
        )
    else:
        msg = (
            f"🧩 *{escape_markdown(name)}*\n"
            f"✅ Все необходимые процессы запущены"
        )

    try:
        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения о процессах: {e}")

async def fetch_process_data(server):
    if "processes" not in server or not server["processes"].get("required"):
        return []

    if server["type"] == "local":
        try:
            proc = await asyncio.create_subprocess_shell(
                "systemctl list-units --type=service --state=running --no-pager --no-legend",
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().split("\n")
            services = [line.split()[0].replace(".service", "") for line in lines if line]
            return services
        except Exception as e:
            print(f"[{server['name']}] ❌ Ошибка получения локальных сервисов: {e}")
            return []

    elif server["type"] == "remote":
        try:
            url = f'{server["base_url"]}{server["processes"]["url"]}?token={server["token"]}'
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("running", [])
        except Exception as e:
            print(f"[{server['name']}] ❌ Ошибка получения удалённых сервисов: {e}")
            return []

    return []

async def monitor_processes(server, logger):
    if "processes" not in server or not server["processes"].get("required"):
        return

    interval = server["processes"]["interval"]

    while True:
        try:
            running = await fetch_process_data(server)
            required = server["processes"]["required"]
            missing = [proc for proc in required if proc not in running]

            if missing:
                logger.warning(f"[{server['name']}] ❌ Отсутствуют процессы: {', '.join(missing)}")
                await send_process_status(server, missing)
            else:
                logger.info(f"[{server['name']}] ✅ Все процессы в порядке")

        except Exception as e:
            logger.error(f"[{server['name']}] ❌ Ошибка при мониторинге процессов: {e}")

        await asyncio.sleep(interval)

# Мониторинг майнинговых процессов
async def _get_running_procs_local() -> list[str]:
    names = set()
    try:
        for p in psutil.process_iter(["name", "cmdline"]):
            info = p.info
            if info.get("name"):
                names.add(info["name"].lower())
            if info.get("cmdline"):
                for part in info["cmdline"]:
                    if not part:
                        continue
                    base = os.path.basename(str(part))
                    if base:
                        names.add(base.lower())
    except Exception:
        pass
    return sorted(names)

async def _get_running_procs_remote(server) -> list[str]:
    url = f'{server["base_url"]}{server["processes"]["url"]}?token={server["token"]}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                # пробуем разные ключи
                for key in ("processes", "running", "ps"):
                    if isinstance(data.get(key), list):
                        return [str(x).lower() for x in data[key]]
    except Exception:
        pass
    return []

def _detect_miners(running: list[str], suspects: list[str]) -> list[str]:
    rset = set(running)
    found = set()
    for proc in rset:
        for sig in suspects:
            s = sig.lower()
            if s == proc or s in proc:
                found.add(proc)
    return sorted(found)

async def send_miner_alert(server, found: list[str]):
    name = escape_markdown(server["name"])
    lines = "\n".join(f"• `{escape_markdown(p)}`" for p in found)
    msg = (
        f"⛏️🚨 *Обнаружены майнер-процессы* на *{name}*:\n"
        f"{lines}"
    )
    try:
        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")
    except Exception as e:
        print(f"[{server['name']}] ❌ Ошибка при отправке miner-alert: {e}")

async def monitor_miners(server, logger):
    try:
        interval = int(MINER_SCAN.get("interval", 3600))
        suspects = [s.lower() for s in MINER_SCAN.get("processes", [])]
    except Exception:
        logger.error(f"[{server['name']}] ❌ MINER_SCAN config invalid, мониторинг выключен.")
        return

    if not suspects or interval <= 0:
        logger.info(f"[{server['name']}] ⛏️ MINER_SCAN отключён (пустой список или неверный interval).")
        return

    while True:
        try:
            if server["type"] == "local":
                running = await _get_running_procs_local()
            else:
                if "processes" not in server or "url" not in server["processes"]:
                    logger.warning(f"[{server['name']}] ⛏️ Нет remote /processes API — пропускаю проверку.")
                    await asyncio.sleep(interval)
                    continue
                running = await _get_running_procs_remote(server)

            found = _detect_miners(running, suspects)
            if found:
                logger.warning(f"[{server['name']}] ⛏️🚨 Найдены майнеры: {', '.join(found)}")
                await send_miner_alert(server, found)
            else:
                logger.info(f"[{server['name']}] ⛏️ Проверка майнеров: ничего не найдено.")

        except Exception as e:
            logger.error(f"[{server['name']}] ❌ Ошибка проверки майнеров: {e}")

        await asyncio.sleep(interval)

# Информация о обновлениях
async def send_update_status(server, updates=None):
    name = server["name"]
    if updates:
        msg = (
            f"📦 *{escape_markdown(name)}*\n"
            f"🔄 Есть доступны обновления\\!\n"
        )
    else:
        msg = (
            f"📦 *{escape_markdown(name)}*\n"
            f"✅ Обновлений нет"
        )

    try:
        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения об обновлениях: {e}")

async def fetch_updates(server):
    if server["type"] == "local":
        try:
            proc = await asyncio.create_subprocess_shell(
                "apt list --upgradable 2>/dev/null | tail -n +2",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return bool(stdout.decode().strip())
        except Exception as e:
            print(f"[{server['name']}] ❌ Ошибка при проверке обновлений: {e}")
            return None

    elif server["type"] == "remote":
        try:
            url = f'{server["base_url"]}{server["updates"]["url"]}?token={server["token"]}'
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return bool(data.get("updates"))
        except Exception as e:
            print(f"[{server['name']}] ❌ Ошибка при получении удалённых обновлений: {e}")
            return None

    return None

async def monitor_updates(server, logger):
    if "updates" not in server:
        return

    update_time_str = server["updates"]["time"]
    hour, minute = map(int, update_time_str.split(":"))

    while True:
        now = datetime.datetime.now()
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if now >= target_time:
            # если уже позже — сдвигаем на следующий день
            target_time += datetime.timedelta(days=1)

        sleep_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            updates_available = await fetch_updates(server)
            if updates_available is None:
                logger.warning(f"[{server['name']}] ❌ Не удалось получить данные об обновлениях.")
            elif updates_available:
                logger.warning(f"[{server['name']}] 📦 Есть доступные обновления.")
                await send_update_status(server, updates_available)
            else:
                logger.info(f"[{server['name']}] ✅ Обновлений нет.")
        except Exception as e:
            logger.error(f"[{server['name']}] ❌ Ошибка при мониторинге обновлений: {e}")

# 🔁 Основной мониторинг одного сервера
async def monitor(server):
    logger = get_server_logger(server["name"])
    tasks = [
        asyncio.create_task(monitor_cpu_ram(server, logger)),
        asyncio.create_task(monitor_disks(server, logger)),
        asyncio.create_task(monitor_processes(server, logger)),
        asyncio.create_task(monitor_updates(server, logger)),
        asyncio.create_task(monitor_miners(server, logger)),
    ]
    await asyncio.gather(*tasks)

# 🚀 Запуск всех мониторингов
async def main():
    print("🚀 Мониторинг запущен...")
    tasks = [monitor(server) for server in SERVERS]
    tasks.append(monitor_sites())
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())