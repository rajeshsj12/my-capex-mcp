import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    MASTER_API_KEY: str = os.getenv("MASTER_API_KEY", "mcp_admin_sec_999")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
