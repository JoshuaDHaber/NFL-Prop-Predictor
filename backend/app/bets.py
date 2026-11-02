"""Tracked bets: a signed-in visitor records the bets they placed at a sportsbook, and each model run settles them from the
box scores, the same way it grades the board (app/grading.py, app/nba/grading.py). Private to their owner.

Phase 1 of docs/bet-tracker-plan.md: player props the site prices (main and alternate lines), singles and parlays, in
dollars, tracked only before the first game starts.
"""
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import auth, grading
from .db import Bet, BetLeg, NbaProjection, NbaRun, Projection, Run, User
from .market_fit import kickoff_utc
from .schemas import BetIn, BetLegOut, BetOut, BetPatch, BetsOut, BetSummary

router = APIRouter(prefix="/api/me", tags=["bets"])

NBA_KINDS = {"pts", "reb", "ast", "threes", "pra", "pr", "pa", "stl", "blk", "dd", "tpl"}
MAX_LEGS = 12
MAX_STAKE = 100_000
MAX_TAGS, TAG_LEN = 6, 24


def league_of(kind: str) -> str:
    """The two leagues' markets don't overlap, so a leg's market says which league it's from."""
    return "nba" if kind in NBA_KINDS else "nfl"


def to_decimal(american: int) -> float:
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def valid_odds(american: int) -> bool:
    return abs(american) >= 100 and abs(american) <= 100_000


def clean_tags(tags: list) -> list:
    """The bettor's labels, trimmed and de-duplicated ignoring case (the first spelling wins), at most MAX_TAGS."""
    out, seen = [], set()
    for t in tags or []:
        t = " ".join(str(t).split())[:TAG_LEN]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:MAX_TAGS]


def months_ago(now: datetime, n: int) -> datetime:
    """The same day and time n calendar months back (the 31st of March, one month back, is the 28th or 29th of February)."""
    y, m = divmod(now.year * 12 + now.month - 1 - n, 12)
    m += 1
    days = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day
    return now.replace(year=y, month=m, day=min(now.day, days))


def require_member(user: User = Depends(auth.require_user)) -> User:
    """Signed in and 21+ confirmed: the account's age check comes before anything is saved to it."""
    if not user.age_confirmed_at:
        raise HTTPException(403, "Confirm you're 21 or older first")
    return user


# ---------- settling ----------
def settle(bet: Bet, now: Optional[datetime] = None) -> None:
    """A bet's status and payout from its legs. A losing leg loses the bet straight away. Pushed and void legs drop out
    and the parlay pays on the rest, as FanDuel and DraftKings settle: the recorded price is divided by those legs' prices,
    which keeps a book's same-game or boosted pricing in proportion. Every leg out: stake back. A bet settled by hand is
    left alone."""
    if bet.settled_by == "user":
        return
    results = [leg.result for leg in bet.legs]
    if "loss" in results:
        bet.status, bet.payout = "lost", 0.0
    elif None in results:
        bet.status, bet.payout, bet.settled_by, bet.settled_at = "open", None, None, None
        return
    elif "win" not in results:
        bet.status, bet.payout = ("push" if "push" in results else "void"), bet.stake
    else:
        dec = to_decimal(bet.odds)
        for leg in bet.legs:
            if leg.result in ("push", "void") and len(bet.legs) > 1:
                dec /= to_decimal(leg.odds)
        bet.status, bet.payout = "won", round(bet.stake * max(dec, 1.0), 2)
    bet.settled_by, bet.settled_at = "grading", now or datetime.utcnow()


def _settle_touched(session, legs: list, now: datetime) -> None:
    for bet in {leg.bet for leg in legs}:
        settle(bet, now)


