import os
import time
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
FIXTURES = Path(__file__).parent / "fixtures"


def _server_reachable(timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/status", timeout=2)
            if r.status_code in (200, 401):
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session", autouse=True)
def live_server():
    if not _server_reachable(timeout=5):
        pytest.skip(
            f"server at {BASE_URL} not reachable; start it with `docker-compose up -d`"
        )
    return BASE_URL


@pytest.fixture
def base_url():
    return BASE_URL


@pytest.fixture
def tmp_user():
    return f"u_{uuid.uuid4().hex[:10]}", "Password!123"


@pytest.fixture
def token(tmp_user):
    username, password = tmp_user
    requests.post(
        f"{BASE_URL}/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    r = requests.post(
        f"{BASE_URL}/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def png_bytes():
    return (FIXTURES / "tiny.png").read_bytes()


@pytest.fixture
def bad_bytes():
    return (FIXTURES / "notimage.bin").read_bytes()
