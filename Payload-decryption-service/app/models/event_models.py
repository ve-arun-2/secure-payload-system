from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SecurePayloadReceivedEvent(BaseModel):
    """Event published to RabbitMQ once a payload was decrypted and validated."""

    event_type: Literal["Secure_Payload_Received"] = "Secure_Payload_Received"
    transaction_id: str
    partner_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]
