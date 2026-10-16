"""Sync jobs and the weekly schedule that runs them, so nobody has to press a button.

One job runs at a time (model run and/or odds fetch), whether the schedule or the admin page started it. Every job
is logged as a SyncRun. Odds fetches stop before the key drops under config.ODDS_CREDIT_FLOOR credits.
The schedule runs in a background thread of the web process: fine on a single always-on instance (Railway Hobby).
"""
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import config, pipeline
from .db import NbaRun, Run, SessionLocal, SyncRun
from .nba import pipeline as nba_pipeline

ET = ZoneInfo("America/New_York")
CATCH_UP = timedelta(hours=3)   # a slot missed by less than this (a redeploy at the wrong moment) runs on startup
LOG_LINES = 200                 # lines of job output kept per run


@dataclass(frozen=True)
class Slot:
    id: str
    label: str
    days: tuple[int, ...]   # weekdays, 0 = Monday
    hour: int               # Eastern time
    minute: int
    odds: str               # none | missing | thin | all
    full: bool = False      # refit the calibration
    why: str = ""
    league: str = "nfl"     # nfl | nba


EVERY_DAY = (0, 1, 2, 3, 4, 5, 6)
SLOTS = [
    Slot("daily-topup", "Daily top-up", EVERY_DAY, 9, 0, "thin",
         why="Model run, plus odds for games with no lines or only a few old ones"),
    Slot("new-week", "New week", (1,), 10, 0, "none", full=True,
         why="After Monday night's stats land: recalibrate and project the new week. No credits"),
    Slot("wed-odds", "Wednesday odds", (2,), 10, 0, "missing", why="Model run, plus odds for games that have none yet"),
    Slot("thu-odds", "Thursday odds", (3,), 10, 0, "missing", why="Model run, plus odds for games that have none yet"),
    Slot("thu-injuries", "Thursday injuries", (3,), 16, 0, "none", why="Model run after the practice reports. No credits"),
    Slot("sat-injuries", "Saturday statuses", (5,), 10, 0, "none", why="Model run after Friday's game statuses. No credits"),
    Slot("sun-pregame", "Sunday pregame", (6,), 11, 0, "none", why="Model run with the latest statuses. No credits"),
    Slot("sun-topup", "Sunday top-up", (6,), 11, 30, "thin", why="Last top-up of thin games before the early kickoffs"),
    # NBA (its own key, ODDS_API_KEY_NBA): games every day, props posted the day of
    Slot("nba-morning", "NBA morning", EVERY_DAY, 10, 0, "missing", league="nba",
         why="NBA model run after last night's box scores, moneylines (1 credit), props already posted for today (3 per game)"),
    Slot("nba-afternoon", "NBA afternoon", EVERY_DAY, 14, 0, "missing", league="nba",
         why="NBA model run, moneylines, and props for today's games that had none in the morning"),
    Slot("nba-pregame", "NBA pregame", EVERY_DAY, 18, 0, "all", league="nba",
         why="NBA model run with the late injury news, and a fresh pull of tonight's props and moneylines (3 per game)"),
]
BY_ID = {s.id: s for s in SLOTS}


def _utc(local: datetime) -> datetime:
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _local_times(slot: Slot, now: datetime, step: int):
    """Slot times from now's Eastern date, walking forward (step 1) or back (-1) day by day; naive UTC."""
    day = now.replace(tzinfo=timezone.utc).astimezone(ET).date()
    for d in range(0, 9):
        date = day + timedelta(days=d * step)
        if date.weekday() in slot.days:
            yield _utc(datetime(date.year, date.month, date.day, slot.hour, slot.minute, tzinfo=ET))


def next_fire(slot: Slot, now: datetime) -> datetime:
    """The first time after now (naive UTC) that the slot runs."""
    return next(t for t in _local_times(slot, now, 1) if t > now)


