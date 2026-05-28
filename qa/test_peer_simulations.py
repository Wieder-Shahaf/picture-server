"""Peer interop simulation — what a careful classmate is likely to write.

Interop rules (HW1-2.pdf §Important Technical Requirements):
  - Tests can ONLY check behaviors explicitly in interface.md
  - Cannot rely on implementation details

So every test here cites the EXACT spec sentence it probes.  If we fail
any test in this file, we likely lose interop points against a peer who
writes the same probe.  The list below is the catalog of risky corners
I'd consider as an attacker writing the 5-test interop file."""
import time
import uuid
import json
import requests
import pytest

BASE_URL = None  # filled by fixture


# ───────────────────────── exact response bodies ─────────────────────────
class TestExactSuccessBodies:
    """interface.md gives literal JSON for 201/200 success bodies.
       A strict peer will assert equality, not just presence."""

    def test_register_201_body_exact(self, base_url):
        # spec §Register, possible response 201:
        # 'the json body SHALL be `{"message": "User registered successfully"}`'
        u = f"p_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{base_url}/register",
                          json={"username": u, "password": "pw"}, timeout=10)
        assert r.status_code == 201
        assert r.json() == {"message": "User registered successfully"}

    def test_logout_200_body_exact(self, base_url, bearer):
        # spec §Log out, 200: '{"message": "Logged out successfully"}'
        r = requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        assert r.status_code == 200
        assert r.json() == {"message": "Logged out successfully"}

    def test_login_200_body_has_token_string(self, base_url):
        # spec §Log in, 200: body contains the token
        u = f"p_{uuid.uuid4().hex[:8]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        r = requests.post(f"{base_url}/login", json={"username": u, "password": "pw"}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "token" in body, "/login 200 body must contain 'token'"
        assert isinstance(body["token"], str)
        assert body["token"], "token must be non-empty"


# ───────────────────────── status response schema (literal) ─────────────────────────
class TestStatusSchemaLiteral:
    """spec §Get server status — the response body block:
       {"status": {"uptime": number, "processed": {"success": number,
       "fail": number}, "health": "ok" | "error", "api_version": number}}
    """

    def test_top_level_only_status(self, base_url, bearer):
        body = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()
        assert "status" in body
        # spec shows ONLY status at the top — extras are spec-undefined,
        # so a peer can assert exactly this set.
        assert set(body.keys()) == {"status"}, \
            f"extra top-level keys: {set(body.keys())}"

    def test_status_block_has_required_keys(self, base_url, bearer):
        body = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()
        s = body["status"]
        required = {"uptime", "processed", "health", "api_version"}
        assert required.issubset(set(s.keys())), \
            f"missing keys: {required - set(s.keys())}"

    def test_processed_keys_exactly_success_and_fail(self, base_url, bearer):
        s = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]
        assert set(s["processed"].keys()) == {"success", "fail"}, \
            f"processed keys = {s['processed'].keys()}"

    def test_api_version_is_integer_one_literal(self, base_url, bearer):
        # spec §Get server status: '"api_version": 1' (integer in the JSON example)
        r = requests.get(f"{base_url}/status", headers=bearer, timeout=10)
        av = r.json()["status"]["api_version"]
        assert av == 1
        assert isinstance(av, int) and not isinstance(av, bool), \
            f"api_version must be int 1, got {type(av).__name__}"
        # check on the wire too — \"api_version\":1 with no decimal
        import re
        assert re.search(r'"api_version"\s*:\s*1\b', r.text), \
            f"api_version not serialized as integer: {r.text[:200]}"

    def test_health_value_exact_strings(self, base_url, bearer):
        # spec: '"health": "ok" | "error"'
        h = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["health"]
        assert h in ("ok", "error"), f"health must be 'ok' or 'error', got {h!r}"

    def test_uptime_is_a_number(self, base_url, bearer):
        # spec: '"uptime": number' (and example uses 230.7 — fractional)
        u = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["uptime"]
        assert isinstance(u, (int, float)) and not isinstance(u, bool)
        assert u > 0


