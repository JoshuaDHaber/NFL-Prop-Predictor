"""Tracked bets (app/bets.py): settling singles and parlays, the API's rules, and grading from NFL stats and NBA game logs."""
import re
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import auth, bets, main
from app.db import Bet, BetLeg, NbaProjection, NbaRun, Projection, Run, SessionLocal, User

SOON = (datetime.utcnow() + timedelta(days=3)).date().isoformat()
PAST = (datetime.utcnow() - timedelta(days=3)).date().isoformat()
NFL_GAME, NFL_OLD = f"2099_05_HOU_JAX", f"2099_04_HOU_DAL"
NBA_GAME = "2099_10_BOS_NYK"


@pytest.fixture(scope="module", autouse=True)
def board():
    """A latest NFL run with one future game and one already played, and a latest NBA run with a future game."""
    with SessionLocal() as s:
        run = Run(season=2099, week=5, backtest={}, variance={})
        s.add(run)
        s.flush()
        for gid, day, pid, name in ((NFL_GAME, SOON, "00-R1", "Rusher One"), (NFL_GAME, SOON, "00-W1", "Wideout One"),
                                    (NFL_OLD, PAST, "00-R1", "Rusher One")):
            s.add(Projection(run_id=run.id, player_id=pid, name=name, pos="RB", team="HOU", opp="JAX", home=False, kind="rush",
                             mu=70, sd=25, vol=15, eff=4.5, spread=0, game_id=gid, gameday=day, gametime="13:00", last5=[]))
        nrun = NbaRun(season=2100, slate=[SOON], backtest={}, variance={}, games=[{"game_id": NBA_GAME, "start": f"{SOON}T23:30:00Z"}])
        s.add(nrun)
        s.flush()
        s.add(NbaProjection(run_id=nrun.id, player_id="9001", name="Guard One", pos="G", team="BOS", opp="NYK", home=False, kind="pts",
                            mu=25, sd=6, vol=34, eff=0.7, spread=0, game_id=NBA_GAME, gameday=SOON, gametime="19:30", last5=[]))
        s.commit()
        ids = run.id, nrun.id
    yield
    # later test files read "the latest run": leave theirs as it was
    with SessionLocal() as s:
        for model, rid in zip((Run, NbaRun), ids):
            s.delete(s.get(model, rid))
        s.commit()


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(auth, "send_email", lambda to, subject, text, html: out.append(re.search(r"#t=([\w-]+)", text).group(1)))
    auth._hits.clear()
    return out


def member(sent, email, ip):
    """A remote visitor signed in as `email`, 21+ confirmed."""
    c = TestClient(main.app, client=(ip, 5000))
    c.post("/api/auth/email", json={"email": email})
    c.post("/api/auth/email/verify", json={"token": sent[-1]})
    c.post("/api/auth/age")
    return c


def leg(pid="00-R1", kind="rush", side="Over", line=69.5, odds=-110, game=NFL_GAME, **kw):
    return dict(game_id=game, player_id=pid, kind=kind, side=side, line=line, odds=odds, **kw)


# ---------- settling ----------
def make(odds=+250, stake=10.0, results=(None,), leg_odds=None):
    bet = Bet(stake=stake, odds=odds, kind="parlay" if len(results) > 1 else "single", status="open")
    for i, r in enumerate(results):
        bet.legs.append(BetLeg(result=r, odds=(leg_odds or [-110] * len(results))[i]))
    return bet


def test_settle_singles():
    for r, status, payout in (("win", "won", 20.0), ("loss", "lost", 0.0), ("push", "push", 10.0), ("void", "void", 10.0)):
        b = make(odds=+100, results=(r,))
        bets.settle(b)
        assert (b.status, b.payout, b.settled_by) == (status, payout, "grading")


def test_settle_parlays():
    lost_early = make(results=("loss", None))
    bets.settle(lost_early)
    assert lost_early.status == "lost"                       # a losing leg settles it before the rest are in
    waiting = make(results=("win", None))
    bets.settle(waiting)
    assert waiting.status == "open" and waiting.payout is None
    # a void leg drops out: +250 over two -110 legs, one void, pays on the other leg's price
    repriced = make(odds=+250, results=("win", "void"), leg_odds=[-110, -110])
    bets.settle(repriced)
    assert repriced.status == "won" and repriced.payout == pytest.approx(10 * 3.5 / (1 + 100 / 110), abs=0.01)
    all_out = make(results=("void", "push"))
    bets.settle(all_out)
    assert (all_out.status, all_out.payout) == ("push", 10.0)
    by_hand = make(results=("loss",))
    by_hand.settled_by, by_hand.status = "user", "won"
    bets.settle(by_hand)
    assert by_hand.status == "won"                          # settled by hand: grading leaves it alone


