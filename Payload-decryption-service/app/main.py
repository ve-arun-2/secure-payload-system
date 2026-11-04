from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import keys, secure_payload
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import configure_logging, get_logger
from app.core.observability import setup_metrics, setup_tracing
from app.dependencies.providers import Container, build_container
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.responses import HealthResponse

logger = get_logger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL, settings.APP_NAME, settings.APP_ENV)
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail fast: refuse to start if the broker is unreachable.
        await container.rabbitmq.connect()
        logger.info("application_started", extra={"app_env": settings.APP_ENV})
        yield
        await container.rabbitmq.close()
        await container.cache.close()
        logger.info("application_stopped")

    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.container = container

    # add_middleware: the LAST one added is the OUTERMOST. Request context wraps the
    # rate limiter so that even 429s get a request id and an access-log line.
    app.add_middleware(
        RateLimiterMiddleware,
        rate_limit_service=container.rate_limiter,
        protected_paths=[secure_payload.SECURE_PAYLOAD_PATH],
        max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(secure_payload.router)
    app.include_router(keys.router)

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        return HealthResponse()

    setup_metrics(app, settings)
    setup_tracing(app, settings)
    return app


def __getattr__(name: str) -> FastAPI:
    # Lazy module attribute so `uvicorn app.main:app` works while merely importing
    # this module (e.g. in tests) does not require keys / environment to exist.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