# ───────────────────────── classifier response schema (literal) ─────────────────────────
class TestClassifierSchemaLiteral:
    """spec §Upload image: '{ "matches": [ {"name": string, "score": number}]}'"""

    def test_top_level_only_matches(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            r = requests.post(f"{base_url}/classifier", headers=bearer,
                              files={"image": ("x.png", f, "image/png")},
                              timeout=60)
        body = r.json()
        assert set(body.keys()) == {"matches"}, f"top-level keys: {set(body.keys())}"

    def test_match_keys_exactly_name_and_score(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            body = requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("x.png", f, "image/png")},
                                 timeout=60).json()
        for m in body["matches"]:
            assert set(m.keys()) == {"name", "score"}, \
                f"match has extra/missing keys: {set(m.keys())}"
            assert isinstance(m["name"], str)
            assert isinstance(m["score"], (int, float)) and not isinstance(m["score"], bool)

    def test_score_strictly_positive_and_capped_at_one(self, base_url, bearer, png_path):
        # spec §Classification Quality: '0.0 < score <= 1.0'  (STRICT lower bound)
        with open(png_path, "rb") as f:
            body = requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("x.png", f, "image/png")},
                                 timeout=60).json()
        for m in body["matches"]:
            assert m["score"] > 0,  f"score {m['score']} violates strict > 0"
            assert m["score"] <= 1, f"score {m['score']} > 1"

    def test_sum_of_scores_between_0_and_1(self, base_url, bearer, png_path):
        # spec §Classification Quality: 'sum ... at least 0 and at most 1'
        with open(png_path, "rb") as f:
            body = requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("x.png", f, "image/png")},
                                 timeout=60).json()
        s = sum(m["score"] for m in body["matches"])
        assert 0 <= s <= 1.0 + 1e-6, f"sum of scores {s} not in [0, 1]"

    def test_matches_is_a_list(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            body = requests.post(f"{base_url}/classifier", headers=bearer,
                                 files={"image": ("x.png", f, "image/png")},
                                 timeout=60).json()
        assert isinstance(body["matches"], list), \
            f"matches must be a list, got {type(body['matches']).__name__}"


# ───────────────────────── error envelope completeness ─────────────────────────
class TestErrorEnvelopeUniversal:
    """spec §Server response: every error response carries the envelope and the
       http_status field equals the HTTP status code."""

    def _envelope_check(self, r, expected_status):
        assert r.status_code == expected_status
        assert r.headers.get("Content-Type", "").startswith("application/json")
        body = r.json()
        assert "error" in body and isinstance(body["error"], dict)
        assert body["error"].get("http_status") == expected_status
        assert isinstance(body["error"].get("message"), str)

    def test_400_register_missing_fields(self, base_url):
        self._envelope_check(requests.post(f"{base_url}/register", json={}, timeout=10), 400)

    def test_401_status_no_token(self, base_url):
        self._envelope_check(requests.get(f"{base_url}/status", timeout=10), 401)

    def test_401_login_bad_password(self, base_url):
        u = f"p_{uuid.uuid4().hex[:8]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "right"}, timeout=10)
        self._envelope_check(requests.post(f"{base_url}/login",
                                           json={"username": u, "password": "wrong"}, timeout=10), 401)

    def test_405_get_register(self, base_url):
        self._envelope_check(requests.get(f"{base_url}/register", timeout=10), 405)

    def test_405_post_status(self, base_url):
        self._envelope_check(requests.post(f"{base_url}/status", timeout=10), 405)

    def test_405_get_login(self, base_url):
        self._envelope_check(requests.get(f"{base_url}/login", timeout=10), 405)

    def test_405_get_logout(self, base_url):
        self._envelope_check(requests.get(f"{base_url}/logout", timeout=10), 405)

    def test_405_get_classifier(self, base_url):
        self._envelope_check(requests.get(f"{base_url}/classifier", timeout=10), 405)

    def test_409_register_duplicate(self, base_url):
        u = f"p_{uuid.uuid4().hex[:8]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        self._envelope_check(requests.post(f"{base_url}/register",
                                           json={"username": u, "password": "pw"}, timeout=10), 409)