# ---------- the API ----------
def test_track_and_list(sent):
    with member(sent, "tracker@example.com", "198.51.100.1") as c:
        r = c.post("/api/me/bets", json={"book": "DraftKings", "kind": "parlay", "stake": 20, "odds": 264,
                                         "legs": [leg(), leg("00-W1", "rec", line=54.5, alt=True, prob=0.58, ev=0.04)]})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["league"] == "nfl" and b["status"] == "open" and not b["started"] and b["to_pay"] == pytest.approx(72.8)
        assert [lg["name"] for lg in b["legs"]] == ["Rusher One", "Wideout One"]   # names come from the board, not the client
        out = c.get("/api/me/bets").json()
        assert out["summary"]["open"] == 1 and out["summary"]["open_stake"] == 20 and out["books"] == ["DraftKings"]
        single = c.post("/api/me/bets", json={"book": "FanDuel", "kind": "single", "stake": 5, "legs": [leg(game=NBA_GAME, pid="9001", kind="pts", line=24.5)]})
        assert single.json()["league"] == "nba" and single.json()["odds"] == -110
        assert [x["book"] for x in c.get("/api/me/bets?league=nba").json()["bets"]] == ["FanDuel"]


def test_track_refuses_bad_bets(sent):
    with member(sent, "strict@example.com", "198.51.100.2") as c:
        post = lambda **body: c.post("/api/me/bets", json={"book": "FanDuel", "kind": "single", "stake": 10, **body})
        assert "started" in post(legs=[leg(game=NFL_OLD)]).json()["detail"]                # no backfilling after kickoff
        assert post(legs=[leg(pid="nobody")]).status_code == 422                           # not on the board
        assert post(legs=[leg(), leg("00-W1")]).status_code == 422                         # a single with two legs
        assert post(kind="parlay", odds=200, legs=[leg(), leg(game=NBA_GAME, pid="9001", kind="pts")]).status_code == 422  # two leagues
        assert post(kind="parlay", odds=200, legs=[leg(), leg(line=80.5)]).status_code == 422   # the same prop twice
        assert post(stake=0, legs=[leg()]).status_code == 422
        assert post(legs=[leg(odds=50)]).status_code == 422                                # not American odds
        assert c.post("/api/me/bets", headers={"Origin": "https://evil.example"},
                      json={"book": "FanDuel", "kind": "single", "stake": 10, "legs": [leg()]}).status_code == 403


def test_bets_need_a_confirmed_account(sent):
    with TestClient(main.app, client=("198.51.100.3", 5000)) as c:
        assert c.get("/api/me/bets").status_code == 401
        c.post("/api/auth/email", json={"email": "young@example.com"})
        c.post("/api/auth/email/verify", json={"token": sent[-1]})
        assert c.get("/api/me/bets").status_code == 403      # signed in, but not 21+ confirmed yet


def test_bets_are_private(sent):
    with member(sent, "owner1@example.com", "198.51.100.4") as a:
        bid = a.post("/api/me/bets", json={"book": "FanDuel", "kind": "single", "stake": 10, "legs": [leg()]}).json()["id"]
    with member(sent, "snoop@example.com", "198.51.100.5") as b:
        assert b.get("/api/me/bets").json()["bets"] == []
        assert b.patch(f"/api/me/bets/{bid}", json={"status": "won"}).status_code == 404
        assert b.delete(f"/api/me/bets/{bid}").status_code == 404


