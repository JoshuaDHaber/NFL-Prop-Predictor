"""Accounts: sign in with Google or with a link/code sent by email, then an httpOnly cookie session. No passwords are stored.

Signing in is optional: every board stays public. An account keeps its preferences, and an email in ADMIN_EMAILS opens
the admin page. See docs/auth-plan.md.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import config
from .db import LoginToken, SessionLocal, User, UserSession
from .schemas import AccountOut, AuthState, EmailSignIn, EmailVerify, Favorites, FavoritesIn, Prefs

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE, STATE_COOKIE = "sid", "g_state"
SESSION_DAYS = 30
TOKEN_MINUTES = 15
MAX_CODE_TRIES = 5
MAX_FAV_TEAMS, MAX_FAV_PLAYERS = 8, 30
TEAM_RE = re.compile(r"^[A-Z]{2,4}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GOOGLE_AUTH, GOOGLE_TOKEN = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

# client_key is main.py's (the real client behind Railway's proxy); main sets it, so the two never disagree
client_key = lambda request: request.client.host if request.client else ""


def get_db():
    with SessionLocal() as s:
        yield s


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


def _secure() -> bool:
    return config.PUBLIC_URL().startswith("https://")


def safe_next(path: Optional[str]) -> str:
    """Where to land after signing in: a path on this site only, never another site (//evil.com, /\\evil.com)."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path or len(path) > 200:
        return "/"
    return path


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(422, "That doesn't look like an email address.")
    return email


# ---------- rate limits (one replica, so in memory, like main.py's admin-password guesses) ----------
_hits: dict[str, list[float]] = {}


def _limited(key: str, most: int, window: float) -> bool:
    """Count a hit on `key`; True when there were already `most` in the last `window` seconds."""
    now = time.time()
    recent = [t for t in _hits.get(key, []) if now - t < window]
    _hits[key] = recent + [now]
    return len(recent) >= most


def same_origin(request: Request):
    """The session is a cookie, which a browser sends whatever page makes the request. SameSite=Lax already stops other
    sites' POSTs; this refuses any write whose Origin (or Referer) is another site too."""
    sent = request.headers.get("origin") or request.headers.get("referer")
    if not sent:
        return   # not a browser (curl, tests): it has no cookie of a visitor's to ride on
    ok = {config.PUBLIC_URL(), *config.CORS_ORIGINS()}
    if not any(sent == o or sent.startswith(o + "/") for o in ok):
        raise HTTPException(403, "Cross-site request refused")


# ---------- sessions ----------
def session_user(request: Request, db: Session) -> Optional[User]:
    """The signed-in account, or None. Pushes the session's expiry out a day at a time while it's in use."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = db.get(UserSession, _hash(token))
    now = _now()
    if not sess or sess.expires_at < now:
        return None
    if now - sess.last_seen_at > timedelta(days=1):
        sess.last_seen_at, sess.expires_at = now, now + timedelta(days=SESSION_DAYS)
        db.commit()
        request.state.slid = token
    return db.get(User, sess.user_id)


def request_user(request: Request) -> Optional[User]:
    """session_user with its own database session, for callers outside a route (main.py's admin check)."""
    if not request.cookies.get(COOKIE):
        return None
    with SessionLocal() as db:
        return session_user(request, db)


def is_admin_user(user: Optional[User]) -> bool:
    return bool(user and user.age_confirmed_at and user.email in config.ADMIN_EMAILS())


def _set_cookie(response: Response, token: str):
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=_secure(), samesite="lax", path="/")


def start_session(db: Session, user: User, request: Request, response: Response):
    token = secrets.token_urlsafe(32)
    now = _now()
    # the old cookie (if any) is replaced, and expired rows are cleared while we're here
    if old := request.cookies.get(COOKIE):
        db.execute(delete(UserSession).where(UserSession.id == _hash(old)))
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.execute(delete(LoginToken).where(LoginToken.expires_at < now - timedelta(days=1)))
    db.add(UserSession(id=_hash(token), user_id=user.id, created_at=now, expires_at=now + timedelta(days=SESSION_DAYS),
                       last_seen_at=now, user_agent=request.headers.get("user-agent", "")[:200]))
    user.last_login_at = now
    db.commit()
    _set_cookie(response, token)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user(request, db)
    if not user:
        raise HTTPException(401, "Sign in first")
    return user


def _account(user: User) -> AccountOut:
    return AccountOut(email=user.email, name=user.name, avatar_url=user.avatar_url, is_admin=is_admin_user(user),
                      age_confirmed=user.age_confirmed_at is not None, prefs=Prefs(**(user.prefs or {})),
                      favorites=Favorites(**(user.favorites or {})))


def _state(user: Optional[User], next_path: Optional[str] = None) -> AuthState:
    return AuthState(user=_account(user) if user else None, google=bool(config.GOOGLE_CLIENT_ID() and config.GOOGLE_CLIENT_SECRET()),
                     next=next_path)


def _user_for_email(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, created_at=_now())
        db.add(user)
        db.flush()
    return user


# ---------- who's signed in ----------
@router.get("/me", response_model=AuthState)
def me(request: Request, response: Response, db: Session = Depends(get_db)):
    user = session_user(request, db)
    if token := getattr(request.state, "slid", None):
        _set_cookie(response, token)   # the session moved out: so does the cookie
    return _state(user)


@router.post("/logout", response_model=AuthState, dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    if token := request.cookies.get(COOKIE):
        db.execute(delete(UserSession).where(UserSession.id == _hash(token)))
        db.commit()
    response.delete_cookie(COOKIE, path="/")
    return _state(None)


@router.delete("/me", response_model=AuthState, dependencies=[Depends(same_origin)])
def delete_account(response: Response, user: User = Depends(require_user), db: Session = Depends(get_db)):
    from . import bets   # bets imports this module
    bets.delete_all(db, user.id)
    from . import slip_sync
    slip_sync.delete_for(db, user.id)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))   # SQLite doesn't enforce the cascade
    db.execute(delete(LoginToken).where(LoginToken.email == user.email))
    db.delete(db.get(User, user.id))
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return _state(None)


