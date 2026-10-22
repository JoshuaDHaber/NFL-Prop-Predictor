"""Odds API requests: server errors are retried, and the API key never reaches an error message or a sync log."""
from datetime import datetime

import pandas as pd
import pytest
import requests

from app import scheduler
from app.db import NbaOddsLine, SessionLocal, SyncRun
from app.engine import odds
from app.nba import pipeline as nba_pipeline

URL = "https://api.the-odds-api.com/v4/sports"


class Resp:
    def __init__(self, status, headers=None):
        self.status_code, self.headers = status, headers or {}
        self.url = f"{URL}?apiKey=secret123"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error: Bad Gateway for url: {self.url}", response=self)

    def json(self):
        return []


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(odds, "_sleep", lambda s: None)


def test_a_502_is_retried_and_then_succeeds(monkeypatch):
    replies = iter([Resp(502), Resp(503), Resp(200, {"x-requests-remaining": "480"})])
    monkeypatch.setattr(odds.requests, "get", lambda *a, **k: next(replies))
    assert odds.credits_remaining("secret123") == 480


def test_a_lasting_502_raises_with_the_key_redacted(monkeypatch):
    calls = []
    monkeypatch.setattr(odds.requests, "get", lambda *a, **k: calls.append(1) or Resp(502))
    with pytest.raises(requests.HTTPError) as e:
        odds.credits_remaining("secret123")
    assert len(calls) == 3 and "secret123" not in str(e.value) and "apiKey=<redacted>" in str(e.value)


def test_client_errors_are_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(odds.requests, "get", lambda *a, **k: calls.append(1) or Resp(401))
    with pytest.raises(requests.HTTPError):
        odds.credits_remaining("secret123")
    assert len(calls) == 1


def test_redact_hides_keys_anywhere_in_text():
    assert odds.redact("for url: https://x/v4/sports?apiKey=abc123&regions=us") == "for url: https://x/v4/sports?apiKey=<redacted>&regions=us"


def _slate(monkeypatch):
    slate = [dict(game_id=f"2027_20261020_{a}_{h}", away=a, home=h, gameday="2026-10-20", start="2026-10-20T23:30Z")
             for a, h in (("BOS", "DET"), ("PHI", "NY"))]
    monkeypatch.setattr(nba_pipeline.config, "ODDS_API_KEY_NBA", lambda: "secret123")
    monkeypatch.setattr(nba_pipeline.espn, "slate", lambda now=None: slate)
    monkeypatch.setattr(nba_pipeline.nba_odds, "list_events", lambda key: [
        dict(id="e1", away="BOS", home="DET", commence="2026-10-20T23:30:00Z"), dict(id="e2", away="PHI", home="NY", commence="2026-10-20T23:30:00Z")])
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_moneylines", lambda key: ({}, "400"))
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.commit()


def test_a_failed_balance_check_or_game_does_not_stop_the_nba_sync(monkeypatch):
    _slate(monkeypatch)
    def boom(key):
        raise requests.HTTPError(f"502 Server Error: Bad Gateway for url: {URL}?apiKey=<redacted>")
    monkeypatch.setattr(nba_pipeline.nfl_odds, "credits_remaining", boom)
    props = pd.DataFrame([dict(player="Star Guard", market="pts", alt=False, side=s_, line=24.5, odds=-110, book="FanDuel", link=None, event_link=None)
                          for s_ in ("over", "under")])
    def fetch(key, eid, kinds, alt_kinds):
        if eid == "e1":
            raise requests.HTTPError("502 Server Error")
        return props, "390"
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_props", fetch)
    lines = []
    res = nba_pipeline.refresh_odds("missing", log=lines.append, credit_floor=75, now=datetime(2026, 10, 20, 14))
    assert res["fetched"] == 1 and res["failed"] == 1 and res["credits_after"] == 390
    assert any("couldn't check the balance" in l for l in lines)
    with SessionLocal() as s:
        assert s.query(NbaOddsLine).filter(NbaOddsLine.game_id == "2027_20261020_PHI_NY").count() == 1


def test_a_sync_error_is_logged_without_the_key(monkeypatch):
    monkeypatch.setattr(scheduler.nba_pipeline, "run_projections", lambda log: 1)
    def fail(*a, **k):
        raise requests.HTTPError(f"502 Server Error: Bad Gateway for url: {URL}?apiKey=secret123")
    monkeypatch.setattr(scheduler.nba_pipeline, "refresh_odds", fail)
    assert scheduler.claim()
    scheduler.run("missing", slot="nba-afternoon", league="nba")
    with SessionLocal() as s:
        rec = s.query(SyncRun).order_by(SyncRun.id.desc()).first()
        assert rec.status == "error" and "secret123" not in rec.error and "secret123" not in " ".join(rec.log)


def test_the_nba_sync_switches_to_the_spare_key_at_the_floor(monkeypatch):
    _slate(monkeypatch)
    monkeypatch.setattr(nba_pipeline.config, "ODDS_API_KEY_NBA_SECONDARY", lambda: "spare456")
    monkeypatch.setattr(nba_pipeline.nfl_odds, "credits_remaining", lambda key: {"secret123": 75, "spare456": 400}[key])
    used = []
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_moneylines", lambda key: used.append(key) or ({}, "399"))
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_props", lambda key, *a: used.append(key) or (pd.DataFrame(columns=["player", "market", "alt", "side", "line", "odds", "book", "link", "event_link"]), "391"))
    res = nba_pipeline.refresh_odds("missing", log=lambda m: None, credit_floor=75, now=datetime(2026, 10, 20, 14))
    assert set(used) == {"spare456"} and res["rotate"] == ["ODDS_API_KEY_NBA"] and res["skipped_for_credits"] == 0