def last_fire(slot: Slot, now: datetime) -> datetime:
    """The latest time at or before now (naive UTC) that the slot was due."""
    return next(t for t in _local_times(slot, now, -1) if t <= now)


def describe(slot: Slot) -> str:
    """'Tue 10:00 AM ET', 'Daily 9:00 AM ET'."""
    days = "Daily" if slot.days == EVERY_DAY else "/".join("Mon Tue Wed Thu Fri Sat Sun".split()[d] for d in slot.days)
    t = datetime(2000, 1, 1, slot.hour, slot.minute).strftime("%I:%M %p").lstrip("0")
    return f"{days} {t} ET"


# ---------- the job ----------
_job = {"state": "idle", "started_at": None, "finished_at": None, "log": [], "error": None,
        "stage": None, "step": 0, "steps": 0, "detail": None, "progress": None}
_lock = threading.Lock()
after_job: Callable[[], None] = lambda: None   # main.py hooks in cache clearing and memory release


def claim() -> bool:
    """Mark a job as running; False if one already is."""
    with _lock:
        if _job["state"] == "running":
            return False
        _job.update(state="running", started_at=datetime.utcnow().isoformat(), finished_at=None, log=[], error=None,
                    stage="Starting", step=0, steps=0, detail=None, progress=None)
        return True


def run(odds_mode: str, full: bool = False, slot: str = "manual", trigger: str = "manual",
        scheduled_for: Optional[datetime] = None, league: str = "nfl") -> None:
    """Run a claimed job: the model (unless this host only fetches odds), then odds. Logs it as a SyncRun."""
    nba = league == "nba"
    run_model = nba or config.PROJECTIONS_ON_SERVER()   # the NBA model is small enough for any host
    steps = int(run_model) + int(odds_mode != "none")
    _job.update(steps=steps, step=0, stage=None, detail=None, progress=None)
    with SessionLocal() as s:
        rec = SyncRun(slot=slot, trigger=trigger, scheduled_for=scheduled_for, odds_mode=odds_mode, full=full,
                      started_at=datetime.utcnow(), log=[])
        s.add(rec)
        s.commit()
        rec_id = rec.id

    def log(msg):
        _job["log"].append(msg)
        _job["detail"] = msg.strip()

    def odds_progress(done: int, total: int):
        _job.update(progress=(done / total) if total else 1.0, detail=f"game {min(done + 1, total)} of {total}")

    res, status, parts, error = {}, "ok", [], None
    try:
        if nba:
            _job.update(step=1, stage="Running the NBA model", progress=None)
            parts.append("NBA model run" if nba_pipeline.run_projections(log=log) else "No NBA games coming up")
        elif run_model:
            _job.update(step=1, stage="Running the model" + (" (full recalibration)" if full else ""), progress=None)
            pipeline.run_projections(log=log, full=full)
            parts.append("Model recalibrated" if full else "Model run")
        else:
            log("Projections run off-server on this host; fetching odds only")
        if odds_mode != "none":
            _job.update(step=steps, stage="Fetching odds", detail=None, progress=0.0)
            refresh = nba_pipeline.refresh_odds if nba else pipeline.refresh_odds
            res = refresh(odds_mode, log=log, progress=odds_progress, credit_floor=config.ODDS_CREDIT_FLOOR()) or {}
            parts.append(_odds_summary(res))
            if res.get("skipped_for_credits"):
                status = "partial"
    except Exception as e:  # surfaced to the UI and the run log
        status, error = "error", f"{type(e).__name__}: {e}"
        log(traceback.format_exc(limit=3))
    finally:
        # the log row is written before the job reads as finished, so the admin page never sees one without the other
        try:
            with SessionLocal() as s:
                rec = s.get(SyncRun, rec_id)
                latest = s.scalars(select(NbaRun if nba else Run).order_by((NbaRun if nba else Run).id.desc()).limit(1)).first()
                rec.finished_at, rec.status, rec.error = datetime.utcnow(), status, error
                rec.season, rec.week = (latest.season, None if nba else latest.week) if latest else (None, None)
                rec.games_fetched = int(res.get("fetched", 0))
                rec.credits_before, rec.credits_after = res.get("credits_before"), res.get("credits_after")
                rec.summary = (" · ".join(p for p in parts if p) or (error or ""))[:500]
                rec.log = _job["log"][-LOG_LINES:]
                s.commit()
        except Exception:  # a failed log write must never leave the job looking stuck
            traceback.print_exc()
        if error:
            _job.update(state="error", error=error)
        else:
            _job.update(state="done", stage="Done", detail=None, progress=1.0)
        _job["finished_at"] = datetime.utcnow().isoformat()
        after_job()


