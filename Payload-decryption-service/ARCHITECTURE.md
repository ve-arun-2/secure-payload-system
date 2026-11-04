# Secure Payload Processing Service — Architecture Guide

A FastAPI backend (Python 3.13, Pydantic v2) that accepts RSA-encrypted partner payloads, rate-limits per partner, decrypts and validates them, and publishes a `Secure_Payload_Received` event to RabbitMQ. This document explains how the system is organised and how a request flows through it.

---

## 1. System context

```
 ┌──────────┐  1. GET /api/v1/keys/public        ┌───────────────────────────┐
 │ Frontend │ ─────────────────────────────────▶ │                           │
 │ / Partner│  2. encrypt JSON with public key   │   FastAPI service (N pods)│
 │          │  3. POST /api/v1/sandbox/          │                           │
 │          │        secure-payload              │                           │
 └──────────┘ ─────────────────────────────────▶ │                           │
                                                 └───────┬───────────┬───────┘
                                      token bucket (Lua) │           │ publish (confirmed)
                                                         ▼           ▼
                                                  ┌──────────┐  ┌──────────────┐
                                                  │  Redis   │  │  RabbitMQ    │──▶ downstream consumers
                                                  └──────────┘  └──────────────┘
```

* **Frontend** fetches the public key, encrypts a small JSON document with RSA-OAEP (SHA-256), and submits it base64-encoded.
* **Service pods** are stateless. All shared state lives in Redis (rate limits) and RabbitMQ (events).
* **Private key** never leaves the service; only the public key is exposed.

---

## 2. Request lifecycle (the main workflow)

`POST /api/v1/sandbox/secure-payload` with `{"partner_id": "...", "encrypted_data": "<base64>"}`

```
Request
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ RequestContextMiddleware (outermost)                        │
│  • assign/validate X-Request-ID, start timer                │
│  • on exit: write the JSON access-log line                  │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│ RateLimiterMiddleware                                       │
│  • only for POST /api/v1/sandbox/secure-payload             │
│  • buffer body (max 16 KB, else 413), extract partner_id    │
│  • consume 1 token from bucket rate_limit:{partner_id}      │
│      ├─ rejected → 429 {"error","message"} + Retry-After    │
│      │             ── request STOPS here, never decrypted   │
│      ├─ Redis down → 503 (or allow if FAIL_OPEN=true)       │
│      └─ allowed → replay buffered body downstream           │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│ Route: secure_payload.py                                    │
│  • Pydantic validates SecurePayloadRequest (else 422)       │
│  • calls PayloadService.process()                           │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│ PayloadService                                              │
│  1. CryptoService.decrypt_payload()  (in a worker thread)   │
│        fail → 400 "Invalid encrypted payload"               │
│  2. json.loads → must be an object                          │
│  3. DecryptedPayload validation                             │
│        fail → 400 "Malformed payload"                       │
│  4. TransactionService → txn_<16 hex>                       │
│  5. Build SecurePayloadReceivedEvent                        │
│  6. RabbitMQService.publish() (publisher-confirmed)         │
│        fail → 503 "Failed to publish event"                 │
│  7. return transaction_id                                   │
└───────────────┬─────────────────────────────────────────────┘
                ▼
        200 {"status":"success","transaction_id":"txn_..."}
```

Ordering guarantees:
* Rate limiting happens **before** routing, schema validation, and decryption. A throttled caller costs one Redis call and no RSA work.
* Exceptions raised inside middleware are not seen by FastAPI's exception handlers, so the rate limiter builds its own responses with the same `error_response()` helper.

---

## 3. Layers and folder map

The code follows Clean Architecture: dependencies point **inward**, and infrastructure details sit behind interfaces.

```
app/
├── main.py                  Application factory, middleware order, lifespan, /health
├── api/routes/              HTTP layer (thin): parse request, call a service, shape response
│   ├── secure_payload.py      POST /api/v1/sandbox/secure-payload
│   └── keys.py                GET  /api/v1/keys/public
├── services/                Application / business logic
│   ├── payload_service.py     Orchestrates the whole pipeline
│   ├── crypto_service.py      RSA-OAEP only (+ KeyProvider abstraction)
│   ├── transaction_service.py txn id generation
│   ├── rate_limit_service.py  Token-bucket policy on top of RedisCache
│   └── rabbitmq_service.py    aio-pika publisher + topology
├── cache/redis_cache.py     RedisCache interface; RedisCacheImpl and InMemoryCache
├── middleware/
│   ├── request_context.py     request id, timing, access log
│   └── rate_limiter.py        enforces limit before decryption
├── schemas/                 Pydantic models
│   ├── requests.py            SecurePayloadRequest (API in)
│   ├── responses.py           success / key / health / error (API out)
│   └── internal.py            DecryptedPayload, BucketDecision, refill_tokens()
├── models/event_models.py   SecurePayloadReceivedEvent (message contract)
├── dependencies/providers.py Container (composition root) + FastAPI Depends providers
├── core/                    Cross-cutting
│   ├── config.py              Pydantic Settings (env vars)
│   ├── logger.py              JSON logging + per-request context
│   ├── security.py            masking / redaction helpers
│   ├── exceptions.py          domain exceptions + HTTP mapping + handlers
│   └── observability.py       Prometheus / OpenTelemetry placeholders
└── tests/                   conftest.py, test_crypto.py, test_rate_limiter.py, test_api.py
scripts/generate_keys.py     Creates mock RSA key pair in keys/
```

