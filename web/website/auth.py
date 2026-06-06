from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import Blueprint, g, jsonify, request

from website.errors import make_error
from website.models import create_user, get_user, is_revoked, revoke_jti

auth = Blueprint("auth", __name__)

ALGO = "HS256"


def _bcrypt_secret(password: str) -> bytes:
    """Pre-hash the password before handing it to bcrypt.

    bcrypt silently truncates its input at 72 bytes (and stops at the first NUL
    byte), so two distinct passwords sharing the first 72 bytes would hash
    identically — a wrong password could then authenticate, violating
    interface.md's "401: invalid username or password". We defuse this the
    standard `bcrypt_sha256` way: SHA-256 the UTF-8 password (so the WHOLE
    password contributes), then base64-encode the digest. The result is a fixed
    44 ASCII bytes — well under 72 and NUL-free — so bcrypt sees the full
    entropy of any password, no matter its length or contents."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def _secret() -> str:
    return os.environ.get("JWT_SECRET", "dev-only-change-me")


def _issue_token(username: str) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": username,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGO)


def _decode_bearer(header_value: str):
    if not header_value or not isinstance(header_value, str):
        return None
    parts = header_value.split(" ")
    # RFC 7235: the auth-scheme token is case-insensitive. Accept 'bearer' too.
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    try:
        payload = jwt.decode(parts[1], _secret(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if "sub" not in payload or "jti" not in payload:
        return None
    if is_revoked(payload["jti"]):
        return None
    return payload


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        payload = _decode_bearer(request.headers.get("Authorization", ""))
        if payload is None:
            return make_error(401, "Missing or invalid token")
        g.username = payload["sub"]
        g.jti = payload["jti"]
        return fn(*args, **kwargs)
    return wrapper


def _read_json_fields() -> tuple[str, str] | None:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    u = data.get("username")
    p = data.get("password")
    if not isinstance(u, str) or not isinstance(p, str) or not u or not p:
        return None
    return u, p


@auth.route("/register", methods=["POST"])
def register():
    creds = _read_json_fields()
    if creds is None:
        return make_error(400, "Missing or invalid username/password")
    u, p = creds
    pw_hash = bcrypt.hashpw(_bcrypt_secret(p), bcrypt.gensalt()).decode("utf-8")
    if not create_user(u, pw_hash):
        return make_error(409, "Username already exists")
    return jsonify({"message": "User registered successfully"}), 201


@auth.route("/login", methods=["POST"])
def login():
    creds = _read_json_fields()
    if creds is None:
        return make_error(400, "Missing or invalid username/password")
    u, p = creds
    row = get_user(u)
    if row is None:
        return make_error(401, "Invalid username or password")
    if not bcrypt.checkpw(_bcrypt_secret(p), row["password_hash"].encode("utf-8")):
        return make_error(401, "Invalid username or password")
    return jsonify({"token": _issue_token(u)}), 200


@auth.route("/logout", methods=["POST"])
@require_auth
def logout():
    revoke_jti(g.jti)
    return jsonify({"message": "Logged out successfully"}), 200
