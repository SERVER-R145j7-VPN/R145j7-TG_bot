"""
• Логгер для каждого сервера
  - Отдельный лог-файл на сервер, ротация ежедневно, хранение 7 дней.

• Список серверов в файле конфига
  - Имя сервера, ip, monitoring_port, токен, пороги CPU/RAM, пороги по диску, расписание обновлений.

• Запросы данных с серверов по АПИ
  - /cpu_ram             → загрузка CPU и RAM, load average
  - /disk                → заполнение диска
  - /processes           → статус системных сервисов
  - /updates             → наличие системных обновлений
  - /backup_json         → отчёт о выполнении бэкапов

• Контроль майнеров
  - Поиск подозрительных процессов (майнеров) в списке запущенных.

• Мониторинг сайтов
  - Проверка списка URL, уведомления при падении и восстановлении.
"""

import asyncio
import aiohttp
import datetime
from config import TG_ID, SERVERS, BOTS_MONITOR, SITES_MONITOR, MINERS
from aiogram import Bot
import ssl
import logging
from utils import escape_markdown

# ===== Бот берём извне (из bot.py) =====
from typing import Optional

bot: Optional[Bot] = None

def set_bot(external_bot: Bot) -> None:
    global bot
    bot = external_bot

# ===== Мониторинг сайтов =====
async def send_site_status(type, msg: str):
    if type == "problem":
        message = f"🌐 *Проблема с сайтом:*\n\n{escape_markdown(msg)}"
    elif type == "request":
        message = f"🌐 *Результат опроса сайтов:*\n\n{escape_markdown(msg)}"
    try:
        b = bot
        if b is None:
            print("Bot instance is not set. Call set_bot() from bot.py first.")
            return
        await b.send_message(
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
    logger = logging.getLogger("sites_monitoring")

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
                        b = bot
                        if b is None:
                            print("Bot instance is not set. Call set_bot() from bot.py first.")
                            return
                        await b.send_message(
                            chat_id=TG_ID,
                            text=f"🌐 *Сайт восстановился:*\n\n{escape_markdown(url)}",
                            parse_mode="MarkdownV2",
                        )
                    except Exception as e:
                        print(f"Ошибка при отправке отчёта о восстановлении: {e}")
            last_status[url] = is_ok
        await asyncio.sleep(interval)








# ===== Мониторинг БОТов =====
# Глобальное состояние БОТОВ для всех серверов
BOTS_STATE = {bot_name: {"success": None, "version": "", "uptime": ""} 
              for srv in BOTS_MONITOR["bots"].values() 
              for bot_name in srv.keys()}

# http://83.229.84.192:58423/bots?token=aZ7@Lp9Vd6qW2!mN4r$X8hJzC1e%KtY&ports=5151,5252

# Запрос данных о БОТах с API сервера
async def bots__fetch_data(server_id):
    print(f"[{server_id}] === bots__fetch_data: старт ===")
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]

    # Проверяем, есть ли боты на этом сервере
    print(f"[{server_id}] Проверка наличия ботов...")
    from config import BOTS_MONITOR
    bots_cfg = BOTS_MONITOR.get("bots", {}).get(server_id)
    if not bots_cfg:
        print(f"[{server_id}] Нет ботов для мониторинга, пропуск")
        logger.info(f"[{server_id}] ⚪ Нет ботов для мониторинга, пропуск")
        return {}

    # Формируем строку портов
    ports = list(bots_cfg.values())
    print(f"[{server_id}] Порты ботов: {ports}")
    ports_param = ",".join(str(p) for p in ports)
    url = f"http://{srv['ip']}:{srv['monitoring_port']}/bots?token={srv['token']}&ports={ports_param}"
    print(f"[{server_id}] URL: {url}")
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print(f"[{server_id}] Открытие сессии aiohttp...")
            async with session.get(url) as resp:
                print(f"[{server_id}] Response status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"[{server_id}] Data: {data}")
                    return data
                else:
                    print(f"[{server_id}] Ошибка при запросе ботов: {resp.status}")
                    logger.warning(f"[{server_id}] ❌ Ошибка при запросе ботов: {resp.status}")
    except Exception as e:
        print(f"[{server_id}] Ошибка при подключении к API ботов: {e}")
        logger.error(f"[{server_id}] ❌ Ошибка при подключении к API ботов: {e}")

    print(f"[{server_id}] Возврат пустого словаря из bots__fetch_data")
    return {}

# Анализ полученных данных и обновление BOTS_STATE
async def bots__analyzer(server_id, data):
    print(f"[{server_id}] === bots__analyzer: старт ===")
    logger = logging.getLogger(server_id)

    def _parse_uptime_tuple(uptime_str: str):
        try:
            m_part, d_part, t_part = uptime_str.strip().split()
            months = int(m_part[:-1])
            days = int(d_part[:-1])
            h, mi, se = map(int, t_part.split(":"))
            return (months, days, h, mi, se)
        except Exception:
            print(f"[{server_id}] Не удалось распарсить uptime: '{uptime_str}'")
            return (0, 0, 0, 0, 0)
    try:
        if not data:
            print(f"[{server_id}] bots__analyzer: пустые данные")
            logger.warning(f"[{server_id}] bots__analyzer: пустые данные")
            return False

        notify = False

        print(f"[{server_id}] Начало анализа {len(data)} ботов")
        # Получаем только ботов для текущего сервера
        bots_cfg = BOTS_MONITOR["bots"].get(server_id, {})
        print(f"[{server_id}] Поиск имени бота только в bots_cfg: {bots_cfg}")
        # проходим по всем ботам, которые пришли с сервера
        for port, bot_info in data.items():
            print(f"[{server_id}] for port={port} ...")
            try:
                success = bool(bot_info.get("success"))
                version = str(bot_info.get("version", "")).strip()
                uptime  = str(bot_info.get("uptime", "")).strip()
                print(f"[{server_id}] Обработка порта {port}: success={success}, version={version}, uptime={uptime}")

                # ищем имя бота по порту только внутри bots_cfg
                bot_name = None
                for name, p in bots_cfg.items():
                    print(f"[{server_id}] Проверка пары name={name}, p={p} для порта {port}")
                    if str(p) == str(port):
                        bot_name = name
                        print(f"[{server_id}] Найден бот: {bot_name} (поиск только внутри сервера)")
                        break

                if not bot_name:
                    print(f"[{server_id}] неизвестный бот на порту {port}")
                    logger.warning(f"[{server_id}] неизвестный бот на порту {port}")
                    continue

                prev_state = BOTS_STATE.get(bot_name, {})
                prev_version = str(prev_state.get("version", "")).strip()
                prev_uptime  = str(prev_state.get("uptime", "")).strip()
                print(f"[{bot_name}] prev_state: {prev_state}")

                # если первый цикл (пустая версия и аптайм) — не уведомляем
                if prev_version == "" and prev_uptime == "":
                    print(f"[{bot_name}] Первый цикл, просто обновляем состояние")
                    BOTS_STATE[bot_name] = {
                        "success": success,
                        "version": version,
                        "uptime": uptime
                    }
                    print(f"[{bot_name}] State updated: {BOTS_STATE[bot_name]}")
                    continue

                # анализ условий для уведомления
                if not success:
                    print(f"[{bot_name}] Trigger reason: success == False")
                    notify = True
                elif version != prev_version:
                    print(f"[{bot_name}] Trigger reason: version changed ({prev_version} -> {version})")
                    notify = True
                elif _parse_uptime_tuple(uptime) < _parse_uptime_tuple(prev_uptime):
                    print(f"[{bot_name}] Trigger reason: uptime уменьшился ({prev_uptime} -> {uptime})")
                    notify = True
                else:
                    print(f"[{bot_name}] Нет условий для уведомления")

                # обновляем текущее состояние
                BOTS_STATE[bot_name] = {
                    "success": success,
                    "version": version,
                    "uptime": uptime
                }
                print(f"[{bot_name}] State updated: {BOTS_STATE[bot_name]}")

            except Exception as e:
                print(f"[{server_id}] bots__analyzer: ошибка при обработке бота на порту {port} -> {e}")
                logger.error(f"[{server_id}] bots__analyzer: ошибка при обработке бота на порту {port} -> {e}")

        print(f"[{server_id}] Анализ завершён, notify={notify}")
        return notify

    except Exception as e:
        print(f"[{server_id}] bots__analyzer failed -> {e}")
        logger.error(f"[{server_id}] bots__analyzer failed -> {e}")
        return False


# Разовый прогон мониторинга ботов по серверу (заглушка)
async def bots__updates__auto_monitoring(server_id: str):
    logger = logging.getLogger(server_id)
    data = await bots__fetch_data(server_id)
    notify = await bots__analyzer(server_id, data)

    bots_cfg = BOTS_MONITOR["bots"].get(server_id, {})
    for bot_name in bots_cfg.keys():
        state = BOTS_STATE.get(bot_name, {})
        success = state.get("success")
        version = state.get("version", "")
        uptime = state.get("uptime", "")
        msg = f"[{bot_name}]: success={success}, version={version}, uptime={uptime}"

        if notify:
            logger.warning(msg)
        else:
            logger.info(msg)

    print(f"[{server_id}] bots__analyzer -> notify={notify}")





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
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]
    url = f"http://{srv['ip']}:{srv['monitoring_port']}/cpu_ram?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа для CPU/RAM: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе CPU/RAM: {e}")

    return None

