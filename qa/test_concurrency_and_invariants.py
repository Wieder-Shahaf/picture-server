"""Concurrency correctness & cross-cutting invariants.

These tests probe behaviors that are implicitly required by interface.md
but are easy to get wrong in implementation: thread-safety of the
inference pipeline, atomicity of the job counters under parallel load,
deterministic model output, and cross-user token isolation.

Unlike the throttle tests (which probe *latency* of the tarpit), these
tests probe *correctness* of shared mutable state when multiple requests
race through the server simultaneously.
"""
import concurrent.futures as cf
import uuid

import pytest
import requests

from conftest import BASE_URL


# ───────────── helpers ─────────────
def _make(base_url):
    u, p = f"ci_{uuid.uuid4().hex[:8]}", "Password!123"
    requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
    tok = requests.post(f"{base_url}/login", json={"username": u, "password": p}, timeout=10).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _counters(base_url, headers):
    return requests.get(f"{base_url}/status", headers=headers, timeout=10).json()["status"]["processed"]


# ───────────── 1. counter atomicity under parallel classifier load ─────────────

class TestCounterAtomicity:
    """status_tracker uses a threading.Lock, but a subtle race between
    bump_fail/bump_success and snapshot could yield inconsistent totals.
    We fire N parallel classifier calls (some valid, some malformed) and
    assert that the counter deltas sum exactly to N."""

    N_VALID = 5
    N_MALFORMED = 5

    def test_parallel_mixed_jobs_counter_delta_exact(self, base_url, bearer, png_path):
        """Fire N_VALID valid images + N_MALFORMED bad payloads concurrently.
        After all complete, success_delta + fail_delta must equal exactly
        N_VALID + N_MALFORMED (no double-counts, no drops)."""
        before = _counters(base_url, bearer)

        def _valid(_):
            with open(png_path, "rb") as f:
                r = requests.post(f"{base_url}/classifier", headers=bearer,
                                  files={"image": ("ok.png", f, "image/png")},
                                  timeout=120)
            return r.status_code

        def _bad(_):
            r = requests.post(f"{base_url}/classifier", headers=bearer,
                              files={"image": ("bad.bin", b"\x00\x01garbage", "application/octet-stream")},
                              timeout=30)
            return r.status_code

        total = self.N_VALID + self.N_MALFORMED
        with cf.ThreadPoolExecutor(max_workers=total) as ex:
            futs_ok = [ex.submit(_valid, i) for i in range(self.N_VALID)]
            futs_bad = [ex.submit(_bad, i) for i in range(self.N_MALFORMED)]
            all_results = [f.result() for f in futs_ok + futs_bad]

        # every request must be 200 or 400 (no 5xx)
        for code in all_results:
            assert code in (200, 400), f"unexpected status {code} under load"

        after = _counters(base_url, bearer)
        d_ok = after["success"] - before["success"]
        d_fail = after["fail"] - before["fail"]
        assert d_ok + d_fail == total, (
            f"counter delta {d_ok}+{d_fail}={d_ok+d_fail} != {total} requests; "
            f"race condition in counter update"
        )
        assert d_ok == self.N_VALID, f"success delta {d_ok} != {self.N_VALID}"
        assert d_fail == self.N_MALFORMED, f"fail delta {d_fail} != {self.N_MALFORMED}"


# ───────────── 2. concurrent inference produces consistent results ─────────────

class TestInferenceDeterminism:
    """YOLOv8n-cls is a deterministic model (no dropout at inference time).
    Submitting the exact same image twice must return the same set of
    match names and very close scores (floating-point jitter allowed)."""

    def test_same_image_returns_same_labels(self, base_url, bearer, png_path):
        """Two sequential classifications of the same PNG must agree on
        label order and scores within float tolerance."""
        results = []
        for _ in range(2):
            with open(png_path, "rb") as f:
                r = requests.post(f"{base_url}/classifier", headers=bearer,
                                  files={"image": ("det.png", f, "image/png")},
                                  timeout=60)
            assert r.status_code == 200
            results.append(r.json()["matches"])

        names_a = [m["name"] for m in results[0]]
        names_b = [m["name"] for m in results[1]]
        assert names_a == names_b, (
            f"same image returned different labels: {names_a} vs {names_b}"
        )
        for ma, mb in zip(results[0], results[1]):
            assert abs(ma["score"] - mb["score"]) < 1e-4, (
                f"score jitter too large: {ma} vs {mb}"
            )

    def test_parallel_inferences_all_succeed(self, base_url, bearer, png_path):
        """The _inference_lock serializes YOLO calls. Under parallel load,
        every request must still succeed (200) — not deadlock, not crash."""
        def _classify(_):
            with open(png_path, "rb") as f:
                return requests.post(f"{base_url}/classifier", headers=bearer,
                                     files={"image": ("p.png", f, "image/png")},
                                     timeout=120).status_code

        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            codes = list(ex.map(_classify, range(4)))

        assert all(c == 200 for c in codes), (
            f"concurrent inference should all be 200, got {codes}"
        )


