# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a Technion course mini-project ("כתיבת תוכנה ללמידת מכונה"). The repo currently contains only the assignment spec and a smoke test — **no server implementation exists yet**. The task is to build the `PictureServer` HTTP API described in `interface.md`.

- `interface.md` — wire protocol spec (authoritative). Treat as a contract; deviations from status codes, JSON shapes, or auth semantics will fail grading.
- `HW1-2.pdf` — assignment PDF.
- `test_noam.py` — sample integration test (register → login → logout). Hits `http://localhost:5000` by default; the port is a `TODO` in the file, so the server must either run on 5000 or the test must be updated.

## Running the tests

```bash
# Start the server first on the port matching test_noam.py (default 5000), then:
pytest test_noam.py -v
# Single test:
pytest test_noam.py::test_register_login_logout_flow -v
```

`requests` is the only external dependency used by tests so far.

## Architecture the implementation must satisfy

Single HTTP server exposing six endpoints (see `interface.md` for full status-code matrices and JSON shapes):

| Endpoint | Auth | Body | Notes |
|---|---|---|---|
| `POST /register` | none | JSON `{username, password}` | 201/400/409/405/500 |
| `POST /login` | none | JSON `{username, password}` | Returns `{"token": ...}` (Bearer) |
| `POST /logout` | Bearer | — | Invalidates token |
| `POST /classifier` | Bearer | multipart form-data, field `image`, PNG/JPEG only | Synchronous; returns `{"matches": [{"name", "score"}]}` |
| `GET /status` | Bearer | — | Returns uptime (fractional seconds), success/fail counts, health, `api_version: 1` |

Cross-cutting contract rules that span endpoints (easy to miss if implementing endpoint-by-endpoint):

- **Error envelope**: every error response body is `{"error": {"http_status": N, "message": "..."}}` where `http_status` *must equal* the HTTP status code on the response. Status mismatches are an explicit failure mode called out in the spec.
- **Content-Type**: all responses are `application/json` (including errors).
- **Auth**: missing/malformed/expired Bearer token → 401 on every protected endpoint. `/status` is protected.
- **Job counters** (`/status.processed`): a "job" is a `/classifier` call. A malformed upload (e.g., non-PNG/JPEG, undecodable bytes) returns 400 *and* increments `fail`. Successful classification (regardless of correctness) → 200 and increments `success`. Other endpoints don't touch these counters.
- **Health**: `"ok"` iff classification is currently possible, else `"error"` (e.g., downstream model/API unreachable).
- **Method handling**: wrong HTTP method on a known endpoint → 405 (not 404). The spec lists 405 explicitly per endpoint.
- **No redirects, no CORS, no keep-alive guarantees**, HTTP scheme only for API v1.
- **Classifier score invariant**: each score in `(0.0, 1.0]`, and the *sum* of returned scores is in `[0, 1]` (i.e., the response is a partial top-k of a probability distribution, not a renormalized one).

## Working in this repo

The directory path contains Hebrew characters and spaces — always quote paths in shell commands. There is no `package.json`, `requirements.txt`, `pyproject.toml`, or git repo yet; introduce them deliberately when starting implementation rather than assuming they exist.
