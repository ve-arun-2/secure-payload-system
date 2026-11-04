import uuid


class TransactionService:
    """Generates unguessable transaction ids, e.g. ``txn_f8de98ab2d384d87``."""

    PREFIX = "txn_"
    _HEX_LENGTH = 16

    def generate_transaction_id(self) -> str:
        # uuid4 is built from os.urandom (CSPRNG); 16 hex chars = 64 random bits.
        return f"{self.PREFIX}{uuid.uuid4().hex[: self._HEX_LENGTH]}"
