from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main, scheduler
from app.db import NbaOddsLine, NbaProjection, NbaRun, SessionLocal
from app.nba import espn, model
from app.nba import pipeline as nba_pipeline
from app.nba import routes as nba_routes

GID = "2027_20261020_BOS_DET"


def test_scoreboard_keeps_real_games_with_eastern_times_and_home_spread():
    js = {"events": [
        {"id": "1", "date": "2026-10-20T23:30Z", "season": {"year": 2027, "type": 2},
         "competitions": [{"competitors": [
             {"homeAway": "home", "team": {"abbreviation": "DET", "displayName": "Detroit Pistons"}},
             {"homeAway": "away", "team": {"abbreviation": "BOS", "displayName": "Boston Celtics"}}],
             "status": {"type": {"state": "pre"}}, "odds": [{"spread": -4.5, "overUnder": 221.5}]}]},
        {"id": "2", "date": "2026-10-10T23:30Z", "season": {"year": 2027, "type": 1},   # preseason: left out
         "competitions": [{"competitors": [], "status": {"type": {"state": "pre"}}}]},
    ]}
    [g] = espn.parse_scoreboard(js)
    assert g["game_id"] == "2027_20261020_BOS_DET" and (g["gameday"], g["gametime"]) == ("2026-10-20", "19:30")
    assert g["spread_line"] == 4.5 and g["total"] == 221.5   # the home team favored by 4.5


def test_gamelog_parses_regular_season_games_with_home_and_eastern_date():
    names = ["minutes", "fieldGoalsMade-fieldGoalsAttempted", "totalRebounds", "assists", "points"]
    js = {"names": names,
          "events": {"9": {"atVs": "@", "gameDate": "2026-01-10T00:30:00.000+00:00", "team": {"abbreviation": "BOS"},
                           "opponent": {"abbreviation": "NY"}, "homeTeamScore": "110", "awayTeamScore": "104"}},
          "seasonTypes": [{"displayName": "2025-26 Regular Season", "categories": [
              {"type": "event", "events": [{"eventId": "9", "stats": ["34", "9-18", "7", "5", "27"]}]},
              {"type": "total", "events": []}]},
              {"displayName": "2025-26 Preseason", "categories": [{"type": "event", "events": [{"eventId": "9", "stats": ["1"] * 5}]}]}]}
    [r] = espn.parse_gamelog(js, "p1")
    assert r["season"] == 2026 and r["date"] == "2026-01-09" and r["home"] is False
    assert (r["min"], r["pts"], r["reb"], r["ast"], r["home_score"]) == (34.0, 27.0, 7.0, 5.0, 110.0)


def _logs(n=40, start=date(2025, 11, 1)):
    """Two players on two teams: a 30-point guard and a 10-rebound center, one game every other day."""
    rows = []
    for i in range(n):
        d = (start + timedelta(days=2 * i)).isoformat()
        rows.append(dict(player_id="g", event_id=str(i), season=2026, date=d, team="BOS", opp="NY", home=True,
                         min=36.0, pts=30.0 + (i % 3), reb=4.0, ast=7.0, home_score=110.0 + i % 5, away_score=105.0))
        rows.append(dict(player_id="c", event_id=str(i), season=2026, date=d, team="NY", opp="BOS", home=False,
                         min=30.0, pts=12.0, reb=10.0 + (i % 2), ast=2.0, home_score=110.0 + i % 5, away_score=105.0))
    return pd.DataFrame(rows)


def test_projection_is_minutes_times_a_rate_shrunk_toward_the_position():
    logs = _logs()
    pos = {"g": "G", "c": "C"}
    st = model.states(logs, pos, 2026, model.priors(logs, pos))
    assert st["g"]["min"] == pytest.approx(36.0)
    mu = model.project_rows(st["g"], {k: {} for k in model.KINDS}, "NY")
    assert 29 < mu["pts"][0] < 32 and mu["pts"][0] == pytest.approx(36.0 * mu["pts"][1])
    # too few games: not projected
    assert "g" not in model.states(logs.head(6), pos, 2026, model.priors(logs, pos))


