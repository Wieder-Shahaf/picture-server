"""Five interop tests run against any classmate's PictureServer.

Each assertion maps to an explicit requirement in interface.md (cited inline).
Per the assignment, interop tests may ONLY check behavior that interface.md
specifies; checks on unspecified behavior are not counted. Each test is
therefore packed only with spec-literal probes and is engineered to pass a
fully-compliant server (zero false positives) while catching the mistakes
AI-generated and hand-written servers most commonly make.

BASE_URL is read from env (default http://localhost:5000) so the grader's
runner can point the suite at any target server.
"""
import base64
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

# A strong password used everywhere we register/login. interface.md mandates no
# password policy, but using a robust one avoids a server's optional policy
# turning a register/conflict probe into a false negative.
_PW = "Password!123_aZ"

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
    requests.post(f"{BASE_URL}/register", json={"username": u, "password": _PW}, timeout=10)
    r = requests.post(f"{BASE_URL}/login", json={"username": u, "password": _PW}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert isinstance(token, str) and token, "login response missing token string"
    return token


def _processed(token: str):
    r = requests.get(f"{BASE_URL}/status", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, f"/status failed: {r.status_code} {r.text}"
    return r.json()["status"]["processed"]


def _assert_error_envelope(r, expected: int):
    """interface.md §Server response: every error is application/json with body
    {"error": {"http_status": N, ...}} where N == the HTTP status code."""
    assert r.status_code == expected, f"expected {expected}, got {r.status_code}: {r.text[:200]}"
    ct = r.headers.get("Content-Type", "")
    assert ct.startswith("application/json"), f"error Content-Type was {ct!r} (must be application/json)"
    body = r.json()
    assert "error" in body and isinstance(body["error"], dict), f"missing error object: {body}"
    assert body["error"].get("http_status") == expected, \
        f"error.http_status={body['error'].get('http_status')!r}, expected {expected}"


def test_interop_error_envelope_and_status_code_matrix():
    """T1: the error envelope's `http_status` must equal the HTTP status code,
    across the full set of error codes the spec lists for these endpoints.
    interface.md §Server response + per-endpoint 'Possible Response' lists.

    Codes exercised: 400 (/register missing password), 401 (/status no token),
    405 (GET /register on a POST endpoint, and POST /status on a GET endpoint),
    409 (duplicate /register).
    """
    # 401: protected /status without any token
    _assert_error_envelope(requests.get(f"{BASE_URL}/status", timeout=10), 401)

    # 405: wrong method on a POST-only endpoint, and on the GET-only /status.
    # interface.md lists 405 explicitly per endpoint -> must be 405, not 404.
    _assert_error_envelope(requests.get(f"{BASE_URL}/register", timeout=10), 405)
    _assert_error_envelope(requests.post(f"{BASE_URL}/status", timeout=10), 405)

    # 409: duplicate registration (use a strong password so an optional policy
    # can't reject the first register and erase the conflict).
    u = f"i_{uuid.uuid4().hex[:10]}"
    r_first = requests.post(f"{BASE_URL}/register", json={"username": u, "password": _PW}, timeout=10)
    assert r_first.status_code == 201, f"first register should be 201, got {r_first.status_code}: {r_first.text[:200]}"
    _assert_error_envelope(
        requests.post(f"{BASE_URL}/register", json={"username": u, "password": _PW}, timeout=10), 409
    )

    # 400: /register missing the password field.
    _assert_error_envelope(
        requests.post(f"{BASE_URL}/register", json={"username": f"x_{uuid.uuid4().hex[:6]}"}, timeout=10), 400
    )


def test_interop_classifier_counters_accurate():
    """T2: /status.processed counters. interface.md §Upload image + §Get server
    status: a non-decodable payload SHALL return 400 AND increment `fail`; a
    classified image returns 200 AND increments `success`.

    We only tie the counter delta to UNAMBIGUOUS jobs: one valid PNG (+1 success)
    and one file whose bytes are non-decodable garbage (+1 fail). A request with
    no `image` field is checked for its 400 status OUTSIDE the delta window,
    because the spec defines a job as 'uploading an image' — whether a
    field-less request counts as a failed job is not specified, so counting it
    would risk failing a compliant server.
    """
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    # Spec-status check, deliberately outside the counter window:
    r_missing = requests.post(f"{BASE_URL}/classifier", headers=headers, timeout=10)
    assert r_missing.status_code == 400, f"missing image field should be 400, got {r_missing.status_code}"

    before = _processed(token)

    # +1 success: a valid, decodable PNG.
    r_ok = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("tiny.png", _png_bytes(), "image/png")},
        timeout=60,
    )
    assert r_ok.status_code == 200, f"valid PNG should be 200, got {r_ok.status_code}: {r_ok.text[:200]}"

    # +1 fail: a .png filename whose bytes are non-decodable -> spec-mandated 400 + fail.
    r_bad = requests.post(
        f"{BASE_URL}/classifier",
        headers=headers,
        files={"image": ("not_really.png", b"\x00\x01garbage-not-an-image", "image/png")},
        timeout=10,
    )
    assert r_bad.status_code == 400, f"non-decodable payload should be 400, got {r_bad.status_code}"

    after = _processed(token)
    assert after["success"] - before["success"] == 1, \
        f"success delta {after['success'] - before['success']} != 1"
    assert after["fail"] - before["fail"] == 1, \
        f"fail delta {after['fail'] - before['fail']} != 1"


