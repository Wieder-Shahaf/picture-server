# QA stress suite

**Not** part of the graded submission. This is an out-of-band stress suite
that probes every entry point of the PictureServer from many angles —
contract compliance, security, concurrency, adversarial input, image
prompt-injection, oversize payloads.

## Run

```bash
docker compose up -d                       # or whatever brings the server up
BASE_URL=http://localhost:15000 \
  python -m pytest qa/ -v
```

Roughly 80 seconds on a CPU laptop (the bulk is the 100-iteration
sequential `/classifier` load test).

## Coverage

180 tests over five files:

| File | Focus | Tests |
|---|---|---|
| `test_endpoint_surface.py` | Every endpoint × every reasonable input edge | ~55 |
| `test_concurrency_and_load.py` | Parallel requests, counter integrity, sequential load | 5 |
| `test_contract_compliance.py` | interface.md envelope shape, headers, status code matching, response schemas | 10 |
| `test_security.py` | JWT forgery (alg:none, empty sig, tampered subject), header injection, large body | 11 |
| `test_inputs_and_injection.py` | Character classes (NUL, CRLF, RTL override, unicode), SQL/XSS attempts, path-traversal filenames, image prompt-injection via PNG tEXt + JPEG EXIF comment, oversize JSON, 1×1 / 10000×1 / 3000×3000 images, format-confusion (PNG bytes with .jpeg filename, etc.) | ~50 |
| `test_ui_e2e.py` | Playwright: console errors, full flow, dropzone state, multi-format normalization (.png/.webp/.gif/.bmp → JPEG), log filtering, mobile horizontal scroll, localStorage hygiene | 13 |

## Threat models covered

- **Auth bypass.** Forged JWTs with `alg:none`, empty signature, tampered subject, random signature, expired exp, missing claims.
- **Credential leakage.** Password never echoed in any response.
- **Internal-detail leakage.** No `Traceback`, `Flask`, `Werkzeug`, `sqlite3`, or file paths in any error body.
- **SQL injection.** Classic payloads (`'; DROP TABLE`, etc.) survive harmless; a guard user planted before injection still authenticates after.
- **Header injection.** `\r\n` in username does not split the response.
- **Path traversal in filenames.** `../../etc/passwd.png` and similar produce 4xx with envelope, never side effects.
- **XSS.** No `<script>` reflected with a non-JSON Content-Type.
- **Prompt injection in images.** PNG `tEXt` chunks and JPEG EXIF comments containing prompt-like text do not affect YOLO output and the injected text never appears in the response.
- **CRLF / NUL / RTL-override** in usernames and passwords don't crash, corrupt, or split responses.
- **Concurrency.** 20-way race on duplicate `/register` yields exactly one 201 + nineteen 409. Parallel `/classifier` counters track exactly. Mixed valid/invalid parallel jobs increment success and fail by their respective counts.
- **Replay.** Double-logout returns 200 then 401 (idempotent). Revoked tokens survive across new connections (DB persistence).
- **Boundary sizes.** 1, 64, 256, 1024, 8192, 65536-char usernames + passwords. 1 MB JSON body. 1×1, 10000×1, 4000×50 images.
- **Format confusion.** PNG bytes with `.jpeg` filename, JPEG bytes with `.png` filename, polyglot PNG with garbage tail.

## Contract compliance (interface.md)

- Error envelope `{"error":{"http_status":N,"message":"..."}}` on **every** error path
- `http_status` field equals HTTP response status code, always
- `Content-Type: application/json` on every response (success and error)
- No 3xx redirects from any endpoint
- Exact success bodies: `{"message":"User registered successfully"}`, `{"message":"Logged out successfully"}`, `{"token":"..."}`
- `/status.api_version` is integer `1`, not `"1"` or `1.0`
- `/status.uptime` is fractional float and monotonically increasing
- Score invariants: each `score` strictly in `(0,1]`, sum `≤ 1`
- Match schema: exactly `{name: string, score: float}`, no extra keys

## Files NOT in submission

`qa/` should NOT be in the submission zip — interface.md doesn't define it
and graders run only `tests/` + `test_interop_*.py`. Keep `qa/` in the
team repo for ongoing regression but exclude when zipping.

## Auto-generated fixtures

`qa/_fixtures/` holds programmatically generated PNG/JPEG/WebP/GIF/BMP files
used across tests. It is gitignored — the fixtures regenerate on first run.
