"""Endpoint × input surface — every spec endpoint hit with every reasonable
edge case derived from interface.md."""
import uuid
import requests
import pytest

from conftest import envelope_ok


# ───────────────────────── method × path matrix ─────────────────────────
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
SPEC_METHOD = {
    "/register":  "POST",
    "/login":     "POST",
    "/logout":    "POST",
    "/classifier":"POST",
    "/status":    "GET",
}


@pytest.mark.parametrize("path", list(SPEC_METHOD.keys()))
@pytest.mark.parametrize("method", METHODS)
def test_method_path_matrix(base_url, path, method):
    """Spec method → eventually 401/200 (depending on auth). Other methods → 405.
       PUT/DELETE/PATCH are not in the spec contract, so the server is free to
       return 405 or 404 — but it must NEVER 5xx and the envelope must be intact."""
    r = requests.request(method, f"{base_url}{path}", timeout=10)
    assert r.status_code < 500, f"{method} {path} → {r.status_code} (server error)"
    # error responses must carry the envelope
    if r.status_code >= 400:
        envelope_ok(r, r.status_code)


def test_unknown_path_404(base_url):
    # Paths chosen to NOT collapse to "/" under Werkzeug's path normalization
    # (e.g. "/././." would resolve to "/" and hit the UI route).
    for p in ("/foo", "/admin", "/api/v1/users", "/totally/not/a/route"):
        r = requests.get(f"{base_url}{p}", timeout=10)
        assert r.status_code in (404, 405), f"{p} → {r.status_code}"
        envelope_ok(r, r.status_code)


def test_no_redirects_emitted(base_url):
    """interface.md says clients MUST NOT follow redirects → server must not emit them."""
    for path in ("/register", "/login", "/status", "/classifier"):
        r = requests.post(f"{base_url}{path}", allow_redirects=False, timeout=10)
        assert r.status_code < 300 or r.status_code >= 400, \
            f"{path} produced 3xx redirect {r.status_code}"


def test_trailing_slash_does_not_redirect(base_url):
    for path in ("/register/", "/login/", "/status/"):
        r = requests.post(f"{base_url}{path}", json={}, allow_redirects=False, timeout=10)
        assert 300 > r.status_code or r.status_code >= 400, \
            f"{path} produced 3xx ({r.status_code})"


# ───────────────────────── /register edge cases ─────────────────────────
class TestRegister:
    def _u(self): return f"qa_{uuid.uuid4().hex[:10]}"

    def test_happy_path(self, base_url):
        r = requests.post(f"{base_url}/register",
                          json={"username": self._u(), "password": "pw"}, timeout=10)
        assert r.status_code == 201
        assert r.json() == {"message": "User registered successfully"}

    @pytest.mark.parametrize("body", [
        {},
        {"username": "x"},
        {"password": "y"},
        {"username": "", "password": "y"},
        {"username": "x", "password": ""},
        {"username": None, "password": "y"},
        {"username": "x", "password": None},
        {"username": 42, "password": "y"},
        {"username": "x", "password": {"nested": "obj"}},
    ])
    def test_invalid_bodies_400(self, base_url, body):
        r = requests.post(f"{base_url}/register", json=body, timeout=10)
        envelope_ok(r, 400)

    def test_non_json_body_400(self, base_url):
        r = requests.post(f"{base_url}/register", data="not json", timeout=10,
                          headers={"Content-Type": "text/plain"})
        envelope_ok(r, 400)

    def test_empty_body_400(self, base_url):
        r = requests.post(f"{base_url}/register", data="", timeout=10)
        envelope_ok(r, 400)

    def test_partial_json_400(self, base_url):
        r = requests.post(f"{base_url}/register", data='{"username": "x", "password":',
                          timeout=10, headers={"Content-Type": "application/json"})
        envelope_ok(r, 400)

    def test_duplicate_returns_409(self, base_url):
        u = self._u()
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        r = requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        envelope_ok(r, 409)

    def test_unicode_username(self, base_url):
        u = "שחף_" + uuid.uuid4().hex[:6]  # Hebrew
        r = requests.post(f"{base_url}/register",
                          json={"username": u, "password": "pw"}, timeout=10)
        assert r.status_code == 201, f"unicode username rejected: {r.text}"
        # And login must work with the exact same string
        r2 = requests.post(f"{base_url}/login",
                           json={"username": u, "password": "pw"}, timeout=10)
        assert r2.status_code == 200

    def test_emoji_username(self, base_url):
        u = "🦄_" + uuid.uuid4().hex[:6]
        r = requests.post(f"{base_url}/register",
                          json={"username": u, "password": "pw"}, timeout=10)
        assert r.status_code == 201 or (r.status_code == 400)  # spec doesn't mandate
        if r.status_code == 400:
            envelope_ok(r, 400)

    def test_long_password(self, base_url):
        r = requests.post(f"{base_url}/register",
                          json={"username": self._u(), "password": "a" * 2000}, timeout=20)
        assert r.status_code in (201, 400, 413)
        if r.status_code != 201: envelope_ok(r, r.status_code)

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users;--",
        "admin' OR '1'='1",
        "x\x00y",     # null byte
        "x\ny",       # newline
        "x\ty",       # tab
    ])
    def test_sqli_and_control_chars_safe(self, base_url, payload):
        """Whatever the input, the server must not 5xx and the envelope must hold.
           SQLite via parameterized queries makes these literal characters in the
           username — there must be no SQL execution."""
        r = requests.post(f"{base_url}/register",
                          json={"username": payload, "password": "pw"}, timeout=10)
        assert r.status_code < 500
        if r.status_code >= 400:
            envelope_ok(r, r.status_code)


