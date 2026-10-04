from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import AltLine, OddsLine, Projection, Run, SessionLocal


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


def test_picks_can_be_limited_to_one_sportsbook(client):
    assert client.get("/api/meta").json()["books"] == ["X"]
    assert client.get("/api/picks", params={"min_ev": 0.0, "book": "X"}).json()
    assert client.get("/api/picks", params={"min_ev": -1, "book": "Other"}).json() == []


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


def _seed_alt(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ODDS_API_KEY", lambda: "test-key")
    monkeypatch.setattr(main.config, "ODDS_API_KEY", lambda: "test-key")


def test_ladder_lists_main_quotes_priced(client):
    d = client.get("/api/players/p0/lines", params={"kind": "rush"}).json()
    assert d["alt_fetched_at"] is None
    row = d["quotes"][0]
    assert row["line"] == 60.5 and row["alt"] is False and row["over"]["ev"] > 0 > row["under"]["ev"]


def test_alt_fetch_needs_a_key(client):
    assert client.post("/api/players/p0/alt-lines").status_code == 400


def test_alt_fetch_stores_alternates_and_shows_them_in_the_ladder(client, monkeypatch):
    _seed_alt(monkeypatch)
    calls = []

    def fake(game_id, kinds, log=print):
        calls.append((game_id, kinds))
        from datetime import datetime
        with SessionLocal() as s:
            s.add_all([AltLine(fetched_at=datetime.utcnow(), game_id=game_id, player="Alpha Back", market="rush", line=ln,
                               over_odds=o, under_odds=None, book="X", over_link="https://book/slip", under_link=None,
                               event_link=None) for ln, o in [(80.5, 250), (100.5, 600)]])
            s.commit()
        return {"alt_quotes": 2, "linked": 0, "credits_remaining": "100"}

    monkeypatch.setattr(main.pipeline, "fetch_game_lines", fake)
    r = client.post("/api/players/p0/alt-lines")
    assert r.status_code == 200 and r.json()["alt_quotes"] == 2 and calls == [("2026_04_BBB_AAA", ["rush"])]
    d = client.get("/api/players/p0/lines", params={"kind": "rush", "odds_range": 0}).json()
    alts = [q for q in d["quotes"] if q["alt"]]
    assert [q["line"] for q in alts] == [80.5, 100.5] and alts[0]["over"]["link"] == "https://book/slip"
    assert d["alt_fetched_at"] is not None
    # default view hides prices beyond -300..+300: the +600 longshot is gone, the +250 stays
    d = client.get("/api/players/p0/lines", params={"kind": "rush"}).json()
    assert [q["line"] for q in d["quotes"] if q["alt"]] == [80.5]


def test_alt_fetch_reports_upstream_failures(client, monkeypatch):
    _seed_alt(monkeypatch)

    def boom(game_id, kinds, log=print):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(main.pipeline, "fetch_game_lines", boom)
    assert client.post("/api/players/p0/alt-lines").status_code == 502


def test_meta_reports_a_lan_address_for_sharing_to_phones(client):
    assert "lan_url" in client.get("/api/meta").json()


def test_other_devices_are_read_only(monkeypatch):
    """Phones on the LAN can read but not POST (refreshes and alt-line fetches spend API credits)."""
    with TestClient(main.app, client=("192.168.1.50", 50000)) as phone:
        assert phone.get("/api/meta").status_code == 200
        assert phone.post("/api/players/p0/alt-lines").status_code == 403
        assert phone.post("/api/refresh", json={"odds": "none"}).status_code == 403


def test_tailscale_address_is_recognised_in_ifconfig_output():
    sample = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.1.194 netmask 0xffffff00 broadcast 192.168.1.255
utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280
\tinet 100.101.102.103 --> 100.101.102.103 netmask 0xffffffff
"""
    assert main.tailscale_ip(sample) == "100.101.102.103"
    assert main.tailscale_ip("inet 100.20.1.1 netmask 0xff") is None  # outside 100.64.0.0/10
    assert main.tailscale_ip("inet 192.168.1.5 netmask 0xff") is None


def test_app_url_override_wins_for_sharing(client, monkeypatch):
    monkeypatch.setenv("APP_URL", "http://my-mac.tail1234.ts.net:8000/")
    assert client.get("/api/meta").json()["lan_url"] == "http://my-mac.tail1234.ts.net:8000"


# ---------- hosted-deployment behaviour: admin token, CORS, health, database URL ----------
def test_remote_writes_need_the_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    monkeypatch.setattr(main.pipeline, "run_projections", lambda log=print: None)
    monkeypatch.setattr(main.pipeline, "refresh_odds", lambda mode, log=print: None)
    with TestClient(main.app, client=("203.0.113.9", 4000)) as remote:
        assert remote.post("/api/refresh", json={"odds": "none"}).status_code == 403
        bad = remote.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 403
        ok = remote.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 202
        main._job.update(state="idle")


def test_meta_tells_each_client_whether_it_can_write(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    with TestClient(main.app, client=("203.0.113.9", 4000)) as remote:
        assert remote.get("/api/meta").json()["can_write"] is False
        assert remote.get("/api/meta", headers={"Authorization": "Bearer s3cret"}).json()["can_write"] is True
    with TestClient(main.app) as local:
        assert local.get("/api/meta").json()["can_write"] is True


def test_without_a_configured_token_remote_clients_stay_read_only(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with TestClient(main.app, client=("203.0.113.9", 4000)) as remote:
        assert remote.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": "Bearer "}).status_code == 403


def test_forbidden_responses_still_carry_cors_headers_so_the_browser_can_read_them():
    with TestClient(main.app, client=("203.0.113.9", 4000)) as remote:
        r = remote.post("/api/refresh", json={"odds": "none"}, headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 403 and r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_health_check(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_projection_refresh_can_be_turned_off_for_small_hosts(client, monkeypatch):
    calls = []
    monkeypatch.setenv("PROJECTIONS_ON_SERVER", "0")
    monkeypatch.setattr(main.pipeline, "run_projections", lambda log=print: calls.append("projections"))
    monkeypatch.setattr(main.pipeline, "refresh_odds", lambda mode, log=print: calls.append(f"odds:{mode}"))
    assert client.get("/api/meta").json()["can_run_projections"] is False
    client.post("/api/refresh", json={"odds": "missing"})
    assert calls == ["odds:missing"]
    main._job.update(state="idle")


def test_hosted_postgres_urls_are_pointed_at_the_installed_driver():
    from app import config
    assert config.normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert config.normalize_db_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert config.normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"


def test_a_kind_can_be_excluded_from_picks_and_projections(client):
    assert client.get("/api/projections", params={"exclude_kind": "rush"}).json() == []
    assert len(client.get("/api/projections", params={"exclude_kind": "td"}).json()) == 2
    assert client.get("/api/picks", params={"min_ev": -1, "exclude_kind": "rush"}).json() == []
    assert client.get("/api/picks", params={"min_ev": -1, "exclude_kind": "td"}).json()


def test_picks_can_be_limited_to_overs_or_unders(client):
    both = client.get("/api/picks", params={"min_ev": -1}).json()
    assert {p["side"] for p in both} == {"Over", "Under"}
    overs = client.get("/api/picks", params={"min_ev": -1, "side": "Over"}).json()
    unders = client.get("/api/picks", params={"min_ev": -1, "side": "Under"}).json()
    assert overs and unders and {p["side"] for p in overs} == {"Over"} and {p["side"] for p in unders} == {"Under"}
    assert len(overs) + len(unders) == len(both)
    assert client.get("/api/picks", params={"side": "Sideways"}).status_code == 422


def test_old_runs_with_only_gamma_parameters_still_price(client):
    from app.db import Run
    run = Run(season=2026, week=4, backtest={}, variance={"rush": [1.0, 0.1]}, excluded=[])
    assert main._dists(run) == {}  # legacy [a, b] lists are ignored, so pricing falls back to the gamma curve
    run.variance = {"rush": dict(mu=[1.0], sd=[1.0], z=[0.0]), "td": [1.0, 0.0]}
    assert list(main._dists(run)) == ["rush"]


# ---------- a human-chosen admin password ----------
def _post(client, password):
    return client.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": f"Bearer {password}"})


def test_a_password_with_symbols_works_when_the_browser_percent_encodes_it(monkeypatch):
    from urllib.parse import quote
    monkeypatch.setenv("ADMIN_TOKEN", "my p@ss/w0rd 100%!")
    monkeypatch.setattr(main.pipeline, "run_projections", lambda log=print: None)
    monkeypatch.setattr(main.pipeline, "refresh_odds", lambda mode, log=print: None)
    with TestClient(main.app, client=("203.0.113.20", 4000)) as remote:
        assert _post(remote, quote("my p@ss/w0rd 100%!", safe="")).status_code == 202
        main._job.update(state="idle")


def test_repeated_wrong_guesses_are_throttled_but_the_right_password_still_works(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")
    monkeypatch.setattr(main.pipeline, "run_projections", lambda log=print: None)
    monkeypatch.setattr(main.pipeline, "refresh_odds", lambda mode, log=print: None)
    main._FAILS.clear()
    with TestClient(main.app, client=("203.0.113.21", 4000)) as attacker:
        assert [_post(attacker, f"guess{i}").status_code for i in range(main.MAX_FAILS)] == [403] * main.MAX_FAILS
        assert _post(attacker, "one-more-guess").status_code == 429       # slowed down
        assert _post(attacker, "correct-horse").status_code == 202        # but the owner is never locked out
        main._job.update(state="idle")
    with TestClient(main.app, client=("203.0.113.22", 4000)) as other:
        assert _post(other, "nope").status_code == 403                   # throttling is per client
    main._FAILS.clear()


def test_behind_a_proxy_throttling_follows_the_forwarded_client_not_the_proxy(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")
    main._FAILS.clear()
    with TestClient(main.app, client=("10.0.0.9", 4000)) as proxy:  # every request arrives from the proxy
        for i in range(main.MAX_FAILS + 1):
            proxy.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": f"Bearer bad{i}", "X-Forwarded-For": "198.51.100.7"})
        blocked = proxy.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": "Bearer bad", "X-Forwarded-For": "198.51.100.7"})
        innocent = proxy.post("/api/refresh", json={"odds": "none"}, headers={"Authorization": "Bearer bad", "X-Forwarded-For": "198.51.100.8"})
    assert blocked.status_code == 429 and innocent.status_code == 403
    main._FAILS.clear()
