import json
import re

import pytest
from fastapi.testclient import TestClient

from app.services.crypto_service import CryptoService
from app.tests.conftest import VALID_PAYLOAD, FakeRabbitMQ, encrypt_body

URL = "/api/v1/sandbox/secure-payload"


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_public_key_endpoint(client: TestClient, crypto: CryptoService) -> None:
    response = client.get("/api/v1/keys/public")
    assert response.status_code == 200
    assert response.json() == {"algorithm": "RSA", "public_key": crypto.get_public_key()}


def test_success_path_publishes_event(client: TestClient, crypto: CryptoService, broker: FakeRabbitMQ) -> None:
    response = client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert re.fullmatch(r"txn_[0-9a-f]{16}", body["transaction_id"])
    assert response.headers["X-Request-ID"]

    assert len(broker.events) == 1
    event = broker.events[0]
    assert event.event_type == "Secure_Payload_Received"
    assert event.transaction_id == body["transaction_id"]
    assert event.partner_id == "partner-123"
    assert event.payload == VALID_PAYLOAD


def test_rate_limit_rejection_never_reaches_decryption(
    client: TestClient, crypto: CryptoService, broker: FakeRabbitMQ, monkeypatch: pytest.MonkeyPatch
) -> None:
    decrypt_calls = 0
    original = crypto.decrypt_payload

    def spy(encrypted_data: str) -> bytes:
        nonlocal decrypt_calls
        decrypt_calls += 1
        return original(encrypted_data)

    monkeypatch.setattr(crypto, "decrypt_payload", spy)
    body = encrypt_body(crypto, VALID_PAYLOAD)

    statuses = [client.post(URL, json=body).status_code for _ in range(11)]

    assert statuses == [200] * 10 + [429]
    assert decrypt_calls == 10  # the 11th request was stopped before decryption
    assert len(broker.events) == 10

    rejected = client.post(URL, json=body)
    assert rejected.status_code == 429
    assert rejected.json() == {"error": "Rate limit exceeded", "message": "Rate limit exceeded"}
    assert int(rejected.headers["Retry-After"]) >= 1


def test_rate_limit_is_per_partner(client: TestClient, crypto: CryptoService) -> None:
    for _ in range(10):
        client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD, partner_id="partner-a"))

    assert client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD, partner_id="partner-a")).status_code == 429
    assert client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD, partner_id="partner-b")).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        '["a", "list"]',
        {"aadhaar_number": "123456789012", "device_id": "DEVICE001"},  # missing name
        {"name": "John", "aadhaar_number": "123456789012"},  # missing device_id
        {"name": "John", "aadhaar_number": "12345678901", "device_id": "D1"},  # 11 digits
        {"name": "John", "aadhaar_number": "1234567890123", "device_id": "D1"},  # 13 digits
        {"name": "John", "aadhaar_number": "12345678901a", "device_id": "D1"},  # non-numeric
        {"name": "John", "aadhaar_number": 123456789012, "device_id": "D1"},  # number, not string
        {"name": "  ", "aadhaar_number": "123456789012", "device_id": "D1"},  # blank name
        {**VALID_PAYLOAD, "unexpected": "field"},
    ],
)
def test_malformed_decrypted_payload(
    client: TestClient, crypto: CryptoService, broker: FakeRabbitMQ, payload: dict | str
) -> None:
    response = client.post(URL, json=encrypt_body(crypto, payload))

    assert response.status_code == 400
    assert response.json() == {"error": "Malformed payload"}
    assert broker.events == []


@pytest.mark.parametrize("encrypted_data", ["###", "aGVsbG8=", "A" * 344])
def test_invalid_encrypted_payload(client: TestClient, encrypted_data: str) -> None:
    response = client.post(URL, json={"partner_id": "partner-123", "encrypted_data": encrypted_data})

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid encrypted payload"}


def test_rabbitmq_publish_failure_returns_503(
    client: TestClient, crypto: CryptoService, broker: FakeRabbitMQ
) -> None:
    broker.fail = True
    response = client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD))

    assert response.status_code == 503
    assert response.json() == {"error": "Failed to publish event"}


def test_request_schema_validation_does_not_echo_input(client: TestClient) -> None:
    response = client.post(URL, json={"partner_id": "bad id!", "encrypted_data": "secret-value"})

    assert response.status_code == 422
    assert "secret-value" not in response.text


def test_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post(URL, content=b"x" * 100_000, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_logs_never_contain_decrypted_aadhaar(
    capsys: pytest.CaptureFixture[str], client: TestClient, crypto: CryptoService
) -> None:
    client.post(URL, json=encrypt_body(crypto, VALID_PAYLOAD))
    client.post(URL, json=encrypt_body(crypto, {**VALID_PAYLOAD, "aadhaar_number": "999988887777x"}))

    output = capsys.readouterr().out
    assert output, "expected structured log output"
    assert "123456789012" not in output
    assert "999988887777" not in output

    access = [json.loads(line) for line in output.splitlines() if '"request_completed"' in line]
    assert access[0]["partner_id"] == "partner-123"
    assert access[0]["transaction_id"].startswith("txn_")
    assert access[0]["event_publish_status"] == "published"
    assert access[0]["request_id"] and access[0]["response_time_ms"] >= 0