def grade_nfl(session, stats: pd.DataFrame, sched: pd.DataFrame, now: Optional[datetime] = None) -> int:
    """Grade open NFL legs whose game is final and whose teams' stats are in (as grading.grade does the board): a player
    with no stats row didn't play, so the leg is void. Settles the bets they belong to. Returns how many legs were graded."""
    now = now or datetime.utcnow()
    todo = [leg for leg in session.scalars(select(BetLeg).where(BetLeg.result.is_(None))) if league_of(leg.kind) == "nfl"]
    if not todo or stats.empty:
        return 0
    final = set(sched.loc[sched.home_score.notna(), "game_id"])
    have = set(zip(stats.season, stats.week, stats.team))
    cols = [c for c in {*grading.STAT.values(), "rushing_tds", "receiving_tds"} if c in stats]
    by_player = {(r["player_id"], r["season"], r["week"]): r for r in stats[["player_id", "season", "week", *cols]].to_dict("records")}
    done = []
    for leg in todo:
        if leg.game_id not in final:
            continue
        season, week, away, home = leg.game_id.split("_", 3)
        season, week = int(season), int(week)
        if not {(season, week, away), (season, week, home)} <= have:
            continue   # final, but nflverse hasn't published this game's stats yet
        st = by_player.get((leg.player_id, season, week))
        leg.actual = None if st is None else grading.actual_value(leg.kind, st)
        leg.result, leg.graded_at = grading.outcome(leg.side, leg.line, leg.actual), now
        done.append(leg)
    _settle_touched(session, done, now)
    session.commit()
    return len(done)


def grade_nba(session, logs: pd.DataFrame, today: date, fetch: Optional[Callable] = None, now: Optional[datetime] = None) -> int:
    """Grade open NBA legs from games before today (Eastern) against the ESPN game logs, with nba/grading.py's rules: a
    player missing from a finished box score is void once he has played again or two days have passed, and a box score
    that never appears (a postponement) voids the leg after a week. Settles their bets; returns how many legs were graded."""
    from .nba import espn, model
    from .nba.grading import STALE_AFTER_DAYS, VOID_AFTER_DAYS
    fetch = fetch or espn.gamelogs
    now = now or datetime.utcnow()
    todo = [leg for leg in session.scalars(select(BetLeg).where(BetLeg.result.is_(None), BetLeg.gameday < today.isoformat()))
            if league_of(leg.kind) == "nba"]
    if not todo:
        return 0
    missing = sorted({leg.player_id for leg in todo} - set(logs.player_id))
    if missing:
        seasons = sorted({int(leg.gameday[:4]) + (int(leg.gameday[5:7]) >= 9) for leg in todo})   # an NBA season ends in its spring
        extra = fetch(missing, seasons, max(seasons), log=lambda _: None)
        logs = pd.concat([logs, extra], ignore_index=True) if not extra.empty else logs
    have = set(zip(logs.date, logs.team))
    by_player = {(r.player_id, r.date): r for r in logs.itertuples()}
    last_game = logs.groupby("player_id").date.max().to_dict() if not logs.empty else {}
    done = []
    for leg in todo:
        _, _, away, home = leg.game_id.split("_", 3)
        age = (today - date.fromisoformat(leg.gameday)).days
        if not {(leg.gameday, away), (leg.gameday, home)} <= have:
            if age < STALE_AFTER_DAYS:
                continue
            leg.actual = None
        else:
            st = by_player.get((leg.player_id, leg.gameday))
            if st is None and last_game.get(leg.player_id, "") <= leg.gameday and age < VOID_AFTER_DAYS:
                continue
            v = None if st is None or not st.min else model.actual(st, leg.kind)
            leg.actual = None if v is None or pd.isna(v) else float(v)
        leg.result, leg.graded_at = grading.outcome(leg.side, leg.line, leg.actual), now
        done.append(leg)
    _settle_touched(session, done, now)
    session.commit()
    return len(done)


# ---------- the API ----------
def _game(db: Session, league: str, game_id: str, player_id: str) -> Optional[dict]:
    """The player and game as the latest run has them: who he plays for, against whom, and when it starts (UTC)."""
    if league == "nfl":
        run = db.scalar(select(Run).order_by(Run.id.desc()).limit(1))
        row = run and db.scalar(select(Projection).where(Projection.run_id == run.id, Projection.game_id == game_id,
                                                         Projection.player_id == player_id).limit(1))
        if not row:
            return None
        return dict(name=row.name, team=row.team, opp=row.opp, gameday=row.gameday, kickoff=kickoff_utc(row.gameday, row.gametime))
    run = db.scalar(select(NbaRun).order_by(NbaRun.id.desc()).limit(1))
    row = run and db.scalar(select(NbaProjection).where(NbaProjection.run_id == run.id, NbaProjection.game_id == game_id,
                                                        NbaProjection.player_id == player_id).limit(1))
    if not row:
        return None
    start = next((g.get("start") for g in run.games or [] if g.get("game_id") == game_id), None)
    ko = datetime.fromisoformat(start.replace("Z", "+00:00")).replace(tzinfo=None) if start else kickoff_utc(row.gameday, row.gametime)
    return dict(name=row.name, team=row.team, opp=row.opp, gameday=row.gameday, kickoff=ko)