# Анализ полученных данных и обновление CPU_STATE
async def cpu_ram__analizer(server_id, data):
    logger = logging.getLogger(server_id)
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
async def cpu_ram__send_message(data_by_server, edit_to: tuple[int, int] | None = None):
    logger = logging.getLogger("global_monitoring")
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
                    f"🖥 CPU: `{cpu_val} %` \\| 💻 RAM: `{ram_val} %` \\| 📈 Load: `{l1}`, `{l5}`, `{l15}`"
                )
            msg = "\n\n".join(parts)

        b = bot
        if b is None:
            logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
            return

        if edit_to:
            try:
                await b.edit_message_text(
                    chat_id=edit_to[0],
                    message_id=edit_to[1],
                    text=msg,
                    parse_mode="MarkdownV2",
                )
                return
            except Exception as e:
                logger.warning(f"edit_message_text failed -> {e}; fallback to send")

        await b.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"cpu_ram__send_message failed -> {e}")

# Автоматический мониторинг CPU/RAM (циклически)
async def cpu_ram__auto_monitoring(server_id):
    logger = logging.getLogger(server_id)
    while True:
        try:
            data = await cpu_ram__fetch_data(server_id)
            if data is None:
                logger.warning("CPU-RAM: нет данных (fetch failed)")
                interval = SERVERS[server_id]["cpu_ram"]["interval"][STATUS[CPU_STATE[server_id]["status"]]["interval_key"]]
                await asyncio.sleep(interval)
                continue
            interval, notify = await cpu_ram__analizer(server_id, data)
            if notify and data:
                await cpu_ram__send_message({server_id: data})

            st = CPU_STATE[server_id]
            cpu  = float(data.get("cpu", float("nan")))
            ram  = float(data.get("ram", float("nan")))
            load = data.get("load") or {}
            l1   = float(load.get("1min", float("nan")))
            l5   = float(load.get("5min", float("nan")))
            l15  = float(load.get("15min", float("nan")))

            log_line = (
                f"CPU-RAM: cpu={cpu:.1f} ram={ram:.1f} "
                f"l1={l1:.2f} l5={l5:.2f} l15={l15:.2f} "
                f"status={st['status']} level={st['level']} interval={interval}"
            )

            if st["status"] == "NORMAL":
                logger.info(log_line)
            else:
                logger.warning(log_line)

        except Exception as e:
            logger.error(f"[{server_id}] cpu_ram__auto_monitoring failed -> {e}")
            interval = SERVERS[server_id]["cpu_ram"]["interval"][STATUS[CPU_STATE[server_id]["status"]]["interval_key"]]
        await asyncio.sleep(interval)