# ───────────────────────── /login edge cases ─────────────────────────
class TestLogin:
    def _make_user(self, base_url):
        u = f"qa_{uuid.uuid4().hex[:10]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        return u

    def test_happy_path_returns_jwt_shape(self, base_url):
        u = self._make_user(base_url)
        r = requests.post(f"{base_url}/login",
                          json={"username": u, "password": "pw"}, timeout=10)
        assert r.status_code == 200
        token = r.json().get("token")
        assert isinstance(token, str) and token
        parts = token.split(".")
        assert len(parts) == 3, f"not a JWT shape: {token[:40]}..."

    def test_bad_password_401(self, base_url):
        u = self._make_user(base_url)
        r = requests.post(f"{base_url}/login",
                          json={"username": u, "password": "wrong"}, timeout=10)
        envelope_ok(r, 401)

    def test_nonexistent_user_401(self, base_url):
        r = requests.post(f"{base_url}/login",
                          json={"username": "nobody_" + uuid.uuid4().hex,
                                "password": "x"}, timeout=10)
        envelope_ok(r, 401)

    def test_missing_password_400(self, base_url):
        r = requests.post(f"{base_url}/login", json={"username": "x"}, timeout=10)
        envelope_ok(r, 400)

    def test_token_distinct_across_logins(self, base_url):
        """Each login must mint a unique JWT (different jti). Verifies that
           the server isn't caching/reusing tokens."""
        u = self._make_user(base_url)
        tokens = set()
        for _ in range(8):
            r = requests.post(f"{base_url}/login",
                              json={"username": u, "password": "pw"}, timeout=10)
            assert r.status_code == 200
            tokens.add(r.json()["token"])
        assert len(tokens) == 8, "JWT was not unique across consecutive logins"


# ───────────────────────── /logout & token edge cases ─────────────────────────
class TestLogout:
    def test_no_header_401(self, base_url):
        envelope_ok(requests.post(f"{base_url}/logout", timeout=10), 401)

    def test_wrong_scheme_401(self, base_url):
        r = requests.post(f"{base_url}/logout",
                          headers={"Authorization": "Basic dGVzdDp0ZXN0"}, timeout=10)
        envelope_ok(r, 401)

    def test_empty_bearer_401(self, base_url):
        r = requests.post(f"{base_url}/logout",
                          headers={"Authorization": "Bearer "}, timeout=10)
        envelope_ok(r, 401)

    def test_garbage_token_401(self, base_url):
        r = requests.post(f"{base_url}/logout",
                          headers={"Authorization": "Bearer not.a.jwt"}, timeout=10)
        envelope_ok(r, 401)

    def test_tampered_token_401(self, base_url, token):
        """Flip a byte in the signature → must be rejected."""
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        r = requests.post(f"{base_url}/logout",
                          headers={"Authorization": f"Bearer {tampered}"}, timeout=10)
        envelope_ok(r, 401)

    def test_double_logout_returns_401_on_second(self, base_url, bearer):
        r1 = requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        assert r1.status_code == 200
        r2 = requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        envelope_ok(r2, 401)

    def test_revoked_token_blocks_all_protected_endpoints(self, base_url, bearer):
        requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        envelope_ok(requests.get(f"{base_url}/status", headers=bearer, timeout=10), 401)
        envelope_ok(requests.post(f"{base_url}/classifier", headers=bearer, timeout=10), 401)


