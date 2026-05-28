import requests


def _processed(base_url, headers):
    r = requests.get(f"{base_url}/status", headers=headers, timeout=10)
    assert r.status_code == 200
    return r.json()["status"]["processed"]


def test_classifier_valid_png_returns_matches(base_url, auth_headers, png_bytes):
    before = _processed(base_url, auth_headers)
    r = requests.post(
        f"{base_url}/classifier",
        headers=auth_headers,
        files={"image": ("tiny.png", png_bytes, "image/png")},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    matches = r.json()["matches"]
    assert isinstance(matches, list) and matches
    total = 0.0
    for m in matches:
        assert isinstance(m["name"], str)
        s = m["score"]
        assert isinstance(s, (int, float))
        assert 0 < s <= 1
        total += s
    assert total <= 1.0 + 1e-6

    after = _processed(base_url, auth_headers)
    assert after["success"] == before["success"] + 1
    assert after["fail"] == before["fail"]


def test_classifier_malformed_payload_fails(base_url, auth_headers, bad_bytes):
    before = _processed(base_url, auth_headers)
    r = requests.post(
        f"{base_url}/classifier",
        headers=auth_headers,
        files={"image": ("not.bin", bad_bytes, "application/octet-stream")},
        timeout=30,
    )
    assert r.status_code == 400
    assert r.json()["error"]["http_status"] == 400
    after = _processed(base_url, auth_headers)
    assert after["fail"] == before["fail"] + 1
    assert after["success"] == before["success"]


def test_classifier_missing_image_field(base_url, auth_headers):
    r = requests.post(f"{base_url}/classifier", headers=auth_headers, timeout=10)
    assert r.status_code == 400
    assert r.json()["error"]["http_status"] == 400


def test_classifier_without_token_unauthorized(base_url, png_bytes):
    r = requests.post(
        f"{base_url}/classifier",
        files={"image": ("tiny.png", png_bytes, "image/png")},
        timeout=10,
    )
    assert r.status_code == 401
    assert r.json()["error"]["http_status"] == 401
