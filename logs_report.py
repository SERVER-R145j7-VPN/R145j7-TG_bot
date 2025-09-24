"""
Отчёт по локальным логам бота.
— Папки берутся из config.LOG_DIRS (fallback: logs/bot, logs/monitoring).
— Читаем только файлы с расширением .log (ротационные .log.YYYY-MM-DD игнорим).
— Считаем в каждом файле строки с [WARNING] и [ERROR].
— Формируем MarkdownV2: заголовок папки, под ним строки по файлам:
    • file.log — ⚠️ N | ❌ M   или   • file.log — ✅
"""

import os
import logging
from aiogram.types import Message
from config import LOG_DIRS
from utils import escape_markdown

logger = logging.getLogger("bot")

async def handle_logs_command(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass

    try:
        lines: list[str] = []

        for group_name, dir_path in LOG_DIRS.items():
            header = f"*{escape_markdown(group_name)}*"
            lines.append(header)

            dir_path = os.path.abspath(dir_path)
            if not os.path.isdir(dir_path):
                lines.append("• папка не найдена")
                lines.append("")
                continue

            try:
                entries = sorted(
                    [f for f in os.listdir(dir_path) if f.endswith(".log")],
                    key=str.lower
                )
            except Exception as e:
                logger.error(f"/logs: не удалось прочитать каталог '{dir_path}': {e}")
                lines.append("• ошибка чтения папки")
                lines.append("")
                continue

            if not entries:
                lines.append("• файлы не найдены")
                lines.append("")
                continue

            for fname in entries:
                fpath = os.path.join(dir_path, fname)

                warn_cnt = 0
                err_cnt = 0

                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            if "[WARNING]" in line:
                                warn_cnt += 1
                            if "[ERROR]" in line:
                                err_cnt += 1
                except Exception as e:
                    logger.error(f"/logs: ошибка чтения файла '{fpath}': {e}")
                    lines.append(f"• `{escape_markdown(fname)}` — ошибка чтения файла")
                    continue

                if warn_cnt == 0 and err_cnt == 0:
                    status = "✅"
                else:
                    status = f"⚠️ {warn_cnt} \\| ❌ {err_cnt}"

                lines.append(f"• `{escape_markdown(fname)}` — {status}")
            lines.append("")
        text = "\n".join(lines).rstrip()

        await message.bot.send_message(
            chat_id=message.chat.id,
            text=text if text else "_(пусто)_",
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        try:
            logger.error(f"/logs failed -> {e}")
        finally:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text="Не удалось сформировать отчёт по логам.",
            )