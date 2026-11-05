import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import RabbitMQPublishException
from app.dependencies.providers import Container, assemble_container
from app.main import create_app
from app.models.event_models import SecurePayloadReceivedEvent
from app.services.crypto_service import CryptoService, FileKeyProvider
from app.tests.fakes import InMemoryCache

VALID_PAYLOAD = {"name": "John Doe", "aadhaar_number": "123456789012", "device_id": "DEVICE001"}


class ManualClock:
    """Deterministic clock so token-bucket tests never depend on wall time."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRabbitMQ:
    def __init__(self) -> None:
        self.events: list[SecurePayloadReceivedEvent] = []
        self.fail = False

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def publish(self, event: SecurePayloadReceivedEvent) -> None:
        if self.fail:
            raise RabbitMQPublishException("simulated broker outage")
        self.events.append(event)


def write_key_pair(directory: Path, key_size: int = 2048) -> tuple[Path, Path]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    private_path, public_path = directory / "private.pem", directory / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private_path, public_path


@pytest.fixture(scope="session")
def key_paths(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    return write_key_pair(tmp_path_factory.mktemp("keys"))


@pytest.fixture
def crypto(key_paths: tuple[Path, Path]) -> CryptoService:
    return CryptoService(FileKeyProvider(*key_paths))


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def broker() -> FakeRabbitMQ:
    return FakeRabbitMQ()


@pytest.fixture
def container(crypto: CryptoService, clock: ManualClock, broker: FakeRabbitMQ) -> Container:
    settings = Settings(APP_ENV="test", RATE_LIMIT_CAPACITY=10, RATE_LIMIT_REFILL_PER_SECOND=10)
    return assemble_container(settings, crypto=crypto, cache=InMemoryCache(clock=clock), publisher=broker)


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    app = create_app(container.settings, container)
    with TestClient(app) as test_client:
        yield test_client


def encrypt_body(crypto: CryptoService, payload: dict | bytes | str, partner_id: str = "partner-123") -> dict:
    """Build a request body the way the frontend would."""
    if isinstance(payload, dict):
        raw = json.dumps(payload).encode()
    elif isinstance(payload, str):
        raw = payload.encode()
    else:
        raw = payload
    return {"partner_id": partner_id, "encrypted_data": crypto.encrypt_payload(raw)}