def _out(bet: Bet, now: datetime) -> BetOut:
    settled = bet.status != "open"
    return BetOut(
        id=bet.id, league=bet.league, book=bet.book, kind=bet.kind, stake=bet.stake, odds=bet.odds, status=bet.status,
        payout=bet.payout, profit=round(bet.payout - bet.stake, 2) if settled and bet.payout is not None else None,
        to_pay=round(bet.stake * to_decimal(bet.odds), 2), settled_by=bet.settled_by, notes=bet.notes, tags=bet.tags or [],
        placed_at=bet.placed_at.isoformat(), settled_at=bet.settled_at.isoformat() if bet.settled_at else None,
        started=min(leg.kickoff for leg in bet.legs) <= now,
        legs=[BetLegOut(id=leg.id, game_id=leg.game_id, gameday=leg.gameday, kickoff=leg.kickoff.isoformat(), player_id=leg.player_id,
                        name=leg.name, team=leg.team, opp=leg.opp, kind=leg.kind, side=leg.side, line=leg.line, odds=leg.odds,
                        alt=leg.alt, prob=leg.prob, ev=leg.ev, actual=leg.actual, result=leg.result) for leg in bet.legs])


def summarize(bets: list) -> BetSummary:
    won_lost = [b for b in bets if b.status in ("won", "lost")]
    staked = sum(b.stake for b in won_lost)
    profit = sum(b.payout - b.stake for b in won_lost)
    running, curve = 0.0, []
    for b in sorted((b for b in bets if b.status != "open" and b.settled_at), key=lambda b: b.settled_at):
        running += (b.payout or 0) - b.stake if b.status in ("won", "lost") else 0
        curve.append((b.settled_at.isoformat(), round(running, 2)))
    open_ = [b for b in bets if b.status == "open"]
    return BetSummary(wins=sum(b.status == "won" for b in bets), losses=sum(b.status == "lost" for b in bets),
                      pushes=sum(b.status in ("push", "void") for b in bets), open=len(open_),
                      open_stake=round(sum(b.stake for b in open_), 2), staked=round(staked, 2), profit=round(profit, 2),
                      roi=round(profit / staked, 4) if staked else None, curve=curve)


def _mine(db: Session, user: User, bet_id: int) -> Bet:
    bet = db.get(Bet, bet_id)
    if not bet or bet.user_id != user.id:
        raise HTTPException(404, "No such bet")
    return bet


