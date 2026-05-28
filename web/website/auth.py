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
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
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


def _read_json_fields():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, None
    u = data.get("username")
    p = data.get("password")
    if not isinstance(u, str) or not isinstance(p, str) or not u or not p:
        return None, None
    return u, p


@auth.route("/register", methods=["POST"])
def register():
    u, p = _read_json_fields()
    if u is None:
        return make_error(400, "Missing or invalid username/password")
    pw_hash = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    if not create_user(u, pw_hash):
        return make_error(409, "Username already exists")
    return jsonify({"message": "User registered successfully"}), 201


@auth.route("/login", methods=["POST"])
def login():
    u, p = _read_json_fields()
    if u is None:
        return make_error(400, "Missing or invalid username/password")
    row = get_user(u)
    if row is None:
        return make_error(401, "Invalid username or password")
    if not bcrypt.checkpw(p.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return make_error(401, "Invalid username or password")
    return jsonify({"token": _issue_token(u)}), 200


@auth.route("/logout", methods=["POST"])
@require_auth
def logout():
    revoke_jti(g.jti)
    return jsonify({"message": "Logged out successfully"}), 200
