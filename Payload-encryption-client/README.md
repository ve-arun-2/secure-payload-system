# Payload Encryption Client (Secure Payload Simulator)

A React + TypeScript single-page app that simulates a partner sending sensitive data to the
[Payload Decryption Service](../Payload-decryption-service). Plaintext is encrypted **in the browser**
with the service's RSA public key, so only ciphertext is ever sent over the network.

## How it works

```
 Form (partner_id, name, aadhaar_number, device_id)
   │  validated with Zod
   ▼
 GET /api/v1/keys/public ───────────────► RSA public key (SPKI PEM)
   │
   ▼
 Web Worker: import key → RSA-OAEP/SHA-256 encrypt → Base64
   │
   ▼
 POST /api/v1/sandbox/secure-payload   { partner_id, encrypted_data }
   │
   ▼
 { status: "success", transaction_id }  → success screen (Aadhaar shown masked)
```

1. The public key is fetched and checked (`algorithm` is `RSA`, value is a `BEGIN PUBLIC KEY` PEM).
2. `name`, `aadhaar_number` and `device_id` are serialized to JSON and encrypted with **RSA-OAEP / SHA-256**
   in a dedicated Web Worker, so the UI thread never touches the encryption work. There is no
   configurable or legacy algorithm fallback.
3. Only `partner_id` and the Base64 ciphertext (`encrypted_data`) are sent. `partner_id` is not encrypted.

## Security design

- The imported key is non-extractable and encrypt-only.
- The plaintext byte buffer is zero-filled as soon as encryption finishes.
- Worker failures carry no error text, so nothing derived from the payload leaves the worker.
- Request and response bodies are never logged; only HTTP status codes leave the HTTP client.
- Requests use `credentials: 'omit'` and `cache: 'no-store'`, with a 15 s timeout.
- Only the masked Aadhaar and the transaction ID are kept for display.

## Validation rules

| Field            | Rule                                                              |
| ---------------- | ----------------------------------------------------------------- |
| `partner_id`     | Required, max 64 characters                                       |
| `name`           | 3+ characters, max 50 UTF-8 bytes                                 |
| `aadhaar_number` | Exactly 12 digits                                                 |
| `device_id`      | Required, max 64 characters, only `A-Z a-z 0-9 . _ : -`           |

The byte limits exist because RSA-2048 with OAEP/SHA-256 can encrypt at most 190 bytes. They keep the
JSON payload inside that limit.

## Tech stack

React 19, TypeScript 5.8, Vite 7, Tailwind CSS 4, React Hook Form + Zod, TanStack Query, Web Crypto API.

## Getting started

Prerequisites: Node.js 20+ and the decryption service running (default `http://localhost:8000`).

```bash
npm install
cp .env.example .env     # optional; defaults work for local dev
npm run dev              # http://localhost:5173
```

### Scripts

| Command             | Description                          |
| ------------------- | ------------------------------------ |
| `npm run dev`       | Start the Vite dev server (port 5173) |
| `npm run build`     | Type-check, then build to `dist/`    |
| `npm run preview`   | Serve the production build locally   |
| `npm run typecheck` | Run `tsc -b --noEmit`                |

## Configuration

| Variable                | Default                 | Purpose                                                                      |
| ----------------------- | ----------------------- | ---------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`     | *(empty)*               | API base URL. Leave empty in dev to use same-origin `/api/...` via the proxy. |
| `VITE_DEV_PROXY_TARGET` | `http://localhost:8000` | Backend that the Vite dev server proxies `/api` to.                          |

In dev, the Vite proxy makes requests same-origin, so no CORS setup is needed. For a production build,
set `VITE_API_BASE_URL` to the API origin and allow that origin in the backend's CORS settings, or serve
both behind one reverse proxy.

## Error handling

| Situation                          | Message shown                                          |
| ---------------------------------- | ------------------------------------------------------ |
| Public key fetch or validation fails | Unable to obtain encryption key.                      |
| Encryption fails                   | Failed to encrypt payload.                             |
| HTTP 429                           | Rate limit exceeded. Please try again later.           |
| HTTP 5xx                           | Unexpected server error.                               |
| Network failure or timeout         | Unable to reach the server. Check your connection and try again. |
| Any other non-2xx                  | Unable to submit the secure payload.                   |

The backend rate limit is a per-partner token bucket (default: burst of 10, 10 requests/s sustained).

## Project structure

```
src/
├── api/          httpClient (fetch wrapper), keysApi, payloadApi
├── components/   Form, submit button, loading overlay, error banner, success result
├── hooks/        usePublicKey, useEncryptPayload, useSubmitPayload
├── pages/        SecurePayloadPage
├── schemas/      Zod validation (securePayloadSchema)
├── services/     cryptoService (Web Crypto), workerService (worker bridge)
├── types/        Shared TypeScript types and error codes
└── workers/      encryption.worker.ts
```

## Backend API used

| Method | Path                              | Purpose                      |
| ------ | --------------------------------- | ---------------------------- |
| GET    | `/api/v1/keys/public`             | Fetch the RSA public key     |
| POST   | `/api/v1/sandbox/secure-payload`  | Submit the encrypted payload |
