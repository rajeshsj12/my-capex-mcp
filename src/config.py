import os
from urllib.parse import urlparse
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql://root:password@upkbh-106-192-73-56.run.pinggy-free.link:34659/capex")
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    DB_NAME: str = os.getenv("DB_NAME", "capex")

    MASTER_API_KEY: str = os.getenv("MASTER_API_KEY", "mcp_admin_sec_999")
    ALICE_API_KEY: str = os.getenv("ALICE_API_KEY", "mcp_alice_sec_101")
    BOB_API_KEY: str = os.getenv("BOB_API_KEY", "mcp_bob_sec_202")

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

def get_db_credentials():
    """
    Parses DATABASE_URL or individual DB_* settings into host, port, user, password, db.
    Handles 'tcp://' prefix from Pinggy tunnels gracefully.
    """
    url = settings.DATABASE_URL
    if url.startswith("tcp://"):
        url = "mysql://" + url[len("tcp://"):]

    if url and (url.startswith("mysql://") or url.startswith("mysql+aiomysql://")):
        parsed = urlparse(url)
        return {
            "host": parsed.hostname or settings.DB_HOST,
            "port": parsed.port or settings.DB_PORT or 3306,
            "user": parsed.username or settings.DB_USER,
            "password": parsed.password or settings.DB_PASSWORD,
            "db": (parsed.path.lstrip("/") if parsed.path else "") or settings.DB_NAME or "capex"
        }

    return {
        "host": settings.DB_HOST or "127.0.0.1",
        "port": settings.DB_PORT or 3306,
        "user": settings.DB_USER or "root",
        "password": settings.DB_PASSWORD or "password",
        "db": settings.DB_NAME or "capex"
    }
