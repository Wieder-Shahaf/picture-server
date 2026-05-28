"""Stress-suite fixtures. Kept OUTSIDE tests/ so the graded suite
isn't polluted with thousands of nuisance requests at grading time.

Run with:  python -m pytest qa/ -v
"""
import os
import time
import uuid
from io import BytesIO
from pathlib import Path

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("BASE_URL", "http://localhost:15000")
FIXTURES = Path(__file__).parent / "_fixtures"
FIXTURES.mkdir(exist_ok=True)


def _make_png(size=(96, 96), color=(120, 60, 200)):
    p = FIXTURES / "ok.png"
    if not p.exists():
        Image.new("RGB", size, color).save(p, "PNG")
    return p


def _make_jpeg(size=(96, 96), color=(200, 60, 60)):
    p = FIXTURES / "ok.jpeg"
    if not p.exists():
        Image.new("RGB", size, color).save(p, "JPEG", quality=92)
    return p


def _make_webp():
    p = FIXTURES / "ok.webp"
    if not p.exists():
        Image.new("RGB", (64, 64), "green").save(p, "WEBP")
    return p


def _make_gif():
    p = FIXTURES / "ok.gif"
    if not p.exists():
        Image.new("RGB", (64, 64), "purple").save(p, "GIF")
    return p


def _make_huge_png():
    p = FIXTURES / "huge.png"
    if not p.exists():
        Image.new("RGB", (3000, 3000), "blue").save(p, "PNG")
    return p


def _make_text_as_png():
    """File named .png but holding plain text bytes."""
    p = FIXTURES / "fake.png"
    p.write_bytes(b"this is plain text, not an image at all\n" * 50)
    return p


def _make_truncated_png():
    """Real PNG header, truncated body — decoder should fail."""
    real = _make_png().read_bytes()
    p = FIXTURES / "trunc.png"
    p.write_bytes(real[: len(real) // 3])
    return p


def _make_zero_bytes():
    p = FIXTURES / "empty.png"
    p.write_bytes(b"")
    return p


@pytest.fixture(scope="session", autouse=True)
def _check_server():
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/status", timeout=2)
            if r.status_code in (200, 401):
                return
        except Exception:
            pass
        time.sleep(0.5)
    pytest.skip(f"server not reachable at {BASE_URL}")


@pytest.fixture
def base_url():
    return BASE_URL


@pytest.fixture
def fresh_user():
    return f"qa_{uuid.uuid4().hex[:10]}", "Password!123"


@pytest.fixture
def token(fresh_user):
    u, p = fresh_user
    requests.post(f"{BASE_URL}/register", json={"username": u, "password": p}, timeout=10)
    r = requests.post(f"{BASE_URL}/login", json={"username": u, "password": p}, timeout=10)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture
def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def png_path():    return str(_make_png())
@pytest.fixture
def jpeg_path():   return str(_make_jpeg())
@pytest.fixture
def webp_path():   return str(_make_webp())
@pytest.fixture
def gif_path():    return str(_make_gif())
@pytest.fixture
def huge_png():    return str(_make_huge_png())
@pytest.fixture
def fake_png():    return str(_make_text_as_png())
@pytest.fixture
def trunc_png():   return str(_make_truncated_png())
@pytest.fixture
def empty_png():   return str(_make_zero_bytes())


def envelope_ok(r, expected_status):
    """Assert error envelope and status alignment per interface.md."""
    assert r.status_code == expected_status, \
        f"expected {expected_status}, got {r.status_code} {r.text}"
    ct = r.headers.get("Content-Type", "")
    assert ct.startswith("application/json"), f"Content-Type was {ct!r}"
    body = r.json()
    assert "error" in body, f"no `error` key: {body}"
    err = body["error"]
    assert isinstance(err, dict), f"error not dict: {err}"
    assert err.get("http_status") == expected_status, \
        f"error.http_status={err.get('http_status')!r}, expected {expected_status}"
    assert isinstance(err.get("message"), str) and err["message"], \
        f"no message: {err}"