def test_interop_auth_enforcement_matrix():
    """T3: the 401 contract is broad. interface.md §Authentication: the server
    SHALL return 401 when the Bearer header is MISSING, MALFORMED, or the token
    is INVALID/EXPIRED; §Log in: wrong credentials SHALL be 401; protected
    endpoints SHALL reject before processing the body.

    Probes (all must be 401, with a valid error envelope):
      (a) wrong password on /login
      (b) malformed Authorization headers on /status: wrong scheme, no token,
          and a syntactically-valid-but-bogus Bearer token
      (c) auth precedence: /classifier with NO token but a (bad) upload -> 401,
          never 400 (auth is checked before the file)
      (d) /logout invalidates the token: a revoked token -> 401 afterwards
    """
    # (a) wrong password -> 401 (a registered user, wrong secret).
    u = f"i_{uuid.uuid4().hex[:10]}"
    requests.post(f"{BASE_URL}/register", json={"username": u, "password": _PW}, timeout=10)
    _assert_error_envelope(
        requests.post(f"{BASE_URL}/login", json={"username": u, "password": "wrong-" + _PW}, timeout=10), 401
    )

    # (b) malformed / bogus Authorization headers on a protected endpoint.
    for bad_header in ("Basic abc123", "Bearer", "Bearer not.a.real.token"):
        r = requests.get(f"{BASE_URL}/status", headers={"Authorization": bad_header}, timeout=10)
        _assert_error_envelope(r, 401)

    # (c) auth precedence: no token + bad upload must be 401 (auth before body).
    r_pre = requests.post(
        f"{BASE_URL}/classifier",
        files={"image": ("bad.png", b"\x00not-an-image", "image/png")},
        timeout=10,
    )
    _assert_error_envelope(r_pre, 401)

    # (d) logout revokes the token.
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    r_logout = requests.post(f"{BASE_URL}/logout", headers=headers, timeout=10)
    assert r_logout.status_code == 200, f"/logout should be 200, got {r_logout.status_code}: {r_logout.text[:200]}"
    _assert_error_envelope(requests.get(f"{BASE_URL}/status", headers=headers, timeout=10), 401)


