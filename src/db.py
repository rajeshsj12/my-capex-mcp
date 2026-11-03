import json
import logging
from typing import Any, Dict, List, Optional
import asyncpg
from src.config import settings

logger = logging.getLogger("mcp-server")

_pool: Optional[asyncpg.Pool] = None

def _clean_database_url(url: str) -> tuple[str, bool]:
    """
    Parses DATABASE_URL to make it asyncpg compatible.
    asyncpg does not accept ?sslmode=... in the connection string directly;
    instead it expects ssl=True or ssl='require' parameter.
    """
    use_ssl = False
    if "sslmode=require" in url:
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")
        use_ssl = True
    elif "ssl=true" in url.lower():
        url = url.replace("?ssl=true", "").replace("&ssl=true", "")
        use_ssl = True
    return url, use_ssl

async def get_db_pool() -> asyncpg.Pool:
    """Returns or initializes the asyncpg connection pool."""
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool

    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not configured.")

    clean_url, use_ssl = _clean_database_url(settings.DATABASE_URL)
    
    # In serverless environments, keep min_size small to avoid exhausting DB connections
    ssl_param = "require" if use_ssl else None
    
    _pool = await asyncpg.create_pool(
        dsn=clean_url,
        min_size=1,
        max_size=5,
        command_timeout=15,
        ssl=ssl_param
    )
    return _pool

async def check_connection() -> Dict[str, Any]:
    """Health check for database connectivity."""
    if not settings.DATABASE_URL:
        return {"connected": False, "error": "DATABASE_URL not set"}
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            return {"connected": val == 1, "provider": "PostgreSQL"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"connected": False, "error": str(e)}

async def fetch_all(query: str, *args) -> List[Dict[str, Any]]:
    """Execute a query and return all rows as dictionaries."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(query, *args)
        results = []
        for r in records:
            row_dict = dict(r)
            # Serialize JSON / JSONB fields if needed
            for k, v in row_dict.items():
                if isinstance(v, (dict, list)):
                    pass
                elif hasattr(v, "isoformat"):
                    row_dict[k] = v.isoformat()
            results.append(row_dict)
        return results

async def fetch_one(query: str, *args) -> Optional[Dict[str, Any]]:
    """Execute a query and return a single row as a dictionary."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(query, *args)
        if not record:
            return None
        row_dict = dict(record)
        for k, v in row_dict.items():
            if hasattr(v, "isoformat"):
                row_dict[k] = v.isoformat()
        return row_dict

async def execute(query: str, *args) -> str:
    """Execute an INSERT/UPDATE/DELETE query and return status."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
