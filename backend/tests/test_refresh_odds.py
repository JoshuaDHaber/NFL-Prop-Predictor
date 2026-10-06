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
    monkeypatch.setattr(pipeline.odds, "list_events", lambda key: [dict(id="evt1", away="AWY", home="HOM"), dict(id="evt2", away="CCC", home="DDD")])
    calls = []

    def fake_fetch(key, event_id, main_kinds, alt_kinds=()):
        calls.append((event_id, sorted(main_kinds), sorted(alt_kinds)))
        rows = []
        player = {"evt1": "Test Back", "evt2": "Other Back"}[event_id]
        for kind in main_kinds:
            for side, odds in (("over", -110), ("under", -110)):
                rows.append(dict(player=player, market=kind, alt=False, side=side, line=60.5, odds=odds, book="X", link=None, event_link="https://sportsbook.draftkings.com/event/1"))
        for kind in alt_kinds:
            rows.append(dict(player=player, market=kind, alt=True, side="over", line=80.5, odds=250, book="X", link="https://sportsbook.draftkings.com/?outcomes=A", event_link=None))
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


# ---------- a new week, and games whose lines post at different times ----------
GAME2 = "2026_99_CCC_DDD"
TWO = pd.DataFrame([dict(game_id=GAME, away_team="AWY", home_team="HOM", season=2026, week=99, gameday="2026-10-11"),
                    dict(game_id=GAME2, away_team="CCC", home_team="DDD", season=2026, week=99, gameday="2026-10-12")])


def test_a_new_weeks_games_are_fetched_in_full_even_though_every_market_already_has_lines(clean_and_stub, monkeypatch):
    pipeline.refresh_odds("missing", log=lambda m: None)            # last week: GAME
    clean_and_stub.clear()
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO.iloc[[1]])   # the next week's game is a different one
    pipeline.refresh_odds("missing", log=lambda m: None)
    assert clean_and_stub == [("evt2", ["pass", "rec", "rr", "rush", "td"], ["pass", "rec", "rr", "rush"])]  # main AND alternates
    from app.db import current_lines
    with SessionLocal() as s:
        assert set(current_lines(s).player) == {"Test Back", "Other Back"}      # last week's lines are not hidden by the new fetch


def test_lines_fetched_for_a_later_game_do_not_hide_the_earlier_ones(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO.iloc[[0]])
    pipeline.refresh_odds("missing", log=lambda m: None)            # Thursday: only game 1 has lines
    clean_and_stub.clear()
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO)
    pipeline.refresh_odds("missing", log=lambda m: None)            # Sunday: game 1 is already covered, game 2 is not
    assert [c[0] for c in clean_and_stub] == ["evt2"]
    from app.db import current_lines
    with SessionLocal() as s:
        assert set(current_lines(s).player) == {"Test Back", "Other Back"}


def test_only_the_markets_a_game_lacks_are_fetched(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO.iloc[[0]])
    pipeline.refresh_odds("missing", log=lambda m: None)
    with SessionLocal() as s:
        s.query(OddsLine).filter(OddsLine.market == "td").delete(); s.commit()          # TD lines vanished for this game
    clean_and_stub.clear()
    pipeline.refresh_odds("missing", log=lambda m: None)
    assert clean_and_stub == [("evt1", ["td"], [])]


def test_refetching_a_game_replaces_its_old_quotes_instead_of_piling_up(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO.iloc[[0]])
    pipeline.refresh_odds("missing", log=lambda m: None)
    with SessionLocal() as s:
        before = s.query(OddsLine).count()
    pipeline.refresh_odds("all", log=lambda m: None)
    with SessionLocal() as s:
        assert s.query(OddsLine).count() == before


def test_the_plan_prices_a_sync_before_it_runs(clean_and_stub):
    with SessionLocal() as s:
        plan = pipeline.sync_plan(s, TWO, "missing")
        assert plan["week"] == 99 and plan["total_games"] == 2 and len(plan["games"]) == 2
        assert plan["credits"] == 2 * (5 + 4)                       # five main markets + four alternate markets, per game
        pipeline.refresh_odds("missing", log=lambda m: None)
    with SessionLocal() as s:
        covered = pipeline.sync_plan(s, TWO.iloc[[0]], "missing")
        assert covered["games"] == [] and covered["credits"] == 0   # nothing left to buy for game 1
        assert pipeline.sync_plan(s, TWO.iloc[[0]], "all")["credits"] == 9


# ---------- thin games and progress ----------
def age_everything(hours):
    from datetime import datetime, timedelta
    with SessionLocal() as s:
        for model_ in (OddsLine, AltLine):
            s.query(model_).update({"fetched_at": datetime.utcnow() - timedelta(hours=hours)})
        s.commit()


def test_games_with_few_old_quotes_are_topped_up_in_thin_mode_only(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO)
    pipeline.refresh_odds("missing", log=lambda m: None)         # both games stored, 9 quotes each: thin
    with SessionLocal() as s:
        fresh = pipeline.sync_plan(s, TWO, "thin")
        assert fresh["games"] == []                              # just fetched: lines may still be arriving, don't re-buy yet
    age_everything(5)
    with SessionLocal() as s:
        assert pipeline.sync_plan(s, TWO, "missing")["games"] == []          # 'missing' never re-buys a covered game
        thin = pipeline.sync_plan(s, TWO, "thin")
    assert [g["reason"] for g in thin["games"]] == ["thin", "thin"]
    assert [g["stored_quotes"] for g in thin["games"]] == [9, 9] and thin["credits"] == 18
    monkeypatch.setattr(pipeline, "THIN_MIN_QUOTES", 5)           # a game with plenty of lines isn't thin
    with SessionLocal() as s:
        assert pipeline.sync_plan(s, TWO, "thin")["games"] == []


def test_thin_mode_refetches_those_games_in_full_and_buys_missing_ones_too(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO.iloc[[0]])
    pipeline.refresh_odds("missing", log=lambda m: None)         # game 1 only, early in the week
    age_everything(5)
    clean_and_stub.clear()
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO)  # now game 2 exists too
    pipeline.refresh_odds("thin", log=lambda m: None)
    assert [c[0] for c in clean_and_stub] == ["evt1", "evt2"]     # game 1 topped up, game 2 fetched for the first time
    assert all(c[1] == ["pass", "rec", "rr", "rush", "td"] and c[2] == ["pass", "rec", "rr", "rush"] for c in clean_and_stub)


def test_progress_is_reported_game_by_game(clean_and_stub, monkeypatch):
    monkeypatch.setattr(pipeline, "upcoming_games", lambda: TWO)
    seen = []
    pipeline.refresh_odds("missing", log=lambda m: None, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(0, 2), (1, 2), (2, 2)]
