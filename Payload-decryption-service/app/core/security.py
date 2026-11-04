"""Masking / redaction helpers used by the logger and the event builder.

Nothing sensitive (decrypted Aadhaar number, names, ciphertext, key material)
may reach the logs. Masking is applied in two ways:

1. By key name   - values stored under a sensitive key are masked.
2. By pattern    - any free-text 12-digit run (Aadhaar shape) is masked.
"""

import re
from typing import Any

_AADHAAR_PATTERN = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")

# Keys whose values must never be logged in clear text.
_FULL_REDACT_KEYS = frozenset(
    {"encrypted_data", "private_key", "password", "authorization", "secret", "token"}
)
_AADHAAR_KEYS = frozenset({"aadhaar_number", "aadhaar"})
_NAME_KEYS = frozenset({"name"})

# Identifiers that are hex/opaque and must not be pattern-scanned (avoids false positives).
_SAFE_KEYS = frozenset({"transaction_id", "request_id", "message_id"})


def mask_aadhaar(value: str) -> str:
    """Return the Aadhaar number with only the last 4 digits visible."""
    digits = str(value)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_name(value: str) -> str:
    value = str(value)
    return value[:1] + "***" if value else value


def mask_text(text: str) -> str:
    """Mask any Aadhaar-shaped number embedded in free text."""
    return _AADHAAR_PATTERN.sub(lambda m: mask_aadhaar(m.group(0)), text)


def mask_sensitive(value: Any, key: str | None = None) -> Any:
    """Recursively mask sensitive data in dicts / lists / strings."""
    normalized = key.lower() if key else None

    if normalized in _FULL_REDACT_KEYS:
        return "[REDACTED]"
    if normalized in _AADHAAR_KEYS:
        return mask_aadhaar(str(value))
    if normalized in _NAME_KEYS and isinstance(value, str):
        return mask_name(value)

    if isinstance(value, dict):
        return {k: mask_sensitive(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_sensitive(v) for v in value]
    if isinstance(value, str) and normalized not in _SAFE_KEYS:
        return mask_text(value)
    return value
