from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RM_", extra="ignore")

    app_name: str = "Report Manager"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://localhost/rm_dev"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False

    max_failed_logins: int = 5
    # Failed sign-ins allowed from one IP per lockout window, across all usernames
    max_failed_logins_per_ip: int = 20
    lockout_minutes: int = 15
    password_min_length: int = 12

    storage_dir: Path = Path(__file__).resolve().parents[2] / "storage"
    max_upload_mb: int = 1024

    # Run Celery tasks inline (tests, single-process dev)
    task_always_eager: bool = False

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
