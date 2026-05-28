# Picture.Server

Image classification HTTP server — JSON contract, JWT auth, YOLOv8n-cls behind it.
Technion "Software Writing for Machine Learning" mini-project, Spring 2026.

```
docker compose up --build
```

Server boots on `localhost:5000`. Browser UI at the same URL.

---

## API contract

The wire protocol is the project. Full spec in [`interface.md`](./interface.md).

| method | path         | auth   | success | failure modes                  |
|--------|--------------|--------|---------|--------------------------------|
| POST   | `/register`  | —      | `201`   | `400` `409` `405` `500` `413`  |
| POST   | `/login`     | —      | `200`   | `400` `401` `405` `500` `413`  |
| POST   | `/logout`    | Bearer | `200`   | `401` `405` `500`              |
| POST   | `/classifier`| Bearer | `200`   | `400` `401` `405` `413` `500`  |
| GET    | `/status`    | Bearer | `200`   | `401` `405` `500`              |

Every error carries the spec envelope:

```json
{ "error": { "http_status": <N>, "message": "..." } }
```

with `http_status === HTTP status code`.

---

## Quick demo

```bash
# create + log in
curl -sX POST localhost:5000/register -H 'Content-Type: application/json' \
     -d '{"username":"demo","password":"pw"}'
TOKEN=$(curl -sX POST localhost:5000/login -H 'Content-Type: application/json' \
     -d '{"username":"demo","password":"pw"}' | jq -r .token)

# classify
curl -sX POST localhost:5000/classifier \
     -H "Authorization: Bearer $TOKEN" \
     -F "image=@some.png;type=image/png" | jq .

# inspect
curl -s localhost:5000/status -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Run the tests

```bash
docker compose up -d                                  # server first
python -m pytest tests/                               # 18 endpoint tests
python -m pytest test_interop_*.py                    # 5 interop tests
python -m pytest qa/                                  # 247 stress tests
```

`qa/` is out-of-band — not in the graded submission.

---

## What you get out of the box

- **Hard contract.** Every error path returns the envelope. `http_status` always matches.
- **Real classifier.** YOLOv8n-cls, weights baked into the image at build time.
- **Score invariants.** Each match `0 < score ≤ 1`, sum `≤ 1`. Filter-and-cap, no surprises.
- **Persistent revocation.** `/logout` writes the JTI to SQLite. Survives restart.
- **25 MB upload cap.** Oversize → `413` envelope, counters untouched.
- **Format-tolerant client.** UI transcodes `.jpg / .webp / .gif / .bmp / …` to JPEG before upload; server stays strict per spec.

---

## Stack

`flask` · `pyjwt` · `bcrypt` · `ultralytics yolov8n-cls` · `sqlite3` · `pillow`

Multi-stage Docker. Image runs offline; weights pre-fetched in the build layer.

---

## Repo layout

```
.
|-- docker-compose.yml          docker-compose.tests.yml      # entrypoint
|-- interface.md                                              # the contract
|-- test_interop_ID1_ID2_ID3.py                               # 5 interop tests
|-- tests/                                                    # graded suite (18)
|-- web/                                                      # server source
|   |-- Dockerfile  main.py  requirements.txt
|   |-- website/    blueprints, models, classifier, errors
|-- qa/                                                       # 247 stress tests
```

---

## Credits

Built by **Shahaf**, **Barak**, **Max**.
