import uuid

import requests


def _u():
    return f"u_{uuid.uuid4().hex[:10]}"


def test_login_returns_token(base_url):
    u, p = _u(), "pw"
    requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
    r = requests.post(f"{base_url}/login", json={"username": u, "password": p}, timeout=10)
    assert r.status_code == 200, r.text
    assert isinstance(r.json().get("token"), str) and r.json()["token"]


def test_login_bad_password_unauthorized(base_url):
    u = _u()
    requests.post(f"{base_url}/register", json={"username": u, "password": "right"}, timeout=10)
    r = requests.post(f"{base_url}/login", json={"username": u, "password": "wrong"}, timeout=10)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["http_status"] == 401


def test_login_missing_field_bad_request(base_url):
    r = requests.post(f"{base_url}/login", json={"username": _u()}, timeout=10)
    assert r.status_code == 400
    assert r.json()["error"]["http_status"] == 400


def test_login_get_method_not_allowed(base_url):
    r = requests.get(f"{base_url}/login", timeout=10)
    assert r.status_code == 405
    assert r.json()["error"]["http_status"] == 405
