"""FastAPI app: JSON API for projections, priced picks and data refresh (+ serves the built React app)."""
import hmac
import os
import time
from urllib.parse import unquote
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Literal, Optional

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

from . import config, grading, pipeline, scheduler
from .db import AltLine, OddsLine, Projection, Run, SessionLocal, SyncRun, current_lines, proj_frame
from .engine import data, model, odds
from .engine import injuries as injm
from .engine import moneyline as mlm
from .engine import td as tdm
from .engine.ladder import build_ladder
from .engine.picks import build_picks
from .engine.search import rank_hits
from .nba import routes as nba_routes
from .schemas import (AdminState, Correlations, GradeReport, AltFetchResult, AutoSync, CreditStatus, KeyBalance, SlotOut, SyncRunDetail, SyncRunOut, SyncPlan, GameLogEntry, InjuryReport, LadderOut, Game, JobStatus, Kind, Meta, MoneylineGame, OddsInfo, PickOut, PlayerDetail, PlayerHit, ProjectionOut,
                      RefreshRequest, RunInfo)

@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as s:
        n = pipeline.seed_odds_from_csv(CSV_SEED, s)
        if n:
            print(f"Seeded {n} odds lines from {CSV_SEED}")
    n = scheduler.mark_interrupted()
    if n:
        print(f"Marked {n} sync run(s) a restart cut off as interrupted")
    scheduler.after_job = _release_memory
    if scheduler.start():
        print("Scheduled syncs are on (AUTO_SYNC)")
    yield
    scheduler.stop()


app = FastAPI(title="NFL Prop Predictor", version="1.0", lifespan=lifespan)
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


# Failed password guesses per client, to slow brute-forcing of a human-chosen admin password.
_FAILS: dict[str, list[float]] = {}
MAX_FAILS, FAIL_WINDOW = 5, 60.0  # more than this many wrong guesses in a minute are refused with 429


def client_key(request: Request) -> str:
    """Who is asking. Behind a host's proxy the real client is the last X-Forwarded-For entry (the one the proxy added)."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "")


def check_admin(request: Request) -> str:
    """'ok' (may change data / spend API credits), 'no', or 'throttled' (too many wrong guesses lately).

    Allowed from this machine, or with the admin password sent as a Bearer token. The right password always
    works, so a stranger's guesses can never lock the owner out; only wrong guesses are slowed.
    """
    host = request.client.host if request.client else ""
    if host in LOCAL_HOSTS:
        return "ok"
    password = config.ADMIN_TOKEN()
    given = request.headers.get("authorization", "")
    if not (password and given.startswith("Bearer ")):
        return "no"
    if hmac.compare_digest(unquote(given[7:]).encode(), password.encode()):
        return "ok"
    key, now = client_key(request), time.time()
    recent = [t for t in _FAILS.get(key, []) if now - t < FAIL_WINDOW]
    _FAILS[key] = recent + [now]
    return "throttled" if len(recent) >= MAX_FAILS else "no"


def is_admin(request: Request) -> bool:
    return check_admin(request) == "ok"


@app.middleware("http")
async def admin_writes_only(request: Request, call_next):
    """The app can be served beyond this machine (LAN, Tailscale, a host). Writes are POSTs, and those
    (refreshes, alt-line fetches) spend API credits, so they need to come from here or carry the admin token."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        verdict = check_admin(request)
        if verdict == "throttled":
            return JSONResponse({"detail": "Too many wrong passwords. Wait a minute."}, status_code=429)
        if verdict != "ok":
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


def game_label(gid: str) -> str:
    _, _, away, home = gid.split("_", 3)
    return f"{away} @ {home}"


_pick_cache: dict = {}


_dists = grading.dists


def all_picks(db: Session, run: Run, w: float, book: Optional[str] = None) -> pd.DataFrame:
    """Priced picks for (run, current odds, market weight); memoized because pricing loops over every line."""
    version = tuple(sorted(db.execute(select(OddsLine.market, func.max(OddsLine.fetched_at))
                                      .group_by(OddsLine.market)).all()))
    key = (run.id, version, round(w, 3), book)
    if key not in _pick_cache:
        if len(_pick_cache) > 20:
            _pick_cache.clear()
        proj = proj_frame(db, run.id)
        picks = build_picks(proj, current_lines(db), w, only_book=book, dists=_dists(run))
        if not picks.empty:
            l5 = dict(zip(zip(proj.player_id, proj.kind), proj.last5))
            picks["last5"] = [l5.get(k, []) for k in zip(picks.player_id, picks.kind)]
        else:
            picks["last5"] = []
        _pick_cache[key] = picks
    return _pick_cache[key]


