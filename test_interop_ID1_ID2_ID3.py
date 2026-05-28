"""Five interop tests run against any classmate's PictureServer.

Each test asserts only behaviors explicitly required by interface.md.
BASE_URL is read from env (default http://localhost:5000) so the grader's
runner can point the suite at any target server.
"""
import os
import time
import uuid
from io import BytesIO

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")


def _png_bytes() -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=(128, 64, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _register_and_login() -> str:
    u = f"i_{uuid.uuid4().hex[:10]}"
    p = "Password!123"
    requests.post(f"{BASE_URL}/register", json={"username": u, "password": p}, timeout=10)
    r = requests.post(f"{BASE_URL}/login", json={"username": u, "password": p}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert isinstance(token, str) and token, "login response missing token string"
    return token


def _processed(token: str):
    r = requests.get(f"{BASE_URL}/status", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, f"/status failed: {r.status_code} {r.text}"
    return r.json()["status"]["processed"]


def test_interop_error_envelope_http_status_matches_code():
    """T1: every error response must carry application/json and an error envelope
    whose `http_status` field equals the HTTP status code. interface.md §Server response."""
    # 401: /status without token
    r401 = requests.get(f"{BASE_URL}/status", timeout=10)
    # 405: GET /register (POST endpoint)
    r405 = requests.get(f"{BASE_URL}/register", timeout=10)
    # 409: duplicate /register
    u = f"i_{uuid.uuid4().hex[:10]}"
    requests.post(f"{BASE_URL}/register", json={"username": u, "password": "pw"}, timeout=10)
    r409 = requests.post(f"{BASE_URL}/register", json={"username": u, "password": "pw"}, timeout=10)
    # 400: /register missing password
    r400 = requests.post(f"{BASE_URL}/register", json={"username": f"x_{uuid.uuid4().hex[:6]}"}, timeout=10)

    for r, expected in [(r401, 401), (r405, 405), (r409, 409), (r400, 400)]:
        assert r.status_code == expected, f"expected {expected}, got {r.status_code}: {r.text}"
        ct = r.headers.get("Content-Type", "")
        assert ct.startswith("application/json"), f"Content-Type was {ct!r}"
        body = r.json()
        assert "error" in body and isinstance(body["error"], dict), f"missing error obj: {body}"
        assert body["error"].get("http_status") == expected, \
            f"error.http_status={body['error'].get('http_status')!r}, expected {expected}"


def test_interop_classifier_counters_accurate():
    """T2: /classifier increments `success` exactly on 200 and `fail` exactly on 400
    (malformed input). interface.md §Upload image and §Get server status."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    before = _processed(token)

    # 1 valid PNG → +1 success
    r_ok = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("tiny.png", _png_bytes(), "image/png")},
        timeout=60,
    )
    assert r_ok.status_code == 200, f"valid PNG should be 200, got {r_ok.status_code}: {r_ok.text}"

    # 2 malformed → +2 fail
    r_bad1 = requests.post(f"{BASE_URL}/classifier", headers=headers, timeout=10)
    assert r_bad1.status_code == 400, f"missing image field should be 400, got {r_bad1.status_code}"
    r_bad2 = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("not.bin", b"\x00\x01garbage", "application/octet-stream")},
        timeout=10,
    )
    assert r_bad2.status_code == 400, f"non-image payload should be 400, got {r_bad2.status_code}"

    after = _processed(token)
    assert after["success"] - before["success"] == 1, \
        f"success delta {after['success'] - before['success']} != 1"
    assert after["fail"] - before["fail"] == 2, \
        f"fail delta {after['fail'] - before['fail']} != 2"


def test_interop_logout_revokes_token():
    """T3: after /logout, the same token must be rejected by protected endpoints with 401.
    interface.md §Log out (invalidates session token)."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r_logout = requests.post(f"{BASE_URL}/logout", headers=headers, timeout=10)
    assert r_logout.status_code == 200, f"/logout should be 200, got {r_logout.status_code}: {r_logout.text}"
    r_after = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10)
    assert r_after.status_code == 401, \
        f"revoked token should yield 401, got {r_after.status_code}: {r_after.text}"
    body = r_after.json()
    assert body["error"]["http_status"] == 401


def test_interop_status_uptime_is_fractional_float_and_grows():
    """T4: /status.uptime must be in fractional seconds and strictly increase between calls.
    interface.md says 'The uptime value is in fractional seconds, e.g. 55.6'."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    s1 = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10).json()["status"]
    time.sleep(1.2)
    s2 = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10).json()["status"]
    u1, u2 = s1["uptime"], s2["uptime"]
    assert isinstance(u1, (int, float)) and isinstance(u2, (int, float))
    assert u2 - u1 >= 1.0, f"uptime didn't grow by >=1s: u1={u1}, u2={u2}"
    fractional = (u1 != int(u1)) or (u2 != int(u2))
    assert fractional, f"uptime must be fractional (spec example: 55.6), got u1={u1}, u2={u2}"


def test_interop_classifier_score_invariants():
    """T5: every match score is in (0, 1] and sum of scores is in [0, 1].
    interface.md §classifier response: '0.0 < score <= 1.0' and 'sum ... between 0 and 1'."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("tiny.png", _png_bytes(), "image/png")},
        timeout=60,
    )
    assert r.status_code == 200, f"/classifier on valid PNG should be 200: {r.status_code} {r.text}"
    body = r.json()
    assert "matches" in body, f"missing 'matches' key: {body}"
    matches = body["matches"]
    assert isinstance(matches, list) and matches, "matches must be a non-empty list"
    total = 0.0
    for m in matches:
        assert "name" in m and "score" in m, f"match missing keys: {m}"
        s = m["score"]
        assert isinstance(s, (int, float)), f"score not numeric: {s!r}"
        assert 0 < s <= 1, f"score {s} not in (0, 1]"
        total += s
    assert 0 <= total <= 1.0 + 1e-6, f"sum of scores {total} not in [0, 1]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
