import base64
from pathlib import Path

import pytest

from app.core.exceptions import InvalidEncryptedPayloadException
from app.services.crypto_service import CryptoService, FileKeyProvider
from app.tests.conftest import write_key_pair


def test_encrypt_then_decrypt_round_trip(crypto: CryptoService) -> None:
    plaintext = b'{"name": "John Doe", "aadhaar_number": "123456789012", "device_id": "DEVICE001"}'
    assert crypto.decrypt_payload(crypto.encrypt_payload(plaintext)) == plaintext


def test_encryption_is_randomised(crypto: CryptoService) -> None:
    # OAEP is probabilistic: identical plaintexts must give different ciphertexts.
    assert crypto.encrypt_payload(b"same") != crypto.encrypt_payload(b"same")


def test_public_key_is_pem(crypto: CryptoService) -> None:
    pem = crypto.get_public_key()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert "PRIVATE" not in pem


def test_invalid_base64_is_rejected(crypto: CryptoService) -> None:
    with pytest.raises(InvalidEncryptedPayloadException):
        crypto.decrypt_payload("***not-base64***")


def test_wrong_ciphertext_length_is_rejected(crypto: CryptoService) -> None:
    with pytest.raises(InvalidEncryptedPayloadException):
        crypto.decrypt_payload(base64.b64encode(b"too short").decode())


def test_tampered_ciphertext_is_rejected(crypto: CryptoService) -> None:
    raw = bytearray(base64.b64decode(crypto.encrypt_payload(b"hello")))
    raw[10] ^= 0xFF
    with pytest.raises(InvalidEncryptedPayloadException):
        crypto.decrypt_payload(base64.b64encode(bytes(raw)).decode())


def test_ciphertext_for_another_key_is_rejected(crypto: CryptoService, tmp_path: Path) -> None:
    other = CryptoService(FileKeyProvider(*write_key_pair(tmp_path)))
    with pytest.raises(InvalidEncryptedPayloadException):
        crypto.decrypt_payload(other.encrypt_payload(b"hello"))


def test_oversized_plaintext_cannot_be_encrypted(crypto: CryptoService) -> None:
    with pytest.raises(InvalidEncryptedPayloadException):
        crypto.encrypt_payload(b"x" * 1000)


def test_mismatched_key_pair_fails_fast(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    private_path, _ = write_key_pair(first)
    _, other_public = write_key_pair(second)
    with pytest.raises(ValueError, match="does not match"):
        FileKeyProvider(private_path, other_public)