def test_edit_settle_by_hand_and_delete(sent):
    with member(sent, "editor@example.com", "198.51.100.6") as c:
        bid = c.post("/api/me/bets", json={"book": "FanDuel", "kind": "single", "stake": 10, "legs": [leg(odds=150)]}).json()["id"]
        r = c.patch(f"/api/me/bets/{bid}", json={"stake": 20, "odds": 120}).json()
        assert (r["stake"], r["odds"], r["legs"][0]["odds"], r["status"]) == (20, 120, 120, "open")
        r = c.patch(f"/api/me/bets/{bid}", json={"status": "won"}).json()
        assert (r["status"], r["payout"], r["profit"], r["settled_by"]) == ("won", 44.0, 24.0, "user")
        s = c.get("/api/me/bets").json()["summary"]
        assert (s["wins"], s["profit"], s["roi"]) == (1, 24.0, 1.2)
        r = c.patch(f"/api/me/bets/{bid}", json={"status": "open"}).json()
        assert (r["status"], r["settled_by"]) == ("open", None)   # handed back to grading
        assert c.delete(f"/api/me/bets/{bid}").status_code == 204
        assert c.get("/api/me/bets").json()["bets"] == []


def test_deleting_the_account_deletes_its_bets(sent):
    with member(sent, "leaver@example.com", "198.51.100.7") as c:
        bid = c.post("/api/me/bets", json={"book": "FanDuel", "kind": "single", "stake": 10, "legs": [leg()]}).json()["id"]
        c.delete("/api/auth/me")
    with SessionLocal() as s:
        assert s.get(Bet, bid) is None and not s.query(BetLeg).filter(BetLeg.bet_id == bid).count()


# ---------- grading ----------
def tracked(legs, kind="parlay", odds=300, stake=10.0):
    """A bet stored straight in the database (its games can be in the past, as when grading runs)."""
    with SessionLocal() as s:
        owner = s.query(User).filter(User.email == "grader@example.com").first() or User(email="grader@example.com")
        s.add(owner)
        s.flush()
        b = Bet(user_id=owner.id, league=bets.league_of(legs[0]["kind"]), book="FanDuel", kind=kind, stake=stake, odds=odds, status="open")
        for lg in legs:
            b.legs.append(BetLeg(name="x", team="HOU", opp="JAX", kickoff=datetime(2000, 1, 1), alt=False, **lg))
        s.add(b)
        s.commit()
        return b.id


def test_grade_nfl_settles_main_and_alternate_lines_and_dnps():
    g = "2098_03_HOU_JAX"
    win_alt = tracked([dict(game_id=g, gameday="2098-09-20", player_id="00-A", kind="rush", side="Over", line=99.5, odds=+300),
                       dict(game_id=g, gameday="2098-09-20", player_id="00-B", kind="rec", side="Under", line=40.5, odds=-110)], odds=+700)
    dnp = tracked([dict(game_id=g, gameday="2098-09-20", player_id="00-GONE", kind="rush", side="Over", line=50.5, odds=-110)], kind="single", odds=-110)
    stats = pd.DataFrame([dict(player_id="00-A", season=2098, week=3, team="HOU", rushing_yards=120, receiving_yards=5),
                          dict(player_id="00-B", season=2098, week=3, team="JAX", rushing_yards=0, receiving_yards=31)])
    sched = pd.DataFrame([dict(game_id=g, home_score=24)])
    with SessionLocal() as s:
        assert bets.grade_nfl(s, stats, sched) == 3
        a, d = s.get(Bet, win_alt), s.get(Bet, dnp)
        assert [(lg.actual, lg.result) for lg in a.legs] == [(120.0, "win"), (31.0, "win")]
        assert (a.status, a.payout) == ("won", 80.0)
        assert (d.status, d.payout, d.legs[0].result) == ("void", 10.0, "void")   # didn't play: stake back, as the books do


def test_grade_nba_from_game_logs():
    day = (date.today() - timedelta(days=1)).isoformat()
    bid = tracked([dict(game_id="2098_11_BOS_NYK", gameday=day, player_id="77", kind="pra", side="Over", line=30.5, odds=-120)],
                  kind="single", odds=-120)
    logs = pd.DataFrame([dict(player_id="77", date=day, team="BOS", min=34, pts=20, reb=8, ast=6),
                         dict(player_id="88", date=day, team="NYK", min=30, pts=10, reb=3, ast=2)])
    with SessionLocal() as s:
        assert bets.grade_nba(s, logs, date.today(), fetch=lambda *a, **k: pd.DataFrame()) == 1
        b = s.get(Bet, bid)
        assert (b.legs[0].actual, b.status) == (34.0, "won") and b.payout == pytest.approx(10 * (1 + 100 / 120), abs=0.01)


