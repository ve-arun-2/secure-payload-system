"""RSA-OAEP (SHA-256) cryptography. Pure crypto: no business logic lives here.

Key storage is separated from key usage:
  * `KeyProvider`      - where keys come from (files today; KMS/HSM/Vault tomorrow).
  * `CryptoService`    - what is done with them (base64 + OAEP decrypt/encrypt).
"""

import base64
import binascii
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.exceptions import InvalidEncryptedPayloadException
from app.core.logger import get_logger

logger = get_logger(__name__)


def _oaep() -> padding.OAEP:
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


class KeyProvider(ABC):
    @abstractmethod
    def private_key(self) -> rsa.RSAPrivateKey: ...

    @abstractmethod
    def public_key(self) -> rsa.RSAPublicKey: ...


class FileKeyProvider(KeyProvider):
    """Loads PEM keys from two separate files and verifies that they form a pair."""

    def __init__(self, private_key_path: Path, public_key_path: Path, password: bytes | None = None) -> None:
        private = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=password)
        public = serialization.load_pem_public_key(Path(public_key_path).read_bytes())

        if not isinstance(private, rsa.RSAPrivateKey) or not isinstance(public, rsa.RSAPublicKey):
            raise ValueError("Configured keys must be RSA keys")
        if private.public_key().public_numbers() != public.public_numbers():
            raise ValueError("RSA public key does not match the private key")

        self._private = private
        self._public = public

    def private_key(self) -> rsa.RSAPrivateKey:
        return self._private

    def public_key(self) -> rsa.RSAPublicKey:
        return self._public


class CryptoService:
    def __init__(self, key_provider: KeyProvider) -> None:
        self._keys = key_provider
        self._key_bytes = (key_provider.public_key().key_size + 7) // 8

    def get_public_key(self) -> str:
        """PEM (SubjectPublicKeyInfo) of the public key clients must encrypt with."""
        return (
            self._keys.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    def decrypt_payload(self, encrypted_data: str) -> bytes:
        """Base64-decode and RSA-OAEP decrypt. Raises InvalidEncryptedPayloadException on any failure.

        All failure modes share one exception and one public message so the endpoint cannot be
        used as a padding / decryption oracle. Specifics only go to the (non-sensitive) log detail.
        """
        try:
            ciphertext = base64.b64decode(encrypted_data, validate=True)
        except (binascii.Error, ValueError):
            raise InvalidEncryptedPayloadException("not valid base64") from None

        # An RSA ciphertext is always exactly key-size bytes; reject anything else cheaply.
        if len(ciphertext) != self._key_bytes:
            raise InvalidEncryptedPayloadException("unexpected ciphertext length") from None

        try:
            return self._keys.private_key().decrypt(ciphertext, _oaep())
        except (ValueError, InvalidKey):
            raise InvalidEncryptedPayloadException("rsa-oaep decryption failed") from None

    def encrypt_payload(self, plaintext: bytes) -> str:
        """Encrypt with the public key and return base64 (what a client/frontend does)."""
        try:
            ciphertext = self._keys.public_key().encrypt(plaintext, _oaep())
        except ValueError:
            raise InvalidEncryptedPayloadException("plaintext too large for RSA-OAEP") from None
        return base64.b64encode(ciphertext).decode("ascii")
