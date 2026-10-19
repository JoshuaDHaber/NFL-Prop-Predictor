"""Grading the board: snapshot every pick before kickoff, then score it against the box score.

The backtest checks projections against results, but never against the sportsbook lines, so it can't say whether the
model beats the market or how much to trust it. This log can: each NFL sync snapshots the priced picks for games
still to kick off (the last snapshot before a game is the one graded), and each model run grades finished games from
nflverse's weekly stats, which it has just loaded anyway.
"""
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from .db import PickLog, Run, current_lines, proj_frame
from .engine.picks import build_picks

ET = ZoneInfo("America/New_York")
MARKET_WEIGHT = 0.35   # the board's default "trust the market" setting
BOARD_MIN_EV = 0.03    # the board's default Min EV: what a visitor sees without touching the sliders
# market -> stats column (rr and td are sums, below)
STAT = {"rush": "rushing_yards", "rec": "receiving_yards", "pass": "passing_yards", "recs": "receptions",
        "ptd": "passing_tds", "lng": "receiving_long"}


def dists(run: Run) -> dict:
    """Per-kind error tables from the run's backtest (older runs stored only gamma parameters: those are skipped)."""
    return {k: v for k, v in (run.variance or {}).items() if isinstance(v, dict) and not k.startswith("_")}


def _kickoff_utc(gameday: str, gametime: str) -> Optional[datetime]:
    try:
        local = datetime.fromisoformat(f"{gameday}T{gametime or '00:00'}").replace(tzinfo=ET)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def snapshot_board(session, now: datetime = None) -> int:
    """Price the latest run against the current lines and store every pick for games not yet kicked off, replacing
    that game's earlier snapshot of the same player/market/side. Returns how many picks were stored."""
    now = now or datetime.utcnow()
    run = session.scalars(select(Run).order_by(Run.id.desc()).limit(1)).first()
    if not run:
        return 0
    picks = build_picks(proj_frame(session, run.id), current_lines(session), MARKET_WEIGHT, dists=dists(run))
    if picks.empty:
        return 0
    ko = [_kickoff_utc(str(d), str(t)) for d, t in zip(picks.gameday, picks.gametime)]
    picks = picks[[k is not None and k > now for k in ko]]
    if picks.empty:
        return 0
    existing = {(r.game_id, r.player_id, r.kind, r.side): r for r in session.scalars(
        select(PickLog).where(PickLog.game_id.in_(set(picks.game_id))))}
    for p in picks.itertuples():
        row = existing.get((p.game_id, p.player_id, p.kind, p.side))
        if row is None:
            row = PickLog(game_id=p.game_id, player_id=p.player_id, kind=p.kind, side=p.side)
            session.add(row)
        row.season, row.week = run.season, run.week
        row.gameday, row.gametime, row.name, row.pos, row.team = str(p.gameday), str(p.gametime), p.name, p.pos, p.team
        row.line, row.odds, row.book = float(p.line), int(p.odds), p.book
        row.mu, row.prob, row.p_model, row.p_mkt, row.ev = (float(x) for x in (p.mu, p.prob, p.p_model, p.p_mkt, p.ev))
        row.flagged, row.run_id, row.snapped_at = bool(p.flagged), run.id, now
    session.commit()
    return len(picks)


def actual_value(kind: str, stat_row) -> float:
    """The player's result in a market, from one row of nflverse's weekly stats (missing stats count as 0)."""
    v = lambda c: float(stat_row.get(c, 0) or 0) if pd.notna(stat_row.get(c, 0)) else 0.0
    if kind == "rr":
        return v("rushing_yards") + v("receiving_yards")
    if kind == "td":
        return v("rushing_tds") + v("receiving_tds")
    return v(STAT[kind])


def outcome(side: str, line: float, actual: Optional[float]) -> str:
    if actual is None:
        return "void"
    if actual == line:
        return "push"
    return "win" if (actual > line) == (side == "Over") else "loss"


def grade(session, stats: pd.DataFrame, sched: pd.DataFrame, now: datetime = None) -> int:
    """Grade logged picks whose game is final and whose teams' stats are in. A player with no stats row didn't play:
    void, as the books settle it. Returns how many picks were graded."""
    now = now or datetime.utcnow()
    todo = session.scalars(select(PickLog).where(PickLog.result.is_(None))).all()
    if not todo or stats.empty:
        return 0
    final = set(sched.loc[sched.home_score.notna(), "game_id"])
    have = set(zip(stats.season, stats.week, stats.team))
    by_player = {(r["player_id"], r["season"], r["week"]): r
                 for r in stats[["player_id", "season", "week", *{c for c in (*STAT.values(), "rushing_tds", "receiving_tds") if c in stats}]]
                 .to_dict("records")}
    n = 0
    for row in todo:
        if row.game_id not in final:
            continue
        _, _, away, home = row.game_id.split("_", 3)
        if not {(row.season, row.week, away), (row.season, row.week, home)} <= have:
            continue   # final, but nflverse hasn't published this game's stats yet
        st = by_player.get((row.player_id, row.season, row.week))
        row.actual = None if st is None else actual_value(row.kind, st)
        row.result, row.graded_at = outcome(row.side, row.line, row.actual), now
        n += 1
    session.commit()
    return n