@router.get("/bets", response_model=BetsOut)
def my_bets(league: Optional[str] = Query(None, pattern="^(nfl|nba)$"), book: Optional[str] = None, tag: Optional[str] = None,
            months: Optional[int] = Query(None, ge=1, le=120), user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    """This person's tracked bets, newest first, and their record, for the filters given: a league, a sportsbook, a tag
    (ignoring case) and the last `months` calendar months (by when the bet was placed)."""
    now = datetime.utcnow()
    every = db.scalars(select(Bet).where(Bet.user_id == user.id).order_by(Bet.placed_at.desc(), Bet.id.desc())).all()
    since = months_ago(now, months) if months else None
    want = tag.strip().lower() if tag else None
    bets = [b for b in every if (not league or b.league == league) and (not book or b.book == book)
            and (not want or want in {t.lower() for t in b.tags or []}) and (not since or b.placed_at >= since)]
    tags = sorted({t.lower(): t for b in every for t in b.tags or []}.values(), key=str.lower)
    return BetsOut(bets=[_out(b, now) for b in bets], summary=summarize(bets), books=sorted({b.book for b in every}), tags=tags)


@router.post("/bets", response_model=BetOut, dependencies=[Depends(auth.same_origin)])
def track(body: BetIn, user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    now = datetime.utcnow()
    if not 1 <= len(body.legs) <= MAX_LEGS:
        raise HTTPException(422, f"A bet has 1 to {MAX_LEGS} legs")
    if body.kind == "single" and len(body.legs) != 1:
        raise HTTPException(422, "A single has one leg")
    if body.kind == "parlay" and len(body.legs) < 2:
        raise HTTPException(422, "A parlay has two or more legs")
    if not 0 < body.stake <= MAX_STAKE:
        raise HTTPException(422, "Enter a stake above $0")
    leagues = {league_of(leg.kind) for leg in body.legs}
    if len(leagues) > 1:
        raise HTTPException(422, "A parlay's legs are all NFL or all NBA")
    league = leagues.pop()
    if len({(leg.game_id, leg.player_id, leg.kind) for leg in body.legs}) < len(body.legs):
        raise HTTPException(422, "The same prop is on this bet twice")
    odds = body.legs[0].odds if body.kind == "single" else body.odds
    if odds is None or not valid_odds(odds) or not all(valid_odds(leg.odds) for leg in body.legs):
        raise HTTPException(422, "Odds look wrong: use American odds like -110 or +250")
    bet = Bet(user_id=user.id, league=league, book=body.book.strip()[:40], kind=body.kind, stake=round(body.stake, 2), odds=odds,
              status="open", notes=(body.notes or "").strip()[:500] or None, tags=clean_tags(body.tags), placed_at=now)
    for leg in body.legs:
        g = _game(db, league, leg.game_id, leg.player_id)
        if not g or not g["kickoff"]:
            raise HTTPException(422, "One of these props isn't on the board any more")
        if g["kickoff"] <= now:
            raise HTTPException(422, f"{g['name']}'s game has started, so this bet can't be tracked now")
        bet.legs.append(BetLeg(game_id=leg.game_id, gameday=g["gameday"], kickoff=g["kickoff"], player_id=leg.player_id, name=g["name"],
                               team=g["team"], opp=g["opp"], kind=leg.kind, side=leg.side, line=leg.line, odds=leg.odds, alt=leg.alt,
                               prob=leg.prob, ev=leg.ev))
    db.add(bet)
    db.commit()
    return _out(bet, now)


@router.patch("/bets/{bet_id}", response_model=BetOut, dependencies=[Depends(auth.same_origin)])
def edit(bet_id: int, body: BetPatch, user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    """Fix the stake, odds or notes, or settle it by hand (status "open" hands it back to grading)."""
    bet = _mine(db, user, bet_id)
    now = datetime.utcnow()
    if body.stake is not None:
        if not 0 < body.stake <= MAX_STAKE:
            raise HTTPException(422, "Enter a stake above $0")
        bet.stake = round(body.stake, 2)
    if body.odds is not None:
        if not valid_odds(body.odds):
            raise HTTPException(422, "Odds look wrong: use American odds like -110 or +250")
        bet.odds = body.odds
        if bet.kind == "single":
            bet.legs[0].odds = body.odds
    if body.notes is not None:
        bet.notes = body.notes.strip()[:500] or None
    if body.tags is not None:
        bet.tags = clean_tags(body.tags)
    if body.status == "open":
        bet.settled_by = None
    elif body.status is not None:
        payout = {"won": bet.stake * to_decimal(bet.odds), "lost": 0.0}.get(body.status, bet.stake)
        bet.status, bet.payout, bet.settled_by, bet.settled_at = body.status, round(payout, 2), "user", now
    if bet.settled_by == "user" and body.status is None and (body.stake is not None or body.odds is not None):
        bet.payout = round({"won": bet.stake * to_decimal(bet.odds), "lost": 0.0}.get(bet.status, bet.stake), 2)
    if bet.settled_by != "user":
        settle(bet, now)   # stake or odds changed (or handed back): what grading says now
    db.commit()
    return _out(bet, now)


@router.delete("/bets/{bet_id}", status_code=204, dependencies=[Depends(auth.same_origin)])
def remove(bet_id: int, user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    bet = _mine(db, user, bet_id)
    db.execute(delete(BetLeg).where(BetLeg.bet_id == bet.id))   # SQLite doesn't enforce the cascade
    db.delete(bet)
    db.commit()
    return Response(status_code=204)


def delete_all(db: Session, user_id: int) -> None:
    """Every bet of an account being deleted (app/auth.py)."""
    ids = db.scalars(select(Bet.id).where(Bet.user_id == user_id)).all()
    if ids:
        db.execute(delete(BetLeg).where(BetLeg.bet_id.in_(ids)))
        db.execute(delete(Bet).where(Bet.id.in_(ids)))
