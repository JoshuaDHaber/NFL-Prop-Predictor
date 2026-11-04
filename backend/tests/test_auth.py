"""Accounts (app/auth.py): emailed link and code, Google, sessions, preferences, the 21+ check and admin by account."""
import base64
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, main


@pytest.fixture
def sent(monkeypatch):
    """Every sign-in email, as (to, link token, code); nothing leaves the test."""
    out = []

    def capture(to, subject, text, html):
        out.append((to, re.search(r"#t=([\w-]+)", text).group(1), re.search(r"\b(\d{6})\b", subject).group(1)))
    monkeypatch.setattr(auth, "send_email", capture)
    auth._hits.clear()
    return out


def remote(ip="203.0.113.20"):
    """A visitor from elsewhere: not localhost, so none of this machine's admin shortcut."""
    return TestClient(main.app, client=(ip, 5000))


def sign_in(c, sent, email="fan@example.com", next_path="/props"):
    assert c.post("/api/auth/email", json={"email": email, "next": next_path}).json() == {"ok": True}
    return c.post("/api/auth/email/verify", json={"token": sent[-1][1]})


def test_email_link_signs_in_once(sent):
    with remote() as c:
        assert c.get("/api/auth/me").json()["user"] is None
        r = sign_in(c, sent, "Fan@Example.com ")
        assert r.status_code == 200 and r.json()["next"] == "/props"
        assert r.json()["user"]["email"] == "fan@example.com"
        assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
        me = c.get("/api/auth/me").json()["user"]
        assert me["email"] == "fan@example.com" and not me["age_confirmed"] and not me["is_admin"]
        # the link is good once
        assert c.post("/api/auth/email/verify", json={"token": sent[-1][1]}).status_code == 400


def test_the_session_is_stored_hashed(sent):
    from app.db import SessionLocal, UserSession
    with remote() as c:
        sign_in(c, sent, "hash@example.com")
        cookie = c.cookies.get("sid")
    with SessionLocal() as s:
        ids = {r.id for r in s.query(UserSession)}
    assert cookie not in ids and auth._hash(cookie) in ids


def test_code_works_and_wrong_codes_run_out(sent):
    with remote() as c:
        c.post("/api/auth/email", json={"email": "code@example.com"})
        code = sent[-1][2]
        wrong = "000000" if code != "000000" else "111111"
        assert c.post("/api/auth/email/verify", json={"email": "code@example.com", "code": wrong}).json()["detail"] == "That code isn't right."
        assert c.post("/api/auth/email/verify", json={"email": "code@example.com", "code": code}).status_code == 200

        c.post("/api/auth/email", json={"email": "code2@example.com"})
        code = sent[-1][2]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(auth.MAX_CODE_TRIES):
            c.post("/api/auth/email/verify", json={"email": "code2@example.com", "code": wrong})
        # five wrong guesses and even the right code is refused
        assert c.post("/api/auth/email/verify", json={"email": "code2@example.com", "code": code}).status_code == 400


def test_expired_links_are_refused(sent, monkeypatch):
    with remote() as c:
        c.post("/api/auth/email", json={"email": "late@example.com"})
        later = auth._now() + auth.timedelta(minutes=auth.TOKEN_MINUTES + 1)
        monkeypatch.setattr(auth, "_now", lambda: later)
        assert c.post("/api/auth/email/verify", json={"token": sent[-1][1]}).status_code == 400