def records(df: pd.DataFrame) -> list[dict]:
    return df.replace({np.nan: None}).to_dict("records")


# ---------- job runner (app/scheduler.py runs jobs; the same state object is shared here) ----------
_job = scheduler._job


def _release_memory():
    """Hand a finished job's memory back to the OS (matters on a 1 GB host) and drop caches the new data outdates."""
    import gc
    _injury_report.cache_clear()
    _stats.cache_clear()   # game logs in the player drawer come from the stats files, which a sync just refreshed
    _pick_cache.clear()
    nba_routes.clear_caches()
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass  # not glibc (e.g. macOS): nothing to trim


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
        weather = run.weather or {}
        games = [Game(game_id=g, label=game_label(g), gameday=d, gametime=t, weather=weather.get(g))
                 for g, d, t in sorted(rows, key=lambda r: (r[1], r[2], r[0]))]
        backtest = run.backtest
    return Meta(redistribution=(run.variance or {}).get("_redistribution") if run else None,
                weather=(run.variance or {}).get("_weather") if run else None,
                calibration=(run.variance or {}).get("_calibration") if run else None,
                run=None if not run else RunInfo(id=run.id, season=run.season, week=run.week,
                                                  created_at=run.created_at.isoformat(), excluded=run.excluded),
                backtest=backtest, odds=_odds_info(db), games=games, has_odds_key=bool(config.ODDS_API_KEY()),
                job=JobStatus(**_job), lan_url=lan_url, auto_sync=_auto_sync(),
                books=sorted(b for (b,) in db.execute(select(OddsLine.book).distinct()).all()))


def _lan_url(request: Request) -> Optional[str]:
    if os.environ.get("APP_URL"):  # e.g. a Tailscale MagicDNS name: http://my-mac.tailnet-name.ts.net:8000
        return os.environ["APP_URL"].rstrip("/")
    ip = lan_ip()
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    return f"{request.url.scheme}://{ip}:{port}" if ip else None


def _odds_info(db: Session) -> dict:
    """Per market: when its newest quotes were fetched and how many quotes are current (across all games)."""
    fetched = {m: t for m, t in db.execute(select(OddsLine.market, func.max(OddsLine.fetched_at)).group_by(OddsLine.market)).all()}
    counts = current_lines(db).groupby("market").size().to_dict()
    return {m: OddsInfo(fetched_at=t.isoformat(), lines=int(counts.get(m, 0))) for m, t in fetched.items()}


def _excluded(kind: str) -> tuple:
    """exclude_kind=td leaves out every touchdown market (anytime and first TD): the "all over/unders" views."""
    return tdm.YES_NO if kind == "td" else (kind,)


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
        stmt = stmt.where(Projection.kind.not_in(_excluded(exclude_kind)))
    if game_id:
        stmt = stmt.where(Projection.game_id == game_id)
    if q:
        stmt = stmt.where(Projection.name.ilike(f"%{q}%"))
    return db.scalars(stmt).all()