def _odds_summary(res: dict) -> str:
    before, after = res.get("credits_before"), res.get("credits_after")
    if not res.get("games"):
        return "odds already complete"
    bits = [f"odds for {res.get('fetched', 0)} of {res['games']} games"]
    if before is not None and after is not None:
        bits.append(f"{before - after} credits used, {after} left")
    if res.get("skipped_for_credits"):
        bits.append(f"{res['skipped_for_credits']} skipped at the {config.ODDS_CREDIT_FLOOR()}-credit floor: rotate the key")
    return ", ".join(bits)


# ---------- the schedule ----------
def _already_ran(slot: Slot, at: datetime) -> bool:
    with SessionLocal() as s:
        return s.scalars(select(SyncRun.id).where(SyncRun.slot == slot.id, SyncRun.scheduled_for == at).limit(1)).first() is not None


def _fire(slot: Slot, at: datetime, trigger: str, stop: threading.Event) -> None:
    """Run a due slot, waiting out a job the admin started (up to half an hour) rather than dropping the slot."""
    if _already_ran(slot, at):
        return
    deadline = datetime.utcnow() + timedelta(minutes=30)
    while not claim():
        if datetime.utcnow() > deadline or stop.wait(20):
            with SessionLocal() as s:
                s.add(SyncRun(slot=slot.id, trigger=trigger, scheduled_for=at, odds_mode=slot.odds, full=slot.full,
                              finished_at=datetime.utcnow(), status="skipped", summary="Another sync was still running"))
                s.commit()
            return
    run(slot.odds, slot.full, slot.id, trigger, at, slot.league)


def _loop(stop: threading.Event) -> None:
    now = datetime.utcnow()
    # a deploy or restart that straddled a slot: run the most recent one missed within the catch-up window
    missed = [(last_fire(s, now), s) for s in SLOTS]
    missed = [(t, s) for t, s in missed if now - t < CATCH_UP and not _already_ran(s, t)]
    if missed:
        t, s = max(missed, key=lambda m: m[0])
        _fire(s, t, "catch-up", stop)
    due = {s.id: next_fire(s, datetime.utcnow()) for s in SLOTS}
    while not stop.wait(30):
        now = datetime.utcnow()
        for s in sorted(SLOTS, key=lambda s: due[s.id]):
            if due[s.id] <= now:
                try:
                    _fire(s, due[s.id], "schedule", stop)
                except Exception:  # never let one bad run stop the schedule
                    traceback.print_exc()
                due[s.id] = next_fire(s, datetime.utcnow())


_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def start() -> bool:
    """Start the schedule (once per process) if AUTO_SYNC is on."""
    global _thread
    if not config.AUTO_SYNC() or (_thread and _thread.is_alive()):
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(_stop,), name="sync-schedule", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    _stop.set()


def upcoming(now: Optional[datetime] = None, league: Optional[str] = None) -> list[tuple[datetime, Slot]]:
    """Every slot (of one league, if given) with its next run time, soonest first."""
    now = now or datetime.utcnow()
    return sorted(((next_fire(s, now), s) for s in SLOTS if league in (None, s.league)), key=lambda x: x[0])
