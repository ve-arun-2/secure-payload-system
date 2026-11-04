"""Observability placeholders.

Wire real exporters here without touching the rest of the app:

* Prometheus: `pip install prometheus-fastapi-instrumentator`, then
      Instrumentator().instrument(app).expose(app, endpoint="/metrics")
  Suggested custom metrics: payloads_received_total{partner}, rate_limited_total,
  decrypt_failures_total, rabbitmq_publish_seconds (histogram).

* OpenTelemetry: `pip install opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp`, then
      FastAPIInstrumentor.instrument_app(app)
  plus the aio-pika / redis instrumentations to get spans across the queue and cache.
"""

from fastapi import FastAPI

from app.core.config import Settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def setup_metrics(app: FastAPI, settings: Settings) -> None:
    """PLACEHOLDER: register Prometheus instrumentation and expose /metrics."""
    logger.debug("metrics_placeholder_registered")


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """PLACEHOLDER: configure the OpenTelemetry tracer provider and instrument FastAPI."""
    logger.debug("tracing_placeholder_registered")