# ───────────────────────── /classifier edge cases ─────────────────────────
class TestClassifier:
    def _counters(self, base_url, headers):
        return requests.get(f"{base_url}/status", headers=headers, timeout=10).json()["status"]["processed"]

    def test_no_auth_401_does_not_touch_counters(self, base_url, bearer, png_path):
        before = self._counters(base_url, bearer)
        r = requests.post(f"{base_url}/classifier",
                          files={"image": ("x.png", open(png_path,"rb"), "image/png")},
                          timeout=20)
        envelope_ok(r, 401)
        after = self._counters(base_url, bearer)
        assert after == before, "auth failure must NOT increment counters"

    def test_valid_png_200_and_success_increments(self, base_url, bearer, png_path):
        before = self._counters(base_url, bearer)
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("x.png", open(png_path,"rb"), "image/png")},
                          timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert "matches" in body and isinstance(body["matches"], list) and body["matches"]
        total = 0.0
        for m in body["matches"]:
            assert isinstance(m["name"], str)
            s = m["score"]; assert 0 < s <= 1, f"score {s} out of (0,1]"
            total += s
        assert total <= 1.0 + 1e-6, f"score sum {total} > 1"
        after = self._counters(base_url, bearer)
        assert after["success"] - before["success"] == 1
        assert after["fail"] == before["fail"]

    def test_valid_jpeg_200(self, base_url, bearer, jpeg_path):
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("x.jpeg", open(jpeg_path,"rb"), "image/jpeg")},
                          timeout=60)
        assert r.status_code == 200, r.text

    def test_missing_image_field_400_and_fail_increments(self, base_url, bearer):
        before = self._counters(base_url, bearer)
        r = requests.post(f"{base_url}/classifier", headers=bearer, timeout=10)
        envelope_ok(r, 400)
        after = self._counters(base_url, bearer)
        assert after["fail"] - before["fail"] == 1
        assert after["success"] == before["success"]

    def test_wrong_field_name_400(self, base_url, bearer, png_path):
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"pic": ("x.png", open(png_path,"rb"), "image/png")},
                          timeout=10)
        envelope_ok(r, 400)

    @pytest.mark.parametrize("filename", [
        "noext", "image.txt", "image.gif", "image.webp",
        "image.bmp", "image.tiff", "image.heic", "image.jpg",
    ])
    def test_unsupported_filename_400(self, base_url, bearer, png_path, filename):
        """interface.md is literal: only .png and .jpeg.  .jpg is NOT in the spec."""
        before = self._counters(base_url, bearer)
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": (filename, open(png_path,"rb"), "application/octet-stream")},
                          timeout=10)
        envelope_ok(r, 400)
        after = self._counters(base_url, bearer)
        assert after["fail"] - before["fail"] == 1

    def test_text_with_png_filename_400(self, base_url, bearer, fake_png):
        before = self._counters(base_url, bearer)
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("trojan.png", open(fake_png,"rb"), "image/png")},
                          timeout=10)
        envelope_ok(r, 400)
        after = self._counters(base_url, bearer)
        assert after["fail"] - before["fail"] == 1, "decode failure must increment fail"

    def test_truncated_png_400(self, base_url, bearer, trunc_png):
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("trunc.png", open(trunc_png,"rb"), "image/png")},
                          timeout=10)
        envelope_ok(r, 400)

    def test_zero_byte_payload_400(self, base_url, bearer, empty_png):
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("empty.png", open(empty_png,"rb"), "image/png")},
                          timeout=10)
        envelope_ok(r, 400)

    def test_huge_image_works_or_fails_safely(self, base_url, bearer, huge_png):
        """3000×3000 PNG is large but legitimate. Either succeeds or returns
           a structured 4xx/5xx — must NOT crash the server."""
        r = requests.post(f"{base_url}/classifier", headers=bearer,
                          files={"image": ("huge.png", open(huge_png,"rb"), "image/png")},
                          timeout=120)
        assert r.status_code in (200, 400, 413, 500), f"unexpected {r.status_code}"
        if r.status_code >= 400:
            envelope_ok(r, r.status_code)


# ───────────────────────── /status edge cases ─────────────────────────
class TestStatus:
    def test_no_auth_401(self, base_url):
        envelope_ok(requests.get(f"{base_url}/status", timeout=10), 401)

    def test_schema(self, base_url, bearer):
        r = requests.get(f"{base_url}/status", headers=bearer, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"status"}, f"top-level keys = {body.keys()}"
        s = body["status"]
        assert set(s.keys()) >= {"uptime", "processed", "health", "api_version"}, f"keys: {s.keys()}"
        assert s["api_version"] == 1, f"api_version must be exactly int 1, got {s['api_version']!r}"
        assert s["health"] in ("ok", "error")
        assert isinstance(s["processed"], dict)
        assert set(s["processed"].keys()) == {"success", "fail"}, f"processed keys: {s['processed'].keys()}"
        assert isinstance(s["processed"]["success"], int)
        assert isinstance(s["processed"]["fail"], int)
        assert isinstance(s["uptime"], (int, float)) and s["uptime"] > 0

    def test_uptime_fractional_and_monotonic(self, base_url, bearer):
        import time
        s1 = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["uptime"]
        time.sleep(1.2)
        s2 = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["uptime"]
        assert s2 > s1
        assert s2 - s1 >= 1.0, f"uptime grew by {s2-s1}s in 1.2s wall time"
        assert (s1 != int(s1)) or (s2 != int(s2)), "uptime must be fractional (spec example: 55.6)"

    def test_counters_never_decrease(self, base_url, bearer, png_path):
        before = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["processed"]
        # do something that bumps counters
        requests.post(f"{base_url}/classifier", headers=bearer,
                      files={"image": ("ok.png", open(png_path,"rb"), "image/png")},
                      timeout=60)
        after = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["processed"]
        assert after["success"] >= before["success"]
        assert after["fail"]    >= before["fail"]
