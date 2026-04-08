from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Centralized application configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    secret_key: str = Field(default="change-this-secret-key", alias="SECRET_KEY")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin123456", alias="ADMIN_PASSWORD")
    web_host: str = Field(default="127.0.0.1", alias="WEB_HOST")
    web_port: int = Field(default=8080, alias="WEB_PORT")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    log_dir: Path = Field(default=BASE_DIR / "logs", alias="LOG_DIR")
    data_dir: Path = Field(default=BASE_DIR / "data", alias="DATA_DIR")
    app_log_file: str = Field(default="app.log", alias="APP_LOG_FILE")
    packet_log_file: str = Field(default="packets.log", alias="PACKET_LOG_FILE")
    session_cookie_name: str = Field(default="u2t_session", alias="SESSION_COOKIE_NAME")
    session_secure: bool = Field(default=False, alias="SESSION_SECURE")

    @property
    def app_log_path(self) -> Path:
        return self.log_dir / self.app_log_file

    @property
    def packet_log_path(self) -> Path:
        return self.log_dir / self.packet_log_file


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
