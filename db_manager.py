"""
🧩 Database Manager
Централизованное подключение к MySQL и функции для работы с БД.
- Автоматическое создание и закрытие соединений.
- Поддержка пула подключений.
- Универсальные функции select / insert / update / delete.
- Логирование всех действий в database.log.
"""

import time
from mysql.connector import pooling, Error
from contextlib import contextmanager
from config import DB_CONFIG
import logging

# === Настройки пула ===
_POOL = None
_LAST_USED = 0
_POOL_TIMEOUT = DB_CONFIG.get("pool_timeout", 120)
logger = logging.getLogger("database")


# === Инициализация пула подключений ===
def init_pool(force=False):
    """
    Инициализация пула подключений.
    - Если force=True — пересоздаёт пул даже если он уже есть.
    - Если соединение уже существует, просто возвращает его.
    - При ошибках логирует и не роняет бот.
    """
    global _POOL
    if _POOL is not None and not force:
        return _POOL
    try:
        _POOL = pooling.MySQLConnectionPool(
            pool_name="r145j7_pool",
            pool_size=DB_CONFIG["pool_size"],
            pool_reset_session=True,
            **{k: v for k, v in DB_CONFIG.items() if k not in ("pool_size", "pool_timeout")}
        )
        logger.info("✅ MySQL connection pool initialized")
        return _POOL
    except Error as e:
        _POOL = None
        logger.error(f"❌ Failed to initialize MySQL pool: {e}")
        return None

# === Получение соединения из пула ===
def _get_connection():
    """
    Получение соединения из пула.
    - Если пула нет или он мёртв — создаёт новый.
    - Если MySQL перезапускался, создаст новый пул автоматически.
    """
    global _LAST_USED, _POOL
    if _POOL is None:
        _POOL = init_pool()

    try:
        conn = _POOL.get_connection()
        _LAST_USED = time.time()
        return conn
    except Error as e:
        logger.warning(f"⚠️ Connection lost, recreating pool... ({e})")
        _POOL = init_pool(force=True)
        if _POOL:
            try:
                conn = _POOL.get_connection()
                _LAST_USED = time.time()
                return conn
            except Error as e2:
                logger.error(f"❌ Failed to re-establish connection: {e2}")
                return None
        return None

# === Автоматическое закрытие неиспользуемого пула ===
def _close_idle_pool():
    global _POOL, _LAST_USED
    if _POOL and (time.time() - _LAST_USED > _POOL_TIMEOUT):
        _POOL = None
        logger.info("🕓 Connection pool closed due to inactivity")


# === Контекстный менеджер курсора ===
@contextmanager
def get_cursor():
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor(dictionary=True)
        yield cursor
        conn.commit()
    except Error as e:
        logger.error(f"❌ DB error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
        _close_idle_pool()


# === Универсальные функции работы с БД ===

def db_select(query, params=None):
    """Выполнить SELECT и вернуть результат (список словарей)"""
    with get_cursor() as cur:
        cur.execute(query, params or ())
        result = cur.fetchall()
    return result


def db_insert(query, params=None):
    """INSERT-запрос с автокоммитом"""
    with get_cursor() as cur:
        cur.execute(query, params or ())
        logger.info(f"🟢 INSERT: {query} {params}")


def db_update(query, params=None):
    """UPDATE-запрос с автокоммитом"""
    with get_cursor() as cur:
        cur.execute(query, params or ())
        logger.info(f"🟠 UPDATE: {query} {params}")


def db_delete(query, params=None):
    """DELETE-запрос с автокоммитом"""
    with get_cursor() as cur:
        cur.execute(query, params or ())
        logger.info(f"🔴 DELETE: {query} {params}")