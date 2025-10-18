"""
utils.py — вспомогательный модуль проекта.
Содержит функции для настройки централизованного логирования и экранирования Markdown.
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler
from config import LOG_PATHS, LOG_DIRS

"""
Создаёт и настраивает все логгеры проекта.
Логи делятся на категории: bot, access, database, monitoring, sites и индивидуальные для серверов.
"""
def setup_loggers(servers: dict):
    for directory in LOG_DIRS:
        os.makedirs(directory, exist_ok=True)

    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%H:%M:%S"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)

    loggers = {}

    def _create_logger(name: str, path: str, level=logging.INFO):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        abs_path = os.path.abspath(path)
        if not any(getattr(h, "baseFilename", None) == abs_path for h in logger.handlers):
            fh = TimedRotatingFileHandler(
                filename=abs_path,
                when="midnight",
                backupCount=7,
                encoding="utf-8"
            )
            fh.setFormatter(log_formatter)
            logger.addHandler(fh)
        if console_handler not in logger.handlers:
            logger.addHandler(console_handler)
        loggers[name] = logger

    # базовые логи
    _create_logger("bot", LOG_PATHS["bot"])
    _create_logger("access", LOG_PATHS["access"], logging.WARNING)
    _create_logger("database", LOG_PATHS["database"])
    _create_logger("global_monitoring", LOG_PATHS["global_monitoring"])
    _create_logger("sites_monitoring", LOG_PATHS["sites_monitoring"])

    # логи серверов
    for sid in servers.keys():
        server_log_path = os.path.join(LOG_PATHS["servers_dir"], f"{sid}.log")
        _create_logger(sid, server_log_path)

    return loggers

"""
Экранирует специальные символы MarkdownV2 для корректного отображения текста в Telegram.
"""
def escape_markdown(text: str) -> str:
    import re
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', str(text))