### Layer responsibilities

| Layer | Knows about | Must not |
|---|---|---|
| **API routes** | schemas, `Depends` providers | contain business logic or touch crypto/Redis/RabbitMQ directly |
| **Services** | schemas, models, interfaces (`RedisCache`, `EventPublisher`, `KeyProvider`) | know about HTTP, FastAPI, or Starlette |
| **Cache / broker adapters** | their client libraries (redis, aio-pika) | contain business rules |
| **Schemas / models** | pydantic only | import services or adapters |
| **Core** | stdlib, pydantic, FastAPI (exceptions only) | depend on services |

`PayloadService` depends on the `EventPublisher` Protocol, not on `RabbitMQService`; `RateLimitService` depends on the `RedisCache` ABC, not on Redis. That is why tests run with no infrastructure.

---

## 4. Component details

### 4.1 Application factory and DI (`main.py`, `dependencies/providers.py`)
* `create_app(settings=None, container=None)` configures logging, builds the `Container`, adds middleware, registers exception handlers and routers.
* `Container` holds the singletons: settings, cache, RabbitMQ, crypto, transaction, rate limiter, payload service. `build_container()` wires production implementations (no network I/O at construction); `assemble_container()` accepts prebuilt infrastructure, which tests use.
* Routes get services through `Depends(get_payload_service)` / `Depends(get_crypto_service)`, which read `request.app.state.container`. Overridable via `app.dependency_overrides`.
* **Lifespan:** on startup `rabbitmq.connect()` (fail fast if the broker is unreachable); on shutdown closes RabbitMQ and Redis.
* **Middleware order:** `add_middleware` makes the last-added the outermost, so `RequestContextMiddleware` wraps `RateLimiterMiddleware`; 429s therefore still get a request id and an access-log line.
* `app.main:app` is a lazy module attribute, so importing the module (e.g. in tests) does not require keys or environment.

### 4.2 Crypto (`services/crypto_service.py`)
* `KeyProvider` (ABC) → `FileKeyProvider` loads two PEM files separately and checks the pair matches. Swap in a KMS/HSM/Vault provider without touching `CryptoService`.
* `CryptoService`:
  * `get_public_key()` → PEM string.
  * `decrypt_payload(encrypted_data)` → bytes. Strict base64 → ciphertext length must equal key size → RSA-OAEP (MGF1-SHA256, SHA256).
  * `encrypt_payload(plaintext)` → base64 (used by tests / client simulation).
* All decrypt failures raise `InvalidEncryptedPayloadException` with the same client-visible message, so callers cannot distinguish failure causes (no oracle).
* **Size limit:** RSA-OAEP/SHA-256 encrypts at most `key_bytes − 66` bytes: 190 for 2048-bit, 318 for the 3072-bit mock keys. For larger payloads use hybrid encryption (RSA-wrapped AES-GCM key).

### 4.3 Payload processing (`services/payload_service.py`, `schemas/internal.py`)
* Decryption runs through `asyncio.to_thread` because RSA private-key operations are CPU-bound.
* `DecryptedPayload` rules: `name` required (1–128, trimmed), `aadhaar_number` exactly 12 ASCII digits and must be a **string** (a JSON number would lose leading zeros), `device_id` required (1–64), unknown fields rejected.
* Pydantic `ValidationError` is converted to `InvalidPayloadException` with only field *names* in the log detail; pydantic messages can contain the submitted value.
* `MASK_AADHAAR_IN_EVENTS=true` publishes only the last 4 digits in the event.

### 4.4 Transaction ids (`services/transaction_service.py`)
`txn_` + first 16 hex chars of `uuid4()` (CSPRNG-backed), e.g. `txn_f8de98ab2d384d87`.

### 4.5 Rate limiting (`rate_limit_service.py`, `cache/redis_cache.py`, `middleware/rate_limiter.py`)

**Token bucket, built from scratch.** Each partner has a bucket of `capacity` tokens (default 10) refilled at `refill_per_second` (default 10/s). Refill is lazy, computed when a request arrives:

```
tokens = min(capacity, tokens + (now − last_refill) × refill_per_second)
allowed    = tokens ≥ 1  → tokens −= 1
retry_after = (1 − tokens) / refill_per_second   (when rejected)
```

Effect: a partner may burst 10 requests, then sustain 10 requests/second.

**`RedisCache` interface:** `get`, `set`, `increment`, plus `consume_token_bucket`, `ping`, `close`. The bucket method exists because get-then-set from several pods would race.

**`RedisCacheImpl`:** runs a Lua script (`HMGET` → refill → consume → `HSET` → `EXPIRE`) atomically in Redis. It uses Redis `TIME` as the clock (immune to pod clock skew) and sets a TTL of `capacity/rate + 2` seconds so idle buckets disappear. Key: `rate_limit:{partner_id}`; Redis errors become `CacheUnavailableException`.

**`InMemoryCache`:** same algorithm (shared `refill_tokens()` function), injectable clock; for tests and local use only, not distributed-safe.

**Middleware details:**
* Applies to `POST` on the protected path only; other routes pass through.
* `partner_id` must match `^[A-Za-z0-9_-]{1,64}$`; otherwise the bucket is `rate_limit:ip:{client_host}`. This stops attackers creating unlimited Redis keys with random ids. Behind a load balancer run uvicorn with `--proxy-headers`.
* On Redis failure: 503 by default (fail closed); `RATE_LIMIT_FAIL_OPEN=true` allows traffic and logs an error.

### 4.6 RabbitMQ (`services/rabbitmq_service.py`)

```
publisher ─▶ secure.payload.exchange (direct, durable)
                 │ routing key: secure.payload.received
                 ▼
             secure.payload.queue  (quorum, durable)
                 │ dead-letter on reject / delivery-limit
                 ▼
             secure.payload.dlx ─▶ secure.payload.queue.dlq (quorum, durable)
```

* `connect()` uses `connect_robust` (auto-reconnect), opens a channel with **publisher confirms**, and declares the topology idempotently.
* `publish(event)` sends a persistent JSON message (`message_id` = transaction id, `type` = event type) with `mandatory=True`, so unroutable messages raise instead of vanishing, and with a timeout. Any failure becomes `RabbitMQPublishException` (HTTP 503); the underlying error is logged by type only.
* `close()` closes the connection. If the first publish happens without a connection, it attempts `connect()` lazily.
* **Event contract** (`models/event_models.py`):
```json
{
  "event_type": "Secure_Payload_Received",
  "transaction_id": "txn_f8de98ab2d384d87",
  "partner_id": "partner-123",
  "timestamp": "2026-11-02T10:15:30.123456Z",
  "payload": { "name": "...", "aadhaar_number": "...", "device_id": "..." }
}
```
> The event contains personal data. Treat the queue as sensitive storage (TLS, access control), enable `MASK_AADHAAR_IN_EVENTS`, or encrypt/tokenise for consumers.

### 4.7 Errors (`core/exceptions.py`)

| Exception | HTTP | Body |
|---|---|---|
| `InvalidEncryptedPayloadException` | 400 | `{"error": "Invalid encrypted payload"}` |
| `InvalidPayloadException` | 400 | `{"error": "Malformed payload"}` |
| `RateLimitExceededException` | 429 | `{"error": "Rate limit exceeded", "message": "Rate limit exceeded"}` + `Retry-After` |
| `RabbitMQPublishException` | 503 | `{"error": "Failed to publish event"}` |
| `CacheUnavailableException` | 503 | `{"error": "Rate limiter unavailable"}` |
| Request schema errors | 422 | `{"error": "Invalid request", "details": [{field, message}]}` (never echoes values) |
| Body > `MAX_REQUEST_BODY_BYTES` | 413 | `{"error": "Request body too large"}` |
| Anything unexpected | 500 | `{"error": "Internal server error"}` |

Each exception carries a `detail` for logs only; it is never sent to the client.

### 4.8 Logging and data protection (`core/logger.py`, `core/security.py`, `middleware/request_context.py`)
* One JSON object per line on stdout. A per-request context dict (`request_id`, `partner_id`, `transaction_id`, `event_publish_status`) is attached automatically to every record emitted during the request.
* The access-log line `request_completed` adds `method`, `path`, `status_code`, `response_time_ms`.
* Inbound `X-Request-ID` is accepted only if it matches `^[A-Za-z0-9._-]{8,64}$` (prevents log injection); otherwise a UUID is generated. It is returned in the response header.
* Masking is applied in the formatter to everything logged: sensitive keys (`aadhaar_number` → `********9012`, `name` → `J***`, `encrypted_data`/`password`/`token`… → `[REDACTED]`) and any free-text 12-digit run. `transaction_id`/`request_id` are exempt from pattern scanning to avoid false positives.
* `DecryptedPayload.__repr__` is redacted so an accidental `print`/`log` of the object leaks nothing.

