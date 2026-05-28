import os
import sqlite3
import time

from flask import g


def _db_path() -> str:
    return os.environ.get("DB_PATH", "/app/data/app.db")


def get_conn() -> sqlite3.Connection:
    if "db" not in g:
        path = _db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


def close_conn(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS revoked_tokens ("
            "jti TEXT PRIMARY KEY, revoked_at REAL NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def create_user(username: str, password_hash: str) -> bool:
    try:
        get_conn().execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user(username: str):
    return get_conn().execute(
        "SELECT username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()


def revoke_jti(jti: str):
    get_conn().execute(
        "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at) VALUES (?, ?)",
        (jti, time.time()),
    )


def is_revoked(jti: str) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)
    ).fetchone()
    return row is not None