@router.post("/age", response_model=AuthState, dependencies=[Depends(same_origin)])
def confirm_age(user: User = Depends(require_user), db: Session = Depends(get_db)):
    user = db.get(User, user.id)
    user.age_confirmed_at = user.age_confirmed_at or _now()
    db.commit()
    return _state(user)


@router.put("/prefs", response_model=AuthState, dependencies=[Depends(same_origin)])
def save_prefs(body: Prefs, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Merge: a field left out (or null) keeps what the account has."""
    if body.game_book is not None and len(body.game_book) > 40:
        raise HTTPException(422, "Unknown sportsbook")
    user = db.get(User, user.id)
    user.prefs = {**(user.prefs or {}), **body.model_dump(exclude_none=True)}
    db.commit()
    return _state(user)


@router.put("/favorites", response_model=AuthState, dependencies=[Depends(same_origin)])
def save_favorites(body: FavoritesIn, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """One league's favorite teams (the Games tab lists their games first) or players (the compare page offers them)."""
    user = db.get(User, user.id)
    league = dict((user.favorites or {}).get(body.league) or {})
    if body.teams is not None:
        teams = list(dict.fromkeys(t.strip().upper() for t in body.teams))
        if len(teams) > MAX_FAV_TEAMS or not all(TEAM_RE.match(t) for t in teams):
            raise HTTPException(422, f"Pick up to {MAX_FAV_TEAMS} teams")
        league["teams"] = teams
    if body.players is not None:
        players = list({p.player_id: p.model_dump() for p in body.players}.values())
        if len(players) > MAX_FAV_PLAYERS:
            raise HTTPException(422, f"Up to {MAX_FAV_PLAYERS} favorite players")
        league["players"] = players
    user.favorites = {**(user.favorites or {}), body.league: league}   # a new dict, so the JSON column sees the change
    db.commit()
    return _state(user)


# ---------- email: a link and a 6-digit code ----------
def send_email(to: str, subject: str, text: str, html: str):
    """Through Resend's HTTP API; with no key (local development) the message goes to the server log instead."""
    key = config.RESEND_API_KEY()
    if not key:
        print(f"[auth] email to {to}: {subject}\n{text}")
        return
    r = requests.post("https://api.resend.com/emails", timeout=10, headers={"Authorization": f"Bearer {key}"},
                      json={"from": config.EMAIL_FROM(), "to": [to], "subject": subject, "text": text, "html": html})
    if r.status_code >= 300:
        print(f"[auth] Resend refused the email to {to}: {r.status_code} {r.text[:300]}")
        raise HTTPException(502, "We couldn't send the email. Try again in a minute.")


def _signin_email(link: str, code: str) -> tuple[str, str, str]:
    subject = f"{code} is your sign-in code for The Haber Process"
    text = (f"Sign in to The Haber Process:\n{link}\n\nOr enter this code: {code}\n\n"
            f"The link and code work once, for {TOKEN_MINUTES} minutes. If you didn't ask to sign in, ignore this email.")
    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:440px;margin:0 auto;color:#111">
  <p style="font-size:16px;margin:0 0 20px">Sign in to <b>The Haber Process</b></p>
  <p style="margin:0 0 24px"><a href="{link}" style="background:#4f46e5;color:#fff;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Sign in</a></p>
  <p style="margin:0 0 6px;color:#555">Or enter this code in the app:</p>
  <p style="font-size:28px;letter-spacing:6px;font-weight:700;margin:0 0 24px;font-family:ui-monospace,Menlo,monospace">{code}</p>
  <p style="color:#777;font-size:13px;margin:0">The link and code work once, for {TOKEN_MINUTES} minutes. If you didn't ask to sign in, ignore this email.</p>
</div>"""
    return subject, text, html


@router.post("/email", dependencies=[Depends(same_origin)])
def email_signin(body: EmailSignIn, request: Request, db: Session = Depends(get_db)):
    """Send a sign-in link and code. The answer is the same whether or not the address has an account."""
    email = normalize_email(body.email)
    if _limited(f"ip:{client_key(request)}", 10, 3600) or _limited(f"email:{email}", 3, TOKEN_MINUTES * 60):
        raise HTTPException(429, "Too many sign-in emails. Try again in a few minutes.")
    token, code = secrets.token_urlsafe(32), f"{secrets.randbelow(10**6):06d}"
    now = _now()
    db.add(LoginToken(email=email, token_hash=_hash(token), code_hash=_hash(f"{email}:{code}"), next_path=safe_next(body.next),
                      created_at=now, expires_at=now + timedelta(minutes=TOKEN_MINUTES)))
    db.commit()
    # the token rides in the #fragment: it never reaches a server log, and mail scanners that open links (GET) can't spend it,
    # since only the page's own POST does
    send_email(email, *_signin_email(f"{config.PUBLIC_URL()}/signin#t={token}", code))
    return {"ok": True}


@router.post("/email/verify", response_model=AuthState, dependencies=[Depends(same_origin)])
def email_verify(body: EmailVerify, request: Request, response: Response, db: Session = Depends(get_db)):
    now = _now()
    expired = HTTPException(400, "That link has expired or was already used. Send yourself a new one.")
    if body.token:
        row = db.scalar(select(LoginToken).where(LoginToken.token_hash == _hash(body.token)))
        if not row or row.used_at or row.expires_at < now:
            raise expired
    elif body.email and body.code:
        email = normalize_email(body.email)
        if _limited(f"code:{client_key(request)}", 20, 900):
            raise HTTPException(429, "Too many tries. Wait a few minutes.")
        row = db.scalar(select(LoginToken).where(LoginToken.email == email, LoginToken.used_at.is_(None), LoginToken.expires_at >= now)
                        .order_by(LoginToken.created_at.desc()))
        if not row or row.attempts >= MAX_CODE_TRIES:
            raise HTTPException(400, "That code has expired. Send yourself a new one.")
        if not hmac.compare_digest(row.code_hash, _hash(f"{email}:{body.code.strip()}")):
            row.attempts += 1
            db.commit()
            raise HTTPException(400, "That code isn't right." if row.attempts < MAX_CODE_TRIES else "Too many wrong codes. Send yourself a new one.")
    else:
        raise HTTPException(422, "Send the link's token, or the email and code")
    row.used_at = now
    user = _user_for_email(db, row.email)
    start_session(db, user, request, response)
    return _state(user, row.next_path)


# ---------- Google (OpenID Connect, authorization-code flow) ----------
def _redirect_uri() -> str:
    return f"{config.PUBLIC_URL()}/api/auth/google/callback"


def _google_on():
    if not (config.GOOGLE_CLIENT_ID() and config.GOOGLE_CLIENT_SECRET()):
        raise HTTPException(404, "Google sign-in isn't set up on this server")


@router.get("/google/start", dependencies=[Depends(_google_on)])
def google_start(next: str = "/"):
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    qs = urlencode({"client_id": config.GOOGLE_CLIENT_ID(), "redirect_uri": _redirect_uri(), "response_type": "code",
                    "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account"})
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{qs}", status_code=302)
    # ten minutes to pick an account; Lax still sends it on Google's top-level redirect back
    resp.set_cookie(STATE_COOKIE, json.dumps([state, nonce, safe_next(next)]), max_age=600, httponly=True, secure=_secure(),
                    samesite="lax", path="/api/auth/google")
    return resp


def exchange_code(code: str) -> str:
    """Google's ID token for an authorization code."""
    r = requests.post(GOOGLE_TOKEN, timeout=10, data={"code": code, "client_id": config.GOOGLE_CLIENT_ID(),
                      "client_secret": config.GOOGLE_CLIENT_SECRET(), "redirect_uri": _redirect_uri(), "grant_type": "authorization_code"})
    r.raise_for_status()
    return r.json()["id_token"]


def id_claims(id_token: str, nonce: str) -> Optional[dict]:
    """The ID token's claims when they're for us, from Google, current and for this sign-in; else None.
    The token came straight from Google's token endpoint over TLS with our secret, so (OpenID Connect Core 3.1.3.7) its
    signature needn't be checked again; audience, issuer, expiry and nonce still are."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    if (claims.get("aud") != config.GOOGLE_CLIENT_ID() or claims.get("iss") not in GOOGLE_ISSUERS
            or claims.get("exp", 0) < time.time() or not hmac.compare_digest(str(claims.get("nonce", "")), nonce) or not claims.get("sub")):
        return None
    return claims


@router.get("/google/callback", dependencies=[Depends(_google_on)])
def google_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    def fail(why: str = "failed"):
        resp = RedirectResponse(f"/?signin={why}", status_code=302)
        resp.delete_cookie(STATE_COOKIE, path="/api/auth/google")
        return resp
    try:
        want, nonce, next_path = json.loads(request.cookies.get(STATE_COOKIE, ""))
    except ValueError:
        return fail()
    if not code or not hmac.compare_digest(state, want):
        return fail()   # cancelled on Google's page, or a forged or stale callback
    try:
        claims = id_claims(exchange_code(code), nonce)
    except (requests.RequestException, KeyError, ValueError):
        claims = None
    if not claims:
        return fail()
    user = db.scalar(select(User).where(User.google_sub == claims["sub"]))
    if not user:
        # an existing account joins Google only on an address Google has verified, or anyone could claim anyone's account
        if not claims.get("email_verified") or not claims.get("email"):
            return fail("unverified")
        user = _user_for_email(db, claims["email"].strip().lower())
        user.google_sub = claims["sub"]
    user.name = claims.get("name") or user.name
    user.avatar_url = claims.get("picture") or user.avatar_url
    resp = RedirectResponse(safe_next(next_path), status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth/google")
    start_session(db, user, request, resp)
    return resp
