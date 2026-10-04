"""refresh_odds: one API call per upcoming game, storing main and alternate lines."""
import pandas as pd
import pytest

from app import config, pipeline
from app.db import AltLine, OddsLine, SessionLocal

GAME = "2026_99_AWY_HOM"


@pytest.fixture(autouse=True)
def clean_and_stub(monkeypatch):
    with SessionLocal() as s:
        s.query(AltLine).delete(); s.query(OddsLine).delete(); s.commit()
    monkeypatch.setattr(config, "ODDS_API_KEY", lambda: "test-key")
    monkeypatch.setattr(pipeline.config, "ODDS_API_KEY", lambda: "test-key")
    games = pd.DataFrame([dict(game_id=GAME, away_team="AWY", home_team="HOM")])
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: games)
    monkeypatch.setattr(pipeline.odds, "list_events", lambda key: [dict(id="evt1", away="AWY", home="HOM")])
    calls = []

    def fake_fetch(key, event_id, main_kinds, alt_kinds=()):
        calls.append((event_id, sorted(main_kinds), sorted(alt_kinds)))
        rows = []
        for kind in main_kinds:
            for side, odds in (("over", -110), ("under", -110)):
                rows.append(dict(player="Test Back", market=kind, alt=False, side=side, line=60.5, odds=odds, book="X", link=None, event_link="https://sportsbook.draftkings.com/event/1"))
        for kind in alt_kinds:
            rows.append(dict(player="Test Back", market=kind, alt=True, side="over", line=80.5, odds=250, book="X", link="https://sportsbook.draftkings.com/?outcomes=A", event_link=None))
        return pd.DataFrame(rows), "400"

    monkeypatch.setattr(pipeline.odds, "fetch_game_odds", fake_fetch)
    return calls


def test_first_refresh_fetches_main_and_alternate_lines_for_every_game(clean_and_stub):
    pipeline.refresh_odds("missing", log=lambda m: None)
    # anytime TD is a main market with no alternates
    assert clean_and_stub == [("evt1", ["pass", "rec", "rr", "rush", "td"], ["pass", "rec", "rr", "rush"])]
    with SessionLocal() as s:
        assert {m for (m,) in s.query(OddsLine.market).distinct()} == {"rush", "rec", "pass", "rr", "td"}
        assert s.query(AltLine).filter(AltLine.game_id == GAME).count() == 4
        assert s.query(AltLine).first().over_link == "https://sportsbook.draftkings.com/?outcomes=A"


def test_second_refresh_spends_nothing_when_everything_is_stored(clean_and_stub):
    pipeline.refresh_odds("missing", log=lambda m: None)
    clean_and_stub.clear()
    pipeline.refresh_odds("missing", log=lambda m: None)
    assert clean_and_stub == []


def test_missing_mode_adds_only_alternates_for_games_that_lack_them(clean_and_stub):
    pipeline.refresh_odds("missing", log=lambda m: None)
    with SessionLocal() as s:
        s.query(AltLine).delete(); s.commit()
    clean_and_stub.clear()
    pipeline.refresh_odds("missing", log=lambda m: None)
    assert clean_and_stub == [("evt1", [], ["pass", "rec", "rr", "rush"])]  # no main markets re-bought


def test_all_mode_refetches_everything_and_replaces_old_alternates(clean_and_stub):
    pipeline.refresh_odds("missing", log=lambda m: None)
    clean_and_stub.clear()
    pipeline.refresh_odds("all", log=lambda m: None)
    assert len(clean_and_stub) == 1 and clean_and_stub[0][1] == ["pass", "rec", "rr", "rush", "td"]
    with SessionLocal() as s:
        assert s.query(AltLine).filter(AltLine.game_id == GAME).count() == 4  # replaced, not doubled


def test_none_mode_and_missing_key_do_nothing(clean_and_stub, monkeypatch):
    pipeline.refresh_odds("none", log=lambda m: None)
    monkeypatch.setattr(pipeline.config, "ODDS_API_KEY", lambda: None)
    pipeline.refresh_odds("missing", log=lambda m: None)
    assert clean_and_stub == []
