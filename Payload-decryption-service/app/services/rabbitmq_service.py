"""RabbitMQ publisher built on aio-pika.

Topology (declared idempotently on connect):

    publisher --> [secure.payload.exchange]  (direct, durable)
                        |  routing key: secure.payload.received
                        v
                  [secure.payload.queue]     (durable quorum queue)
                        |  rejected / expired / delivery-limit
                        v
                  [secure.payload.dlx] --> [secure.payload.dlq]
"""

import asyncio
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractExchange, AbstractRobustChannel, AbstractRobustConnection

from app.core.exceptions import RabbitMQPublishException
from app.core.logger import get_logger
from app.models.event_models import SecurePayloadReceivedEvent

logger = get_logger(__name__)

EXCHANGE_NAME = "secure.payload.exchange"
ROUTING_KEY = "secure.payload.received"
QUEUE_NAME = "secure.payload.queue"
DEAD_LETTER_EXCHANGE = "secure.payload.dlx"
DEAD_LETTER_ROUTING_KEY = "secure.payload.dead"
DEAD_LETTER_QUEUE = "secure.payload.queue.dlq"


class EventPublisher(Protocol):
    """What the payload service needs; lets tests substitute a fake broker."""

    async def publish(self, event: SecurePayloadReceivedEvent) -> None: ...


class RabbitMQService:
    def __init__(self, url: str, publish_timeout: float = 5.0) -> None:
        self._url = url
        self._publish_timeout = publish_timeout
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._connect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        async with self._connect_lock:
            if self.is_connected and self._exchange is not None:
                return

            # connect_robust re-establishes the connection and channel after broker restarts.
            self._connection = await aio_pika.connect_robust(self._url, timeout=10)
            # publisher_confirms: publish() only returns once the broker has accepted the message.
            self._channel = await self._connection.channel(publisher_confirms=True)

            dlx = await self._channel.declare_exchange(DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
            dlq = await self._channel.declare_queue(
                DEAD_LETTER_QUEUE, durable=True, arguments={"x-queue-type": "quorum"}
            )
            await dlq.bind(dlx, routing_key=DEAD_LETTER_ROUTING_KEY)

            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
            )
            queue = await self._channel.declare_queue(
                QUEUE_NAME,
                durable=True,
                arguments={
                    "x-queue-type": "quorum",
                    "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                    "x-dead-letter-routing-key": DEAD_LETTER_ROUTING_KEY,
                },
            )
            await queue.bind(self._exchange, routing_key=ROUTING_KEY)
            logger.info("rabbitmq_connected", extra={"exchange": EXCHANGE_NAME, "queue": QUEUE_NAME})

    async def publish(self, event: SecurePayloadReceivedEvent) -> None:
        """Publish the event; any failure is surfaced as RabbitMQPublishException (HTTP 503)."""
        try:
            if self._exchange is None:
                await self.connect()
            assert self._exchange is not None

            message = aio_pika.Message(
                body=event.model_dump_json().encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=event.transaction_id,
                type=event.event_type,
                timestamp=event.timestamp,
            )
            # mandatory=True: an unroutable message raises instead of being silently dropped.
            await self._exchange.publish(
                message, routing_key=ROUTING_KEY, mandatory=True, timeout=self._publish_timeout
            )
        except Exception as exc:
            logger.error(
                "rabbitmq_publish_failed",
                extra={"error_type": type(exc).__name__, "event_publish_status": "failed"},
            )
            raise RabbitMQPublishException(f"publish failed: {type(exc).__name__}") from None

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = self._channel = self._exchange = None
        logger.info("rabbitmq_closed")
