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
    """
    Обработчик /logs.
    Пишет ошибки в общий логгер "bot".
    """
    # попытка убрать команду из чата — тихо игнорим ошибки
    try:
        await message.delete()
    except Exception:
        pass

    try:
        lines: list[str] = []

        for group_name, dir_path in LOG_DIRS.items():
            # Заголовок группы
            header = f"*{escape_markdown(group_name)}*"
            lines.append(header)

            dir_path = os.path.abspath(dir_path)
            if not os.path.isdir(dir_path):
                lines.append("• _нет такой папки_")
                lines.append("")  # пустая строка между группами
                continue

            # собираем только *.log (текущие файлы), ротационные архивы пропускаем
            try:
                entries = sorted(
                    [f for f in os.listdir(dir_path) if f.endswith(".log")],
                    key=str.lower
                )
            except Exception as e:
                logger.error(f"/logs: не удалось прочитать каталог '{dir_path}': {e}")
                lines.append("• _ошибка чтения папки_")
                lines.append("")
                continue

            if not entries:
                lines.append("• _файлов нет_")
                lines.append("")
                continue

            for fname in entries:
                fpath = os.path.join(dir_path, fname)

                warn_cnt = 0
                err_cnt = 0

                # читаем построчно, чтобы не дёргать память
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            # строго ищем маркеры в строке
                            if "[WARNING]" in line:
                                warn_cnt += 1
                            if "[ERROR]" in line:
                                err_cnt += 1
                except Exception as e:
                    logger.error(f"/logs: ошибка чтения файла '{fpath}': {e}")
                    lines.append(f"• `{escape_markdown(fname)}` — _ошибка чтения_")
                    continue

                if warn_cnt == 0 and err_cnt == 0:
                    status = "✅"
                else:
                    status = f"⚠️ {warn_cnt} \\| ❌ {err_cnt}"

                lines.append(f"• `{escape_markdown(fname)}` — {status}")

            lines.append("")  # пустая строка между группами

        text = "\n".join(lines).rstrip()

        # отправляем отчёт в чат
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=text if text else "_(пусто)_",
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        # в случае падения — логируем в переданный логгер и отправляем краткую ошибку в чат
        try:
            logger.error(f"/logs failed -> {e}")
        finally:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text="Не удалось сформировать отчёт по логам.",
            )