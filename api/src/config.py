from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Vercel Deployment Public URL
    VERCEL_URL: str = os.getenv("VERCEL_URL", "https://capex-mcp.vercel.app")
    MCP_PUBLIC_URL: str = os.getenv("MCP_PUBLIC_URL", "https://capex-mcp.vercel.app")

    # Online Tunnel Database Settings (Default)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql://root:password@upkbh-106-192-73-56.run.pinggy-free.link:34659/capex",
    )
    DB_HOST: str = os.getenv("DB_HOST", "upkbh-106-192-73-56.run.pinggy-free.link")
    DB_PORT: int = int(os.getenv("DB_PORT", "34659"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    DB_NAME: str = os.getenv("DB_NAME", "capex")

    # Access Settings (Public by default)
    REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1")
    MASTER_API_KEY: str = os.getenv("MASTER_API_KEY", "")

    # Server Settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def get_public_url() -> str:
    """Returns the public base URL of the deployed MCP server."""
    url = settings.MCP_PUBLIC_URL or settings.VERCEL_URL
    if not url:
        return "https://capex-mcp.vercel.app"
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


def get_db_credentials() -> dict[str, Any]:
    """
    Returns database credentials targeting the online Pinggy tunnel exclusively.
    Handles 'tcp://' and 'cp://' prefixes automatically.
    """
    url = settings.DATABASE_URL
    if url.startswith("tcp://"):
        url = "mysql://" + url[len("tcp://") :]
    elif url.startswith("cp://"):
        url = "mysql://" + url[len("cp://") :]

    if url and (url.startswith(("mysql://", "mysql+aiomysql://"))):
        parsed = urlparse(url)
        return {
            "host": parsed.hostname or settings.DB_HOST,
            "port": parsed.port or settings.DB_PORT or 34659,
            "user": parsed.username or settings.DB_USER,
            "password": parsed.password or settings.DB_PASSWORD,
            "db": (parsed.path.lstrip("/") if parsed.path else "") or settings.DB_NAME or "capex",
        }

    return {
        "host": settings.DB_HOST or "upkbh-106-192-73-56.run.pinggy-free.link",
        "port": settings.DB_PORT or 34659,
        "user": settings.DB_USER or "root",
        "password": settings.DB_PASSWORD or "password",
        "db": settings.DB_NAME or "capex",
    }
