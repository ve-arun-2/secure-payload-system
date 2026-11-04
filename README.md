# Secure Payload System

An end-to-end system for sending sensitive partner data (name, Aadhaar number, device ID) safely.
The browser encrypts the data with the service's RSA public key, so the plaintext never crosses the
network. The backend rate-limits each partner, decrypts and validates the payload, assigns a
transaction ID, and publishes a `Secure_Payload_Received` event to RabbitMQ.

| Component | Path | Stack |
| --- | --- | --- |
| **UI client** (partner simulator) | [Payload-encryption-client/](Payload-encryption-client) | React 19, TypeScript, Vite, Tailwind, Web Crypto |
| **Backend service** | [Payload-decryption-service/](Payload-decryption-service) | Python 3.13, FastAPI, Redis, RabbitMQ |

### Request flow

1. The client fetches the RSA public key from `GET /api/v1/keys/public`.
2. In a Web Worker, it encrypts `{name, aadhaar_number, device_id}` with **RSA-OAEP / SHA-256** and Base64-encodes the result.
3. It sends `POST /api/v1/sandbox/secure-payload` with `{ "partner_id": "...", "encrypted_data": "<base64>" }`.
4. The backend consumes one token from the partner's bucket **before** any decryption. An empty bucket returns `429` with `Retry-After`.
5. The backend decrypts with the private key, validates the fields, generates `txn_<16 hex>`, and publishes the event with publisher confirms.
6. It returns `200 {"status": "success", "transaction_id": "txn_..."}`.

## UI client

A single-page simulator of a partner integration.

- Validates input with Zod before anything is encrypted.
- Encrypts off the UI thread, in a dedicated Web Worker.
- Uses a non-extractable, encrypt-only key and zero-fills the plaintext buffer after use.
- Sends only `partner_id` and ciphertext. It never logs request or response bodies.
- Keeps only the masked Aadhaar and the transaction ID for the success screen.
- Maps failures to stable, user-safe messages (key fetch failed, rate limited, server error, network error).

Details: [Payload-encryption-client/README.md](Payload-encryption-client/README.md)

## Backend service

A FastAPI service organised as Clean Architecture (routes → services → adapters).

- **Crypto:** RSA-OAEP (MGF1-SHA256) only, with no legacy fallback. Every decrypt failure returns the same generic error, so callers can't tell why it failed. The private key stays in the service behind a swappable `KeyProvider` (file today, KMS/HSM/Vault later).
- **Rate limiting:** a token bucket per `partner_id` (default burst 10, 10 req/s sustained), written from scratch. Refill and consume run atomically in a Redis Lua script, so all pods share one bucket per partner. It uses Redis `TIME`, so pod clock skew doesn't matter.
- **Messaging:** a durable direct exchange, a quorum queue and a dead-letter queue. Messages are persistent and published with confirms and `mandatory=True`, so a `200` means the broker accepted the event.
- **Safe logging:** JSON logs with a per-request ID. Aadhaar numbers, names, ciphertext and tokens are masked or redacted before they are written.
- **Operations:** the pods hold no state, `/health` is a liveness probe, and Swagger is disabled in production.

Details: [Payload-decryption-service/ARCHITECTURE.md](Payload-decryption-service/ARCHITECTURE.md)

### API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/keys/public` | RSA public key (SPKI PEM) |
| `POST` | `/api/v1/sandbox/secure-payload` | Submit an encrypted payload |
| `GET` | `/health` | Liveness check |

| Status | Meaning |
| --- | --- |
| `200` | Accepted; returns `transaction_id` |
| `400` | Invalid ciphertext, or malformed decrypted payload |
| `413` | Request body over 16 KB |
| `422` | Request schema error (input values are never echoed) |
| `429` | Rate limit exceeded; see `Retry-After` |
| `503` | Redis or RabbitMQ unavailable |


## Things to know before using this for real

The backend's own checklist is in [ARCHITECTURE.md §8](Payload-decryption-service/ARCHITECTURE.md). The main points:

- **No authentication.** `partner_id` is self-declared, so the rate limit is only as trustworthy as the caller. Add API keys, mTLS or signed requests.
- **No replay protection.** Add a nonce or timestamp inside the encrypted payload.
- **Mock keys are for development only.** Load production keys from a secrets manager or HSM, and add key rotation (for example a `kid`).
- **The event carries personal data.** Use TLS and access control on the queue, enable `MASK_AADHAAR_IN_EVENTS`, or tokenise for consumers.
- **RSA payload size limit.** RSA-OAEP/SHA-256 encrypts at most `key bytes − 66` bytes (190 for a 2048-bit key). The client caps field lengths to stay within that. Larger payloads need hybrid encryption (an RSA-wrapped AES-GCM key).
- **Redis Lua script and RabbitMQ topology are untested against real servers.** The tests use in-memory fakes, so run an integration check with `docker compose`.
- **`/health` is liveness only.** Add a readiness probe that checks Redis and RabbitMQ.
- **Metrics and tracing are placeholders.**

## Repository layout

```
secure-payload-system/
├── README.md
├── Payload-encryption-client/      React UI (Vite)
│   └── src/  api · components · hooks · pages · schemas · services · types · workers
└── Payload-decryption-service/     FastAPI backend
    ├── app/  api · cache · core · dependencies · middleware · models · schemas · services · tests
    ├── scripts/generate_keys.py
    ├── Dockerfile · docker-compose.yml
    └── ARCHITECTURE.md
```