def test_interop_spec_literal_response_formats():
    """T4: spec-literal formats that AI-generated servers commonly get wrong.

    (a) POST /register returns 201 (not 200). interface.md: '201: user created'.
    (b) POST /login -> 200 with key 'token' (not 'access_token'), application/json.
        interface.md: 'the json body SHALL contain the token: {"token": "..."}'
        and §Server response: 'Content-Type=application/json' on every response.
    (c) Filenames must end in '.png' or '.jpeg'. 'photo.PNG' (uppercase) and
        'photo.jpg' (not '.jpeg') are both non-compliant -> 400.
        interface.md: 'images uploaded MUST end in ".png" or ".jpeg"'.
    """
    u = f"i_{uuid.uuid4().hex[:10]}"

    # (a) register -> 201
    r_reg = requests.post(f"{BASE_URL}/register", json={"username": u, "password": _PW}, timeout=10)
    assert r_reg.status_code == 201, f"register must return 201 (not {r_reg.status_code}): {r_reg.text[:200]}"

    # (b) login -> 200, application/json, body has non-empty string 'token'
    r_login = requests.post(f"{BASE_URL}/login", json={"username": u, "password": _PW}, timeout=10)
    assert r_login.status_code == 200, f"login failed: {r_login.status_code} {r_login.text[:200]}"
    ct = r_login.headers.get("Content-Type", "")
    assert ct.startswith("application/json"), f"login Content-Type was {ct!r} (must be application/json)"
    login_body = r_login.json()
    assert "token" in login_body, f"login response must have key 'token', got keys: {list(login_body.keys())}"
    assert isinstance(login_body["token"], str) and login_body["token"], \
        "login 'token' must be a non-empty string"

    # (c) bad extensions -> 400 with a valid error envelope
    headers = {"Authorization": f"Bearer {login_body['token']}"}
    for bad_name in ("photo.PNG", "photo.jpg"):
        r = requests.post(
            f"{BASE_URL}/classifier",
            headers=headers,
            files={"image": (bad_name, _png_bytes(), "image/png")},
            timeout=60,
        )
        _assert_error_envelope(r, 400)


def test_interop_classifier_score_and_status_structure():
    """T5: classifier score invariants + /status response structure & types.

    Score invariants (interface.md §classifier):
      - each score: 0.0 < score <= 1.0
      - sum of scores: 0 <= total <= 1.0

    /status structure (interface.md §Get server status):
      - response is application/json, wrapped as {"status": {...}}
      - processed has exactly keys 'success' and 'fail', both integers
      - api_version is the integer 1 (not the string "1")
      - health is exactly "ok" or "error"
      - uptime is a number
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
    assert r.status_code == 200, f"/classifier on valid PNG should be 200: {r.status_code} {r.text[:200]}"
    clf_body = r.json()
    assert "matches" in clf_body, f"missing 'matches' key: {clf_body}"
    matches = clf_body["matches"]
    assert isinstance(matches, list) and matches, "matches must be a non-empty list"
    total = 0.0
    for m in matches:
        assert "name" in m and "score" in m, f"match missing keys: {m}"
        s = m["score"]
        assert isinstance(s, (int, float)) and not isinstance(s, bool), f"score not numeric: {s!r}"
        assert 0 < s <= 1, f"score {s} not in (0, 1]"
        total += s
    assert 0 <= total <= 1.0 + 1e-6, f"sum of scores {total} not in [0, 1]"

    # /status structure + content type
    r_st = requests.get(f"{BASE_URL}/status", headers=headers, timeout=10)
    assert r_st.status_code == 200, f"/status failed: {r_st.status_code} {r_st.text[:200]}"
    ct = r_st.headers.get("Content-Type", "")
    assert ct.startswith("application/json"), f"/status Content-Type was {ct!r} (must be application/json)"
    st_body = r_st.json()
    assert "status" in st_body, \
        f"/status response must be wrapped as {{\"status\": {{...}}}}, got keys: {list(st_body.keys())}"
    st = st_body["status"]
    proc = st.get("processed", {})
    assert "success" in proc, f"processed must have key 'success', got: {list(proc.keys())}"
    assert "fail" in proc, f"processed must have key 'fail', got: {list(proc.keys())}"
    assert isinstance(proc["success"], int) and not isinstance(proc["success"], bool), \
        f"processed.success must be an integer, got {type(proc['success']).__name__}: {proc['success']!r}"
    assert isinstance(proc["fail"], int) and not isinstance(proc["fail"], bool), \
        f"processed.fail must be an integer, got {type(proc['fail']).__name__}: {proc['fail']!r}"
    assert st.get("api_version") == 1 and not isinstance(st.get("api_version"), bool), \
        f"api_version must be the integer 1, got: {st.get('api_version')!r}"
    assert isinstance(st.get("uptime"), (int, float)) and not isinstance(st.get("uptime"), bool), \
        f"uptime must be a number, got: {st.get('uptime')!r}"
    assert st.get("health") in ("ok", "error"), \
        f"health must be 'ok' or 'error', got: {st.get('health')!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