# Ручной запрос CPU/RAM по кнопке (одноразовый)
async def cpu_ram__manual_button(server_id):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        try:
            placeholder = await bot.send_message(
                chat_id=TG_ID,
                text="⏳ Ожидание данных",
                parse_mode="MarkdownV2",
            )
            edit_to = (placeholder.chat.id, placeholder.message_id)
        except Exception as e:
            logger.warning(f"cpu_ram__manual_button: placeholder send failed -> {e}")
            edit_to = None

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
                await cpu_ram__send_message(data_map, edit_to=edit_to)
            else:
                logger.warning("❌ Ручной запрос CPU/RAM: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await cpu_ram__fetch_data(server_id)
        if data:
            await cpu_ram__send_message({server_id: data}, edit_to=edit_to)
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос CPU/RAM: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] cpu_ram__manual_button failed -> {e}")

# ===== SSD =====
# Глобальное состояние DISK для всех серверов
DISK_STATE = {sid: {"alert": False} for sid in SERVERS}

# Запрос данных о DISK с API сервера
async def disk__fetch_data(server_id):
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]
    url = f"http://{srv['ip']}:{srv['monitoring_port']}/disk?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["disk_percent"])
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа для DISK: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе DISK: {e}")

    return None

# Анализ полученных данных и обновление DISK_STATE
async def disk__analyzer(server_id, data):
    logger = logging.getLogger(server_id)
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
async def disk__send_message(data_by_server, edit_to: tuple[int, int] | None = None):
    logger = logging.getLogger("global_monitoring")
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
            usage = float(data)
            used  = (total * usage) / 100.0
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

        b = bot
        if b is None:
            logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
            return

        if edit_to:
            try:
                await b.edit_message_text(
                    chat_id=edit_to[0],
                    message_id=edit_to[1],
                    text=msg,
                    parse_mode="MarkdownV2",
                )
                return
            except Exception as e:
                logger.warning(f"edit_message_text failed -> {e}; fallback to send")

        await b.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"disk__send_message failed -> {e}")

