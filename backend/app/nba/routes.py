"""/api/nba/*: the NBA side of the app, in the same response shapes as the NFL routes so the UI can share components."""
import time
from datetime import datetime
from functools import lru_cache
from typing import Callable, Literal, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..db import NbaOddsLine, NbaProjection, NbaRun, SessionLocal, current_lines
from ..engine import moneyline as mlm
from ..engine import odds
from ..engine.ladder import build_ladder
from ..engine.picks import build_picks
from ..schemas import (AutoSync, BacktestStat, Game, GameLogEntry, InjuredPlayer, InjuryReport, LadderOut, MoneylineGame,
                       NbaMeta, NbaRunInfo, OddsInfo, PickOut, PlayerDetail, ProjectionOut)
from . import espn, model
from . import odds as nba_odds

NbaKind = Literal["pts", "reb", "ast", "threes"]
router = APIRouter(prefix="/api/nba", tags=["nba"])
# main.py sets these: who may see owner-only bits, and the next scheduled NBA sync
is_admin: Callable[[Request], bool] = lambda request: False
auto_sync: Callable[[], AutoSync] = lambda: AutoSync(enabled=False)


def get_db():
    with SessionLocal() as s:
        yield s


def latest_run(db: Session) -> Optional[NbaRun]:
    return db.scalars(select(NbaRun).order_by(NbaRun.id.desc()).limit(1)).first()


def _records(df: pd.DataFrame) -> list[dict]:
    return df.replace({np.nan: None}).to_dict("records")


def _label(gid: str) -> str:
    _, _, away, home = gid.split("_", 3)
    return f"{away} @ {home}"


def _upcoming(run: NbaRun, now: Optional[datetime] = None) -> list[dict]:
    """The run's games that haven't tipped off yet (a game in progress has no pregame prices worth showing)."""
    now = now or datetime.utcnow()
    return [g for g in run.games or [] if datetime.fromisoformat(g["start"].replace("Z", "+00:00")).replace(tzinfo=None) > now]


@router.get("/meta", response_model=NbaMeta)
def meta(request: Request, db: Session = Depends(get_db)):
    run = latest_run(db)
    games = [Game(game_id=g["game_id"], label=_label(g["game_id"]), gameday=g["gameday"], gametime=g["gametime"])
             for g in (_upcoming(run) if run else [])]
    fetched = dict(db.execute(select(NbaOddsLine.market, func.max(NbaOddsLine.fetched_at)).group_by(NbaOddsLine.market)).all())
    counts = current_lines(db, NbaOddsLine).groupby("market").size().to_dict()
    return NbaMeta(
        run=None if not run else NbaRunInfo(id=run.id, season=run.season, slate=run.slate or [],
                                            created_at=run.created_at.isoformat(), excluded=run.excluded or []),
        backtest={k: BacktestStat(**v) for k, v in (run.backtest or {}).items()} if run else {},
        odds={m: OddsInfo(fetched_at=t.isoformat(), lines=int(counts.get(m, 0))) for m, t in fetched.items()},
        games=games, has_odds_key=bool(config.ODDS_API_KEY_NBA()), auto_sync=auto_sync(), can_write=is_admin(request),
        books=sorted(b for (b,) in db.execute(select(NbaOddsLine.book).distinct()).all()))


def _proj_frame(db: Session, run_id: int) -> pd.DataFrame:
    rows = db.scalars(select(NbaProjection).where(NbaProjection.run_id == run_id)).all()
    return pd.DataFrame([{c.name: getattr(r, c.name) for c in NbaProjection.__table__.columns} for r in rows])


def _dists(run: NbaRun) -> dict:
    return {k: v for k, v in (run.variance or {}).items() if isinstance(v, dict) and not k.startswith("_")}


_pick_cache: dict = {}


def all_picks(db: Session, run: NbaRun, w: float, book: Optional[str] = None) -> pd.DataFrame:
    version = tuple(sorted(db.execute(select(NbaOddsLine.market, func.max(NbaOddsLine.fetched_at)).group_by(NbaOddsLine.market)).all()))
    live = frozenset(g["game_id"] for g in _upcoming(run))   # a game that tips off leaves the board
    key = (run.id, version, round(w, 3), book, live)
    if key not in _pick_cache:
        if len(_pick_cache) > 20:
            _pick_cache.clear()
        proj = _proj_frame(db, run.id)
        picks = build_picks(proj, current_lines(db, NbaOddsLine), w, only_book=book, dists=_dists(run))
        if not picks.empty:
            l5 = dict(zip(zip(proj.player_id, proj.kind), proj.last5))
            picks["last5"] = [l5.get(k, []) for k in zip(picks.player_id, picks.kind)]
            picks = picks[picks.game_id.isin(live)]
        else:
            picks["last5"] = []
        _pick_cache[key] = picks
    return _pick_cache[key]


@router.get("/projections", response_model=list[ProjectionOut])
def projections(kind: Optional[NbaKind] = None, game_id: Optional[str] = None, q: Optional[str] = None,
                db: Session = Depends(get_db)):
    run = latest_run(db)
    if not run:
        return []
    live = [g["game_id"] for g in _upcoming(run)]
    stmt = select(NbaProjection).where(NbaProjection.run_id == run.id, NbaProjection.game_id.in_(live)).order_by(NbaProjection.mu.desc())
    if kind:
        stmt = stmt.where(NbaProjection.kind == kind)
    if game_id:
        stmt = stmt.where(NbaProjection.game_id == game_id)
    if q:
        stmt = stmt.where(NbaProjection.name.ilike(f"%{q}%"))
    return db.scalars(stmt).all()


