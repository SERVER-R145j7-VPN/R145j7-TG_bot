"""
• Логгер для каждого сервера
  - Отдельный лог-файл на сервер, ротация ежедневно, хранение 7 дней.

• Список серверов в файле конфига
  - Имя сервера, base_url, токен, пороги CPU/RAM, пороги по диску, расписание обновлений.

• Запросы данных с серверов по АПИ
  - /cpu_ram             → загрузка CPU и RAM, load average
  - /disk                → заполнение диска
  - /processes_systemctl → статус системных сервисов
  - /processes_pm2       → статус процессов pm2
  - /updates             → наличие системных обновлений
  - /backup_json         → отчёт о выполнении бэкапов

• Контроль майнеров
  - Поиск подозрительных процессов (через локальный psutil или remote /processes_*).

• Мониторинг сайтов
  - Проверка списка URL, уведомления при падении и восстановлении.
"""
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

# ===== Логгер ===== 
def get_server_logger(server_id: str):
    os.makedirs("logs/monitoring", exist_ok=True)
    logger = logging.getLogger(f"monitoring.{server_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        file_handler = TimedRotatingFileHandler(
            filename=f"logs/monitoring/{server_id}.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# ===== Глобальные логгеры =====
LOGGERS: dict[str, logging.Logger] = {}

def init_loggers():
    # серверные логгеры
    for sid in SERVERS.keys():
        LOGGERS[sid] = get_server_logger(sid)
    LOGGERS["sites"] = get_server_logger("sites")
    LOGGERS["global"] = get_server_logger("global")

# ===== Инициализация бота =====
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="MarkdownV2"))

# ===== Правка сообщений для Телеграм =====
def escape_markdown(text: str) -> str:
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', str(text))

# ===== Мониторинг сайтов =====
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

async def monitor_sites():
    logger = LOGGERS["sites"]

    interval = int(SITES_MONITOR.get("interval", 3600))
    interval = max(30, interval)
    urls = SITES_MONITOR.get("urls", [])
    last_status: dict[str, bool] = {}

    while True:
        for url in urls:
            is_ok = await check_single_site(url)
            if is_ok:
                logger.info(f"✅ {url} — доступен")
            else:
                logger.warning(f"❌ {url} — недоступен")
            prev = last_status.get(url)
            if prev is None:
                if not is_ok:
                    await send_site_status("problem", url)
            else:
                if prev and not is_ok:
                    await send_site_status("problem", url)
                elif (not prev) and is_ok:
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

# ===== CPU/RAM =====
# Глобальное состояние CPU/RAM для всех серверов
CPU_STATE = {sid: {"status": "NORMAL", "level": 0} for sid in SERVERS}

# Маппинг статуса → ключа интервала и метки для сообщения
STATUS = {
    "NORMAL":  {"label": "✅ *НОРМА* ✅",           "interval_key": "normal"},
    "WARNING": {"label": "⚠️ *ПРЕДУПРЕЖДЕНИЕ* ⚠️",  "interval_key": "warning"},
    "ALARM":   {"label": "🚨 *ПЕРЕГРУЗКА* 🚨",      "interval_key": "critical"},
}

# Запрос данных о CPU/RAM с API сервера
async def cpu_ram__fetch_data(server_id):
    logger = LOGGERS[server_id]
    srv = SERVERS[server_id]
    url = f"{srv['base_url']}/cpu_ram?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе CPU/RAM: {e}")

    return None


# Анализ полученных данных и обновление CPU_STATE
async def cpu_ram__analizer(server_id, data):
    logger = LOGGERS[server_id]
    srv = SERVERS[server_id]
    cfg = srv["cpu_ram"]
    intervals = cfg["interval"]

    st = CPU_STATE[server_id]
    status = st["status"]
    level = st["level"]

    try:
        # нет данных — интервал по текущему статусу, без уведомлений
        if not data:
            interval = intervals[STATUS[st["status"]]["interval_key"]]
            return interval, False

        cpu = float(data["cpu"])
        ram = float(data["ram"])

        hi_cpu, lo_cpu = cfg["cpu_high"], cfg["cpu_low"]
        hi_ram, lo_ram = cfg["ram_high"], cfg["ram_low"]

        in_critical = (cpu > hi_cpu) or (ram > hi_ram)
        in_warning  = ((lo_cpu < cpu < hi_cpu) or (lo_ram < ram < hi_ram))
        in_normal   = (cpu < lo_cpu) and (ram < lo_ram)

        notify = False

        if in_critical:
            if status != "ALARM":
                level += 1
                # logger.debug(f"[{srv['name']}] critical sample #{level} (cpu={cpu:.1f} ram={ram:.1f})")
                if level >= 4:
                    st["status"] = "ALARM"
                    level = 0
                    notify = True
                else:
                    st["status"] = "WARNING"
            else:
                st["status"] = "ALARM"
                level = 0

        elif in_warning:
            st["status"] = "WARNING"
            level = 0

        elif in_normal:
            st["status"] = "NORMAL"
            if status == "ALARM":
                notify = True
            level = 0

        st["level"] = level
        interval = intervals[STATUS[st["status"]]["interval_key"]]

        # logger.info(f"[{srv['name']}] status={st['status']} level={level} cpu={cpu:.1f}% ram={ram:.1f}% -> interval={interval}s notify={notify}")
        return interval, notify
    
    except Exception as e:
        logger.error(f"[{server_id}] cpu_ram__analizer:failed -> {e}")
        interval = intervals[STATUS[st["status"]]["interval_key"]]
        return interval, False


