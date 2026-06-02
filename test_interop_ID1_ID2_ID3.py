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


def test_interop_spec_literal_response_formats():
    """T4: three spec-literal requirements that AI-generated servers commonly get wrong.

    (a) POST /register must return 201, not 200.
        interface.md: '201: user created successfully'

    (b) POST /login body must contain the key 'token', not 'access_token'.
        interface.md: 'json body SHALL contain the token: {"token": "eyJ..."}'

    (c) Filenames 'photo.PNG' (uppercase) and 'photo.jpg' (wrong suffix) must
        both be rejected with 400.
        interface.md: 'images uploaded MUST end in \".png\" or \".jpeg\"'
        '.jpg' is a common JPEG extension but is NOT '.jpeg' per the spec.
    """
    u = f"i_{uuid.uuid4().hex[:10]}"
    pw = "Password!123"

    # (a) register → 201
    r_reg = requests.post(f"{BASE_URL}/register", json={"username": u, "password": pw}, timeout=10)
    assert r_reg.status_code == 201, \
        f"register must return 201 (not {r_reg.status_code}): {r_reg.text[:200]}"

    # (b) login → {"token": "..."}
    r_login = requests.post(f"{BASE_URL}/login", json={"username": u, "password": pw}, timeout=10)
    assert r_login.status_code == 200, f"login failed: {r_login.status_code} {r_login.text}"
    login_body = r_login.json()
    assert "token" in login_body, (
        f"login response must have key 'token', got keys: {list(login_body.keys())}"
    )
    assert isinstance(login_body["token"], str) and login_body["token"], \
        "login 'token' must be a non-empty string"

    # (c) bad extensions → 400
    headers = {"Authorization": f"Bearer {login_body['token']}"}
    for bad_name in ("photo.PNG", "photo.jpg"):
        r = requests.post(
            f"{BASE_URL}/classifier",
            headers=headers,
            files={"image": (bad_name, _png_bytes(), "image/png")},
            timeout=60,
        )
        assert r.status_code == 400, (
            f"filename '{bad_name}' must be rejected with 400, got {r.status_code}: {r.text[:200]}"
        )
        assert r.json()["error"]["http_status"] == 400, \
            f"error envelope http_status must equal 400 for '{bad_name}'"


def test_interop_classifier_score_and_status_structure():
    """T5: classifier score invariants + /status response structure.

    Score invariants (interface.md §classifier):
      - each score: 0.0 < score <= 1.0
      - sum of scores: 0 <= total <= 1.0

    /status structure (interface.md §Get server status):
      - response wrapped as {"status": {...}}  (not a flat object)
      - processed has exact keys 'success' and 'fail' (not 'successes'/'failures')
      - 'success' and 'fail' are integers
      - api_version is the integer 1 (not the string "1")
      - health is exactly "ok" or "error"
    """
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    # score invariants
    r = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("tiny.png", _png_bytes(), "image/png")},
        timeout=60,
    )
    assert r.status_code == 200, f"/classifier on valid PNG should be 200: {r.status_code} {r.text}"
    clf_body = r.json()
    assert "matches" in clf_body, f"missing 'matches' key: {clf_body}"
    matches = clf_body["matches"]
    assert isinstance(matches, list) and matches, "matches must be a non-empty list"
    total = 0.0
    for m in matches:
        assert "name" in m and "score" in m, f"match missing keys: {m}"
        s = m["score"]
        assert isinstance(s, (int, float)), f"score not numeric: {s!r}"
        assert 0 < s <= 1, f"score {s} not in (0, 1]"
        total += s
    assert 0 <= total <= 1.0 + 1e-6, f"sum of scores {total} not in [0, 1]"

    # /status structure
    r_st = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10)
    assert r_st.status_code == 200, f"/status failed: {r_st.status_code} {r_st.text}"
    st_body = r_st.json()
    assert "status" in st_body, \
        f"/status response must be wrapped as {{\"status\": {{...}}}}, got keys: {list(st_body.keys())}"
    st = st_body["status"]
    proc = st.get("processed", {})
    assert "success" in proc, \
        f"processed must have key 'success', got: {list(proc.keys())}"
    assert "fail" in proc, \
        f"processed must have key 'fail', got: {list(proc.keys())}"
    assert isinstance(proc["success"], int), \
        f"processed.success must be an integer, got {type(proc['success']).__name__}: {proc['success']!r}"
    assert isinstance(proc["fail"], int), \
        f"processed.fail must be an integer, got {type(proc['fail']).__name__}: {proc['fail']!r}"
    assert st.get("api_version") == 1, \
        f"api_version must be the integer 1, got: {st.get('api_version')!r}"
    assert st.get("health") in ("ok", "error"), \
        f"health must be 'ok' or 'error', got: {st.get('health')!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
