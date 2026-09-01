"""Application configuration (Pydantic Settings, env-driven)."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(p).strip() for p in value if str(p).strip()]
    return [str(value)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Telegram
    BOT_TOKEN: str = Field(default="")
    ADMIN_USER_IDS: list[int] = Field(default_factory=list)

    # Storage
    DB_PATH: str = Field(default="./data/autopilot.db")
    SCREENSHOT_DIR: str = Field(default="./data/screenshots")
    LOG_DIR: str = Field(default="./data/logs")

    # Automation (APK defaults)
    MAX_SESSIONS: int = Field(default=10, ge=1, le=50)
    MAX_TABS: int = Field(default=8, ge=1, le=16)

    # Proxies
    PROXY_SOURCES: list[str] = Field(default_factory=lambda: ["geonode", "proxyscrape"])
    PROXY_REFRESH_MINUTES: int = Field(default=10, ge=1)
    CUSTOM_PROXIES: list[str] = Field(default_factory=list)

    # Monitoring
    WATCHDOG_HEARTBEAT_SECONDS: int = Field(default=30, ge=5)

    # Health server (Railway)
    HEALTH_PORT: int = Field(default=8080)

    # Logging
    LOG_LEVEL: str = Field(default="INFO")

    @field_validator("ADMIN_USER_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        out = []
        for p in _split_csv(v):
            try:
                out.append(int(p))
            except ValueError:
                continue
        return out

    @field_validator("PROXY_SOURCES", "CUSTOM_PROXIES", mode="before")
    @classmethod
    def _parse_csv_lists(cls, v: object) -> object:
        return _split_csv(v)

    @property
    def is_admin(self) -> bool:
        return len(self.ADMIN_USER_IDS) > 0

    def is_allowed_user(self, user_id: int) -> bool:
        if not self.is_admin:
            return False
        return user_id in self.ADMIN_USER_IDS


@lru_cache
def get_settings() -> Settings:
    return Settings()