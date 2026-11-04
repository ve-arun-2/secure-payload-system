"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "secure-payload-service"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    RSA_PRIVATE_KEY_PATH: Path = Path("keys/private.pem")
    RSA_PUBLIC_KEY_PATH: Path = Path("keys/public.pem")
    RSA_PRIVATE_KEY_PASSWORD: SecretStr | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # Token bucket: `capacity` is the burst size, `refill_per_second` the sustained rate.
    RATE_LIMIT_CAPACITY: int = Field(default=10, ge=1)
    RATE_LIMIT_REFILL_PER_SECOND: float = Field(default=10.0, gt=0)
    RATE_LIMIT_FAIL_OPEN: bool = False

    MAX_REQUEST_BODY_BYTES: int = Field(default=16_384, ge=1_024)
    RABBITMQ_PUBLISH_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    MASK_AADHAAR_IN_EVENTS: bool = False

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