def test_walk_forward_and_team_ratings_run_on_the_logs():
    logs = _logs(60)
    bt = model.walk_forward(logs, {"g": "G", "c": "C"}, date(2025, 12, 15), date(2026, 2, 1))
    assert set(bt.kind) == set(model.KINDS) and np.isfinite(bt.mu).all()
    summary, dists = model.calibrate(bt)
    assert summary["pts"]["n"] > 0 and "z" in dists["pts"]
    games = espn.team_games(logs)
    r, hfa = model.ratings(games, date(2026, 3, 1))
    assert r["BOS"] > r["NY"]   # BOS won every game at home


@pytest.fixture()
def nba_client(monkeypatch):
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.query(NbaProjection).delete()
        s.query(NbaRun).delete()
        start = (datetime.utcnow() + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%MZ")
        game = dict(event_id="1", game_id=GID, season=2027, gameday="2026-10-20", gametime="19:30", start=start,
                    home="DET", away="BOS", state="pre", spread_line=1.5, total=221.5)
        run = NbaRun(season=2027, slate=["2026-10-20"], backtest={"pts": dict(n=10, mae_model=5.0, mae_naive=5.1, bias=0.0)},
                     variance={}, excluded=["Hurt Guy (Out)"], games=[game],
                     teams={GID: dict(home="DET", away="BOS", gameday="2026-10-20", gametime="19:30", margin=2.0,
                                      p_home=0.56, home_rating=1.0, away_rating=0.5, spread=1.5, total=221.5)})
        run.projections = [NbaProjection(player_id="p1", name="Star Guard", pos="PG", team="DET", opp="BOS", home=True,
                                         kind=k, mu=mu, sd=sd, vol=36.0, eff=mu / 36, spread=1.5, status="", game_id=GID,
                                         gameday="2026-10-20", gametime="19:30", last5=[mu] * 5, wx=1.0, teammate_out="")
                           for k, mu, sd in (("pts", 28.0, 6.0), ("reb", 5.0, 2.0), ("ast", 8.0, 2.5))]
        s.add(run)
        t = datetime.utcnow()
        s.add_all([NbaOddsLine(fetched_at=t, player="Star Guard", market="pts", line=24.5, over_odds=-110, under_odds=-110, book="FanDuel", game_id=GID),
                   NbaOddsLine(fetched_at=t, player="Detroit Pistons", market="ml", line=0.0, over_odds=-130, under_odds=110, book="FanDuel", game_id=GID)])
        s.commit()
    nba_routes.clear_caches()
    monkeypatch.setattr(nba_routes, "_injuries", lambda slot: ([dict(player_id="p9", name="Hurt Guy", team="BOS", pos="C", status="Out",
                                                                      injury="Knee", comment="Out for the opener", updated=None, return_date="2026-11-01")], None))
    with TestClient(main.app) as c:
        yield c


def test_nba_meta_lists_the_slate_and_books(nba_client):
    m = nba_client.get("/api/nba/meta").json()
    assert m["league"] == "nba" and m["run"]["slate"] == ["2026-10-20"]
    assert [g["label"] for g in m["games"]] == ["BOS @ DET"] and m["books"] == ["FanDuel"]
    assert m["odds"]["pts"]["lines"] == 1 and m["supports_alt"] is False


def test_nba_picks_moneylines_and_projections(nba_client):
    picks = nba_client.get("/api/nba/picks", params={"min_ev": -1}).json()
    over = next(p for p in picks if p["side"] == "Over")
    assert over["kind"] == "pts" and over["line"] == 24.5 and over["prob"] > 0.5
    [ml] = nba_client.get("/api/nba/moneylines").json()
    away, home = ml["sides"]
    assert (away["team"], home["team"]) == ("BOS", "DET") and home["odds"] == -130 and ml["total"] == 221.5
    assert len(nba_client.get("/api/nba/projections", params={"kind": "reb"}).json()) == 1
    # the NFL board never sees NBA quotes
    assert all(g["game_id"] != GID for g in nba_client.get("/api/moneylines").json())


def test_nba_games_that_tipped_off_drop_off_the_board(nba_client):
    with SessionLocal() as s:
        run = s.query(NbaRun).one()
        run.games = [dict(run.games[0], start=(datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%MZ"))]
        s.commit()
    assert nba_client.get("/api/nba/meta").json()["games"] == []
    assert nba_client.get("/api/nba/moneylines").json() == []
    assert nba_client.get("/api/nba/picks", params={"min_ev": -1}).json() == []


def test_nba_injuries_cover_slate_teams(nba_client):
    rep = nba_client.get("/api/nba/injuries").json()
    [p] = rep["teams"]["BOS"]
    assert p["status"] == "Out" and p["comment"] == "Out for the opener" and p["return_date"] == "2026-11-01"


def test_nba_player_lines_ladder(nba_client):
    lad = nba_client.get("/api/nba/players/p1/lines", params={"kind": "pts"}).json()
    assert [q["line"] for q in lad["quotes"]] == [24.5]
    assert nba_client.get("/api/nba/players/p1/lines", params={"kind": "rush"}).status_code == 422


def test_odds_plan_buys_props_only_for_games_tipping_off_soon():
    now = datetime(2026, 10, 20, 14)
    soon = dict(game_id="a", away="BOS", home="DET", gameday="2026-10-20", start="2026-10-20T23:30Z")
    tomorrow = dict(game_id="b", away="NY", home="SA", gameday="2026-10-21", start="2026-10-22T00:30Z")
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.add(NbaOddsLine(fetched_at=now, player="X", market="pts", line=20.5, over_odds=-110, under_odds=-110, book="B", game_id="a"))
        s.commit()
        plan = nba_pipeline.sync_plan(s, [soon, tomorrow], "missing", now)
        assert [g["game_id"] for g in plan["games"]] == ["a"] and plan["games"][0]["need"] == ["reb", "ast"]
        assert plan["credits"] == 1 + 2   # one for every moneyline, one per missing market
        assert nba_pipeline.sync_plan(s, [soon, tomorrow], "all", now)["games"][0]["need"] == ["pts", "reb", "ast"]
        assert nba_pipeline.sync_plan(s, [soon], "none", now)["credits"] == 0


def test_refresh_odds_stores_moneylines_and_props(monkeypatch):
    slate = [dict(game_id=GID, away="BOS", home="DET", gameday="2026-10-20", start="2026-10-20T23:30Z")]
    monkeypatch.setattr(nba_pipeline.config, "ODDS_API_KEY_NBA", lambda: "k")
    monkeypatch.setattr(nba_pipeline.espn, "slate", lambda now=None: slate)
    monkeypatch.setattr(nba_pipeline.nba_odds, "list_events",
                        lambda key: [dict(id="e1", away="BOS", home="DET", commence="2026-10-20T23:30:00Z")])
    ml = pd.DataFrame([dict(player="Detroit Pistons", market="ml", alt=False, side="over", line=0.0, odds=-130, book="FanDuel", link=None, event_link=None),
                       dict(player="Detroit Pistons", market="ml", alt=False, side="under", line=0.0, odds=110, book="FanDuel", link=None, event_link=None)])
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_moneylines", lambda key: ({"e1": ml}, "500"))
    props = pd.DataFrame([dict(player="Star Guard", market="pts", alt=False, side=s_, line=24.5, odds=-110, book="FanDuel", link=None, event_link=None)
                          for s_ in ("over", "under")])
    calls = []
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_props", lambda key, eid, kinds: (calls.append((eid, kinds)), (props, "497"))[1])
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.commit()
    res = nba_pipeline.refresh_odds("missing", log=lambda m: None, now=datetime(2026, 10, 20, 14))
    assert calls == [("e1", ["pts", "reb", "ast"])] and res["fetched"] == 1 and res["credits_after"] == 497
    with SessionLocal() as s:
        assert sorted(m for (m,) in s.query(NbaOddsLine.market)) == ["ml", "pts"]


def test_nba_slots_are_scheduled_apart_from_the_nfl():
    nba = [s for _, s in scheduler.upcoming(league="nba")]
    assert nba and all(s.league == "nba" for s in nba)
    assert all(s.league == "nfl" for _, s in scheduler.upcoming(league="nfl"))
