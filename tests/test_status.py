import time

import requests


def test_status_requires_auth(base_url):
    r = requests.get(f"{base_url}/status", timeout=10)
    assert r.status_code == 401
    assert r.json()["error"]["http_status"] == 401


def test_status_schema_and_api_version(base_url, auth_headers):
    r = requests.get(f"{base_url}/status", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    s = r.json()["status"]
    assert set(s.keys()) >= {"uptime", "processed", "health", "api_version"}
    assert s["api_version"] == 1
    assert s["health"] in ("ok", "error")
    assert isinstance(s["processed"]["success"], int)
    assert isinstance(s["processed"]["fail"], int)
    assert isinstance(s["uptime"], (int, float)) and s["uptime"] > 0


def test_status_uptime_is_float_and_grows(base_url, auth_headers):
    r1 = requests.get(f"{base_url}/status", headers=auth_headers, timeout=10).json()["status"]
    time.sleep(1.2)
    r2 = requests.get(f"{base_url}/status", headers=auth_headers, timeout=10).json()["status"]
    assert r2["uptime"] - r1["uptime"] >= 1.0
    assert (r1["uptime"] != int(r1["uptime"])) or (r2["uptime"] != int(r2["uptime"]))