### 4.9 Observability
* `GET /health` → `{"status": "healthy"}` (liveness only; it does not probe dependencies).
* `core/observability.py` contains `setup_metrics` and `setup_tracing` placeholders with instructions for Prometheus (`/metrics`) and OpenTelemetry (FastAPI, Redis and aio-pika instrumentation).
* Swagger/OpenAPI is disabled when `APP_ENV` is `production`/`prod`.

---

## 5. Scalability and shared state

* **Stateless pods:** nothing is stored in process memory that matters across requests, so pods scale horizontally behind any load balancer.
* **Shared rate limiting:** all pods call the same Lua script on the same key. Redis executes scripts serially, so two pods can never both spend the last token; the limit is global per partner regardless of which pod receives the request.
* **Backpressure:** throttling happens before CPU-heavy decryption, protecting the service under abusive load.
* **Durability:** persistent messages + publisher confirms + quorum queues mean a `200` response implies the broker has accepted the event.
* **Redis memory** is bounded by active partners thanks to key TTLs.
* For Redis Cluster/HA, the script touches a single key, so it is cluster-safe.

---

## 6. Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `secure-payload-service` | Service name in logs/title |
| `APP_ENV` | `development` | `production`/`prod` disables docs |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `RSA_PRIVATE_KEY_PATH` | `keys/private.pem` | Private key (PKCS8 PEM) |
| `RSA_PUBLIC_KEY_PATH` | `keys/public.pem` | Public key (SPKI PEM) |
| `RSA_PRIVATE_KEY_PASSWORD` | – | Optional key passphrase |
| `REDIS_URL` | `redis://localhost:6379/0` | Rate-limit store |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Broker |
| `RATE_LIMIT_CAPACITY` | `10` | Bucket size (burst) |
| `RATE_LIMIT_REFILL_PER_SECOND` | `10` | Sustained rate |
| `RATE_LIMIT_FAIL_OPEN` | `false` | Behaviour when Redis is down |
| `MAX_REQUEST_BODY_BYTES` | `16384` | Body cap enforced in middleware |
| `RABBITMQ_PUBLISH_TIMEOUT_SECONDS` | `5` | Publish timeout |
| `MASK_AADHAAR_IN_EVENTS` | `false` | Mask Aadhaar in published event |

Copy `.env.example` to `.env` to start.

---

## 7. Running, testing, and client usage

```bash
# setup
uv venv --python 3.13 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python scripts/generate_keys.py        # mock keys (dev only)

# infrastructure + service
docker compose up redis rabbitmq
.venv/Scripts/uvicorn app.main:app --proxy-headers

# tests (no Redis/RabbitMQ needed)
.venv/Scripts/python -m pytest
```

**Client side** (Python example of what the frontend does):
```python
import base64, json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

public_key = serialization.load_pem_public_key(pem_from_keys_endpoint.encode())
ciphertext = public_key.encrypt(
    json.dumps({"name": "John Doe", "aadhaar_number": "123456789012", "device_id": "DEVICE001"}).encode(),
    padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
)
body = {"partner_id": "partner-123", "encrypted_data": base64.b64encode(ciphertext).decode()}
```
Browsers: use WebCrypto `RSA-OAEP` with `hash: "SHA-256"`, which matches.

### Test map
| File | Covers |
|---|---|
| `test_crypto.py` | round trip, randomised OAEP, bad base64/length, tampering, wrong key, key-pair mismatch |
| `test_rate_limiter.py` | refill maths, burst then reject, refill over time, sustained 10 rps, per-partner isolation, fail-closed/open |
| `test_api.py` | success + event contents, 429 and "decrypt never called", per-partner limits, malformed payload variants, invalid ciphertext, RabbitMQ failure → 503, 422 not echoing input, 413, log masking and fields |

Tests use `InMemoryCache` with a manual clock and a `FakeRabbitMQ`, so they are deterministic and offline.

---

## 8. Known limitations / production checklist
1. The Lua script and the RabbitMQ topology have not been exercised against real servers in this repo's test suite; run an integration check with `docker compose`.
2. Mock keys in `keys/` are for development only; load real keys from a secrets manager or HSM and add key rotation (e.g. a `kid` in the request and key list in `KeyProvider`).
3. No authentication/authorisation: `partner_id` is self-declared, so the rate limit is only as trustworthy as the caller. Add API keys, mTLS, or signed requests before real use.
4. Replay protection (nonce/timestamp inside the encrypted payload) is not implemented.
5. `/health` is liveness only; add a readiness probe that checks Redis and RabbitMQ.
6. The event includes personal data (see 4.6).
7. Metrics and tracing are placeholders.
