import requests


def test_logout_happy_path(base_url, auth_headers):
    r = requests.post(f"{base_url}/logout", headers=auth_headers, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json() == {"message": "Logged out successfully"}


def test_logout_without_token_unauthorized(base_url):
    r = requests.post(f"{base_url}/logout", timeout=10)
    assert r.status_code == 401
    assert r.json()["error"]["http_status"] == 401


def test_logout_revoked_token_unauthorized_on_reuse(base_url, auth_headers):
    r1 = requests.post(f"{base_url}/logout", headers=auth_headers, timeout=10)
    assert r1.status_code == 200
    r2 = requests.get(f"{base_url}/status", headers=auth_headers, timeout=10)
    assert r2.status_code == 401
    assert r2.json()["error"]["http_status"] == 401
