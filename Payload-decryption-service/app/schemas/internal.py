"""Internal domain types shared across layers (not exposed on the API surface)."""

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator

# [0-9] rather than \d: \d also matches non-ASCII Unicode digits.
_AADHAAR_RE = re.compile(r"[0-9]{12}")


class DecryptedPayload(BaseModel):
    """Schema of the JSON found inside the RSA ciphertext."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    aadhaar_number: str = Field(min_length=12, max_length=12)
    device_id: str = Field(min_length=1, max_length=64)

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _aadhaar_must_be_12_ascii_digits(cls, value: object) -> str:
        # Reject JSON numbers: they would silently drop leading zeros.
        if not isinstance(value, str) or not _AADHAAR_RE.fullmatch(value.strip()):
            # Deliberately generic: pydantic would otherwise echo the input value.
            raise ValueError("aadhaar_number must be exactly 12 digits")
        return value.strip()

    def __repr__(self) -> str:  # keep PII out of accidental repr()/log calls
        return "DecryptedPayload(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class BucketDecision:
    """Result of one token-bucket consumption attempt."""

    allowed: bool
    tokens_remaining: float
    retry_after: float  # seconds until `cost` tokens are available; 0 when allowed


def refill_tokens(
    tokens: float, last_refill: float, now: float, capacity: float, refill_per_second: float
) -> float:
    """Token-bucket refill calculation (pure function, unit-testable).

    tokens_now = min(capacity, tokens + elapsed * refill_per_second)

    `elapsed` is clamped at 0 so a clock that steps backwards never removes tokens.
    """
    elapsed = max(0.0, now - last_refill)
    return min(capacity, tokens + elapsed * refill_per_second)