# Автоматический мониторинг DISK (циклически)
async def disk__auto_monitoring(server_id):
    logger = logging.getLogger(server_id)
    interval = SERVERS[server_id]["disk"]["interval"]

    while True:
        try:
            data = await disk__fetch_data(server_id)
            if data is None:
                logger.warning("DISK: нет данных (fetch failed)")
                await asyncio.sleep(interval)
                continue

            notify = await disk__analyzer(server_id, data)
            if notify:
                await disk__send_message({server_id: data})

            log_line = f"DISK: usage={data:.1f}%"
            if DISK_STATE[server_id]["alert"]:
                logger.warning(log_line)
            else:
                logger.info(log_line)

        except Exception as e:
            logger.error(f"[{server_id}] disk__auto_monitoring failed -> {e}")
        await asyncio.sleep(interval)

# Ручной запрос DISK по кнопке (одноразовый)
async def disk__manual_button(server_id):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        # плейсхолдер "ожидание"
        try:
            placeholder = await bot.send_message(
                chat_id=TG_ID,
                text="⏳ Ожидание данных",
                parse_mode="MarkdownV2",
            )
            edit_to = (placeholder.chat.id, placeholder.message_id)
        except Exception as e:
            logger.warning(f"disk__manual_button: placeholder send failed -> {e}")
            edit_to = None

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
                await disk__send_message(data_map, edit_to=edit_to)
            else:
                logger.warning("❌ Ручной запрос DISK: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await disk__fetch_data(server_id)
        if data is not None:
            await disk__send_message({server_id: data}, edit_to=edit_to)
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос DISK: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] disk__manual_button failed -> {e}")

# ===== PROCESSES =====
# Глобальное состояние PROCESSES для всех серверов
PROCESSES_STATE = {sid: {"failed": [], "miners": []} for sid in SERVERS}

# Запрос списка запущенных сервисов с API сервера
async def processes__fetch_data(server_id):
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)
    results = []

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ===== systemctl =====
            url_sys = f"http://{srv['ip']}:{srv['monitoring_port']}/processes_systemctl?token={srv['token']}"
            try:
                async with session.get(url_sys) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for svc in data.get("services", []):
                            name   = str(svc.get("name", "")).strip()
                            active = str(svc.get("active")).lower()
                            sub    = str(svc.get("sub")).lower()
                            state  = "failed" if "failed" in (active, sub) else "ok"
                            results.append({"name": name, "source": "SCT", "state": state})
                    else:
                        logger.warning(f"[{server_id}] ❌ Неверный статус ответа для systemctl: {resp.status}")
            except Exception as e:
                logger.error(f"[{server_id}] ❌ Ошибка при запросе systemctl -> {e}")

            # ===== pm2 =====
            url_pm2 = f"http://{srv['ip']}:{srv['monitoring_port']}/processes_pm2?token={srv['token']}"
            try:
                async with session.get(url_pm2) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for proc in data.get("processes", []):
                            name   = str(proc.get("name", "")).strip()
                            status = str(proc.get("status")).lower()
                            state  = "failed" if status == "failed" else "ok"
                            results.append({"name": name, "source": "PM2", "state": state})
                    else:
                        logger.warning(f"[{server_id}] ❌ Неверный статус ответа для pm2: {resp.status}")
            except Exception as e:
                logger.error(f"[{server_id}] ❌ Ошибка при запросе pm2 -> {e}")

    except Exception as e:
        logger.error(f"[{server_id}] ❌ processes__fetch_data global error -> {e}")

    return results

# Анализ полученных данных и обновление PROCESSES_STATE
async def processes__analyzer(server_id, data):
    logger = logging.getLogger(server_id)
    state  = PROCESSES_STATE[server_id]

    try:
        items = data or []
        if not items:
            return False

        # ==== упавшие процессы ====
        failed = [
            {
                "name":   str(it.get("name", "")).strip(),
                "source": str(it.get("source", "")).upper(),
            }
            for it in items
            if str(it.get("state")).lower() == "failed"
        ]

        # ==== процессы-майнеры ====
        miners = [
            {
                "name":   str(it.get("name", "")).strip(),
                "source": str(it.get("source", "")).upper(),
                "state":  str(it.get("state", "")).lower(),
            }
            for it in items
            if str(it.get("name", "")).lower() in [m.lower() for m in MINERS]
        ]

        changed = False

        failed_names = [f["name"] for f in failed]
        prev_failed_names = [f.get("name") for f in state.get("failed", [])]

        if set(failed_names) != set(prev_failed_names):
            state["failed"] = failed
            changed = True

        miners_names = [m["name"] for m in miners]
        prev_names   = [m["name"] for m in state.get("miners", [])]

        if set(miners_names) != set(prev_names):
            state["miners"] = miners
            changed = True

        return changed

    except Exception as e:
        logger.error(f"[{server_id}] processes__analyzer failed -> {e}")
        return False

