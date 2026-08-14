"""Application configuration loaded from environment variables."""
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _cookie_domain() -> str:
    raw = os.environ.get("AUTH_COOKIE_DOMAIN", "").strip()
    if "://" in raw:
        raw = urlparse(raw).hostname or ""
    if raw.lower() in {"localhost", "127.0.0.1", "::1"}:
        return ""
    return raw


def _database_url() -> str:
    raw = _required_env("DATABASE_URL")
    ssl_mode = os.environ.get("DATABASE_SSLMODE", "").strip()
    if not ssl_mode and "supabase.co" in raw.lower():
        ssl_mode = "require"
    if ssl_mode and "sslmode=" not in raw.lower():
        raw = f"{raw}{'&' if '?' in raw else '?'}sslmode={ssl_mode}"
    return raw


def _cors_origins() -> list[str]:
    configured = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    origins = ["https://edvatiq.app", "https://www.edvatiq.app", *configured]
    return list(dict.fromkeys(origin.strip().rstrip("/") for origin in origins if origin.strip()))


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _is_serverless_runtime() -> bool:
    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


class Settings:
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development").strip().lower()
    SERVERLESS_RUNTIME: bool = _is_serverless_runtime()
    RUN_STARTUP_MIGRATIONS: bool = _bool_env(
        "RUN_STARTUP_MIGRATIONS",
        ENVIRONMENT != "production" and not SERVERLESS_RUNTIME,
    )
    RUN_STARTUP_SEEDING: bool = _bool_env(
        "RUN_STARTUP_SEEDING",
        ENVIRONMENT != "production" and not SERVERLESS_RUNTIME,
    )
    DATABASE_URL: str = _database_url()
    DATABASE_POOL_SIZE: int = max(1, int(os.environ.get("DATABASE_POOL_SIZE", 5)))
    DATABASE_MAX_OVERFLOW: int = max(0, int(os.environ.get("DATABASE_MAX_OVERFLOW", 5)))
    DATABASE_POOL_TIMEOUT_SECONDS: int = max(1, int(os.environ.get("DATABASE_POOL_TIMEOUT_SECONDS", 10)))
    DATABASE_POOL_RECYCLE_SECONDS: int = max(30, int(os.environ.get("DATABASE_POOL_RECYCLE_SECONDS", 300)))
    DATABASE_CONNECT_TIMEOUT_SECONDS: int = max(1, int(os.environ.get("DATABASE_CONNECT_TIMEOUT_SECONDS", 10)))
    DATABASE_APPLICATION_NAME: str = os.environ.get("DATABASE_APPLICATION_NAME", "edvatiq_api").strip() or "edvatiq_api"
    JWT_SECRET_KEY: str = _required_env("JWT_SECRET_KEY")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 14))
    AUTH_COOKIE_SECURE: bool = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() == "true"
    AUTH_COOKIE_DOMAIN: str = _cookie_domain()
    AUTH_COOKIE_SAMESITE: str = os.environ.get("AUTH_COOKIE_SAMESITE", "lax")
    ACCESS_COOKIE_NAME: str = os.environ.get("ACCESS_COOKIE_NAME", "edvatiq_access")
    REFRESH_COOKIE_NAME: str = os.environ.get("REFRESH_COOKIE_NAME", "edvatiq_refresh")
    CSRF_COOKIE_NAME: str = os.environ.get("CSRF_COOKIE_NAME", "edvatiq_csrf")
    AUTH_CODE_TTL_MINUTES: int = int(os.environ.get("AUTH_CODE_TTL_MINUTES", 10))
    PASSWORD_RESET_TTL_MINUTES: int = int(os.environ.get("PASSWORD_RESET_TTL_MINUTES", 15))
    AUTH_CODE_MAX_ATTEMPTS: int = int(os.environ.get("AUTH_CODE_MAX_ATTEMPTS", 5))
    AUTH_EXPOSE_TEST_CODES: bool = os.environ.get("AUTH_EXPOSE_TEST_CODES", "false").lower() == "true"
    SUPER_ADMIN_EMAIL: str = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@edvatiq.com").strip().lower()
    SUPER_ADMIN_INITIAL_PASSWORD: str = os.environ.get("SUPER_ADMIN_INITIAL_PASSWORD", "" if ENVIRONMENT == "production" else "SuperAdmin@123")

    AI_API_KEY: str = os.environ.get("AI_API_KEY", "")
    OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "")
    GEMINI_BASE_URL: str = os.environ.get("GEMINI_BASE_URL", "")
    DEFAULT_AI_PROVIDER: str = os.environ.get("DEFAULT_AI_PROVIDER", "openai")
    AI_MODEL_BASIC: str = os.environ.get("AI_MODEL_BASIC", "gpt-5.4-mini")
    AI_TRANSCRIBE_MODEL: str = os.environ.get("AI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    AI_EMBEDDING_MODEL: str = os.environ.get("AI_EMBEDDING_MODEL", "text-embedding-3-small")

    S3_ENDPOINT_URL: str = os.environ.get("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY_ID: str = os.environ.get("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    S3_BUCKET: str = os.environ.get("S3_BUCKET", "edvatiq")
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME: str = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "").replace(" ", "") if SMTP_HOST.lower() == "smtp.gmail.com" else os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.environ.get("SMTP_FROM_EMAIL", os.environ.get("SMTP_USERNAME", ""))
    SMTP_FROM_NAME: str = os.environ.get("SMTP_FROM_NAME", "Edvatiq")
    SMTP_USE_TLS: bool = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    EMAIL_PROVIDER: str = os.environ.get("EMAIL_PROVIDER", "resend").strip().lower()
    RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "").strip()
    RESEND_FROM_EMAIL: str = os.environ.get("RESEND_FROM_EMAIL", "Edvatiq <onboarding@resend.dev>").strip()
    APP_URL: str = os.environ.get("APP_URL", "http://localhost:3000")
    WHATSAPP_TOKEN: str = os.environ.get("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_GRAPH_VERSION: str = os.environ.get("WHATSAPP_GRAPH_VERSION", "v23.0")
    WHATSAPP_DEFAULT_COUNTRY_CODE: str = os.environ.get("WHATSAPP_DEFAULT_COUNTRY_CODE", "91")
    WHATSAPP_TEMPLATE_LANGUAGE: str = os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    WHATSAPP_TEMPLATE_APPOINTMENT_REMINDER: str = os.environ.get("WHATSAPP_TEMPLATE_APPOINTMENT_REMINDER", "appointment_reminder")
    WHATSAPP_TEMPLATE_APPOINTMENT_CONFIRMATION: str = os.environ.get("WHATSAPP_TEMPLATE_APPOINTMENT_CONFIRMATION", "appointment_confirmation")
    WHATSAPP_TEMPLATE_APPOINTMENT_STATUS: str = os.environ.get("WHATSAPP_TEMPLATE_APPOINTMENT_STATUS", "appointment_status_update")
    WHATSAPP_TEMPLATE_MEMBERSHIP_EXPIRY: str = os.environ.get("WHATSAPP_TEMPLATE_MEMBERSHIP_EXPIRY", "membership_expiry_reminder")
    WHATSAPP_TEMPLATE_MEMBERSHIP_UPDATE: str = os.environ.get("WHATSAPP_TEMPLATE_MEMBERSHIP_UPDATE", "membership_update")
    WHATSAPP_TEMPLATE_CLIENT_UPDATE: str = os.environ.get("WHATSAPP_TEMPLATE_CLIENT_UPDATE", "client_update")
    WHATSAPP_REMINDERS_ENABLED: bool = os.environ.get("WHATSAPP_REMINDERS_ENABLED", "false").lower() == "true"
    PROVIDER_MOCK_MODE: bool = os.environ.get("PROVIDER_MOCK_MODE", "true").lower() == "true"

    PAYMENT_GATEWAY: str = os.environ.get("PAYMENT_GATEWAY", "razorpay").strip().lower()
    if PAYMENT_GATEWAY not in {"razorpay", "cashfree"}:
        raise ValueError("PAYMENT_GATEWAY must be razorpay or cashfree")

    RAZORPAY_MODE: str = os.environ.get(
        "RAZORPAY_MODE", "mock" if PROVIDER_MOCK_MODE else "test"
    ).strip().lower()
    if RAZORPAY_MODE not in {"mock", "test", "live"}:
        raise ValueError("RAZORPAY_MODE must be mock, test, or live")

    # Legacy names remain as a safe fallback for the matching key type.
    RAZORPAY_KEY_ID: str = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET: str = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    RAZORPAY_TEST_KEY_ID: str = os.environ.get("RAZORPAY_TEST_KEY_ID", "")
    RAZORPAY_TEST_KEY_SECRET: str = os.environ.get("RAZORPAY_TEST_KEY_SECRET", "")
    RAZORPAY_TEST_WEBHOOK_SECRET: str = os.environ.get("RAZORPAY_TEST_WEBHOOK_SECRET", "")
    RAZORPAY_LIVE_KEY_ID: str = os.environ.get("RAZORPAY_LIVE_KEY_ID", "")
    RAZORPAY_LIVE_KEY_SECRET: str = os.environ.get("RAZORPAY_LIVE_KEY_SECRET", "")
    RAZORPAY_LIVE_WEBHOOK_SECRET: str = os.environ.get("RAZORPAY_LIVE_WEBHOOK_SECRET", "")

    def razorpay_credentials(self, mode: str | None = None) -> tuple[str, str, str]:
        selected = mode or self.RAZORPAY_MODE
        if selected == "mock":
            return "", "", ""
        prefix = f"rzp_{selected}_"
        legacy_matches = self.RAZORPAY_KEY_ID.startswith(prefix)
        if selected == "test":
            return (
                self.RAZORPAY_TEST_KEY_ID or (self.RAZORPAY_KEY_ID if legacy_matches else ""),
                self.RAZORPAY_TEST_KEY_SECRET or (self.RAZORPAY_KEY_SECRET if legacy_matches else ""),
                self.RAZORPAY_TEST_WEBHOOK_SECRET or (self.RAZORPAY_WEBHOOK_SECRET if legacy_matches else ""),
            )
        return (
            self.RAZORPAY_LIVE_KEY_ID or (self.RAZORPAY_KEY_ID if legacy_matches else ""),
            self.RAZORPAY_LIVE_KEY_SECRET or (self.RAZORPAY_KEY_SECRET if legacy_matches else ""),
            self.RAZORPAY_LIVE_WEBHOOK_SECRET or (self.RAZORPAY_WEBHOOK_SECRET if legacy_matches else ""),
        )

    CASHFREE_MODE: str = os.environ.get(
        "CASHFREE_MODE", "mock" if PROVIDER_MOCK_MODE else "test"
    ).strip().lower()
    if CASHFREE_MODE not in {"mock", "test", "live"}:
        raise ValueError("CASHFREE_MODE must be mock, test, or live")
    CASHFREE_API_VERSION: str = os.environ.get("CASHFREE_API_VERSION", "2026-01-01").strip()
    CASHFREE_APP_ID: str = os.environ.get("CASHFREE_APP_ID", "").strip()
    CASHFREE_SECRET_KEY: str = os.environ.get("CASHFREE_SECRET_KEY", "").strip()
    CASHFREE_WEBHOOK_SECRET: str = os.environ.get("CASHFREE_WEBHOOK_SECRET", "").strip()
    CASHFREE_TEST_APP_ID: str = os.environ.get("CASHFREE_TEST_APP_ID", "").strip()
    CASHFREE_TEST_SECRET_KEY: str = os.environ.get("CASHFREE_TEST_SECRET_KEY", "").strip()
    CASHFREE_TEST_WEBHOOK_SECRET: str = os.environ.get("CASHFREE_TEST_WEBHOOK_SECRET", "").strip()
    CASHFREE_LIVE_APP_ID: str = os.environ.get("CASHFREE_LIVE_APP_ID", "").strip()
    CASHFREE_LIVE_SECRET_KEY: str = os.environ.get("CASHFREE_LIVE_SECRET_KEY", "").strip()
    CASHFREE_LIVE_WEBHOOK_SECRET: str = os.environ.get("CASHFREE_LIVE_WEBHOOK_SECRET", "").strip()

    def cashfree_credentials(self, mode: str | None = None) -> tuple[str, str, str]:
        selected = mode or self.CASHFREE_MODE
        if selected == "mock":
            return "", "", ""
        if selected == "test":
            app_id = self.CASHFREE_TEST_APP_ID or self.CASHFREE_APP_ID
            secret = self.CASHFREE_TEST_SECRET_KEY or self.CASHFREE_SECRET_KEY
            webhook = self.CASHFREE_TEST_WEBHOOK_SECRET or self.CASHFREE_WEBHOOK_SECRET or secret
            return app_id, secret, webhook
        app_id = self.CASHFREE_LIVE_APP_ID or self.CASHFREE_APP_ID
        secret = self.CASHFREE_LIVE_SECRET_KEY or self.CASHFREE_SECRET_KEY
        webhook = self.CASHFREE_LIVE_WEBHOOK_SECRET or self.CASHFREE_WEBHOOK_SECRET or secret
        return app_id, secret, webhook

    CORS_ORIGINS: list[str] = _cors_origins()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
