from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./communeer.db"

    # Sessions / auth
    session_secret_key: str = "dev-insecure-secret-change-me"
    session_cookie_name: str = "communeer_session"
    session_cookie_secure: bool = False
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days

    # Seed admin user, created idempotently on startup
    seed_admin_username: str = "admin"
    seed_admin_password: str = "changeme123"

    # WhatsApp provider seam
    whatsapp_provider: str = "mock"

    # WPPConnect Server connection (only used when whatsapp_provider="wppconnect";
    # left unset/defaulted so "mock" mode never needs any of these).
    wppconnect_base_url: str | None = None
    wppconnect_secret_key: str | None = None
    wppconnect_session_name: str = "communeer"
    wppconnect_http_timeout_seconds: float = 30.0

    # CORS (only relevant for local dev where frontend runs on a different
    # origin/port than the backend; Docker/Caddy serves same-origin)
    cors_allow_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