# Формирование и отправка сообщения в Telegram
async def processes__send_message(server_id, edit_to: tuple[int, int] | None = None):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        targets = SERVERS.keys() if server_id == "ALL" else [server_id]
        parts = []

        for sid in targets:
            name  = escape_markdown(SERVERS[sid]["name"])
            state = PROCESSES_STATE[sid]

            # ---- failed (ожидаем список dict{name,source}) ----
            failed_raw = state.get("failed", []) or []
            failed_bkt = {"SCT": [], "PM2": []}
            for item in failed_raw:
                if isinstance(item, dict):
                    src   = str(item.get("source", "")).upper().strip()
                    fname = str(item.get("name", "")).strip()
                    if src == "SCT":
                        failed_bkt["SCT"].append(fname)
                    elif src == "PM2":
                        failed_bkt["PM2"].append(fname)
                    else:
                        logger.error(f"[{sid}] processes__send_message: unknown failed source '{src}' for '{fname}'")
                else:
                    logger.error(f"[{sid}] processes__send_message: failed item without source: {item!r}")

            # ---- miners (ожидаем список dict{name,source}) ----
            miners_raw = state.get("miners", []) or []
            miners_bkt = {"SCT": [], "PM2": []}
            for m in miners_raw:
                src   = str(m.get("source", "")).upper().strip()
                mname = escape_markdown(str(m.get("name", "")).strip())
                if src == "SCT":
                    miners_bkt["SCT"].append(mname)
                elif src == "PM2":
                    miners_bkt["PM2"].append(mname)
                else:
                    logger.error(f"[{sid}] processes__send_message: unknown miner source '{src}' for '{mname}'")

            any_failed = bool(failed_bkt["SCT"] or failed_bkt["PM2"])
            any_miners = bool(miners_bkt["SCT"] or miners_bkt["PM2"])

            if not any_failed and not any_miners:
                parts.append(f"*{name}*\n✅ Крашнутых сервисов нет\n⛏️ Майнеры не обнаружены")
                continue

            block = [f"*{name}*\n"]

            # ---- Крашнутые ----
            block.append("❌ *Сервисы с ошибками:*" if any_failed else "✅ Ошибок сервисов не обнаружено")
            if any_failed:
                block.append("• SCT:\n" + "\n".join(f"  \\- `{escape_markdown(s)}`" for s in failed_bkt["SCT"]) if failed_bkt["SCT"] else "• SCT: ✅ ок")
                block.append("• PM2:\n" + "\n".join(f"  \\- `{escape_markdown(s)}`" for s in failed_bkt["PM2"]) if failed_bkt["PM2"] else "• PM2: ✅ ок")

            # ---- Майнеры ----
            block.append("⛏️ *⚠️ВНИМАНИЕ⚠️: обнаружены майнеры\\!*" if any_miners else "⛏️ Майнеры не обнаружены")
            if any_miners:
                block.append("• SCT:\n" + "\n".join(f"  \\- `{s}`" for s in miners_bkt["SCT"]) if miners_bkt["SCT"] else "• SCT: ✅ ок")
                block.append("• PM2:\n" + "\n".join(f"  \\- `{s}`" for s in miners_bkt["PM2"]) if miners_bkt["PM2"] else "• PM2: ✅ ок")

            parts.append("\n".join(block))

        msg = "\n\n".join(parts)
        b = bot
        if b is None:
            logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
            return

        if edit_to:
            try:
                await b.edit_message_text(
                    chat_id=edit_to[0],
                    message_id=edit_to[1],
                    text=msg,
                    parse_mode="MarkdownV2",
                )
                return
            except Exception as e:
                logger.warning(f"edit_message_text failed -> {e}; fallback to send")

        await b.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"[{server_id}] processes__send_message failed -> {e}")

# Автоматический мониторинг (циклически)
async def processes__auto_monitoring(server_id):
    logger = logging.getLogger(server_id)
    interval = int(SERVERS[server_id]["processes"]["interval"])
    while True:
        try:
            data = await processes__fetch_data(server_id)
            if data is None:
                logger.warning("PROCESSES: нет данных (fetch failed)")
                await asyncio.sleep(interval)
                continue

            changed = await processes__analyzer(server_id, data)
            if changed:
                await processes__send_message(server_id)

            st = PROCESSES_STATE[server_id]
            failed_raw = st.get("failed", []) or []
            if failed_raw:
                failed_list = []
                for it in failed_raw:
                    if isinstance(it, dict):
                        name = str(it.get("name", "")).strip()
                        src  = str(it.get("source", "")).upper().strip()
                        failed_list.append(f"{name}({src})")
                    else:
                        failed_list.append(str(it))
                logger.warning("PROCESSES FAILED: " + ", ".join(failed_list))
            else:
                logger.info("PROCESSES FAILED: none")

            miners_raw = st.get("miners", []) or []
            if miners_raw:
                miners_list = []
                for it in miners_raw:
                    name = str(it.get("name", "")).strip()
                    src  = str(it.get("source", "")).upper().strip()
                    miners_list.append(f"{name}({src})")
                logger.warning("PROCESSES MINERS: " + ", ".join(miners_list))
            else:
                logger.info("PROCESSES MINERS: none")

        except Exception as e:
            logger.error(f"[{server_id}] processes__auto_monitoring failed -> {e}")
        await asyncio.sleep(interval)

