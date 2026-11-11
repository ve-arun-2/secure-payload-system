"""Orchestrates the secure payload flow: decrypt -> parse -> validate -> id -> publish."""

import asyncio
import json

from pydantic import ValidationError

from app.core.exceptions import InvalidPayloadException
from app.core.logger import bind_log_context, get_logger
from app.core.security import mask_aadhaar
from app.models.event_models import SecurePayloadReceivedEvent
from app.schemas.internal import DecryptedPayload
from app.schemas.requests import SecurePayloadRequest
from app.services.crypto_service import CryptoService
from app.services.rabbitmq_service import EventPublisher
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class PayloadService:
    def __init__(
        self,
        crypto: CryptoService,
        transactions: TransactionService,
        publisher: EventPublisher,
        mask_aadhaar_in_events: bool = False,
    ) -> None:
        self._crypto = crypto
        self._transactions = transactions
        self._publisher = publisher
        self._mask_aadhaar_in_events = mask_aadhaar_in_events

    async def process(self, request: SecurePayloadRequest) -> str:
        """Run the pipeline and return the transaction id. Rate limiting already happened upstream."""
        bind_log_context(partner_id=request.partner_id)

        # RSA private-key operations are CPU-bound; keep them off the event loop.
        plaintext = await asyncio.to_thread(self._crypto.decrypt_payload, request.encrypted_data)
        payload = self._parse_and_validate(plaintext)

        transaction_id = self._transactions.generate_transaction_id()
        bind_log_context(transaction_id=transaction_id)

        event_payload = payload.model_dump()
        if self._mask_aadhaar_in_events:
            event_payload["aadhaar_number"] = mask_aadhaar(payload.aadhaar_number)

        event = SecurePayloadReceivedEvent(
            transaction_id=transaction_id,
            partner_id=request.partner_id,
            payload=event_payload,
        )

        try:
            await self._publisher.publish(event)
        except Exception:
            bind_log_context(event_publish_status="failed")
            raise
        bind_log_context(event_publish_status="published")
        logger.info("payload_processed")
        return transaction_id

    @staticmethod
    def _parse_and_validate(plaintext: bytes) -> DecryptedPayload:
        try:
            data = json.loads(plaintext)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise InvalidPayloadException("decrypted data is not valid JSON") from None

        if not isinstance(data, dict):
            raise InvalidPayloadException("decrypted JSON is not an object")

        try:
            pydentic_data = DecryptedPayload.model_validate(data)
            return pydentic_data
        except ValidationError as exc:
            # Log field names only: pydantic's messages/inputs may contain the Aadhaar number.
            fields = sorted({str(err["loc"][0]) if err["loc"] else "<root>" for err in exc.errors()})
            raise InvalidPayloadException(f"schema validation failed for fields: {', '.join(fields)}") from None
