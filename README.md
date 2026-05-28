# Picture.Server

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PICTURE.SERVER                                              [ GITHUB ↗ ]   │
│  image classification · http                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ●  HEALTH ok  │  UPTIME 230.7s  │  SUCCESS 9  │  FAIL 1  │  API v1         │
└─────────────────────────────────────────────────────────────────────────────┘
```

> Interactive client for the **PictureServer** JSON API.
> JWT auth · YOLOv8n-cls classifier · scores in `(0, 1]` summing to `≤ 1`.

---

## `01 — RUN`  ·  one command

```bash
docker compose up --build
```

Server boots on `localhost:5000`.  Browser UI at the same URL.

---

## `02 — CONTRACT`  ·  the API is the project

Full wire protocol → [`interface.md`](./interface.md).

```
┌─────────┬──────────────┬─────────┬─────────┬──────────────────────────────┐
│ METHOD  │ PATH         │ AUTH    │ 2XX     │ FAILURE MODES                │
├─────────┼──────────────┼─────────┼─────────┼──────────────────────────────┤
│ POST    │ /register    │ —       │ 201     │ 400 · 409 · 405 · 500 · 413  │
│ POST    │ /login       │ —       │ 200     │ 400 · 401 · 405 · 500 · 413  │
│ POST    │ /logout      │ Bearer  │ 200     │ 401 · 405 · 500              │
│ POST    │ /classifier  │ Bearer  │ 200     │ 400 · 401 · 405 · 413 · 500  │
│ GET     │ /status      │ Bearer  │ 200     │ 401 · 405 · 500              │
└─────────┴──────────────┴─────────┴─────────┴──────────────────────────────┘
```

Every error carries the spec envelope —

```json
{ "error": { "http_status": <N>, "message": "..." } }
```

with `http_status` always equal to the HTTP status code.

---

## `03 — DEMO`  ·  register → login → classify → status

```bash
curl -sX POST localhost:5000/register -H 'Content-Type: application/json' \
     -d '{"username":"demo","password":"pw"}'

TOKEN=$(curl -sX POST localhost:5000/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"demo","password":"pw"}' | jq -r .token)

curl -sX POST localhost:5000/classifier \
     -H "Authorization: Bearer $TOKEN" \
     -F "image=@some.png;type=image/png" | jq .

curl -s localhost:5000/status -H "Authorization: Bearer $TOKEN" | jq .
```

---

## `04 — TESTS`  ·  three suites, all green

```bash
docker compose up -d                              #  server first

python -m pytest tests/                           #  18  endpoint tests   (graded)
python -m pytest test_interop_*.py                #   5  interop tests    (graded)
python -m pytest qa/                              # 247  stress tests     (qa only)
```

```
┌────────────────────────────┬────────┬──────────────────────────────────────┐
│ SUITE                      │ COUNT  │ FOCUS                                │
├────────────────────────────┼────────┼──────────────────────────────────────┤
│ tests/                     │   18   │ endpoint coverage, contract          │
│ test_interop_*.py          │    5   │ bug-magnet probes for peer servers   │
│ qa/                        │  247   │ stress · security · concurrency · ui │
└────────────────────────────┴────────┴──────────────────────────────────────┘
```

`qa/` is out-of-band — not in the graded submission.

---

## `05 — WHAT WORKS WELL`

```
●  hard contract        every error path returns the envelope; http_status
                        always matches the HTTP status code
●  real classifier      ultralytics yolov8n-cls; weights baked into the
                        image at build time → offline at runtime
●  score invariants     each match 0 < score ≤ 1; cumulative sum ≤ 1
                        filter-and-cap, no surprises
●  persistent revoke    /logout writes the jti to sqlite; survives restart
●  25 mb upload cap     oversize → 413 envelope, counters untouched
●  format-tolerant ui   .jpg/.webp/.gif/.bmp/… transcoded to jpeg client-side
                        before upload; server stays strict per spec
```

---

## `06 — STACK`

```
flask  ·  pyjwt  ·  bcrypt  ·  ultralytics yolov8n-cls  ·  sqlite3  ·  pillow
```

Multi-stage Docker.  Image runs offline; YOLO weights pre-fetched in the
build layer.  Bind-mounted `./data` keeps SQLite across rebuilds.

---

## `07 — LAYOUT`

```
.
├── docker-compose.yml   docker-compose.tests.yml      # entry point
├── interface.md                                       # the contract
├── test_interop_ID1_ID2_ID3.py                        # 5 interop tests
├── tests/                                             # graded suite (18)
├── web/                                               # server source
│   ├── Dockerfile   main.py   requirements.txt
│   └── website/     blueprints · models · classifier · errors
└── qa/                                                # 247 stress tests
```

---

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BUILT BY   ●  SHAHAF   ●  BARAK   ●  MAX                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```