# ───────────── 3. cross-user token isolation ─────────────

class TestTokenIsolation:
    """Each user gets their own JWT. Verify that one user's token
    cannot be confused with another's, and that operational side effects
    (counter bumps) are global — not per-user."""

    def test_user_a_token_reflects_same_global_counters(self, base_url, png_path):
        """Both users' /status should return identical counters because
        counters are global, not per-user."""
        h1 = _make(base_url)
        h2 = _make(base_url)
        # Bump a counter via user 1
        with open(png_path, "rb") as f:
            requests.post(f"{base_url}/classifier", headers=h1,
                          files={"image": ("g.png", f, "image/png")}, timeout=60)

        s1 = _counters(base_url, h1)
        s2 = _counters(base_url, h2)
        assert s1 == s2, (
            f"counters must be global, but user1 sees {s1} and user2 sees {s2}"
        )

    def test_cross_user_logout_isolation(self, base_url):
        """Logging out user A must NOT invalidate user B's token, even if
        both were issued at nearly the same time."""
        h_a = _make(base_url)
        h_b = _make(base_url)

        # logout A
        r = requests.post(f"{base_url}/logout", headers=h_a, timeout=10)
        assert r.status_code == 200

        # A is dead
        assert requests.get(f"{base_url}/status", headers=h_a, timeout=10).status_code == 401

        # B is alive
        r_b = requests.get(f"{base_url}/status", headers=h_b, timeout=10)
        assert r_b.status_code == 200, (
            f"user B's token was wrongly invalidated by user A's logout"
        )


# ───────────── 4. end-to-end lifecycle flow ─────────────

