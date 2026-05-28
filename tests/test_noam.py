import uuid

import requests


def base_url() -> str:
    host = "localhost"
    port = "15000" #TODO: REMEMBER TO CHANGE TO THE PORT YOUR SERVER IS RUNNING ON
    return f"http://{host}:{port}"


def test_register_login_logout_flow():
    username = f"noam_test_{uuid.uuid4().hex[:8]}"
    password = "simple_password_123"

    register_response = requests.post(
        f"{base_url()}/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert register_response.status_code == 201, register_response.text

    login_response = requests.post(
        f"{base_url()}/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json().get("token")
    assert token

    logout_response = requests.post(
        f"{base_url()}/logout",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert logout_response.status_code == 200, logout_response.text
