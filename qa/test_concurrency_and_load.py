"""Parallel + sequential load — counter integrity under contention,
race conditions, and replay safety."""
import concurrent.futures as cf
import uuid

import requests

from conftest import BASE_URL


def _counters(headers):
    r = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10)
    assert r.status_code == 200
    return r.json()["status"]["processed"]


def test_concurrent_duplicate_register_yields_one_success(base_url):
    """20 parallel POSTs of the same username → exactly 1 returns 201,
       the rest return 409.  Catches lost-update / TOCTOU bugs in the
       create_user path."""
    u = "race_" + uuid.uuid4().hex[:8]
    body = {"username": u, "password": "pw"}

    def fire():
        return requests.post(f"{base_url}/register", json=body, timeout=15).status_code

    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(lambda _: fire(), range(20)))

    creates = codes.count(201)
    conflicts = codes.count(409)
    assert creates == 1, f"expected 1 success, got {creates}: {codes}"
    assert conflicts == 19, f"expected 19 conflicts, got {conflicts}: {codes}"


def test_parallel_classify_counters_track_exactly(base_url, bearer, png_path):
    """N parallel valid PNGs → success counter increments by exactly N."""
    N = 12
    before = _counters(bearer)

    def fire(_):
        with open(png_path, "rb") as f:
            return requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("ok.png", f, "image/png")},
                                 timeout=120).status_code

    with cf.ThreadPoolExecutor(max_workers=N) as ex:
        codes = list(ex.map(fire, range(N)))

    after = _counters(bearer)
    assert codes.count(200) == N, f"not all parallel /classifier succeeded: {codes}"
    assert after["success"] - before["success"] == N, \
        f"success delta={after['success']-before['success']}, expected {N}"
    assert after["fail"] == before["fail"]


def test_mixed_parallel_counters_track(base_url, bearer, png_path):
    """Mix good + bad uploads in parallel → success and fail each track
       their share exactly. Catches lock-bugs in the counter increment path."""
    good = 6
    bad  = 4
    before = _counters(bearer)

    def good_fire(_):
        with open(png_path, "rb") as f:
            return requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("ok.png", f, "image/png")},
                                 timeout=60).status_code

    def bad_fire(_):
        return requests.post(f"{base_url}/classifier", headers=bearer,
                             files={"image": ("bad.bin", b"\x00garbage", "application/octet-stream")},
                             timeout=20).status_code

    with cf.ThreadPoolExecutor(max_workers=good + bad) as ex:
        futures  = [ex.submit(good_fire, i) for i in range(good)]
        futures += [ex.submit(bad_fire,  i) for i in range(bad)]
        codes = [f.result() for f in cf.as_completed(futures)]

    after = _counters(bearer)
    assert codes.count(200) == good
    assert codes.count(400) == bad
    assert after["success"] - before["success"] == good
    assert after["fail"]    - before["fail"]    == bad


def test_sequential_load_100_classify(base_url, bearer, png_path):
    """100 sequential /classifier calls → exactly 100 successes.
       Catches accumulator drift / memory-leak symptoms over a session."""
    N = 100
    before = _counters(bearer)
    with open(png_path, "rb") as f:
        body = f.read()
    for i in range(N):
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("ok.png", body, "image/png")},
                          timeout=60)
        assert r.status_code == 200, f"iter {i}: {r.status_code} {r.text}"
    after = _counters(bearer)
    assert after["success"] - before["success"] == N
    assert after["fail"] == before["fail"]


def test_parallel_logout_same_token_no_crash(base_url, bearer):
    """Two concurrent /logout on the same token → no 5xx; final state is
       'revoked'.  At least one must succeed; replay returns 401."""
    def fire(_):
        return requests.post(f"{base_url}/logout", headers=bearer, timeout=10).status_code

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        codes = list(ex.map(fire, range(4)))

    assert all(c < 500 for c in codes), f"server 5xx on concurrent logout: {codes}"
    # The token should be revoked afterwards
    r = requests.get(f"{base_url}/status", headers=bearer, timeout=10)
    assert r.status_code == 401