# Ручной запрос PROCESSES по кнопке (одноразовый)
async def processes__manual_button(server_id):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        try:
            b = bot
            if b is None:
                logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
                edit_to = None
            else:
                placeholder = await b.send_message(
                    chat_id=TG_ID,
                    text="⏳ Ожидание данных",
                    parse_mode="MarkdownV2",
                )
                edit_to = (placeholder.chat.id, placeholder.message_id)
        except Exception as e:
            logger.warning(f"processes__manual_button: placeholder send failed -> {e}")
            edit_to = None

        # ===== все сервера =====
        if server_id == "ALL":
            any_data = False
            for sid in SERVERS.keys():
                data = await processes__fetch_data(sid)
                if data is not None:
                    await processes__analyzer(sid, data)
                    any_data = True
                else:
                    logger.warning(f"[{sid}] ❌ Не удалось получить данные о процессах для ручного запроса")
            if any_data:
                await processes__send_message("ALL", edit_to=edit_to)
            else:
                logger.warning("❌ Ручной запрос PROCESS: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await processes__fetch_data(server_id)
        if data is not None:
            await processes__analyzer(server_id, data)
            await processes__send_message(server_id, edit_to=edit_to)
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос PROCESS: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] processes__manual_button failed -> {e}")

# ===== UPDATES =====
# Глобальное состояние UPDATES для всех серверов
UPDATES_STATE = {sid: {"packages": []} for sid in SERVERS}

# Запрос данных об обновлениях с API сервера
async def updates__fetch_data(server_id):
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]
    url = f"http://{srv['ip']}:{srv['monitoring_port']}/updates?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["updates"]
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа для UPDATES: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе UPDATES: {e}")

    return None

# Анализ полученных данных и обновление UPDATES_STATE
async def updates__analyzer(server_id, data):
    logger = logging.getLogger(server_id)
    state  = UPDATES_STATE[server_id]

    try:
        packages = data or []
        if not isinstance(packages, list):
            return False

        if set(packages) != set(state["packages"]):
            state["packages"] = packages
            return True

        return False

    except Exception as e:
        logger.error(f"[{server_id}] updates__analyzer failed -> {e}")
        return False

# Формирование и отправка сообщения в Telegram
async def updates__send_message(server_id, edit_to: tuple[int, int] | None = None):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        targets = SERVERS.keys() if server_id == "ALL" else [server_id]
        parts = []

        for sid in targets:
            name     = escape_markdown(SERVERS[sid]["name"])
            packages = UPDATES_STATE[sid].get("packages", [])

            if not packages:
                parts.append(f"*{name}*\n✅ Обновлений нет")
                continue

            pkg_lines = "\n".join(f"• `{escape_markdown(pkg)}`" for pkg in packages)
            parts.append(f"*{name}*\n📦 Доступны обновления:\n{pkg_lines}")

        msg = "\n\n".join(parts)
        b = bot
        if b is None:
            logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
            return

        if edit_to:
            try:
                await b.edit_message_text(
                    chat_id=edit_to[0],
                    message_id=edit_to[1],
                    text=msg,
                    parse_mode="MarkdownV2",
                )
                return
            except Exception as e:
                logger.warning(f"edit_message_text failed -> {e}; fallback to send")

        await b.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"[{server_id}] updates__send_message failed -> {e}")

# Автоматический мониторинг (циклически)
async def updates__auto_monitoring(server_id):
    logger = logging.getLogger(server_id)
    interval = int(SERVERS[server_id]["updates"]["interval"])
    while True:
        try:
            data = await updates__fetch_data(server_id)
            changed = await updates__analyzer(server_id, data)
            if changed:
                await updates__send_message(server_id)

            packages = UPDATES_STATE[server_id]["packages"]
            if packages:
                logger.warning("UPDATES: " + ", ".join(packages))
            else:
                logger.info("UPDATES: none")    

        except Exception as e:
            logger.error(f"[{server_id}] updates__auto_monitoring failed -> {e}")
        await asyncio.sleep(interval)

