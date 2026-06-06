"""Authentication is enforced server-side: a token only authenticates while its
subject still exists in the DB. Deleting the account (even by hand) must make
the very next authenticated request fail with 401 — the frontend's stored token
is not a source of truth.

These exercise the auth layer directly against a throwaway SQLite DB so they
need neither a live server nor the heavy classifier model.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
from flask import Flask

WEB = Path(__file__).resolve().parents[1] / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Override conftest's live-server gate: these tests exercise the auth layer
    in-process and need no running server."""
    return None


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    # Re-import under the patched env so module-level state is clean.
    from website import models

    app = Flask(__name__)
    with app.app_context():
        models.init_db()
        yield


def _make_token(username):
    from website import auth, models

    models.create_user(username, "x")  # password hash irrelevant to decoding
    return auth._issue_token(username)


def test_valid_token_decodes_while_user_exists(app_ctx):
    from website import auth

    user = f"u_{uuid.uuid4().hex[:8]}"
    token = _make_token(user)
    payload = auth._decode_bearer(f"Bearer {token}")
    assert payload is not None
    assert payload["sub"] == user


def test_token_rejected_after_user_deleted(app_ctx):
    from website import auth, models

    user = f"u_{uuid.uuid4().hex[:8]}"
    token = _make_token(user)
    assert auth._decode_bearer(f"Bearer {token}") is not None

    # Simulate the manual `DELETE FROM users` the user described.
    models.get_conn().execute("DELETE FROM users WHERE username = ?", (user,))

    # Signature is still valid, but the subject no longer exists -> 401 (None).
    assert auth._decode_bearer(f"Bearer {token}") is None