def test_tags_and_filters(sent):
    with member(sent, "organizer@example.com", "198.51.100.8") as c:
        post = lambda book, legs, **kw: c.post("/api/me/bets", json={"book": book, "kind": "single", "stake": 10, "legs": legs, **kw}).json()
        a = post("DraftKings", [leg()], tags=[" SGP ", "sunday", "sgp", "x" * 40])
        assert a["tags"] == ["SGP", "sunday", "x" * 24]          # trimmed, de-duplicated ignoring case, capped in length
        b = post("FanDuel", [leg(game=NBA_GAME, pid="9001", kind="pts", line=24.5)], tags=["Tailing"])
        out = c.get("/api/me/bets").json()
        assert out["tags"] == ["SGP", "sunday", "Tailing", "x" * 24] and out["books"] == ["DraftKings", "FanDuel"]
        assert [x["id"] for x in c.get("/api/me/bets?tag=sgp").json()["bets"]] == [a["id"]]
        assert [x["id"] for x in c.get("/api/me/bets?league=nba").json()["bets"]] == [b["id"]]
        assert [x["id"] for x in c.get("/api/me/bets?book=DraftKings").json()["bets"]] == [a["id"]]
        r = c.patch(f"/api/me/bets/{b['id']}", json={"tags": ["Tailing", "Late"]}).json()
        assert r["tags"] == ["Tailing", "Late"]
        # an old bet drops out of the 1 and 3 month views but stays in 12 months and all time
        with SessionLocal() as s:
            s.get(Bet, a["id"]).placed_at = datetime.utcnow() - timedelta(days=120)
            s.commit()
        count = lambda q: len(c.get(f"/api/me/bets{q}").json()["bets"])
        assert (count("?months=1"), count("?months=3"), count("?months=12"), count("")) == (1, 1, 2, 2)


def test_months_ago_is_calendar_months():
    assert bets.months_ago(datetime(2026, 3, 31, 12), 1) == datetime(2026, 2, 28, 12)
    assert bets.months_ago(datetime(2026, 1, 15), 3) == datetime(2025, 10, 15)
    assert bets.months_ago(datetime(2026, 11, 1), 12) == datetime(2025, 11, 1)


def test_closing_line_value_and_csv_export(sent):
    with member(sent, "clvfan@example.com", "198.51.100.9") as c:
        good = c.post("/api/me/bets", json={"book": "DraftKings", "kind": "single", "stake": 10, "legs": [leg(odds=+120)], "tags": ["Sunday"]}).json()
        bad = c.post("/api/me/bets", json={"book": "FanDuel", "kind": "parlay", "stake": 5, "odds": 250,
                                           "legs": [leg(), leg("00-W1", "rec", line=54.5)]}).json()
        assert c.get("/api/me/bets").json()["summary"]["clv_n"] == 0          # nothing has closed yet
        with SessionLocal() as s:
            s.get(Bet, good["id"]).legs[0].close_p = 0.50                    # +120 needs 45.5%: beat the close
            for lg, p in zip(s.get(Bet, bad["id"]).legs, (0.45, 0.50)):       # 0.225 x 3.5 = 0.79: didn't
                lg.close_p = p
            s.commit()
        out = c.get("/api/me/bets").json()
        by_id = {b["id"]: b for b in out["bets"]}
        assert by_id[good["id"]]["ev_close"] == pytest.approx(0.10) and by_id[good["id"]]["legs"][0]["ev_close"] == pytest.approx(0.10)
        assert by_id[bad["id"]]["ev_close"] == pytest.approx(0.45 * 0.5 * 3.5 - 1)
        s_ = out["summary"]
        assert (s_["clv_n"], s_["beat_close"]) == (2, 0.5) and s_["ev_close"] == pytest.approx((0.10 + 0.45 * 0.5 * 3.5 - 1) / 2, abs=1e-4)

        r = c.get("/api/me/bets.csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
        rows = [line.split(",") for line in r.text.strip().splitlines()]
        assert rows[0][:3] == ["bet_id", "placed_at", "league"] and len(rows) == 1 + 3      # one row per leg
        assert [int(x[0]) for x in rows[1:]] == [good["id"], bad["id"], bad["id"]]           # oldest bet first
        assert rows[1][11] == "Sunday" and rows[1][-1] == "0.5"
        assert len(c.get("/api/me/bets.csv?book=DraftKings").text.strip().splitlines()) == 2  # the view's filters apply
    with TestClient(main.app, client=("198.51.100.10", 5000)) as anon:
        assert anon.get("/api/me/bets.csv").status_code == 401