class TestEndToEndLifecycle:
    """A full lifecycle test that mirrors what an interop runner does:
    register → login → classify (3 valid + 1 bad) → check counters →
    logout → verify token revoked. Validates all invariants in one flow."""

    def test_full_lifecycle_correctness(self, base_url, png_path):
        u, p = f"e2e_{uuid.uuid4().hex[:8]}", "SecretPw!99"

        # 1. Register
        r = requests.post(f"{base_url}/register",
                          json={"username": u, "password": p}, timeout=10)
        assert r.status_code == 201
        assert r.json() == {"message": "User registered successfully"}

        # 2. Login
        r = requests.post(f"{base_url}/login",
                          json={"username": u, "password": p}, timeout=10)
        assert r.status_code == 200
        token = r.json()["token"]
        assert isinstance(token, str) and len(token.split(".")) == 3
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Snapshot counters
        before = _counters(base_url, headers)

        # 4. Classify 3 valid PNGs
        for i in range(3):
            with open(png_path, "rb") as f:
                r = requests.post(f"{base_url}/classifier", headers=headers,
                                  files={"image": (f"img{i}.png", f, "image/png")},
                                  timeout=60)
            assert r.status_code == 200, f"classify #{i} failed: {r.status_code}"
            body = r.json()
            assert "matches" in body
            assert all(0 < m["score"] <= 1 for m in body["matches"])

        # 5. Classify 1 malformed
        r = requests.post(f"{base_url}/classifier", headers=headers,
                          files={"image": ("bad.png", b"\x00garbage", "image/png")},
                          timeout=10)
        assert r.status_code == 400

        # 6. Verify counters
        after = _counters(base_url, headers)
        assert after["success"] - before["success"] == 3, \
            f"success delta {after['success'] - before['success']} != 3"
        assert after["fail"] - before["fail"] == 1, \
            f"fail delta {after['fail'] - before['fail']} != 1"

        # 7. Logout
        r = requests.post(f"{base_url}/logout", headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json() == {"message": "Logged out successfully"}

        # 8. Token now dead everywhere
        assert requests.get(f"{base_url}/status", headers=headers, timeout=10).status_code == 401
        r = requests.post(f"{base_url}/classifier", headers=headers,
                          files={"image": ("dead.png", b"x", "image/png")}, timeout=10)
        assert r.status_code == 401
        assert requests.post(f"{base_url}/logout", headers=headers, timeout=10).status_code == 401


# ───────────── 5. case-sensitivity of usernames ─────────────

class TestUsernameCaseSensitivity:
    """SQLite text comparison is case-sensitive by default (unless COLLATE
    NOCASE). If the server normalizes usernames, "Alice" and "alice" are
    the same user (409 on second register). If not, they're distinct users
    (both 201). Either behavior is acceptable — but the server must NOT
    crash, and whichever it chooses must be internally consistent: if
    register accepts both, login must work for both independently."""

    def test_case_variants_are_consistent(self, base_url):
        stem = uuid.uuid4().hex[:6]
        u_lower = f"case_{stem}"
        u_upper = f"Case_{stem}"

        # Register lowercase
        r1 = requests.post(f"{base_url}/register",
                           json={"username": u_lower, "password": "pw"}, timeout=10)
        assert r1.status_code == 201

        # Register uppercase variant
        r2 = requests.post(f"{base_url}/register",
                           json={"username": u_upper, "password": "pw"}, timeout=10)

        if r2.status_code == 409:
            # Server normalizes → login with either casing should work
            r_login = requests.post(f"{base_url}/login",
                                    json={"username": u_upper, "password": "pw"}, timeout=10)
            assert r_login.status_code == 200, \
                "server rejected case-variant as duplicate but won't let it login"
        elif r2.status_code == 201:
            # Server treats them as distinct → both must login independently
            for u in (u_lower, u_upper):
                r_login = requests.post(f"{base_url}/login",
                                        json={"username": u, "password": "pw"}, timeout=10)
                assert r_login.status_code == 200, \
                    f"registered {u!r} but can't login"
        else:
            pytest.fail(f"unexpected status for case-variant registration: {r2.status_code}")


# ───────────── 6. classifier idempotency on repeated images ─────────────

class TestClassifierIdempotency:
    """Classifying the same image multiple times must bump the counter
    each time, and each response must be a valid 200 with matches. This
    probes for file-handle exhaustion, caching bugs, or in-memory state
    leaks in the YOLO pipeline."""

    N = 5

    def test_repeated_classification_all_succeed_and_count(self, base_url, bearer, png_path):
        before = _counters(base_url, bearer)
        for i in range(self.N):
            with open(png_path, "rb") as f:
                r = requests.post(f"{base_url}/classifier", headers=bearer,
                                  files={"image": (f"rep{i}.png", f, "image/png")},
                                  timeout=60)
            assert r.status_code == 200, f"iteration {i}: {r.status_code}"
            matches = r.json()["matches"]
            assert len(matches) >= 1, f"iteration {i}: no matches"
            assert sum(m["score"] for m in matches) <= 1.0 + 1e-6

        after = _counters(base_url, bearer)
        assert after["success"] - before["success"] == self.N, \
            f"expected {self.N} success bumps, got {after['success'] - before['success']}"
        assert after["fail"] == before["fail"], \
            "fail counter moved during valid-only runs"


# ───────────── 7. JWT structure validation ─────────────

class TestJWTStructure:
    """The token returned by /login must be a proper JWT (3 base64url
    segments). While the spec doesn't prescribe the token format, every
    classmate's server uses JWT and an interop tester may well validate
    the structure."""

    def test_token_is_three_dot_separated_segments(self, base_url, fresh_user):
        u, p = fresh_user
        requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
        r = requests.post(f"{base_url}/login", json={"username": u, "password": p}, timeout=10)
        token = r.json()["token"]
        parts = token.split(".")
        assert len(parts) == 3, f"token must have 3 JWT segments, got {len(parts)}"
        # Each part must be valid base64url
        import base64
        for i, part in enumerate(parts):
            padded = part + "=" * (-len(part) % 4)
            try:
                base64.urlsafe_b64decode(padded)
            except Exception:
                pytest.fail(f"JWT segment {i} is not valid base64url: {part[:30]}...")

    def test_successive_tokens_have_distinct_jti(self, base_url, fresh_user):
        """Each login must mint a new jti so that revoking one token
        doesn't silently revoke all of a user's sessions."""
        import base64, json
        u, p = fresh_user
        requests.post(f"{base_url}/register", json={"username": u, "password": p}, timeout=10)
        jtis = set()
        for _ in range(3):
            r = requests.post(f"{base_url}/login", json={"username": u, "password": p}, timeout=10)
            token = r.json()["token"]
            payload = token.split(".")[1]
            padded = payload + "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
            assert "jti" in claims, f"JWT payload missing 'jti': {claims}"
            jtis.add(claims["jti"])
        assert len(jtis) == 3, f"expected 3 unique jtis, got {len(jtis)}"


# ───────────── 8. error envelope message field is always a nonempty string ─────────────

class TestErrorEnvelopeMessageField:
    """interface.md: error envelope has a 'message' string. Check that
    it's actually useful — not empty, not null, not missing — across
    all error paths. qa/test_peer_simulations checks http_status match
    but not the message field quality on every code path."""

    @pytest.mark.parametrize("scenario,method,path,kwargs", [
        ("no auth on status",     "GET",  "/status",     {}),
        ("no auth on classifier", "POST", "/classifier", {}),
        ("no auth on logout",     "POST", "/logout",     {}),
        ("GET on POST endpoint",  "GET",  "/register",   {}),
        ("bad JSON body",         "POST", "/register",   {"data": "not json"}),
    ])
    def test_message_is_nonempty_string(self, base_url, scenario, method, path, kwargs):
        r = requests.request(method, f"{base_url}{path}", timeout=10, **kwargs)
        assert r.status_code >= 400
        body = r.json()
        msg = body.get("error", {}).get("message")
        assert isinstance(msg, str) and len(msg) > 0, (
            f"[{scenario}] error.message must be a non-empty string, got {msg!r}"
        )
