"""Dependency injection.

`Container` owns the long-lived singletons (Redis client, RabbitMQ connection,
crypto keys). It is built once in `create_app()` and stored on `app.state`;
FastAPI routes receive pieces of it through the `Depends(...)` providers below,
which tests can swap using `app.dependency_overrides`.
"""

from dataclasses import dataclass

from fastapi import Depends, Request

from app.cache.redis_cache import RedisCache
from app.core.config import Settings
from app.services.crypto_service import CryptoService, FileKeyProvider
from app.services.payload_service import PayloadService
from app.services.rabbitmq_service import EventPublisher, RabbitMQService
from app.services.rate_limit_service import RateLimitService
from app.services.transaction_service import TransactionService


@dataclass
class Container:
    settings: Settings
    cache: RedisCache
    rabbitmq: RabbitMQService | EventPublisher
    crypto: CryptoService
    transactions: TransactionService
    rate_limiter: RateLimitService
    payload_service: PayloadService


def build_container(settings: Settings) -> Container:
    """Composition root for production wiring. Performs no network I/O."""
    password = settings.RSA_PRIVATE_KEY_PASSWORD
    crypto = CryptoService(
        FileKeyProvider(
            settings.RSA_PRIVATE_KEY_PATH,
            settings.RSA_PUBLIC_KEY_PATH,
            password.get_secret_value().encode() if password else None,
        )
    )
    cache = RedisCache(settings.REDIS_URL)
    rabbitmq = RabbitMQService(settings.RABBITMQ_URL, settings.RABBITMQ_PUBLISH_TIMEOUT_SECONDS)
    return assemble_container(settings, crypto=crypto, cache=cache, publisher=rabbitmq)


def assemble_container(
    settings: Settings, *, crypto: CryptoService, cache: RedisCache, publisher: RabbitMQService | EventPublisher
) -> Container:
    """Wire services together from already-built infrastructure (also used by tests)."""
    transactions = TransactionService()
    rate_limiter = RateLimitService(
        cache,
        capacity=settings.RATE_LIMIT_CAPACITY,
        refill_per_second=settings.RATE_LIMIT_REFILL_PER_SECOND,
        fail_open=settings.RATE_LIMIT_FAIL_OPEN,
    )
    payload_service = PayloadService(
        crypto, transactions, publisher, mask_aadhaar_in_events=settings.MASK_AADHAAR_IN_EVENTS
    )
    return Container(settings, cache, publisher, crypto, transactions, rate_limiter, payload_service)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_crypto_service(container: Container = Depends(get_container)) -> CryptoService:
    return container.crypto


def get_payload_service(container: Container = Depends(get_container)) -> PayloadService:
    return container.payload_service
