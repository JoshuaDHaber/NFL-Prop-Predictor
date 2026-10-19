from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main, scheduler
from app.db import NbaAltLine, NbaOddsLine, NbaProjection, NbaRun, SessionLocal
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
    names = ["minutes", "fieldGoalsMade-fieldGoalsAttempted", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "totalRebounds", "assists", "points"]
    js = {"names": names,
          "events": {"9": {"atVs": "@", "gameDate": "2026-01-10T00:30:00.000+00:00", "team": {"abbreviation": "BOS"},
                           "opponent": {"abbreviation": "NY"}, "homeTeamScore": "110", "awayTeamScore": "104"}},
          "seasonTypes": [{"displayName": "2025-26 Regular Season", "categories": [
              {"type": "event", "events": [{"eventId": "9", "stats": ["34", "9-18", "3-7", "7", "5", "27"]}]},
              {"type": "total", "events": []}]},
              {"displayName": "2025-26 Preseason", "categories": [{"type": "event", "events": [{"eventId": "9", "stats": ["1"] * 6}]}]}]}
    [r] = espn.parse_gamelog(js, "p1")
    assert r["season"] == 2026 and r["date"] == "2026-01-09" and r["home"] is False
    assert (r["min"], r["pts"], r["reb"], r["ast"], r["threes"], r["home_score"]) == (34.0, 27.0, 7.0, 5.0, 3.0, 110.0)


def test_gamelogs_leave_out_all_star_weekend(monkeypatch):
    """ESPN files the All-Star game under the regular season; it isn't an NBA team's game."""
    names = ["minutes", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "totalRebounds", "assists", "points"]
    game = lambda team, opp, day: {"atVs": "vs", "gameDate": f"{day}T00:30:00.000+00:00", "team": {"abbreviation": team},  # noqa: E731
                                   "opponent": {"abbreviation": opp}, "homeTeamScore": "110", "awayTeamScore": "104"}
    js = {"names": names, "events": {"1": game("BOS", "NY", "2026-02-10"), "2": game("STARS", "STRIPES", "2026-02-16")},
          "seasonTypes": [{"displayName": "2025-26 Regular Season", "categories": [{"type": "event", "events": [
              {"eventId": "1", "stats": ["34", "3-7", "7", "5", "27"]}, {"eventId": "2", "stats": ["12", "4-6", "2", "1", "14"]}]}]}]}
    monkeypatch.setattr(espn, "_download", lambda url: js)
    logs = espn.gamelogs(["asg1"], [2026], 2027, log=lambda _: None)
    assert list(logs.team) == ["BOS"]


def _logs(n=40, start=date(2025, 11, 1)):
    """Two players on two teams: a 30-point guard and a 10-rebound center, one game every other day."""
    rows = []
    for i in range(n):
        d = (start + timedelta(days=2 * i)).isoformat()
        rows.append(dict(player_id="g", event_id=str(i), season=2026, date=d, team="BOS", opp="NY", home=True,
                         min=36.0, pts=30.0 + (i % 3), reb=4.0, ast=7.0, threes=3.0 + (i % 2), home_score=110.0 + i % 5, away_score=105.0))
        rows.append(dict(player_id="c", event_id=str(i), season=2026, date=d, team="NY", opp="BOS", home=False,
                         min=30.0, pts=12.0, reb=10.0 + (i % 2), ast=2.0, threes=0.0, home_score=110.0 + i % 5, away_score=105.0))
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
    assert summary["threes"]["n"] > 0 and dists["threes"] == {"poisson": True}
    games = espn.team_games(logs)
    r, hfa = model.ratings(games, date(2026, 3, 1))
    assert r["BOS"] > r["NY"]   # BOS won every game at home
    # what the same-game correlations need: each row's game (team, opponent, date ordinal) and position group
    g = bt[bt.player_id == "g"].iloc[0]
    assert (g.team, g.opp, g.pos, g.t) == ("BOS", "NY", "G", date.fromisoformat(g.date).toordinal())
    assert set(bt[bt.player_id == "c"].pos) == {"C"}