@app.get("/api/picks", response_model=list[PickOut])
def picks(kind: Optional[Kind] = None, exclude_kind: Optional[Kind] = None, side: Optional[Literal["Over", "Under"]] = None,
          game_id: Optional[str] = None, q: Optional[str] = None, book: Optional[str] = None,
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
        df = df[~df.kind.isin(_excluded(exclude_kind))]
    if side:
        df = df[df.side == side]
    if game_id:
        df = df[df.game_id == game_id]
    if q:
        df = df[df.name.str.contains(q, case=False, regex=False)]
    return records(df.head(limit))


@app.get("/api/correlations", response_model=Correlations)
def correlations(db: Session = Depends(get_db)):
    """The latest run's same-game correlations, for pricing parlays whose legs share a game."""
    return build_correlations(latest_run(db))


def build_correlations(run: Optional[Run]) -> Correlations:
    c = ((run.variance or {}).get("_correlation") if run else None) or {}
    return Correlations(pairs={k: v[0] for k, v in (c.get("pairs") or {}).items()}, check=c.get("check") or {})


@app.get("/api/grades", response_model=GradeReport)
def grades(season: Optional[int] = None, db: Session = Depends(get_db)):
    """How the logged board did against the box scores, and whether the model or the line landed closer."""
    return grading.report(db, season)


@app.get("/api/moneylines", response_model=list[MoneylineGame])
def moneylines(book: Optional[str] = None, market_weight: float = Query(0.35, ge=0, le=1), db: Session = Depends(get_db)):
    """Both teams' win chances for every game of the week (model, market, blend), with the best moneyline and its EV."""
    run = latest_run(db)
    return build_moneylines(db, run, market_weight, book)


def build_moneylines(db: Session, run: Optional[Run], market_weight: float = 0.35, book: Optional[str] = None) -> list[dict]:
    if not run or not run.teams:
        return []
    return mlm.price(run.teams, current_lines(db), market_weight, book)


@app.get("/api/injuries", response_model=InjuryReport)
def injuries(db: Session = Depends(get_db)):
    """This week's injury report for every team on the slate, both sides of the ball, plus reserve lists (IR, PUP)."""
    return build_injuries(db, latest_run(db))


def build_injuries(db: Session, run: Optional[Run]) -> InjuryReport:
    if not run:
        return InjuryReport()
    games = [g for (g,) in db.execute(select(Projection.game_id).where(Projection.run_id == run.id).distinct())]
    teams = {t for g in games for t in g.split("_")[2:4]}
    order = {"pass": 0, "rush": 1, "rec": 2, "recs": 3, "rr": 4, "td": 5, "ptd": 6, "lng": 7, "rlng": 8, "ftd": 9}
    props = {}
    for pid, kind in db.execute(select(Projection.player_id, Projection.kind).where(Projection.run_id == run.id)):
        if pid not in props or order.get(kind, 9) < order.get(props[pid], 9):
            props[pid] = kind
    # nflverse's file is re-fetched at most hourly, ESPN's feed every 15 minutes
    rep, news_fetched = _injury_report(run.season, run.week, int(time.time() // 900))
    path = os.path.join(data.CACHE, f"injuries_{run.season}.csv")
    fetched = datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat() if os.path.exists(path) else None
    out = {t: [dict(p, kind=props.get(p["player_id"])) for p in ps] for t, ps in rep["teams"].items() if t in teams}
    return InjuryReport(season=run.season, week=run.week, report_week=rep["report_week"], fetched_at=fetched,
                        news_fetched_at=news_fetched, teams=out)


@lru_cache(maxsize=2)
def _injury_report(season: int, week: int, _slot: int) -> tuple[dict, Optional[str]]:
    try:
        espn, news_fetched = data.load_espn_injuries()
    except Exception:   # ESPN only adds detail: the nflverse report stands on its own
        espn, news_fetched = None, None
    rep = injm.build(data.load_injuries(season), data.load_reserve(season), week,
                     espn=espn, espn_ids=data.load_espn_ids(season) if espn is not None else None)
    return rep, news_fetched


@app.get("/api/player-search", response_model=list[PlayerHit])
def player_search(q: str = Query("", max_length=60), limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    """Active offensive players whose name matches q: this week's projected players plus everyone else on a roster
    (on bye, or not projected), names starting with q first, projected players before the rest."""
    run = latest_run(db)
    if not run or not q.strip():
        return []
    shots = data.load_headshots(run.season)
    hits = {pid: dict(player_id=pid, name=n, pos=pos, team=t, headshot=shots.get(pid), projected=True)
            for pid, n, pos, t in db.execute(select(Projection.player_id, Projection.name, Projection.pos, Projection.team)
                                             .where(Projection.run_id == run.id).distinct())}
    for r in data.load_active_players(run.season).to_dict("records"):
        hits.setdefault(r["player_id"], dict(r, projected=False))
    return rank_hits(list(hits.values()), q, limit)


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
                        headshot=data.load_headshots(run.season).get(player_id),
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
    main = main[(main.market == kind) & (main.player.map(odds.norm) == key) & (main.game_id == p.game_id)].assign(alt=False)
    alts = db.scalars(select(AltLine).where(AltLine.game_id == p.game_id, AltLine.market == kind)).all()
    alt_df = pd.DataFrame([dict(player=r.player, market=r.market, line=r.line, over_odds=r.over_odds,
                                under_odds=r.under_odds, book=r.book, over_link=r.over_link, under_link=r.under_link,
                                event_link=r.event_link, alt=True) for r in alts if odds.norm(r.player) == key],
                          columns=list(main.columns))
    quotes = pd.concat([f for f in (main, alt_df) if not f.empty] or [main], ignore_index=True)
    fetched = max((r.fetched_at for r in alts), default=None)
    return LadderOut(kind=kind, mu=p.mu, sd=p.sd, game_id=p.game_id, alt_fetched_at=fetched.isoformat() if fetched else None,
                     # thin-history projections aren't priced (model.THIN_GAMES), so they get no ladder
                     quotes=[] if p.thin else build_ladder(p.mu, p.sd, quotes, odds_range, kind, _dists(db.get(Run, p.run_id)).get(kind)))


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
                "receiving_yards", "passing_yards", "receptions", "carries", "targets", "attempts", "rushing_tds", "receiving_tds", "passing_tds"]


@lru_cache(maxsize=1)
def _stats(season: int) -> pd.DataFrame:
    st = model.prep(data.load_stats([season - 1, season], usecols=_LOG_COLUMNS))
    try:   # longest catch and carry, and the first TD, come from play-by-play; without it those logs are left out
        seasons = [season - 1, season]
        st = model.add_longest(st, data.load_catches(seasons), data.load_rushes(seasons))
        st = model.add_first_td(st, data.load_first_tds(seasons))
    except Exception:
        pass
    return st


def _game_logs(player_id: str, kinds: list[str], season: int, n: int = 12) -> dict:
    st = _stats(season)
    g = st[st.player_id == player_id].sort_values("t").tail(n)
    out = {}
    for kind in kinds:
        if kind == "td":  # touchdowns scored per game (rushing + receiving) against touches
            yards, vol = g.rushing_tds.fillna(0) + g.receiving_tds.fillna(0), g.carries.fillna(0) + g.targets.fillna(0)
        elif kind == "rr":
            yards, vol = g.rushing_yards.fillna(0) + g.receiving_yards.fillna(0), g.carries.fillna(0) + g.targets.fillna(0)
        elif kind == "ftd":   # scored the game's first touchdown (1/0) against touches
            if "first_td" not in g:
                continue
            yards, vol = g.first_td, g.carries.fillna(0) + g.targets.fillna(0)
        elif kind in model.LONG_COLS:   # longest catch against catches, longest rush against carries
            if model.LONG_COLS[kind] not in g:
                continue
            yards, vol = g[model.LONG_COLS[kind]], (g.receptions if kind == "lng" else g.carries).fillna(0)
        else:
            c = model.CFG[kind]
            yards, vol = g[c["yds"]], g[c["vol"]]
        out[kind] = [GameLogEntry(label=f"{int(s)} W{int(w)}", opp=o, yards=float(y), volume=float(v))
                     for s, w, o, y, v in zip(g.season, g.week, g.opponent_team, yards, vol)]
    return out


@app.post("/api/refresh", response_model=JobStatus, status_code=202)
def refresh(req: RefreshRequest, bg: BackgroundTasks):
    if not scheduler.claim():
        raise HTTPException(409, "A refresh is already running")
    bg.add_task(scheduler.run, req.odds, req.full)
    return JobStatus(**_job)


@app.get("/api/refresh/plan", response_model=SyncPlan)
def refresh_plan(request: Request, odds: Literal["none", "missing", "thin", "today", "all"] = "missing", full: bool = False):
    """What a sync would do right now, and what it would cost: for the confirm step in the admin UI."""
    if not is_admin(request):
        raise HTTPException(403, "Admin only")
    games = pipeline.upcoming_games()
    if odds == "none":
        plan = dict(total_games=len(games), games=[], credits=0)
    else:
        with SessionLocal() as s:
            plan = pipeline.sync_plan(s, games, odds)
    if len(games):
        plan["season"], plan["week"] = int(games.iloc[0].season), int(games.iloc[0].week)
    with SessionLocal() as s:
        run = latest_run(s)
        cal = (run.variance or {}).get("_calibration") if run else None
    season = plan.get("season")
    will_recalibrate = bool(full) or season is None or pipeline.reusable_calibration(season) is None
    return SyncPlan(**plan, will_run_projections=config.PROJECTIONS_ON_SERVER(), has_odds_key=bool(config.ODDS_API_KEY()),
                    will_recalibrate=will_recalibrate, calibration=cal)


def _auto_sync(league: Optional[str] = "nfl") -> AutoSync:
    """The next scheduled sync of one league (None: of either)."""
    if not config.AUTO_SYNC():
        return AutoSync(enabled=False)
    at, slot = scheduler.upcoming(league=league)[0]
    return AutoSync(enabled=True, next_at=at.isoformat(), next_label=slot.label)


nba_routes.is_admin = lambda request: is_admin(request)
nba_routes.auto_sync = lambda: _auto_sync("nba")
app.include_router(nba_routes.router)


# ---------- admin page: the schedule, the run log, the key's credits ----------
def require_admin(request: Request):
    verdict = check_admin(request)
    if verdict == "throttled":
        raise HTTPException(429, "Too many wrong passwords. Wait a minute.")
    if verdict != "ok":
        raise HTTPException(403, "Admin only")


_credits: dict = {}   # key -> (checked_at, remaining or error): the admin page polls, the balance changes slowly


def _credit_status(league: str = "nfl") -> CreditStatus:
    """The key syncs are spending (the first one over the floor, app/odds_keys.py) and the ones to rotate."""
    keys, floor = config.odds_keys(league), config.ODDS_CREDIT_FLOOR()
    if not keys:
        return CreditStatus(floor=floor, error=f"No {'ODDS_API_KEY_NBA' if league == 'nba' else 'ODDS_API_KEY'} set")
    now = time.time()
    for _, key in keys:
        if key not in _credits or now - _credits[key][0] > 60 or _job["state"] == "running":
            try:
                _credits[key] = (now, odds.credits_remaining(key), None)
            except Exception as e:
                _credits[key] = (now, None, f"Couldn't check the balance: {e}")
    spent = [name for name, key in keys if _credits[key][1] is not None and _credits[key][1] <= floor]
    name, key = next(((n, k) for n, k in keys if n not in spent), keys[-1])
    checked, left, err = _credits[key]
    others = [KeyBalance(key_name=n, key_hint=k[-4:], remaining=_credits[k][1], error=_credits[k][2]) for n, k in keys if n != name]
    return CreditStatus(remaining=left, floor=floor, key_hint=key[-4:], key_name=name, error=err, rotate=spent, others=others,
                        low=len(spent) == len(keys), checked_at=datetime.utcfromtimestamp(checked).isoformat())


def _run_out(r: SyncRun) -> dict:
    return dict(id=r.id, slot=r.slot, label=scheduler.BY_ID[r.slot].label if r.slot in scheduler.BY_ID else "Manual sync",
                trigger=r.trigger, scheduled_for=r.scheduled_for.isoformat() if r.scheduled_for else None,
                started_at=r.started_at.isoformat(), finished_at=r.finished_at.isoformat() if r.finished_at else None,
                status=r.status, odds_mode=r.odds_mode, full=r.full, season=r.season, week=r.week,
                games_fetched=r.games_fetched, credits_before=r.credits_before, credits_after=r.credits_after,
                summary=r.summary, error=r.error)


@app.get("/api/admin", response_model=AdminState, dependencies=[Depends(require_admin)])
def admin_state(limit: int = Query(60, ge=1, le=500), db: Session = Depends(get_db)):
    runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)).all()
    last = {}
    for r in runs:
        last.setdefault(r.slot, r)
    slots = [SlotOut(id=s.id, label=s.label, league=s.league, when=scheduler.describe(s), odds_mode=s.odds, full=s.full, why=s.why,
                     next_at=at.isoformat(), last_run=SyncRunOut(**_run_out(last[s.id])) if s.id in last else None)
             for at, s in scheduler.upcoming()]
    return AdminState(auto_sync=_auto_sync(None), timezone="America/New_York", credits=_credit_status(),
                      credits_nba=_credit_status("nba"), slots=slots,
                      runs=[SyncRunOut(**_run_out(r)) for r in runs], job=JobStatus(**_job),
                      can_run_projections=config.PROJECTIONS_ON_SERVER())


@app.get("/api/admin/runs/{run_id}", response_model=SyncRunDetail, dependencies=[Depends(require_admin)])
def admin_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(SyncRun, run_id)
    if not r:
        raise HTTPException(404, "No such run")
    return SyncRunDetail(**_run_out(r), log=r.log or [])


@app.post("/api/admin/run/{slot_id}", response_model=JobStatus, status_code=202)
def admin_run_now(slot_id: str, bg: BackgroundTasks):
    """Run one schedule slot right now (logged as a manual run of that slot)."""
    slot = scheduler.BY_ID.get(slot_id)
    if not slot:
        raise HTTPException(404, "No such schedule slot")
    if not scheduler.claim():
        raise HTTPException(409, "A sync is already running")
    bg.add_task(scheduler.run, slot.odds, slot.full, slot.id, "manual", None, slot.league)
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
