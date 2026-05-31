"""Five interop tests run against any classmate's PictureServer.

Each test asserts only behaviors explicitly required by interface.md.
BASE_URL is read from env (default http://localhost:5000) so the grader's
runner can point the suite at any target server.
"""
import base64
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

# A real, decodable 64x64 PNG embedded as base64 so this file depends ONLY on
# the assignment-mandated packages (pytest + requests) plus the stdlib — no
# Pillow/numpy needed, since the grading framework may not have them installed.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAgElEQVR4nNXOQREAIAzAsFJl"
    "SEMeshCxB9coyDr7UiZxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidx"
    "EidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEufv"
    "wNQDI/ICCL1NBWAAAAAASUVORK5CYII="
)


def _png_bytes() -> bytes:
    return base64.b64decode(_PNG_B64)


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


def test_interop_classifier_rejects_unsupported_filename_extension():
    """T4: an upload whose filename does NOT end in '.png' or '.jpeg' must be
    rejected with 400. interface.md is explicit:
        'The images uploaded MUST end in \".png\" or \".jpeg\".'
    We send valid PNG bytes under the name 'photo.PNG' (uppercase) — which does
    NOT end in the lowercase '.png' the spec mandates. A spec-compliant server
    returns 400; a server that lowercases the filename before checking (the
    common shortcut) wrongly returns 200 and is caught here."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("photo.PNG", _png_bytes(), "image/png")},
        timeout=60,
    )
    assert r.status_code == 400, (
        "filename 'photo.PNG' does not end in '.png'/'.jpeg' (spec: MUST), "
        f"expected 400, got {r.status_code}: {r.text[:200]}"
    )
    body = r.json()
    assert body["error"]["http_status"] == 400, \
        f"error envelope http_status must equal 400, got {body}"


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
