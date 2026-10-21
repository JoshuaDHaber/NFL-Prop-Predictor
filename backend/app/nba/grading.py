"""Grading the NBA board, as app/grading.py does the NFL's: every NBA sync snapshots the priced picks for slate games
still to tip off (the last snapshot before a game is the one graded), and each NBA model run grades finished games
from the ESPN game logs it has just loaded.

A game is graded once both teams' box scores are in the logs. A player with no row for the game didn't play (void, as
the books settle it), but only once he has played again or two days have passed: a failed or stale gamelog fetch
would otherwise read as a DNP.
"""
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import pandas as pd
from sqlalchemy import select

from ..db import NbaOddsLine, NbaPickLog, NbaRun, current_lines
from ..engine.picks import build_picks
from ..grading import MARKET_WEIGHT, outcome
from ..grading import report as _report
from . import espn, model

VOID_AFTER_DAYS = 2      # a player missing from a graded game's box score is void after this many days
STALE_AFTER_DAYS = 7     # a game whose box score never shows up (postponed) is voided after this long


def _tipoff(g: dict) -> datetime:
    return datetime.fromisoformat(g["start"].replace("Z", "+00:00")).replace(tzinfo=None)


def snapshot_board(session, now: Optional[datetime] = None) -> int:
    """Price the latest NBA run against the current lines and store every pick for games not yet tipped off,
    replacing that game's earlier snapshot of the same player/market/side. Returns how many picks were stored."""
    from .routes import _dists, _proj_frame   # routes imports this module
    now = now or datetime.utcnow()
    run = session.scalars(select(NbaRun).order_by(NbaRun.id.desc()).limit(1)).first()
    if not run:
        return 0
    live = {g["game_id"] for g in run.games or [] if _tipoff(g) > now}
    proj = _proj_frame(session, run.id)
    if proj.empty or not live:
        return 0
    picks = build_picks(proj, current_lines(session, NbaOddsLine), MARKET_WEIGHT, dists=_dists(run))
    if picks.empty:
        return 0
    picks = picks[picks.game_id.isin(live)]
    if picks.empty:
        return 0
    existing = {(r.game_id, r.player_id, r.kind, r.side): r for r in session.scalars(
        select(NbaPickLog).where(NbaPickLog.game_id.in_(set(picks.game_id))))}
    for p in picks.itertuples():
        row = existing.get((p.game_id, p.player_id, p.kind, p.side))
        if row is None:
            row = NbaPickLog(game_id=p.game_id, player_id=p.player_id, kind=p.kind, side=p.side)
            session.add(row)
        row.season = run.season
        row.gameday, row.gametime, row.name, row.pos, row.team = str(p.gameday), str(p.gametime), p.name, p.pos, p.team
        row.line, row.odds, row.book = float(p.line), int(p.odds), p.book
        row.mu, row.prob, row.p_model, row.p_mkt, row.ev = (float(x) for x in (p.mu, p.prob, p.p_model, p.p_mkt, p.ev))
        row.flagged, row.run_id, row.snapped_at = bool(p.flagged), run.id, now
    session.commit()
    return len(picks)


def grade(session, logs: pd.DataFrame, today: date, fetch: Callable = espn.gamelogs, now: Optional[datetime] = None) -> int:
    """Grade logged picks from games before today (Eastern) against the ESPN game logs. Players with picks who have
    left every roster since (so aren't in logs) are fetched on their own. Returns how many picks were graded."""
    now = now or datetime.utcnow()
    todo = session.scalars(select(NbaPickLog).where(NbaPickLog.result.is_(None), NbaPickLog.gameday < today.isoformat())).all()
    if not todo:
        return 0
    missing = sorted({r.player_id for r in todo} - set(logs.player_id))
    if missing:
        seasons = sorted({r.season for r in todo})
        extra = fetch(missing, seasons, max(seasons), log=lambda _: None)
        logs = pd.concat([logs, extra], ignore_index=True) if not extra.empty else logs
    have = set(zip(logs.date, logs.team))
    by_player = {(r.player_id, r.date): r for r in logs.itertuples()}
    last_game = logs.groupby("player_id").date.max().to_dict() if not logs.empty else {}
    n = 0
    for row in todo:
        _, _, away, home = row.game_id.split("_", 3)
        age = (today - date.fromisoformat(row.gameday)).days
        if not {(row.gameday, away), (row.gameday, home)} <= have:
            if age < STALE_AFTER_DAYS:
                continue   # the box score isn't in the logs yet
            row.actual = None
        else:
            st = by_player.get((row.player_id, row.gameday))
            if st is None and last_game.get(row.player_id, "") <= row.gameday and age < VOID_AFTER_DAYS:
                continue   # no row yet, and nothing newer to show his log is current
            v = None if st is None or not st.min else model.actual(st, row.kind)
            row.actual = None if v is None or pd.isna(v) else float(v)
        row.result, row.graded_at = outcome(row.side, row.line, row.actual), now
        n += 1
    session.commit()
    return n


def grade_logged(session, logs: pd.DataFrame, today: date, log: Callable[[str], None] = print) -> None:
    """grade(), for the model run: a grading problem is logged and never stops the run."""
    try:
        n = grade(session, logs, today)
        if n:
            log(f"Graded {n} logged NBA picks against the box scores")
    except Exception as e:   # noqa: BLE001
        session.rollback()
        log(f"  couldn't grade logged NBA picks ({type(e).__name__}: {e})")


def _week(r) -> tuple:
    """Monday-to-Sunday weeks, labeled by their Monday."""
    d = date.fromisoformat(r.gameday)
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat(), f"Week of {monday:%b} {monday.day}"


def report(session, season: Optional[int] = None) -> dict:
    out = _report(session, season, table=NbaPickLog, period=_week)
    q = select(NbaPickLog.gameday).where(NbaPickLog.result.is_not(None))
    if out["season"] is not None:
        q = q.where(NbaPickLog.season == out["season"])
    days = sorted({d for (d,) in session.execute(q)})
    out["dates"] = [days[0], days[-1]] if days else []
    return out
