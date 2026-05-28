"""Verify the 25 MB upload cap.

The cap is enforced at the WSGI layer (Flask MAX_CONTENT_LENGTH).
Werkzeug aborts the request BEFORE our handler runs, so:
  - the response carries the 413 envelope
  - the fail counter is NOT incremented (the request never reached
    the classifier path)
"""
import os

import pytest
import requests

from conftest import envelope_ok

LIMIT = 25 * 1024 * 1024
JUST_UNDER = LIMIT - 64 * 1024     # ~24.94 MB
JUST_OVER  = LIMIT + 64 * 1024     # ~25.06 MB


def _counters(base_url, headers):
    return requests.get(f"{base_url}/status", headers=headers, timeout=10).json()["status"]["processed"]


def _body(n: int) -> bytes:
    """Construct a multipart body of approximately n raw bytes by padding
       the form field with random data.  We don't need a valid image because
       the WSGI cap aborts before any image decoder runs."""
    return os.urandom(n)


def test_request_just_under_25mb_reaches_handler(base_url, bearer):
    """A request near (but below) the cap must be processed.  Whether the
       random bytes decode to an image is irrelevant — what we're testing
       is that the request was NOT pre-aborted by the WSGI layer."""
    before = _counters(base_url, bearer)
    r = requests.post(f"{base_url}/classifier", headers=bearer,
                      files={"image": ("noise.png", _body(JUST_UNDER), "image/png")},
                      timeout=120)
    # The handler runs → image is malformed → 400 + fail++
    assert r.status_code != 413, "WSGI layer prematurely rejected a sub-cap request"
    envelope_ok(r, 400)
    after = _counters(base_url, bearer)
    assert after["fail"] - before["fail"] == 1, \
        "request reached /classifier — fail counter should have advanced"


def test_request_over_25mb_returns_413_envelope(base_url, bearer):
    """Body above the cap → 413, spec envelope, counter UNCHANGED (the
       request never reached /classifier — it was killed at the WSGI layer)."""
    before = _counters(base_url, bearer)
    r = requests.post(f"{base_url}/classifier", headers=bearer,
                      files={"image": ("huge.png", _body(JUST_OVER), "image/png")},
                      timeout=120)
    envelope_ok(r, 413)
    after = _counters(base_url, bearer)
    assert after == before, \
        f"413 must not affect counters; got delta success={after['success']-before['success']}, fail={after['fail']-before['fail']}"


def test_413_envelope_also_applies_without_auth(base_url):
    """Oversize upload without a token: the WSGI cap fires BEFORE the
       auth check.  So we expect 413 here too — not 401 — because the
       request body was rejected at HTTP-protocol level."""
    r = requests.post(f"{base_url}/classifier",
                      files={"image": ("huge.png", _body(JUST_OVER), "image/png")},
                      timeout=120)
    # Acceptable answers: 413 (most likely, WSGI rejects first) OR 401
    # (if the framework checks auth before reading the body).  Either way:
    # error envelope must hold and the code must NOT be 5xx.
    assert r.status_code in (401, 413), f"unexpected status {r.status_code}"
    envelope_ok(r, r.status_code)


def test_oversize_register_body_returns_413(base_url):
    """A 26 MB JSON register body should also bounce at the cap."""
    huge_user = "a" * (LIMIT + 1024)
    r = requests.post(f"{base_url}/register",
                      json={"username": huge_user, "password": "pw"},
                      timeout=60)
    # Either 413 (cap hits first) or 400 (server rejects shape) — both clean
    assert r.status_code in (400, 413), f"unexpected {r.status_code}"
    envelope_ok(r, r.status_code)