def _shooter_logs(n=150, start=date(2025, 10, 25)):
    """Four guards on two teams, one game a day: a player's points move with his threes, players are independent."""
    rng = np.random.default_rng(7)
    rows = []
    for i in range(n):
        d = (start + timedelta(days=i)).isoformat()
        for pid, team, opp, home in (("g1", "BOS", "NY", True), ("g2", "BOS", "NY", True), ("g3", "NY", "BOS", False), ("g4", "NY", "BOS", False)):
            threes = float(rng.poisson(3.0))
            rows.append(dict(player_id=pid, event_id=str(i), season=2026, date=d, team=team, opp=opp, home=home, min=34.0,
                             pts=max(0.0, 12.0 + 3.0 * threes + rng.normal(0, 3)), reb=float(rng.poisson(5)), ast=float(rng.poisson(5)),
                             threes=threes, home_score=110.0 + i % 7, away_score=106.0))
    return pd.DataFrame(rows)


def test_nba_run_stores_same_game_correlations(monkeypatch):
    logs = _shooter_logs()
    now = datetime(2026, 3, 20, 15)
    game = dict(event_id="9", game_id="2026_20260321_NY_BOS", season=2026, gameday="2026-03-21", gametime="19:30",
                start="2026-03-21T23:30Z", home="BOS", away="NY", state="pre", spread_line=-2.5, total=220.5)
    ro = pd.DataFrame([dict(player_id=p, name=p.upper(), pos=x, team=t, headshot=None)
                       for p, x, t in (("g1", "PG", "BOS"), ("g2", "SG", "BOS"), ("g3", "G", "NY"), ("g4", "PG", "NY"))])
    monkeypatch.setattr(nba_pipeline.espn, "slate", lambda now=None: [game])
    monkeypatch.setattr(nba_pipeline.espn, "rosters", lambda: ro)
    monkeypatch.setattr(nba_pipeline.espn, "gamelogs", lambda *a, **k: logs)
    monkeypatch.setattr(nba_pipeline.espn, "injuries", lambda: ([], None))
    monkeypatch.setattr(nba_pipeline.grading, "grade_logged", lambda *a, **k: None)
    log = []
    rid = nba_pipeline.run_projections(log=log.append, now=now)
    with SessionLocal() as s:
        corr = s.get(NbaRun, rid).variance["_correlation"]
    pairs = corr["pairs"]
    assert pairs["same|pts:G|threes:G"][0] > 0.5
    assert all(abs(r) < 0.3 for k, (r, n) in pairs.items() if not k.startswith("same|"))
    assert corr["check"]["positive"]["n"] > 0 and corr["check"]["triples"] == dict(n=0)   # the QB triple check is NFL-only
    assert any(m.strip().startswith("Same-game correlations:") for m in log)
    with TestClient(main.app) as c:
        js = c.get("/api/nba/correlations").json()
    assert js["pairs"]["same|pts:G|threes:G"] == pairs["same|pts:G|threes:G"][0] and "positive" in js["check"]


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


def test_nba_correlations_are_empty_for_a_run_fitted_before_them(nba_client):
    assert nba_client.get("/api/nba/correlations").json() == dict(pairs={}, check={})


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


def test_nba_player_lines_ladder_includes_alternates(nba_client):
    lad = nba_client.get("/api/nba/players/p1/lines", params={"kind": "pts"}).json()
    assert [q["line"] for q in lad["quotes"]] == [24.5]
    with SessionLocal() as s:
        s.query(NbaAltLine).delete()
        s.add(NbaAltLine(fetched_at=datetime.utcnow(), game_id=GID, player="Star Guard", market="pts", line=29.5, over_odds=150, book="FanDuel"))
        s.commit()
    lad = nba_client.get("/api/nba/players/p1/lines", params={"kind": "pts"}).json()
    assert [(q["line"], q["alt"]) for q in lad["quotes"]] == [(24.5, False), (29.5, True)] and lad["alt_fetched_at"]
    assert nba_client.get("/api/nba/players/p1/lines", params={"kind": "rush"}).status_code == 422


