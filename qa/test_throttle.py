"""Throttle tarpit behavior — the spec-safe abuse defense.

web/website/throttle.py slows abusive clients with a per-(category, client)
token bucket instead of rejecting them, because interface.md's status-code set
is closed and does NOT include 429. These tests pin the two invariants that make
that safe:

  1. legitimate, paced traffic is never delayed; and
  2. a burst that exhausts a bucket IS delayed (the tarpit engages) but every
     response code still stays within the spec set {200,400,401,405,500} —
     never 429, never 5xx.

We exercise the 'auth' bucket (POST /login: capacity 15, ~5 tok/s, per-IP) so
the test stays off the slow YOLO classifier path. _MAX_SLEEP in throttle.py is
2.0s and the auth bucket refills at 5 tok/s; the pre-test settle sleeps long
enough to refill a full bucket (capacity / rate = 3s) before each scenario.
"""
import concurrent.futures as cf
import time
import uuid

import requests

from conftest import BASE_URL

SPEC_CODES = {200, 400, 401, 405, 500}
MAX_SLEEP = 2.0          # mirrors throttle._MAX_SLEEP
AUTH_REFILL_SECS = 3.5   # > capacity/rate (15/5=3.0): drains debt to a full bucket


def _bad_login():
    """A well-formed login for a user that doesn't exist → 401. Hits the
    'auth' throttle bucket without touching bcrypt or the model. Returns
    (status_code, elapsed_seconds)."""
    body = {"username": "nobody_" + uuid.uuid4().hex[:8], "password": "x"}
    t0 = time.monotonic()
    r = requests.post(f"{BASE_URL}/login", json=body, timeout=30)
    return r.status_code, time.monotonic() - t0


def test_paced_auth_traffic_is_not_delayed(base_url):
    """A few spaced-out logins stay well under the tarpit cap — legitimate
    users must never pay the abuse penalty. 5 calls at 0.5s spacing consume
    1 token each while the bucket refills ~5/s, so it never goes into debt."""
    time.sleep(AUTH_REFILL_SECS)  # start from a full auth bucket
    for i in range(5):
        code, dt = _bad_login()
        assert code in SPEC_CODES and code != 429, f"iter {i}: unexpected code {code}"
        assert dt < 1.5, \
            f"paced login {i} was tarpitted ({dt:.2f}s); legit traffic must not be delayed"
        time.sleep(0.5)


def test_auth_burst_is_tarpitted_but_stays_in_spec(base_url):
    """Flooding /login past the bucket capacity must slow the later requests
    (tarpit engaged) yet never emit 429 or 5xx — the spec set is closed."""
    time.sleep(AUTH_REFILL_SECS)  # start from a full auth bucket
    BURST = 30                    # >> capacity (15) → bucket is driven into debt
    with cf.ThreadPoolExecutor(max_workers=BURST) as ex:
        results = list(ex.map(lambda _: _bad_login(), range(BURST)))

    codes = [c for c, _ in results]
    delays = [d for _, d in results]

    # Invariant 1: stay inside the spec's closed status set; never 429, never 5xx.
    assert all(c in SPEC_CODES for c in codes), \
        f"out-of-spec status in burst: {sorted(set(codes))}"
    assert 429 not in codes, "throttle must tarpit (delay), not reject with 429"
    assert all(c < 500 for c in codes), f"5xx during burst: {sorted(set(codes))}"

    # Invariant 2: the tarpit actually engaged — the slowest requests were held.
    assert max(delays) > 0.5, \
        f"no request was delayed (max {max(delays):.2f}s); tarpit never engaged"

    # Invariant 3: each delay is bounded — a flood is slowed, never hung forever.
    assert max(delays) < MAX_SLEEP + 4.0, \
        f"a request slept {max(delays):.2f}s, beyond the {MAX_SLEEP}s cap + slack"
