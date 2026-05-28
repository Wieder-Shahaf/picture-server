import uuid

import requests


def _u():
    return f"u_{uuid.uuid4().hex[:10]}"


def _check_envelope(r, status):
    assert r.status_code == status, r.text
    assert r.headers.get("Content-Type", "").startswith("application/json")
    body = r.json()
    assert body["error"]["http_status"] == status


def test_register_happy_path(base_url):
    r = requests.post(
        f"{base_url}/register",
        json={"username": _u(), "password": "pw"},
        timeout=10,
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"message": "User registered successfully"}


def test_register_missing_password(base_url):
    r = requests.post(
        f"{base_url}/register",
        json={"username": _u()},
        timeout=10,
    )
    _check_envelope(r, 400)


def test_register_duplicate_username(base_url):
    u = _u()
    r1 = requests.post(
        f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10
    )
    assert r1.status_code == 201
    r2 = requests.post(
        f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10
    )
    _check_envelope(r2, 409)


def test_register_get_method_not_allowed(base_url):
    r = requests.get(f"{base_url}/register", timeout=10)
    _check_envelope(r, 405)