def test_the_answer_never_says_whether_an_account_exists(sent):
    with remote() as c:
        sign_in(c, sent, "known@example.com")
    with remote("203.0.113.21") as c:
        known = c.post("/api/auth/email", json={"email": "known@example.com"})
        unknown = c.post("/api/auth/email", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
        assert c.post("/api/auth/email", json={"email": "not an email"}).status_code == 422


def test_sign_in_emails_are_rate_limited(sent):
    with remote("203.0.113.30") as c:
        codes = [c.post("/api/auth/email", json={"email": "spam@example.com"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_next_stays_on_this_site():
    assert auth.safe_next("/nba/props?x=1") == "/nba/props?x=1"
    for bad in ("https://evil.com", "//evil.com", "/\\evil.com", "", None, "props"):
        assert auth.safe_next(bad) == "/"


def test_other_sites_cant_post_with_the_cookie(sent):
    with remote() as c:
        sign_in(c, sent, "csrf@example.com")
        assert c.post("/api/auth/age", headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/auth/age", headers={"Origin": "http://localhost:8000"}).status_code == 200


def test_sign_in_writes_are_open_but_other_writes_stay_admin_only(sent):
    with remote() as c:
        assert c.post("/api/auth/email", json={"email": "open@example.com"}).status_code == 200
        assert c.post("/api/refresh", json={"odds": "none"}).status_code == 403
        # a screenshot shared to the installed app before its service worker runs: on to My bets (303, or no route in tests
        # without a built frontend), never "Admin only"
        assert c.post("/share-slip", follow_redirects=False).status_code != 403
        assert c.post("/share-slip/x").status_code == 403


def test_age_prefs_logout_and_delete(sent):
    with remote() as c:
        sign_in(c, sent, "prefs@example.com")
        assert c.put("/api/auth/prefs", json={"theme": "light"}).status_code == 200
        assert c.post("/api/auth/age").json()["user"]["age_confirmed"]
        r = c.put("/api/auth/prefs", json={"game_book": "DraftKings", "one_per_player": False})
        assert r.json()["user"]["prefs"] == {"theme": "light", "game_book": "DraftKings", "one_per_player": False, "detailed_cards": None,
                                             "tab_order": None}
        assert c.put("/api/auth/prefs", json={"theme": "purple"}).status_code == 422
        r = c.put("/api/auth/prefs", json={"tab_order": ["hot", "games", "picks", "parlays", "projections"]})
        assert r.json()["user"]["prefs"]["tab_order"][0] == "hot"
        assert c.put("/api/auth/prefs", json={"tab_order": ["admin"]}).status_code == 422

        assert c.post("/api/auth/logout").json()["user"] is None
        assert c.get("/api/auth/me").json()["user"] is None
        assert c.put("/api/auth/prefs", json={"theme": "dark"}).status_code == 401

        sign_in(c, sent, "prefs@example.com")
        assert c.get("/api/auth/me").json()["user"]["prefs"]["game_book"] == "DraftKings"   # kept across sessions
        assert c.delete("/api/auth/me").json()["user"] is None
        sign_in(c, sent, "prefs@example.com")
        assert c.get("/api/auth/me").json()["user"]["prefs"]["theme"] is None              # a fresh account


def test_favorites_per_league(sent):
    with remote() as c:
        assert c.put("/api/auth/favorites", json={"league": "nfl", "teams": ["KC"]}).status_code == 401
        sign_in(c, sent, "favs@example.com")
        assert c.get("/api/auth/me").json()["user"]["favorites"] == {"nfl": {"teams": [], "players": []}, "nba": {"teams": [], "players": []}}
        mahomes = {"player_id": "00-0033873", "name": "Patrick Mahomes", "pos": "QB", "team": "KC", "headshot": None}
        c.put("/api/auth/favorites", json={"league": "nfl", "teams": ["kc", "DET", "KC"]})
        r = c.put("/api/auth/favorites", json={"league": "nfl", "players": [mahomes, mahomes]})
        favs = r.json()["user"]["favorites"]
        assert favs["nfl"] == {"teams": ["KC", "DET"], "players": [mahomes]}   # teams kept, duplicates dropped
        assert favs["nba"] == {"teams": [], "players": []}                     # leagues apart: NFL DET isn't NBA DET
        c.put("/api/auth/favorites", json={"league": "nba", "teams": ["DET"]})
        assert c.get("/api/auth/me").json()["user"]["favorites"]["nfl"]["teams"] == ["KC", "DET"]

        assert c.put("/api/auth/favorites", json={"league": "nfl", "teams": ["<script>"]}).status_code == 422
        assert c.put("/api/auth/favorites", json={"league": "nfl", "teams": [f"T{chr(65 + i)}" for i in range(9)]}).status_code == 422
        assert c.put("/api/auth/favorites", json={"league": "mlb", "teams": []}).status_code == 422
        many = [{**mahomes, "player_id": str(i)} for i in range(31)]
        assert c.put("/api/auth/favorites", json={"league": "nfl", "players": many}).status_code == 422


def test_admin_emails_get_the_admin_page_once_21_is_confirmed(sent, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "Owner@example.com")
    with remote() as c:
        assert c.get("/api/admin").status_code == 403
        sign_in(c, sent, "owner@example.com")
        assert c.get("/api/admin").status_code == 403          # not until the 21+ box is ticked
        c.post("/api/auth/age")
        assert c.get("/api/auth/me").json()["user"]["is_admin"]
        assert c.get("/api/admin").status_code == 200
        assert c.get("/api/meta").json()["can_write"]
    with remote("203.0.113.40") as other:
        sign_in(other, sent, "fan2@example.com")
        other.post("/api/auth/age")
        assert other.get("/api/admin").status_code == 403


# ---------- Google ----------
def id_token(**claims):
    body = {"iss": "https://accounts.google.com", "aud": "client-1", "exp": time.time() + 600, **claims}
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'RS256'})}.{enc(body)}.sig"


@pytest.fixture
def google(monkeypatch):
    """Google set up, with the token exchange answering the claims a test puts in `google.claims`."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-1")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")

    class G:
        claims: dict = {}
    monkeypatch.setattr(auth, "exchange_code", lambda code: id_token(**G.claims))
    return G


def google_round_trip(c, google, next_path="/nba"):
    start = c.get(f"/api/auth/google/start?next={next_path}", follow_redirects=False)
    assert start.status_code == 302 and start.headers["location"].startswith(auth.GOOGLE_AUTH)
    q = dict(p.split("=", 1) for p in start.headers["location"].split("?", 1)[1].split("&"))
    google.claims.setdefault("nonce", q["nonce"])
    return c.get(f"/api/auth/google/callback?code=abc&state={q['state']}", follow_redirects=False)


def test_google_is_off_until_configured():
    with remote() as c:
        assert not c.get("/api/auth/me").json()["google"]
        assert c.get("/api/auth/google/start", follow_redirects=False).status_code == 404


def test_google_signs_in_and_links_a_verified_email(sent, google):
    with remote() as c:
        sign_in(c, sent, "both@example.com")
        c.post("/api/auth/logout")
        google.claims = {"sub": "g-1", "email": "Both@example.com", "email_verified": True, "name": "Pat", "picture": "https://x/p.png"}
        r = google_round_trip(c, google)
        assert r.status_code == 302 and r.headers["location"] == "/nba"
        me = c.get("/api/auth/me").json()
        assert me["google"] and me["user"]["email"] == "both@example.com" and me["user"]["name"] == "Pat"
    from app.db import SessionLocal, User
    with SessionLocal() as s:
        assert s.query(User).filter(User.email == "both@example.com").one().google_sub == "g-1"   # one account, not two


def test_google_never_links_an_unverified_email(sent, google):
    with remote() as c:
        sign_in(c, sent, "victim@example.com")
        c.post("/api/auth/logout")
        google.claims = {"sub": "g-evil", "email": "victim@example.com", "email_verified": False}
        r = google_round_trip(c, google)
        assert r.headers["location"] == "/?signin=unverified"
        assert c.get("/api/auth/me").json()["user"] is None


def test_google_refuses_a_forged_state_or_a_wrong_nonce(google):
    with remote() as c:
        c.get("/api/auth/google/start", follow_redirects=False)
        assert c.get("/api/auth/google/callback?code=abc&state=forged", follow_redirects=False).headers["location"] == "/?signin=failed"
        google.claims = {"sub": "g-2", "email": "n@example.com", "email_verified": True, "nonce": "not-this-one"}
        assert google_round_trip(c, google).headers["location"] == "/?signin=failed"


def test_id_claims_checks_audience_issuer_and_expiry(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-1")
    ok = dict(sub="s", nonce="n")
    assert auth.id_claims(id_token(**ok), "n")["sub"] == "s"
    assert auth.id_claims(id_token(**ok, aud="someone-else"), "n") is None
    assert auth.id_claims(id_token(**ok, iss="https://evil.example"), "n") is None
    assert auth.id_claims(id_token(**ok, exp=time.time() - 1), "n") is None
    assert auth.id_claims("garbage", "n") is None


def test_model_check_data_is_admin_only(sent, monkeypatch):
    """The Model check tab is hidden from everyone but the owner; its graded-picks data is refused to them too."""
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    with remote("203.0.113.50") as c:
        assert c.get("/api/grades").status_code == 403 and c.get("/api/nba/grades").status_code == 403
        assert not c.get("/api/meta").json()["can_write"]
        sign_in(c, sent, "fan3@example.com")
        c.post("/api/auth/age")
        assert c.get("/api/grades").status_code == 403
    with remote("203.0.113.51") as owner:
        sign_in(owner, sent, "owner@example.com")
        owner.post("/api/auth/age")
        assert owner.get("/api/grades").status_code == 200 and owner.get("/api/nba/grades").status_code == 200
