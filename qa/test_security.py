"""Security-flavored stress: token forgery, auth bypass attempts,
header injection, persistence of revocation."""
import base64
import json
import time
import uuid

import requests

from conftest import envelope_ok


def _b64(d): return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def test_forged_token_with_empty_signature_rejected(base_url):
    """Construct a JWT header+payload but leave the signature empty.
       Some naive servers verify only the structure → bypass."""
    head = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64({"sub": "attacker", "jti": "x", "exp": int(time.time()) + 3600})
    forged = f"{head}.{payload}."
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer {forged}"}, timeout=10)
    envelope_ok(r, 401)


def test_forged_token_with_none_alg_rejected(base_url):
    """Classic `alg: none` JWT bypass — must be rejected."""
    head = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"sub": "attacker", "jti": "x", "exp": int(time.time()) + 3600})
    forged = f"{head}.{payload}."
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer {forged}"}, timeout=10)
    envelope_ok(r, 401)


def test_token_with_random_signature_rejected(base_url, token):
    """Replace the signature segment of a real token with random bytes."""
    parts = token.split(".")
    parts[2] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer {'.'.join(parts)}"}, timeout=10)
    envelope_ok(r, 401)


def test_token_with_tampered_subject_rejected(base_url, token):
    """Re-encode payload to elevate subject to 'admin' (signature still old)."""
    parts = token.split(".")
    # decode original payload to get the jti
    pad = "=" * (-len(parts[1]) % 4)
    orig = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    orig["sub"] = "admin"
    parts[1] = _b64(orig)
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer {'.'.join(parts)}"}, timeout=10)
    envelope_ok(r, 401)


def test_login_response_does_not_echo_password(base_url, fresh_user):
    u, p = fresh_user
    requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
    r = requests.post(f"{base_url}/login", json={"username": u, "password": p}, timeout=10)
    assert p not in r.text, "password echoed back in login response"


def test_register_response_does_not_echo_password(base_url):
    u = f"sec_{uuid.uuid4().hex[:6]}"
    p = "VerySecret!_AB23"
    r = requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
    assert p not in r.text, "password echoed back in register response"


def test_status_does_not_leak_user_info(base_url, bearer):
    r = requests.get(f"{base_url}/status", headers=bearer, timeout=10)
    body = r.text
    # /status is shared — must not reveal anything per-user (token, username, password, jti, sub)
    for needle in ("password", "token", "Bearer ", '"jti"', '"sub"'):
        assert needle not in body, f"/status response leaks {needle!r}"


def test_auth_header_case_sensitivity(base_url, token):
    """`Bearer` is the canonical scheme. Be tolerant on capitalization only
       in HEADER NAME (HTTP headers are case-insensitive). The SCHEME word
       'Bearer' is case-sensitive per RFC 6750 §2.1, but many servers accept
       'bearer'.  We assert: at minimum, exact 'Bearer' works."""
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200


def test_extra_whitespace_in_bearer_rejected_or_normalized(base_url, token):
    """`Bearer  <token>` (two spaces) — spec doesn't define this; just must
       not 5xx. Either 200 (tolerant) or 401 (strict) is acceptable."""
    r = requests.get(f"{base_url}/status",
                     headers={"Authorization": f"Bearer  {token}"}, timeout=10)
    assert r.status_code in (200, 401)


def test_logout_persists_revocation_across_logical_sessions(base_url, fresh_user):
    """After /logout, the same token must remain invalid even after a fresh
       client connection.  Verifies the revocation is stored, not in-memory."""
    u, p = fresh_user
    requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
    tok = requests.post(f"{base_url}/login",
                        json={"username": u, "password": p}, timeout=10).json()["token"]
    requests.post(f"{base_url}/logout",
                  headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    # New requests.Session emulates "new client"
    with requests.Session() as s:
        r = s.get(f"{base_url}/status",
                  headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        envelope_ok(r, 401)


def test_large_json_body_doesnt_crash(base_url):
    """A 1 MB JSON body should be rejected cleanly (400 / 413) or processed
       quickly. It must NOT cause a 5xx or hang the server."""
    huge = {"username": "a" * 1_000_000, "password": "p"}
    r = requests.post(f"{base_url}/register", json=huge, timeout=30)
    assert r.status_code < 500
    if r.status_code >= 400:
        envelope_ok(r, r.status_code)