# Ручной запрос UPDATES по кнопке (одноразовый)
async def updates__manual_button(server_id):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        # плейсхолдер "ожидание"
        try:
            b = bot
            if b is None:
                logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
                edit_to = None
            else:
                placeholder = await b.send_message(
                    chat_id=TG_ID,
                    text="⏳ Ожидание данных",
                    parse_mode="MarkdownV2",
                )
                edit_to = (placeholder.chat.id, placeholder.message_id)
        except Exception as e:
            logger.warning(f"updates__manual_button: placeholder send failed -> {e}")
            edit_to = None

        # ===== все сервера =====
        if server_id == "ALL":
            any_data = False
            for sid in SERVERS.keys():
                data = await updates__fetch_data(sid)
                if data is not None:
                    await updates__analyzer(sid, data)
                    any_data = True
                else:
                    logger.warning(f"[{sid}] ❌ Не удалось получить данные об обновлениях для ручного запроса")
            if any_data:
                await updates__send_message("ALL", edit_to=edit_to)
            else:
                logger.warning("❌ Ручной запрос UPDATES: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await updates__fetch_data(server_id)
        if data is not None:
            await updates__analyzer(server_id, data)
            await updates__send_message(server_id, edit_to=edit_to)
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос UPDATES: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] updates__manual_button failed -> {e}")

# ===== BACKUPS =====
#  Запрос данных о BACKUPS с API сервера
async def backups__fetch_data(server_id):
    logger = logging.getLogger(server_id)
    srv = SERVERS[server_id]
    url = f"http://{srv['ip']}:{srv['monitoring_port']}/backup_json?token={srv['token']}"
    timeout = aiohttp.ClientTimeout(connect=10, sock_read=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"[{server_id}] ❌ Неверный статус ответа для BACKUP: {resp.status}")
    except Exception as e:
        logger.error(f"[{server_id}] ❌ Ошибка при запросе BACKUP: {e}")

    return None

# Анализ полученных данных
async def backups__analyzer(server_id, data):
    logger = logging.getLogger(server_id)
    try:
        if not data:
            logger.warning(f"[{server_id}] backups__analyzer: пустой ответ")
            return False

        status_ok = str(data.get("status", "")).lower() == "success"
        return not status_ok

    except Exception as e:
        logger.error(f"[{server_id}] backups__analyzer failed -> {e}")
        return False

# Формирование и отправка сообщения в Telegram
async def backups__send_message(server_id, data, edit_to: tuple[int, int] | None = None):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)

    def humanize_seconds(sec: int) -> str:
        try:
            sec = int(sec)
        except Exception:
            return "—"
        if sec < 60:
            return f"{sec} сек"
        m, s = divmod(sec, 60)
        return f"{m} мин {s} сек" if s else f"{m} мин"

    def humanize_size(n: int | float | None) -> str:
        try:
            n = float(n or 0)
        except Exception:
            n = 0.0
        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        i = 0
        while n >= 1024 and i < len(units) - 1:
            n /= 1024.0
            i += 1
        return f"{n:.1f} {units[i]}"

    try:
        # Подготовим набор целей
        if server_id == "ALL":
            items = list(data.items())
        else:
            items = [(server_id, data)]

        parts_out = []

        for sid, payload in items:
            try:
                srv_name = escape_markdown(SERVERS[sid]["name"])
            except Exception:
                srv_name = escape_markdown(str(sid))

            payload = payload or {}

            # Статус
            status_ok = str(payload.get("status", "")).lower() == "success"
            status_line = "✅ *Создание резервной копии данных завершилось успешно*" if status_ok else "❌ *Создание резервной копии данных завершилось неудачно*"

            # Время и длительность
            started = str(payload.get("started_at", "")).strip()
            finished = str(payload.get("finished_at", "")).strip()

            dur_line = None
            if started and finished:
                try:
                    t1 = datetime.datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.datetime.strptime(finished, "%Y-%m-%d %H:%M:%S")
                    duration = max(0, int((t2 - t1).total_seconds()))
                    dur_line = f"🕒 `{escape_markdown(t1.strftime('%d.%m.%Y %H:%M:%S'))}` \\=\\> `{escape_markdown(humanize_seconds(duration))}`"
                except Exception:
                    dur_line = f"🕒 Старт: `{escape_markdown(started)}`, финиш: `{escape_markdown(finished)}`"

            # Части (parts)
            parts_block = []
            parts_dict = payload.get("parts") or {}
            total_size_b = 0
            if isinstance(parts_dict, dict) and parts_dict:
                for key, info in parts_dict.items():
                    name = "База данных" if str(key).lower() == "database" else f"Папка {escape_markdown(str(key))}"
                    ok = bool((info or {}).get("ok"))
                    size_b = (info or {}).get("size_bytes", 0)
                    total_size_b += size_b
                    size_h = humanize_size(size_b)
                    line = f"{'✅' if ok else '❌'} {name} \\=\\> {escape_markdown(size_h)}"
                    parts_block.append(line)
                total_size_h = humanize_size(total_size_b)
                parts_block.append(f"📦 Общий размер бэкапа: {escape_markdown(total_size_h)}")
            else:
                parts_block.append("❌ Нет данных о частях бэкапа")

            # Загрузка (upload)
            up = str(payload.get("upload", "")).lower()
            upload_line = "✅☁️ Загрузка копий в облако прошла успешно" if up == "ok" else "❌☁️ Загрузка копий в облако сорвалась"

            # Собираем блок для одного сервера
            block_lines = [f"*{srv_name}*", status_line]
            if dur_line:
                block_lines.append(dur_line)
            block_lines.extend(parts_block)
            block_lines.append(upload_line)

            parts_out.append("\n".join(block_lines))

        msg = "\n\n".join(parts_out)
        b = bot
        if b is None:
            logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
            return

        if edit_to:
            try:
                await b.edit_message_text(
                    chat_id=edit_to[0],
                    message_id=edit_to[1],
                    text=msg,
                    parse_mode="MarkdownV2",
                )
                return
            except Exception as e:
                logger.warning(f"edit_message_text failed -> {e}; fallback to send")

        await b.send_message(chat_id=TG_ID, text=msg, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"[{server_id}] backups__send_message failed -> {e}")