def test_odds_plan_buys_props_only_for_games_tipping_off_soon():
    now = datetime(2026, 10, 20, 14)
    soon = dict(game_id="a", away="BOS", home="DET", gameday="2026-10-20", start="2026-10-20T23:30Z")
    tomorrow = dict(game_id="b", away="NY", home="SA", gameday="2026-10-21", start="2026-10-22T00:30Z")
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.query(NbaAltLine).delete()
        s.add(NbaOddsLine(fetched_at=now, player="X", market="pts", line=20.5, over_odds=-110, under_odds=-110, book="B", game_id="a"))
        s.add(NbaAltLine(fetched_at=now, game_id="a", player="X", market="pts", line=25.5, over_odds=200, book="B"))
        s.commit()
        plan = nba_pipeline.sync_plan(s, [soon, tomorrow], "missing", now)
        [g] = plan["games"]
        assert g["game_id"] == "a" and g["need"] == ["reb", "ast", "threes"] and g["need_alt"] == ["reb", "ast", "threes"]
        assert plan["credits"] == 1 + 3 + 3   # one for every moneyline, one per missing market, main and alternate
        # 'all' re-pulls every main market, but alternates are bought once
        [g] = nba_pipeline.sync_plan(s, [soon, tomorrow], "all", now)["games"]
        assert g["need"] == ["pts", "reb", "ast", "threes"] and g["need_alt"] == ["reb", "ast", "threes"]
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
                          for s_ in ("over", "under")]
                         + [dict(player="Star Guard", market="pts", alt=True, side="over", line=29.5, odds=180, book="FanDuel", link="https://fd/x", event_link=None)])
    calls = []
    monkeypatch.setattr(nba_pipeline.nba_odds, "fetch_props", lambda key, eid, kinds, alt_kinds: (calls.append((eid, kinds, alt_kinds)), (props, "497"))[1])
    with SessionLocal() as s:
        s.query(NbaOddsLine).delete()
        s.query(NbaAltLine).delete()
        s.commit()
    res = nba_pipeline.refresh_odds("missing", log=lambda m: None, now=datetime(2026, 10, 20, 14))
    kinds = ["pts", "reb", "ast", "threes"]
    assert calls == [("e1", kinds, kinds)] and res["fetched"] == 1 and res["credits_after"] == 497
    with SessionLocal() as s:
        assert sorted(m for (m,) in s.query(NbaOddsLine.market)) == ["ml", "pts"]
        [alt] = s.query(NbaAltLine).all()
        assert (alt.line, alt.over_odds, alt.over_link) == (29.5, 180.0, "https://fd/x")


def test_nba_slots_are_scheduled_apart_from_the_nfl():
    nba = [s for _, s in scheduler.upcoming(league="nba")]
    assert nba and all(s.league == "nba" for s in nba)
    assert all(s.league == "nfl" for _, s in scheduler.upcoming(league="nfl"))


def test_threes_are_priced_as_poisson_counts():
    from scipy.stats import poisson
    from app.engine.model import prob_over_under_dist, sd_at
    po, pu = prob_over_under_dist(2.2, 1.5, {"poisson": True})
    assert po == pytest.approx(poisson.sf(1, 2.2)) and po + pu == pytest.approx(1.0)
    po, pu = prob_over_under_dist(2.2, 2, {"poisson": True})   # a whole-number line leaves room for a push at 2
    assert po + pu == pytest.approx(1 - poisson.pmf(2, 2.2))
    assert sd_at(4.0, {"poisson": True}) == 2.0


def test_nba_player_search_covers_the_slate_and_rosters(nba_client, monkeypatch):
    roster = pd.DataFrame(dict(player_id=["p1", "r2", "r3"], name=["Star Guard", "Starling Wing", "Other Big"],
                               pos=["PG", "SF", "C"], team=["DET", "LAL", "MIA"], headshot=[None, None, "http://x/r3.png"]))
    monkeypatch.setattr(nba_routes, "_rosters", lambda slot: roster)
    hits = nba_client.get("/api/nba/player-search", params={"q": "star"}).json()
    assert [(h["name"], h["projected"]) for h in hits] == [("Star Guard", True), ("Starling Wing", False)]
    assert hits[1]["headshot"].endswith("/r2.png") and hits[1]["team"] == "LAL"
    assert nba_client.get("/api/nba/player-search", params={"q": "big"}).json()[0]["headshot"] == "http://x/r3.png"
