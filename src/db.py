import asyncio
import datetime
import logging
import socket
from decimal import Decimal
from typing import Any

import aiomysql

from src.config import get_db_credentials

logger = logging.getLogger("mcp-server")

_pool: aiomysql.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _serialize_value(val: Any) -> Any:
    """Recursively serialize MySQL types (Decimal, datetime, bytes) to JSON-compatible types."""
    if isinstance(val, Decimal):
        return float(val)
    elif isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    elif isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return str(val)
    elif isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialize_value(v) for v in val]
    return val


def _resolve_host(hostname: str) -> str:
    """Resolves DNS hostname to IP address to ensure reliable connection with tunnels."""
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return hostname


async def get_db_pool() -> aiomysql.Pool:
    """
    Returns or initializes the aiomysql connection pool.
    Guarantees pool matches the active running event loop (critical for Serverless & Starlette).
    """
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()

    if _pool is not None and not _pool.closed and _pool_loop is current_loop:
        return _pool

    if _pool is not None and not _pool.closed:
        _pool.close()

    creds = get_db_credentials()
    resolved_ip = _resolve_host(creds["host"])

    _pool = await aiomysql.create_pool(
        host=resolved_ip,
        port=creds["port"],
        user=creds["user"],
        password=creds["password"],
        db=creds["db"],
        minsize=1,
        maxsize=5,
        connect_timeout=10,
        autocommit=True,
        loop=current_loop,
    )
    _pool_loop = current_loop
    return _pool


async def check_connection() -> dict[str, Any]:
    """Health check for database connectivity."""
    creds = get_db_credentials()
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT 1 AS alive, DATABASE() AS active_db, VERSION() AS mysql_version;"
                )
                res = await cur.fetchone()
                return {
                    "connected": True,
                    "engine": "MySQL",
                    "host": creds["host"],
                    "port": creds["port"],
                    "active_database": res.get("active_db"),
                    "version": res.get("mysql_version"),
                }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "connected": False,
            "engine": "MySQL",
            "host": creds["host"],
            "port": creds["port"],
            "error": str(e),
        }


async def fetch_all(query: str, params: tuple | None = None) -> list[dict[str, Any]]:
    """Execute a query and return all rows as dictionaries with serialized types."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params or ())
            rows = await cur.fetchall()
            return [_serialize_value(row) for row in rows]


async def fetch_one(query: str, params: tuple | None = None) -> dict[str, Any] | None:
    """Execute a query and return a single row as a dictionary."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params or ())
            row = await cur.fetchone()
            return _serialize_value(row) if row else None


async def execute(query: str, params: tuple | None = None) -> int:
    """Execute an INSERT/UPDATE/DELETE query and return affected rows."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            affected = await cur.execute(query, params or ())
            return affected


async def close_pool():
    """Gracefully close connection pool."""
    global _pool, _pool_loop
    if _pool is not None and not _pool.closed:
        _pool.close()
        await _pool.wait_closed()
    _pool = None
    _pool_loop = None
