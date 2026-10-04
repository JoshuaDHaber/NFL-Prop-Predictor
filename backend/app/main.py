"""FastAPI app: JSON API for projections, priced picks and data refresh (+ serves the built React app)."""
import hmac
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
import re
import socket
import subprocess

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, pipeline
from .db import AltLine, OddsLine, Projection, Run, SessionLocal, current_lines
from .engine import data, model, odds
from .engine.ladder import build_ladder
from .engine.picks import build_picks
from .schemas import (AltFetchResult, GameLogEntry, LadderOut, Game, JobStatus, Kind, Meta, OddsInfo, PickOut, PlayerDetail, ProjectionOut,
                      RefreshRequest, RunInfo)

@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as s:
        n = pipeline.seed_odds_from_csv(CSV_SEED, s)
        if n:
            print(f"Seeded {n} odds lines from {CSV_SEED}")
    yield


app = FastAPI(title="NFL Prop Predictor", version="1.0", lifespan=lifespan)
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def is_admin(request: Request) -> bool:
    """May this request change data or spend API credits? Yes from this machine, or with the ADMIN_TOKEN."""
    host = request.client.host if request.client else ""
    if host in LOCAL_HOSTS:
        return True
    token = config.ADMIN_TOKEN()
    given = request.headers.get("authorization", "")
    return bool(token) and given.startswith("Bearer ") and hmac.compare_digest(given[7:], token)