# Формирование и отправка сообщения в Telegram
async def cpu_ram__send_message(data_by_server):
    logger = LOGGERS["global"]
    try:
        if not data_by_server:
            logger.error("cpu_ram__send_message: empty data")
            return

        parts = []
        prepared = []

        for sid, sdata in data_by_server.items():
            srv   = SERVERS[sid]
            name  = escape_markdown(srv["name"])
            st    = CPU_STATE[sid]["status"]
            label = STATUS[st]["label"]

            cpu   = sdata["cpu"]
            ram   = sdata["ram"]
            load  = sdata.get("load") or {}

            cpu_val = escape_markdown(f"{cpu:.1f}%")
            ram_val = escape_markdown(f"{ram:.1f}%")
            l1  = escape_markdown(f"{load['1min']:.2f}")
            l5  = escape_markdown(f"{load['5min']:.2f}")
            l15 = escape_markdown(f"{load['15min']:.2f}")

            prepared.append((name, label, cpu_val, ram_val, l1, l5, l15))

        if len(prepared) == 1:
            name, label, cpu_val, ram_val, l1, l5, l15 = prepared[0]
            msg = (
                f"*{name}*\n"
                f"{label}\n\n"
                f"🖥 *CPU*: `{cpu_val} %`\n"
                f"💻 *RAM*: `{ram_val} %`\n"
                f"📈 *Load Avg*: `{l1}`, `{l5}`, `{l15}`"
            )
        else:
            for (name, label, cpu_val, ram_val, l1, l5, l15) in prepared:
                parts.append(
                    f"*{name}*\n"
                    f"{label}\n"
                    f"🖥 CPU: `{cpu_val} %` | 💻 RAM: `{ram_val} %` | 📈 Load: `{l1}`, `{l5}`, `{l15}`"
                )
            msg = "\n\n".join(parts)

        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"cpu_ram__send_message failed -> {e}")


# Автоматический мониторинг CPU/RAM (циклически)
async def cpu_ram__auto_monitoring(server_id):
    logger = LOGGERS[server_id]
    while True:
        try:
            # 1. получаем свежие данные
            data = await cpu_ram__fetch_data(server_id)

            # 2. анализируем
            interval, notify = await cpu_ram__analizer(server_id, data)

            # 3. если нужно — отправляем сообщение
            if notify and data:
                await cpu_ram__send_message({server_id: data})

        except Exception as e:
            logger.error(f"[{server_id}] cpu_ram__auto_monitoring failed -> {e}")
            interval = SERVERS[server_id]["cpu_ram"]["interval"][STATUS[CPU_STATE[server_id]["status"]]["interval_key"]]

        # 4. ждём до следующего опроса
        await asyncio.sleep(interval)


# Ручной запрос CPU/RAM по кнопке (одноразовый)
async def cpu_ram__manual_button(server_id):
    logger = LOGGERS["global"] if server_id == "ALL" else LOGGERS[server_id]
    try:
        # ===== все сервера =====
        if server_id == "ALL":
            data_map = {}
            for sid in SERVERS.keys():
                data = await cpu_ram__fetch_data(sid)
                if data:
                    data_map[sid] = data
                else:
                    logger.warning(f"[{sid}] ❌ Не удалось получить CPU/RAM для ручного запроса")
            if data_map:
                await cpu_ram__send_message(data_map)
            else:
                logger.warning("❌ Ручной запрос CPU/RAM: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await cpu_ram__fetch_data(server_id)
        if data:
            await cpu_ram__send_message({server_id: data})
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос CPU/RAM: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] cpu_ram__manual_button failed -> {e}")

# ===== SSD =====
# Глобальное состояние DISK для всех серверов
DISK_STATE = {sid: {"alert": False} for sid in SERVERS}

