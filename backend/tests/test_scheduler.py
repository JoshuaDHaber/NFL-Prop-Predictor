"""The sync schedule: slot times in Eastern time, the run log, catch-up and the admin endpoints."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import main, scheduler
from app.db import SessionLocal, SyncRun


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    with SessionLocal() as s:
        s.query(SyncRun).delete(); s.commit()
    scheduler._job.update(state="idle")
    monkeypatch.setattr(scheduler.pipeline, "run_projections", lambda log=print, **kw: log("fake run"))
    yield
    scheduler._job.update(state="idle")


def test_slot_times_follow_eastern_time_across_daylight_saving():
    wed = scheduler.BY_ID["wed-odds"]
    # October is EDT (UTC-4), December is EST (UTC-5)
    assert scheduler.next_fire(wed, datetime(2026, 10, 13, 12)) == datetime(2026, 10, 14, 14)
    assert scheduler.next_fire(wed, datetime(2026, 12, 1, 12)) == datetime(2026, 12, 2, 15)
    # exactly at the slot time it is the last fire, and the next one is a week out
    assert scheduler.last_fire(wed, datetime(2026, 10, 14, 14)) == datetime(2026, 10, 14, 14)
    assert scheduler.next_fire(wed, datetime(2026, 10, 14, 14)) == datetime(2026, 10, 21, 14)


def test_daily_slot_runs_every_day_and_describes_itself():
    daily = scheduler.BY_ID["daily-topup"]
    assert scheduler.next_fire(daily, datetime(2026, 10, 13, 14)) == datetime(2026, 10, 14, 13)
    assert scheduler.describe(daily) == "Daily 9:00 AM ET"
    assert scheduler.describe(scheduler.BY_ID["sun-lines"]) == "Sun 11:30 AM ET"


def test_a_run_is_logged_with_its_odds_result(monkeypatch):
    monkeypatch.setattr(scheduler.pipeline, "refresh_odds", lambda mode, log=print, **kw: dict(
        games=3, fetched=2, skipped_for_credits=1, credits_before=100, credits_after=88))
    assert scheduler.claim()
    scheduler.run("missing", slot="wed-odds", trigger="schedule", scheduled_for=datetime(2026, 10, 14, 14))
    with SessionLocal() as s:
        r = s.query(SyncRun).one()
    assert r.status == "partial" and r.games_fetched == 2 and (r.credits_before, r.credits_after) == (100, 88)
    assert "12 credits used, 88 left" in r.summary and "rotate the key" in r.summary
    assert r.log == ["fake run"] and r.finished_at


def test_a_failed_run_is_logged_as_an_error(monkeypatch):
    def boom(**kw):
        raise RuntimeError("nflverse down")
    monkeypatch.setattr(scheduler.pipeline, "run_projections", boom)
    assert scheduler.claim()
    scheduler.run("none", slot="new-week", trigger="schedule")
    with SessionLocal() as s:
        r = s.query(SyncRun).one()
    assert r.status == "error" and "nflverse down" in r.error
    assert scheduler._job["state"] == "error"


def test_a_slot_never_runs_twice_for_the_same_time(monkeypatch):
    monkeypatch.setattr(scheduler.pipeline, "refresh_odds", lambda mode, log=print, **kw: {})
    slot, at = scheduler.BY_ID["sun-pregame"], datetime(2026, 10, 18, 15)
    stop = scheduler.threading.Event()
    scheduler._fire(slot, at, "schedule", stop)
    scheduler._fire(slot, at, "catch-up", stop)
    with SessionLocal() as s:
        assert s.query(SyncRun).count() == 1


def test_a_restart_marks_cut_off_runs_interrupted_and_catch_up_retries_them_once(monkeypatch):
    monkeypatch.setattr(scheduler.pipeline, "refresh_odds", lambda mode, log=print, **kw: {})
    slot, at = scheduler.BY_ID["sun-pregame"], datetime(2026, 10, 18, 15)
    with SessionLocal() as s:   # the process died mid-run: the row never finished
        s.add(SyncRun(slot=slot.id, trigger="schedule", scheduled_for=at, odds_mode=slot.odds)); s.commit()
    assert scheduler._already_ran(slot, at)
    assert scheduler.mark_interrupted() == 1
    assert not scheduler._already_ran(slot, at)
    scheduler._fire(slot, at, "catch-up", scheduler.threading.Event())
    with SessionLocal() as s:
        assert sorted(r.status for r in s.query(SyncRun)) == ["interrupted", "ok"]
        s.query(SyncRun).filter(SyncRun.status == "ok").update({"status": "running"}); s.commit()
    scheduler.mark_interrupted()   # cut off a second time: a third try would likely crash again
    assert scheduler._already_ran(slot, at)


def test_admin_page_needs_the_password(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    with TestClient(main.app, client=("203.0.113.9", 4000)) as remote:
        assert remote.get("/api/admin").status_code == 403
        assert remote.post("/api/admin/run/wed-odds").status_code == 403
        r = remote.get("/api/admin", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert {s["id"] for s in body["slots"]} == {s.id for s in scheduler.SLOTS}
    assert body["credits"] == {**body["credits"], "error": "No ODDS_API_KEY set", "floor": 75}


def test_admin_can_run_a_slot_now_and_see_it_in_the_log(monkeypatch):
    monkeypatch.setattr(scheduler.pipeline, "refresh_odds", lambda mode, log=print, **kw: {})
    with TestClient(main.app) as local:
        assert local.post("/api/admin/run/nope").status_code == 404
        assert local.post("/api/admin/run/thu-injuries").status_code == 202
        body = local.get("/api/admin").json()
        run = body["runs"][0]
        assert (run["slot"], run["trigger"], run["status"], run["label"]) == ("thu-injuries", "manual", "ok", "Thursday injuries")
        assert next(s for s in body["slots"] if s["id"] == "thu-injuries")["last_run"]["id"] == run["id"]
        assert local.get(f"/api/admin/runs/{run['id']}").json()["log"] == ["fake run"]


def test_meta_shows_the_next_sync_only_when_the_schedule_is_on(monkeypatch):
    with TestClient(main.app) as c:
        assert c.get("/api/meta").json()["auto_sync"] == {"enabled": False, "next_at": None, "next_label": None}
        monkeypatch.setenv("AUTO_SYNC", "1")
        monkeypatch.setattr(scheduler, "start", lambda: False)
        auto = c.get("/api/meta").json()["auto_sync"]
    assert auto["enabled"] and auto["next_label"] in {s.label for s in scheduler.SLOTS}


def test_admin_credits_show_the_spare_key_too(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "main-key-aaaa")
    monkeypatch.setenv("ODDS_API_KEY_NFL_SECONDARY", "spare-key-bbbb")
    monkeypatch.setattr(main.odds, "credits_remaining", lambda key: {"main-key-aaaa": 300, "spare-key-bbbb": 480}[key])
    main._credits.clear()
    with TestClient(main.app) as local:
        c = local.get("/api/admin").json()["credits"]
    assert c["key_name"] == "ODDS_API_KEY" and c["remaining"] == 300 and c["rotate"] == []
    assert c["others"] == [dict(key_name="ODDS_API_KEY_NFL_SECONDARY", key_hint="bbbb", remaining=480, error=None)]
