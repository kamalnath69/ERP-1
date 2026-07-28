"""Application configuration loaded from environment variables."""
import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 14))

    AI_API_KEY: str = os.environ.get("AI_API_KEY", "")
    OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "")
    GEMINI_BASE_URL: str = os.environ.get("GEMINI_BASE_URL", "")
    DEFAULT_AI_PROVIDER: str = os.environ.get("DEFAULT_AI_PROVIDER", "openai")
    DEFAULT_AI_MODEL: str = os.environ.get("DEFAULT_AI_MODEL", "gpt-5.4")

    RAZORPAY_KEY_ID: str = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET: str = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "*").split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