# ───────────────────────── token lifecycle (spec §Auth) ─────────────────────────
class TestTokenLifecycle:
    """spec: tokens issued by /login, used for protected endpoints, revoked by /logout."""

    def test_freshly_issued_token_works_on_status(self, base_url):
        u = f"p_{uuid.uuid4().hex[:8]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        tok = requests.post(f"{base_url}/login",
                            json={"username": u, "password": "pw"}, timeout=10).json()["token"]
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": f"Bearer {tok}"}, timeout=10)
        assert r.status_code == 200

    def test_token_works_on_classifier(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            r = requests.post(f"{base_url}/classifier", headers=bearer,
                              files={"image": ("x.png", f, "image/png")},
                              timeout=60)
        assert r.status_code == 200

    def test_revoked_token_blocks_status(self, base_url, bearer):
        requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        r = requests.get(f"{base_url}/status", headers=bearer, timeout=10)
        assert r.status_code == 401

    def test_revoked_token_blocks_classifier(self, base_url, bearer, png_path):
        requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        with open(png_path, "rb") as f:
            r = requests.post(f"{base_url}/classifier", headers=bearer,
                              files={"image": ("x.png", f, "image/png")},
                              timeout=10)
        assert r.status_code == 401

    def test_revoked_token_blocks_logout_replay(self, base_url, bearer):
        # spec implies tokens shouldn't be reusable post-logout
        r1 = requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        assert r1.status_code == 200
        r2 = requests.post(f"{base_url}/logout", headers=bearer, timeout=10)
        assert r2.status_code == 401

    def test_two_users_distinct_tokens(self, base_url):
        u1, u2 = f"p_{uuid.uuid4().hex[:6]}", f"p_{uuid.uuid4().hex[:6]}"
        for u in (u1, u2):
            requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        t1 = requests.post(f"{base_url}/login", json={"username": u1, "password": "pw"}, timeout=10).json()["token"]
        t2 = requests.post(f"{base_url}/login", json={"username": u2, "password": "pw"}, timeout=10).json()["token"]
        assert t1 != t2, "different users must mint different tokens"

    def test_one_users_logout_does_not_affect_another(self, base_url):
        u1, u2 = f"p_{uuid.uuid4().hex[:6]}", f"p_{uuid.uuid4().hex[:6]}"
        for u in (u1, u2):
            requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        t1 = requests.post(f"{base_url}/login", json={"username": u1, "password": "pw"}, timeout=10).json()["token"]
        t2 = requests.post(f"{base_url}/login", json={"username": u2, "password": "pw"}, timeout=10).json()["token"]
        requests.post(f"{base_url}/logout", headers={"Authorization": f"Bearer {t1}"}, timeout=10)
        # t2 should still work
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": f"Bearer {t2}"}, timeout=10)
        assert r.status_code == 200, "user2's token wrongly invalidated by user1's logout"


# ───────────────────────── counter semantics ─────────────────────────
class TestCounterSemantics:
    """spec §Get server status: counters track /classifier jobs.
       Implicit but probable peer assertions:"""

    def _proc(self, base_url, bearer):
        return requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["processed"]

    def test_status_call_does_not_change_counters(self, base_url, bearer):
        a = self._proc(base_url, bearer)
        time.sleep(0.05)
        b = self._proc(base_url, bearer)
        assert a == b, f"/status itself must not increment counters: {a} -> {b}"

    def test_register_does_not_change_counters(self, base_url, bearer):
        a = self._proc(base_url, bearer)
        u = f"p_{uuid.uuid4().hex[:6]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        b = self._proc(base_url, bearer)
        assert a == b

    def test_login_does_not_change_counters(self, base_url, bearer):
        a = self._proc(base_url, bearer)
        u = f"p_{uuid.uuid4().hex[:6]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        requests.post(f"{base_url}/login", json={"username": u, "password": "pw"}, timeout=10)
        b = self._proc(base_url, bearer)
        assert a == b

    def test_logout_does_not_change_counters(self, base_url):
        u = f"p_{uuid.uuid4().hex[:6]}"
        requests.post(f"{base_url}/register", json={"username": u, "password": "pw"}, timeout=10)
        t1 = requests.post(f"{base_url}/login",
                           json={"username": u, "password": "pw"}, timeout=10).json()["token"]
        h = {"Authorization": f"Bearer {t1}"}
        a = self._proc(base_url, h)
        # second token so we can read after logout
        t2 = requests.post(f"{base_url}/login",
                           json={"username": u, "password": "pw"}, timeout=10).json()["token"]
        h2 = {"Authorization": f"Bearer {t2}"}
        requests.post(f"{base_url}/logout", headers=h, timeout=10)
        b = self._proc(base_url, h2)
        assert a == b

    def test_classifier_401_does_not_change_counters(self, base_url, bearer, png_path):
        a = self._proc(base_url, bearer)
        with open(png_path, "rb") as f:
            requests.post(f"{base_url}/classifier",
                          files={"image": ("x.png", f, "image/png")},
                          timeout=20)  # NO auth header
        b = self._proc(base_url, bearer)
        assert a == b, "401 on /classifier must not move counters"

    def test_classifier_405_does_not_change_counters(self, base_url, bearer):
        a = self._proc(base_url, bearer)
        requests.get(f"{base_url}/classifier", headers=bearer, timeout=10)
        b = self._proc(base_url, bearer)
        assert a == b, "405 on /classifier must not move counters"


# ───────────────────────── method handling ─────────────────────────
class TestMethodHandling:
    """spec enumerates 405 as a possible response for every endpoint.
       Implicit: any non-spec method on a known endpoint should respond
       cleanly (4xx) with envelope, never 5xx, never 3xx."""

    @pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
    @pytest.mark.parametrize("path", ["/register", "/login", "/logout", "/classifier", "/status"])
    def test_non_spec_method_is_4xx_with_envelope(self, base_url, method, path):
        r = requests.request(method, f"{base_url}{path}", timeout=10, allow_redirects=False)
        assert 400 <= r.status_code < 500, f"{method} {path} -> {r.status_code}"
        assert r.headers.get("Content-Type", "").startswith("application/json")


# ───────────────────────── /classifier malformed-input matrix ─────────────────────────
class TestClassifierMalformed:
    """spec §Upload image: 400 on malformed input; treat any non-decodable
       payload as malformed."""

    def _bump(self, base_url, bearer, **kw):
        before = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["processed"]
        r = requests.post(f"{base_url}/classifier", headers=bearer, timeout=20, **kw)
        after  = requests.get(f"{base_url}/status", headers=bearer, timeout=10).json()["status"]["processed"]
        return r, after["fail"] - before["fail"], after["success"] - before["success"]

    def test_no_multipart_at_all(self, base_url, bearer):
        r, df, ds = self._bump(base_url, bearer)
        assert r.status_code == 400 and df == 1 and ds == 0

    def test_wrong_field_name(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            r, df, ds = self._bump(base_url, bearer,
                                   files={"picture": ("x.png", f, "image/png")})
        assert r.status_code == 400 and df == 1

    def test_image_field_as_text(self, base_url, bearer):
        r, df, ds = self._bump(base_url, bearer, data={"image": "not a file"})
        assert r.status_code == 400 and df == 1

    def test_filename_with_no_extension(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            r, df, ds = self._bump(base_url, bearer,
                                   files={"image": ("noext", f, "image/png")})
        assert r.status_code == 400 and df == 1

    def test_random_bytes_with_png_filename(self, base_url, bearer):
        import os
        r, df, ds = self._bump(base_url, bearer,
                               files={"image": ("x.png", os.urandom(2048), "image/png")})
        assert r.status_code == 400 and df == 1


# ───────────────────────── Authorization header tolerance ─────────────────────────
class TestAuthHeaderEdges:
    """A peer might write tests probing Authorization header parsing tolerance.
       Spec says: missing/malformed/expired/invalid → 401.  So anything
       that's not exactly `Bearer <jwt>` must return 401."""

    def test_no_header(self, base_url):
        assert requests.get(f"{base_url}/status", timeout=10).status_code == 401

    def test_basic_scheme(self, base_url):
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": "Basic dGVzdDp0ZXN0"}, timeout=10)
        assert r.status_code == 401

    def test_no_scheme_just_token(self, base_url, token):
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": token}, timeout=10)
        assert r.status_code == 401

    def test_bearer_with_no_space(self, base_url, token):
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": "Bearer"}, timeout=10)
        assert r.status_code == 401

    def test_bearer_followed_by_only_space(self, base_url):
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": "Bearer "}, timeout=10)
        assert r.status_code == 401

    def test_two_bearers(self, base_url, token):
        r = requests.get(f"{base_url}/status",
                         headers={"Authorization": f"Bearer {token} extra"}, timeout=10)
        assert r.status_code == 401


# ───────────────────────── /classifier success cardinality ─────────────────────────
class TestClassifierResultCardinality:
    """spec example shows 2 matches.  Doesn't say minimum/maximum.
       But on a real image a peer would expect AT LEAST 1 match."""

    def test_valid_image_returns_at_least_one_match(self, base_url, bearer, png_path):
        with open(png_path, "rb") as f:
            r = requests.post(f"{base_url}/classifier", headers=bearer,
                              files={"image": ("x.png", f, "image/png")},
                              timeout=60)
        assert r.status_code == 200
        matches = r.json()["matches"]
        assert isinstance(matches, list)
        assert len(matches) >= 1, "no matches returned for a valid image"