@app.middleware("http")
async def admin_writes_only(request: Request, call_next):
    """The app can be served beyond this machine (LAN, Tailscale, a host). Writes are POSTs, and those
    (refreshes, alt-line fetches) spend API credits, so they need to come from here or carry the admin token."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and not is_admin(request):
        return JSONResponse({"detail": "Admin only"}, status_code=403)
    return await call_next(request)


def tailscale_ip(ifconfig_text: str) -> Optional[str]:
    """A Tailscale address (100.64.0.0/10) from `ifconfig` output, if this machine is on a tailnet."""
    for m in re.finditer(r"inet (100\.(\d+)\.\d+\.\d+)\b", ifconfig_text):
        if 64 <= int(m.group(2)) <= 127:
            return m.group(1)
    return None


def lan_ip() -> Optional[str]:
    """The address other devices should use to reach this machine: Tailscale if present (works from
    anywhere), else the local-network address (a UDP 'connect' sends no packets)."""
    try:
        ts = tailscale_ip(subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3).stdout)
        if ts:
            return ts
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS(), allow_methods=["*"], allow_headers=["*"])

CSV_SEED = os.path.join(config.BASE_DIR, ".cache", "odds_latest.csv")


def get_db():
    with SessionLocal() as s:
        yield s


# ---------- helpers ----------
def latest_run(db: Session) -> Optional[Run]:
    return db.scalars(select(Run).order_by(Run.id.desc()).limit(1)).first()


def proj_frame(db: Session, run_id: int) -> pd.DataFrame:
    rows = db.scalars(select(Projection).where(Projection.run_id == run_id)).all()
    return pd.DataFrame([{c.name: getattr(r, c.name) for c in Projection.__table__.columns} for r in rows])


def game_label(gid: str) -> str:
    _, _, away, home = gid.split("_", 3)
    return f"{away} @ {home}"


_pick_cache: dict = {}


def all_picks(db: Session, run: Run, w: float, book: Optional[str] = None) -> pd.DataFrame:
    """Priced picks for (run, current odds, market weight); memoized because pricing loops over every line."""
    version = tuple(sorted(db.execute(select(OddsLine.market, func.max(OddsLine.fetched_at))
                                      .group_by(OddsLine.market)).all()))
    key = (run.id, version, round(w, 3), book)
    if key not in _pick_cache:
        if len(_pick_cache) > 20:
            _pick_cache.clear()
        proj = proj_frame(db, run.id)
        picks = build_picks(proj, current_lines(db), w, only_book=book)
        if not picks.empty:
            l5 = dict(zip(zip(proj.player_id, proj.kind), proj.last5))
            picks["last5"] = [l5.get(k, []) for k in zip(picks.player_id, picks.kind)]
        else:
            picks["last5"] = []
        _pick_cache[key] = picks
    return _pick_cache[key]


def records(df: pd.DataFrame) -> list[dict]:
    return df.replace({np.nan: None}).to_dict("records")


# ---------- job runner ----------
_job = {"state": "idle", "started_at": None, "finished_at": None, "log": [], "error": None}
_lock = threading.Lock()


def _run_job(odds_mode: str):
    def log(msg):
        _job["log"].append(msg)

    try:
        if config.PROJECTIONS_ON_SERVER():
            pipeline.run_projections(log=log)
        else:
            log("Projections run off-server on this host; fetching odds only")
        pipeline.refresh_odds(odds_mode, log=log)
        _job["state"] = "done"
    except Exception as e:  # surfaced to the UI
        _job["state"], _job["error"] = "error", f"{type(e).__name__}: {e}"
    finally:
        _job["finished_at"] = datetime.utcnow().isoformat()


# ---------- routes ----------
@app.get("/api/meta", response_model=Meta)
def meta(request: Request, db: Session = Depends(get_db)):
    out = build_meta(db, _lan_url(request))
    out.can_write, out.can_run_projections = is_admin(request), config.PROJECTIONS_ON_SERVER()
    return out


def build_meta(db: Session, lan_url: Optional[str] = None) -> Meta:
    run = latest_run(db)
    games, backtest = [], {}
    if run:
        rows = db.execute(select(Projection.game_id, Projection.gameday, Projection.gametime)
                          .where(Projection.run_id == run.id).distinct()).all()
        games = [Game(game_id=g, label=game_label(g), gameday=d, gametime=t)
                 for g, d, t in sorted(rows, key=lambda r: (r[1], r[2], r[0]))]
        backtest = run.backtest
    return Meta(run=None if not run else RunInfo(id=run.id, season=run.season, week=run.week,
                                                  created_at=run.created_at.isoformat(), excluded=run.excluded),
                backtest=backtest, odds=_odds_info(db), games=games, has_odds_key=bool(config.ODDS_API_KEY()),
                job=JobStatus(**_job), lan_url=lan_url,
                books=sorted(b for (b,) in db.execute(select(OddsLine.book).distinct()).all()))


def _lan_url(request: Request) -> Optional[str]:
    if os.environ.get("APP_URL"):  # e.g. a Tailscale MagicDNS name: http://my-mac.tailnet-name.ts.net:8000
        return os.environ["APP_URL"].rstrip("/")
    ip = lan_ip()
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    return f"{request.url.scheme}://{ip}:{port}" if ip else None


def _odds_info(db: Session) -> dict:
    latest = {m: t for m, t in db.execute(select(OddsLine.market, func.max(OddsLine.fetched_at))
                                          .group_by(OddsLine.market)).all()}
    return {m: OddsInfo(fetched_at=t.isoformat(),
                        lines=db.scalar(select(func.count()).where(OddsLine.market == m, OddsLine.fetched_at == t)))
            for m, t in latest.items()}


@app.get("/api/projections", response_model=list[ProjectionOut])
def projections(kind: Optional[Kind] = None, exclude_kind: Optional[Kind] = None, game_id: Optional[str] = None,
                q: Optional[str] = None, db: Session = Depends(get_db)):
    run = latest_run(db)
    if not run:
        return []
    stmt = select(Projection).where(Projection.run_id == run.id).order_by(Projection.mu.desc())
    if kind:
        stmt = stmt.where(Projection.kind == kind)
    if exclude_kind:
        stmt = stmt.where(Projection.kind != exclude_kind)
    if game_id:
        stmt = stmt.where(Projection.game_id == game_id)
    if q:
        stmt = stmt.where(Projection.name.ilike(f"%{q}%"))
    return db.scalars(stmt).all()


@app.get("/api/picks", response_model=list[PickOut])
def picks(kind: Optional[Kind] = None, exclude_kind: Optional[Kind] = None, game_id: Optional[str] = None, q: Optional[str] = None,
          book: Optional[str] = None,
          min_ev: float = Query(0.03, ge=-1, le=1), market_weight: float = Query(0.35, ge=0, le=1),
          include_flagged: bool = False, limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    run = latest_run(db)
    if not run:
        return []
    df = all_picks(db, run, market_weight, book)
    if df.empty:
        return []
    df = df[df.ev >= min_ev]
    if not include_flagged:
        df = df[~df.flagged]
    if kind:
        df = df[df.kind == kind]
    if exclude_kind:
        df = df[df.kind != exclude_kind]
    if game_id:
        df = df[df.game_id == game_id]
    if q:
        df = df[df.name.str.contains(q, case=False, regex=False)]
    return records(df.head(limit))


@app.get("/api/players/{player_id}", response_model=PlayerDetail)
def player(player_id: str, market_weight: float = Query(0.35, ge=0, le=1), db: Session = Depends(get_db)):
    detail = build_player_detail(db, latest_run(db), player_id, market_weight)
    if not detail:
        raise HTTPException(404, "Player has no projection in the current run")
    return detail


def build_player_detail(db: Session, run: Optional[Run], player_id: str, market_weight: float = 0.35) -> Optional[PlayerDetail]:
    rows = db.scalars(select(Projection).where(Projection.run_id == run.id, Projection.player_id == player_id)).all() if run else []
    if not rows:
        return None
    p = rows[0]
    df = all_picks(db, run, market_weight)
    pp = df[df.player_id == player_id] if not df.empty else df
    return PlayerDetail(player_id=player_id, name=p.name, pos=p.pos, team=p.team,
                        projections=[ProjectionOut.model_validate(r, from_attributes=True) for r in rows],
                        picks=records(pp), logs=_game_logs(player_id, [r.kind for r in rows], run.season))


def _player_proj(db: Session, player_id: str, kind: str):
    run = latest_run(db)
    p = db.scalars(select(Projection).where(Projection.run_id == run.id, Projection.player_id == player_id,
                                            Projection.kind == kind)).first() if run else None
    if not p:
        raise HTTPException(404, "No projection for that player and market in the current run")
    return p


@app.get("/api/players/{player_id}/lines", response_model=LadderOut)
def player_lines(player_id: str, kind: Kind, odds_range: int = Query(300, ge=0, le=100000), db: Session = Depends(get_db)):
    """Every posted quote (main and alternate lines, all books) for one player/market, priced by the model.
    Prices outside -odds_range..+odds_range are hidden (default 300; 0 shows everything)."""
    return build_ladder_out(db, _player_proj(db, player_id, kind), odds_range)


def build_ladder_out(db: Session, p: Projection, odds_range: int = 0) -> LadderOut:
    key, kind = odds.norm(p.name), p.kind
    main = current_lines(db)
    main = main[(main.market == kind) & (main.player.map(odds.norm) == key)].assign(alt=False)
    alts = db.scalars(select(AltLine).where(AltLine.game_id == p.game_id, AltLine.market == kind)).all()
    alt_df = pd.DataFrame([dict(player=r.player, market=r.market, line=r.line, over_odds=r.over_odds,
                                under_odds=r.under_odds, book=r.book, over_link=r.over_link, under_link=r.under_link,
                                event_link=r.event_link, alt=True) for r in alts if odds.norm(r.player) == key],
                          columns=list(main.columns))
    quotes = pd.concat([f for f in (main, alt_df) if not f.empty] or [main], ignore_index=True)
    fetched = max((r.fetched_at for r in alts), default=None)
    return LadderOut(kind=kind, mu=p.mu, sd=p.sd, game_id=p.game_id, alt_fetched_at=fetched.isoformat() if fetched else None,
                     quotes=build_ladder(p.mu, p.sd, quotes, odds_range, kind))


@app.post("/api/players/{player_id}/alt-lines", response_model=AltFetchResult)
def fetch_alt_lines(player_id: str, db: Session = Depends(get_db)):
    """Fetch alternate lines (and betslip links) for this player's game. Costs 2 API credits per market the
    player has a projection in."""
    run = latest_run(db)
    rows = db.scalars(select(Projection).where(Projection.run_id == run.id, Projection.player_id == player_id)).all() if run else []
    if not rows:
        raise HTTPException(404, "Player has no projection in the current run")
    if not config.ODDS_API_KEY():
        raise HTTPException(400, "No ODDS_API_KEY configured")
    kinds = sorted({r.kind for r in rows})
    try:
        res = pipeline.fetch_game_lines(rows[0].game_id, kinds)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # upstream API failure
        raise HTTPException(502, f"Odds API error: {e}")
    _pick_cache.clear()
    return AltFetchResult(kinds=kinds, **res)


_LOG_COLUMNS = ["player_id", "season", "week", "season_type", "position", "team", "opponent_team", "rushing_yards",
                "receiving_yards", "passing_yards", "carries", "targets", "attempts", "rushing_tds", "receiving_tds"]


@lru_cache(maxsize=1)
def _stats(season: int) -> pd.DataFrame:
    return model.prep(data.load_stats([season - 1, season], usecols=_LOG_COLUMNS))


def _game_logs(player_id: str, kinds: list[str], season: int, n: int = 12) -> dict:
    st = _stats(season)
    g = st[st.player_id == player_id].sort_values("t").tail(n)
    out = {}
    for kind in kinds:
        if kind == "td":  # touchdowns scored per game (rushing + receiving) against touches
            yards, vol = g.rushing_tds.fillna(0) + g.receiving_tds.fillna(0), g.carries.fillna(0) + g.targets.fillna(0)
        elif kind == "rr":
            yards, vol = g.rushing_yards.fillna(0) + g.receiving_yards.fillna(0), g.carries.fillna(0) + g.targets.fillna(0)
        else:
            c = model.CFG[kind]
            yards, vol = g[c["yds"]], g[c["vol"]]
        out[kind] = [GameLogEntry(label=f"{int(s)} W{int(w)}", opp=o, yards=float(y), volume=float(v))
                     for s, w, o, y, v in zip(g.season, g.week, g.opponent_team, yards, vol)]
    return out


@app.post("/api/refresh", response_model=JobStatus, status_code=202)
def refresh(req: RefreshRequest, bg: BackgroundTasks):
    with _lock:
        if _job["state"] == "running":
            raise HTTPException(409, "A refresh is already running")
        _job.update(state="running", started_at=datetime.utcnow().isoformat(), finished_at=None, log=[], error=None)
    bg.add_task(_run_job, req.odds)
    return JobStatus(**_job)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/api/refresh/status", response_model=JobStatus)
def refresh_status():
    return JobStatus(**_job)


# ---------- serve the built React app in production ----------
if os.path.isdir(config.FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(config.FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = os.path.join(config.FRONTEND_DIST, path)
        return FileResponse(f if path and os.path.isfile(f) else os.path.join(config.FRONTEND_DIST, "index.html"))