# Запрос данных о DISK с API сервера
async def disk__fetch_data(server_id):
    logger = LOGGERS[server_id]
    srv = SERVERS[server_id]
    url = f"{srv['base_url']}/disk?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["disk_percent"])
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе DISK: {e}")

    return None


# Анализ полученных данных и обновление DISK_STATE
async def disk__analyzer(server_id, data):
    logger = LOGGERS[server_id]
    try:
        if data is None:
            return False

        usage = float(data)

        threshold = SERVERS[server_id]["disk"]["threshold"]
        alert = DISK_STATE[server_id]["alert"]

        if usage > threshold and not alert:
            DISK_STATE[server_id]["alert"] = True
            return True

        if usage < threshold and alert:
            DISK_STATE[server_id]["alert"] = False
            return True

        return False

    except Exception as e:
        logger.error(f"[{server_id}] disk__analyzer failed -> {e}")
        return False


# Формирование и отправка сообщения в Telegram
async def disk__send_message(data_by_server):
    logger = LOGGERS["global"]
    try:
        if not data_by_server:
            logger.error("disk__send_message: empty data")
            return

        parts = []
        prepared = []

        for sid, data in data_by_server.items():
            srv   = SERVERS[sid]
            name  = escape_markdown(srv["name"])
            total = srv["disk"]["total_gb"]
            usage = float(data["disk_percent"])
            used  = (total * usage) / 100
            alert = DISK_STATE[sid]["alert"]

            state = "⚠️ *ПРЕВЫШЕНИЕ*" if alert else "✅ *НОРМА*"
            usage_val = escape_markdown(f"{usage:.1f}%")
            used_val  = escape_markdown(f"{used:.1f}/{total} ГБ")

            prepared.append((name, state, used_val, usage_val))

        if len(prepared) == 1:
            name, state, used_val, usage_val = prepared[0]
            msg = (
                f"*{name}*\n"
                f"{state}\n\n"
                f"💽 Диск: `{used_val}` — `{usage_val}`"
            )
        else:
            for (name, state, used_val, usage_val) in prepared:
                parts.append(
                    f"*{name}*\n"
                    f"{state}\n"
                    f"💽 Диск: `{used_val}` — `{usage_val}`"
                )
            msg = "\n\n".join(parts)

        await bot.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"disk__send_message failed -> {e}")


# Автоматический мониторинг DISK (циклически)
async def disk__auto_monitoring(server_id):
    logger = LOGGERS[server_id]
    interval = SERVERS[server_id]["disk"]["interval"]

    while True:
        try:
            # 1. получаем свежие данные
            data = await disk__fetch_data(server_id)

            # 2. анализируем
            notify = await disk__analyzer(server_id, data)

            # 3. если нужно — отправляем сообщение
            if notify and data is not None:
                await disk__send_message({server_id: data})

        except Exception as e:
            logger.error(f"[{server_id}] disk__auto_monitoring failed -> {e}")

        # 4. ждём до следующего опроса
        await asyncio.sleep(interval)


# Ручной запрос DISK по кнопке (одноразовый)
async def disk__manual_button(server_id):
    logger = LOGGERS["global"] if server_id == "ALL" else LOGGERS[server_id]
    try:
        # ===== все сервера =====
        if server_id == "ALL":
            data_map = {}
            for sid in SERVERS.keys():
                data = await disk__fetch_data(sid)
                if data is not None:
                    data_map[sid] = data
                else:
                    logger.warning(f"[{sid}] ❌ Не удалось получить данные о диске для ручного запроса")
            if data_map:
                await disk__send_message(data_map)
            else:
                logger.warning("❌ Ручной запрос DISK: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await disk__fetch_data(server_id)
        if data is not None:
            await disk__send_message({server_id: data})
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос DISK: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] disk__manual_button failed -> {e}")

# ===== Процессы =====
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

# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

# ===== Отслеживание майнеров =====
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

# ===== Обновления =====
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

# ===== Основной код одного сервера =====
async def monitor(server_id: str):
    logger = LOGGERS[server_id]
    tasks = [
        asyncio.create_task(cpu_ram__auto_monitoring(server_id)),
        asyncio.create_task(disk__auto_monitoring(server_id)),
        asyncio.create_task(monitor_processes(server_id)),
        asyncio.create_task(monitor_updates(server_id)),
        asyncio.create_task(monitor_miners(server_id)),
    ]
    await asyncio.gather(*tasks)

# 🚀 ===== Запуск мониторинга =====
async def main():
    print("🚀 Мониторинг запущен...")
    init_loggers()
    tasks = [monitor(server_id) for server_id in SERVERS.keys()]
    tasks.append(monitor_sites())
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())