@router.get("/picks", response_model=list[PickOut])
def picks(kind: Optional[NbaKind] = None, side: Optional[Literal["Over", "Under"]] = None, game_id: Optional[str] = None,
          q: Optional[str] = None, book: Optional[str] = None, min_ev: float = Query(0.03, ge=-1, le=1),
          market_weight: float = Query(0.35, ge=0, le=1), include_flagged: bool = False,
          limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
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
    if side:
        df = df[df.side == side]
    if game_id:
        df = df[df.game_id == game_id]
    if q:
        df = df[df.name.str.contains(q, case=False, regex=False)]
    return _records(df.head(limit))


@router.get("/moneylines", response_model=list[MoneylineGame])
def moneylines(book: Optional[str] = None, market_weight: float = Query(0.35, ge=0, le=1), db: Session = Depends(get_db)):
    """Both teams' win chances for every slate game still to tip off (model, market, blend) and the best moneyline."""
    run = latest_run(db)
    if not run or not run.teams:
        return []
    live = {g["game_id"] for g in _upcoming(run)}
    games = {gid: g for gid, g in run.teams.items() if gid in live}
    return mlm.price(games, current_lines(db, NbaOddsLine), market_weight, book, names=nba_odds.TEAM_NAMES,
                     min_market_weight=model.ML_MIN_MARKET_WEIGHT)


@router.get("/injuries", response_model=InjuryReport)
def injuries(db: Session = Depends(get_db)):
    """ESPN's injury report for every team on the slate (re-read at most every 15 minutes)."""
    run = latest_run(db)
    if not run:
        return InjuryReport()
    teams = {t for g in run.games or [] for t in (g["home"], g["away"])}
    props = {pid: kind for pid, kind in db.execute(select(NbaProjection.player_id, NbaProjection.kind)
                                                   .where(NbaProjection.run_id == run.id, NbaProjection.kind == "pts"))}
    rows, fetched = _injuries(int(time.time() // 900))
    out: dict = {}
    for r in rows:
        if r["team"] not in teams:
            continue
        out.setdefault(r["team"], []).append(InjuredPlayer(
            player_id=r["player_id"] or r["name"], name=r["name"], pos=r["pos"], team=r["team"], side="off",
            status=r["status"], injury=r["injury"], practice="", rest=False, kind=props.get(r["player_id"]),
            comment=r["comment"], return_date=r["return_date"], updated=r["updated"]))
    order = {"Out": 0, "Suspension": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 2, "Probable": 3}
    for players in out.values():
        players.sort(key=lambda p: (order.get(p.status, 4), p.name))
    return InjuryReport(season=run.season, fetched_at=fetched, teams=out)


@lru_cache(maxsize=2)
def _injuries(_slot: int):
    return espn.injuries()


@router.get("/players/{player_id}", response_model=PlayerDetail)
def player(player_id: str, market_weight: float = Query(0.35, ge=0, le=1), db: Session = Depends(get_db)):
    run = latest_run(db)
    rows = db.scalars(select(NbaProjection).where(NbaProjection.run_id == run.id, NbaProjection.player_id == player_id)).all() if run else []
    if not rows:
        raise HTTPException(404, "Player has no projection in the current run")
    p = rows[0]
    df = all_picks(db, run, market_weight)
    pp = df[df.player_id == player_id] if not df.empty else df
    return PlayerDetail(player_id=player_id, name=p.name, pos=p.pos, team=p.team,
                        headshot=f"https://a.espncdn.com/i/headshots/nba/players/full/{player_id}.png",
                        projections=[ProjectionOut.model_validate(r, from_attributes=True) for r in rows],
                        picks=_records(pp), logs=_game_logs(player_id, run.season))


def _game_logs(player_id: str, season: int, n: int = 12) -> dict:
    """The player's last n games per stat (value, with minutes as the volume), from the cached ESPN logs."""
    logs = espn.gamelogs([player_id], [season - 1, season], season, log=lambda _: None).tail(n)
    label = lambda d: datetime.fromisoformat(d).strftime("%b %-d")  # noqa: E731
    return {k: [GameLogEntry(label=label(r.date), opp=r.opp or "", yards=float(getattr(r, k)), volume=float(r.min))
                for r in logs.itertuples()] for k in model.KINDS}


@router.get("/players/{player_id}/lines", response_model=LadderOut)
def player_lines(player_id: str, kind: NbaKind, odds_range: int = Query(300, ge=0, le=100000), db: Session = Depends(get_db)):
    """Every posted quote for one player and stat, all books, priced by the model (no alternates for the NBA yet)."""
    run = latest_run(db)
    p = db.scalars(select(NbaProjection).where(NbaProjection.run_id == run.id, NbaProjection.player_id == player_id,
                                               NbaProjection.kind == kind)).first() if run else None
    if not p:
        raise HTTPException(404, "No projection for that player and stat in the current run")
    main = current_lines(db, NbaOddsLine)
    key = odds.norm(p.name)
    main = main[(main.market == kind) & (main.player.map(odds.norm) == key) & (main.game_id == p.game_id)].assign(alt=False)
    return LadderOut(kind=kind, mu=p.mu, sd=p.sd, game_id=p.game_id, alt_fetched_at=None,
                     quotes=build_ladder(p.mu, p.sd, main, odds_range, kind, _dists(run).get(kind)))


def clear_caches():
    _pick_cache.clear()
    _injuries.cache_clear()