# Автоматический мониторинг (циклически)
async def backups__auto_monitoring(server_id):
    logger = logging.getLogger(server_id)
    try:
        time_str = SERVERS[server_id]["backups"]["time"]
        hour, minute = map(int, time_str.split(":"))
    except Exception as e:
        logger.error(f"[{server_id}] backups__auto_monitoring: invalid time config -> {e}")
        return

    while True:
        now = datetime.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)

        sleep_seconds = (target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            data = await backups__fetch_data(server_id)
            if data is None:
                logger.warning("BACKUPS: нет данных (fetch failed)")
                continue

            notify = await backups__analyzer(server_id, data)
            if notify:
                await backups__send_message(server_id, data)

            logger.info(f"BACKUPS: {data}")

        except Exception as e:
            logger.error(f"[{server_id}] backups__auto_monitoring failed -> {e}")

# Ручной запрос по кнопке (одноразовый)
async def backups__manual_button(server_id):
    logger = logging.getLogger("global_monitoring") if server_id == "ALL" else logging.getLogger(server_id)
    try:
        # плейсхолдер "ожидание"
        try:
            b = bot
            if b is None:
                logger.error("Bot instance is not set. Call set_bot() from bot.py first.")
                edit_to = None
            else:
                placeholder = await b.send_message(
                    chat_id=TG_ID,
                    text="⏳ Ожидание данных",
                    parse_mode="MarkdownV2",
                )
                edit_to = (placeholder.chat.id, placeholder.message_id)
        except Exception as e:
            logger.warning(f"backups__manual_button: placeholder send failed -> {e}")
            edit_to = None

        # ===== все сервера =====
        if server_id == "ALL":
            data_map = {}
            any_data = False
            for sid in SERVERS.keys():
                data = await backups__fetch_data(sid)
                if data is not None:
                    # анализ (для логов/диагностики), уведомление шлём в любом случае
                    await backups__analyzer(sid, data)
                    data_map[sid] = data
                    any_data = True
                else:
                    logger.warning(f"[{sid}] ❌ Не удалось получить данные о бэкапах для ручного запроса")
            if any_data:
                await backups__send_message("ALL", data_map, edit_to=edit_to)
            else:
                logger.warning("❌ Ручной запрос BACKUPS: ни по одному серверу данных нет")
            return

        # ===== один сервер =====
        data = await backups__fetch_data(server_id)
        if data is not None:
            await backups__analyzer(server_id, data)
            await backups__send_message(server_id, data, edit_to=edit_to)
        else:
            logger.warning(f"[{server_id}] ❌ Ручной запрос BACKUPS: данных нет")

    except Exception as e:
        logger.error(f"[{server_id}] backups__manual_button failed -> {e}")

# ===== Основной код одного сервера =====
async def monitor(server_id: str):
    logger = logging.getLogger(server_id)
    logger.info("=== START MONITORING ===")

    tasks = []

    def start_task(coro, name):
        try:
            t = asyncio.create_task(coro)
            tasks.append(t)
            logger.info(f"✓ Task started: {name}")
        except Exception as e:
            logger.error(f"❌ Failed to start task {name}: {e}")

    start_task(cpu_ram__auto_monitoring(server_id), "cpu_ram")
    start_task(disk__auto_monitoring(server_id), "disk")
    start_task(processes__auto_monitoring(server_id), "processes")
    start_task(updates__auto_monitoring(server_id), "updates")
    start_task(backups__auto_monitoring(server_id), "backups")

    await asyncio.gather(*tasks)

# ===== Запуск мониторинга =====
async def main():
    print("🚀 Мониторинг запущен...")
    logging.getLogger("global_monitoring").info("=== START GLOBAL MONITORING ===")

    tasks = [monitor(server_id) for server_id in SERVERS.keys()]
    tasks.append(monitor_sites())
    logging.getLogger("global_monitoring").info(f"Мониторинг запущен для серверов: {', '.join(SERVERS.keys())}")

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())