def grade_logged(session, stats: pd.DataFrame, sched: pd.DataFrame, log: Callable[[str], None] = print) -> None:
    """grade(), for the model run: a grading problem is logged and never stops the run."""
    try:
        n = grade(session, stats, sched)
        if n:
            log(f"Graded {n} logged picks against the box scores")
    except Exception as e:   # noqa: BLE001
        session.rollback()
        log(f"  couldn't grade logged picks ({type(e).__name__}: {e})")


# ---------- the report ----------
def _payout(odds: int) -> float:
    return odds / 100 if odds > 0 else 100 / -odds


def _line(label: str, rows: list) -> dict:
    res = [r.result for r in rows]
    w, l = res.count("win"), res.count("loss")
    units = sum(_payout(r.odds) if r.result == "win" else -1.0 if r.result == "loss" else 0.0 for r in rows)
    decided = [r for r in rows if r.result in ("win", "loss")]
    return dict(label=label, n=len(rows), wins=w, losses=l, pushes=res.count("push"), voids=res.count("void"),
                units=round(units, 2), roi=round(units / len(decided), 4) if decided else None,
                expected_wins=round(sum(r.prob for r in decided), 1))


def _one_per_player(rows: list) -> list:
    best = {}
    for r in rows:
        k = (r.game_id, r.player_id)
        if k not in best or r.ev > best[k].ev:
            best[k] = r
    return list(best.values())


def report(session, season: Optional[int] = None) -> dict:
    """How the board did once graded: record and units for what a visitor saw (Min EV 3%, flags hidden), split by
    market, side and EV, plus whether the model or the posted line landed closer to the result, per market."""
    q = select(PickLog).where(PickLog.result.is_not(None))
    if season is None:
        season = session.scalars(select(PickLog.season).order_by(PickLog.season.desc()).limit(1)).first()
    if season is not None:
        q = q.where(PickLog.season == season)
    rows = session.scalars(q).all()
    pending = session.query(PickLog).filter(PickLog.result.is_(None)).count()
    board = [r for r in rows if r.ev >= BOARD_MIN_EV and not r.flagged]
    kinds = sorted({r.kind for r in board})
    by_ev = [(f"EV {lo:.0%}–{hi:.0%}" if hi < 9 else f"EV {lo:.0%}+", lo, hi) for lo, hi in ((0.03, 0.08), (0.08, 0.15), (0.15, 0.25), (0.25, 9))]
    # model vs line: one row per player and market (the Over and Under rows share a line and a projection)
    seen = {}
    for r in rows:
        if r.kind != "td" and r.actual is not None:
            seen[(r.game_id, r.player_id, r.kind)] = r
    checks = []
    for k in sorted({r.kind for r in seen.values()}):
        v = [r for r in seen.values() if r.kind == k]
        checks.append(dict(kind=k, n=len(v), mae_model=round(sum(abs(r.mu - r.actual) for r in v) / len(v), 2),
                           mae_line=round(sum(abs(r.line - r.actual) for r in v) / len(v), 2),
                           model_closer=round(sum(abs(r.mu - r.actual) < abs(r.line - r.actual) for r in v) / len(v), 3)))
    return dict(
        season=season, graded=len(rows), pending=pending,
        weeks=sorted({r.week for r in rows}),
        board=[_line("Board (Min EV 3%, flags hidden)", board),
               _line("One pick per player", _one_per_player(board)),
               _line("Overs", [r for r in board if r.side == "Over" and r.kind != "td"]),
               _line("Unders", [r for r in board if r.side == "Under" and r.kind != "td"]),
               _line("Flagged (hidden)", [r for r in rows if r.flagged and r.ev >= BOARD_MIN_EV])],
        by_market=[_line(k, [r for r in board if r.kind == k]) for k in kinds],
        by_ev=[_line(label, [r for r in board if lo <= r.ev < hi]) for label, lo, hi in by_ev],
        by_week=[_line(f"Week {w}", [r for r in board if r.week == w]) for w in sorted({r.week for r in board})],
        model_vs_line=checks,
    )
