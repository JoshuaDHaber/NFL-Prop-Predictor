from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import OddsLine, Projection, Run, SessionLocal


@pytest.fixture(scope="module")
def client():
    with SessionLocal() as s:
        run = Run(season=2026, week=4, backtest={"rush": dict(n=10, mae_model=20.0, mae_naive=25.0, bias=0.5)},
                  variance={"rush": [1.0, 0.1]}, excluded=["Hurt Guy (Out)"])
        for i, (name, mu) in enumerate([("Alpha Back", 90.0), ("Beta Back", 40.0)]):
            run.projections.append(Projection(
                player_id=f"p{i}", name=name, pos="RB", team="AAA", opp="BBB", home=True, kind="rush", mu=mu, sd=30.0,
                vol=15.0, eff=4.5, spread=3.0, status="", game_id="2026_04_BBB_AAA", gameday="2026-10-04",
                gametime="13:00", last5=[50.0, 60.0, 70.0, 80.0, 90.0]))
        s.add(run)
        t = datetime(2026, 10, 3, 12)
        s.add_all([OddsLine(fetched_at=t, player="Alpha Back", market="rush", line=60.5, over_odds=-110, under_odds=-110, book="X"),
                   OddsLine(fetched_at=t, player="Beta Back", market="rush", line=40.5, over_odds=-110, under_odds=-110, book="X")])
        s.commit()
    with TestClient(main.app) as c:
        yield c


def test_meta_summarises_run_odds_and_games(client):
    m = client.get("/api/meta").json()
    assert m["run"]["week"] == 4 and m["run"]["excluded"] == ["Hurt Guy (Out)"]
    assert m["odds"]["rush"]["lines"] == 2
    assert m["games"][0]["label"] == "BBB @ AAA"
    assert m["backtest"]["rush"]["mae_naive"] == 25.0
    assert m["has_odds_key"] is False


def test_projections_filter_and_search(client):
    assert [p["name"] for p in client.get("/api/projections").json()] == ["Alpha Back", "Beta Back"]  # sorted by mu
    assert len(client.get("/api/projections", params={"q": "beta"}).json()) == 1
    assert client.get("/api/projections", params={"kind": "pass"}).json() == []


def test_picks_rank_by_ev_and_respect_filters(client):
    picks = client.get("/api/picks", params={"min_ev": 0.0}).json()
    assert picks[0]["name"] == "Alpha Back" and picks[0]["side"] == "Over"
    assert all(p["ev"] >= 0 for p in picks)
    assert client.get("/api/picks", params={"min_ev": 0.9}).json() == []
    assert client.get("/api/picks", params={"game_id": "nope"}).json() == []


def test_market_weight_changes_the_pricing(client):
    a = client.get("/api/picks", params={"min_ev": -1, "market_weight": 0}).json()[0]
    b = client.get("/api/picks", params={"min_ev": -1, "market_weight": 1}).json()[0]
    assert a["prob"] != b["prob"]


def test_invalid_parameters_are_rejected(client):
    assert client.get("/api/picks", params={"market_weight": 3}).status_code == 422
    assert client.get("/api/projections", params={"kind": "bogus"}).status_code == 422


def test_unknown_player_is_a_404(client):
    assert client.get("/api/players/nobody").status_code == 404


def test_refresh_runs_once_at_a_time(client, monkeypatch):
    monkeypatch.setattr(main.pipeline, "run_projections", lambda log=print: log("fake run"))
    monkeypatch.setattr(main.pipeline, "refresh_odds", lambda mode, log=print: None)
    main._job.update(state="running")
    assert client.post("/api/refresh", json={"odds": "none"}).status_code == 409
    main._job.update(state="idle")
    r = client.post("/api/refresh", json={"odds": "none"})
    assert r.status_code == 202
    assert client.get("/api/refresh/status").json()["state"] == "done"
