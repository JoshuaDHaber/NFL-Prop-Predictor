"""Teammate volume redistribution: who counts as absent, how much moves, and who receives it."""
import numpy as np
import pandas as pd
import pytest

from app.engine import model, redistribute as rd

COLS = ["player_id", "player_display_name", "position", "team", "opponent_team", "season", "week", "carries", "targets",
        "attempts", "rushing_yards", "receiving_yards", "passing_yards", "rushing_tds", "receiving_tds"]


def row(pid, pos, week, carries=0, targets=0, attempts=0, team="AAA"):
    return dict(player_id=pid, player_display_name=pid, position=pos, team=team, opponent_team="BBB", season=2026, week=week,
                carries=carries, targets=targets, attempts=attempts, rushing_yards=4.5 * carries, receiving_yards=7.0 * targets,
                passing_yards=7.0 * attempts, rushing_tds=0, receiving_tds=0)


def league(rb1_weeks=range(1, 7), weeks=range(1, 9)):
    """AAA: a 15-carry starter (rb1), a 6-carry backup (rb2), a QB and a WR. rb1 only plays rb1_weeks."""
    rows = []
    for w in weeks:
        if w in rb1_weeks:
            rows.append(row("rb1", "RB", w, carries=15, targets=3))
        rows += [row("rb2", "RB", w, carries=6, targets=2), row("qb", "QB", w, carries=5, attempts=33),
                 row("wr", "WR", w, targets=8)]
        rows.append(row("zz", "RB", w, carries=10, targets=1, team="CCC"))  # another team's back, never involved
    return model.prep(pd.DataFrame(rows, columns=COLS))


def sched(weeks=range(1, 10)):
    return pd.DataFrame([dict(season=2026, week=w, home_team="AAA", away_team="BBB", spread_line=0.0, total_line=45.0,
                              home_score=np.nan if w == 9 else 24.0, gameday="2026-10-04", gametime="13:00",
                              game_id=f"2026_{w:02d}_BBB_AAA") for w in weeks])


# ---------- pieces ----------
def test_how_much_of_an_absence_teammates_history_already_shows_grows_with_time_out():
    fracs = [rd.reflected_fraction(m) for m in range(0, 10)]
    assert fracs[0] == 0.0 and all(a < b for a, b in zip(fracs, fracs[1:])) and fracs[-1] < 1.0


def test_volume_competes_within_a_position_group():
    assert rd.group("rush", "RB") == rd.group("rush", "FB") == "RB" and rd.group("rush", "QB") == "QB"
    assert rd.group("rec", "WR") == "WR" and rd.group("rec", "TE") == "TE" and rd.group("rec", "RB") == "RB"


def test_absent_regulars_are_found_with_how_many_games_they_have_missed():
    df = league(rb1_weeks=range(1, 6))                       # rb1 plays weeks 1-5, then is gone
    logs = rd.Logs(df)
    active6 = set(df[df.t == 202606].player_id)
    found = {pid: missed for pid, _, missed in rd.find_absent(logs, "AAA", 202606, active6)}
    assert found == {"rb1": 0}                               # first missed game
    active8 = set(df[df.t == 202608].player_id)
    assert {pid: m for pid, _, m in rd.find_absent(logs, "AAA", 202608, active8)} == {"rb1": 2}   # missed two before this one
    assert rd.find_absent(logs, "AAA", 202606, active6 | {"rb1"}) == []                          # active players are never absent
    assert rd.find_absent(logs, "CCC", 202606, active6) == []                                    # another team's problem


def test_someone_gone_too_long_is_fully_reflected_and_ignored():
    df = league(rb1_weeks=range(1, 2), weeks=range(1, 14))   # rb1 played week 1 only
    logs = rd.Logs(df)
    assert rd.find_absent(logs, "AAA", 202613, set(df[df.t == 202613].player_id)) == []


def test_lost_volume_counts_regulars_only_net_of_what_history_shows():
    hist = pd.DataFrame({"position": ["RB"]})
    comp = lambda h: {"rush": (60.0, 15.0, 4.0), "rec": (10.0, 2.0, 5.0)}       # 15 carries; 2 targets is not a regular
    fresh = rd.lost_volume([("rb1", hist, 0)], comp)
    assert fresh == {("rush", "RB"): 15.0}
    assert rd.lost_volume([("rb1", hist, 3)], comp)[("rush", "RB")] == pytest.approx(15.0 * (1 - rd.reflected_fraction(3)))
    two = rd.lost_volume([("a", hist, 0), ("b", hist, 0)], comp)
    assert two[("rush", "RB")] == 30.0
    assert rd.lost_volume([("rb1", hist, 0)], lambda h: {"rush": (10.0, 5.0, 2.0)}) == {}   # a 5-carry guy isn't a regular


def test_the_lift_is_proportional_and_capped():
    assert rd.lift("rush", 0.6, lost=10, active_volume=20) == pytest.approx(1.3)
    assert rd.lift("rush", 1.0, lost=100, active_volume=10) == rd.LIFT_CAP["rush"]       # capped
    assert rd.lift("pass", 1.0, lost=100, active_volume=10) == 11.0                       # attempts aren't capped
    assert rd.lift("rush", 0.6, lost=0, active_volume=20) == 1.0 and rd.lift("rush", 0.6, lost=5, active_volume=0) == 1.0


def test_rho_is_fit_as_a_slope_and_only_helpful_roles_are_applied():
    rng = np.random.default_rng(0)
    z = rng.uniform(0, 5, 300)
    recs = [("rush", float(v), float(0.7 * v + rng.normal(0, 0.3)), 202601) for v in z] + [("rec", 1.0, 1.0, 202601)] * 10
    fit = rd.fit_rho(recs)
    assert fit["rush"] == pytest.approx(0.7, abs=0.1) and fit["rec"] == rd.DEFAULT_RHO["rec"]  # too little data: default
    used = rd.applied({"rush": 0.7, "rec": 0.3, "pass": 0.3})
    assert used == {"rush": pytest.approx(0.7 * rd.SHRINK), "rec": 0.0, "pass": 0.0}


# ---------- in the backtest ----------
def test_backtest_hands_an_absent_backs_carries_to_his_backup_and_not_to_other_positions():
    df = league(rb1_weeks=range(1, 6))
    s = sched()
    pri = model.league_priors(df)
    base = model.walk_forward(df, pri, s, 202606, rho=None, records=[])
    moved = model.walk_forward(df, pri, s, 202606, rho={"rush": 0.7, "rec": 0.0, "pass": 0.0})

    def mu(frame, pid, t, kind="rush"):
        return float(frame[(frame.player_id == pid) & (frame.t == t) & (frame.kind == kind)].mu.iloc[0])

    assert mu(moved, "rb2", 202606) > mu(base, "rb2", 202606) * 1.4          # the backup inherits carries
    assert mu(moved, "qb", 202606) == pytest.approx(mu(base, "qb", 202606))  # the QB is a different position group
    assert mu(moved, "zz", 202606) == pytest.approx(mu(base, "zz", 202606))  # another team is untouched
    assert bool(base[(base.player_id == "rb2") & (base.t == 202606)].affected.all())


def test_nothing_changes_when_nobody_is_absent_or_rho_is_off():
    df = league(rb1_weeks=range(1, 9))                       # rb1 never misses
    s, pri = sched(), model.league_priors(df)
    a = model.walk_forward(df, pri, s, 202606)
    b = model.walk_forward(df, pri, s, 202606, rho={"rush": 0.7, "rec": 0.0, "pass": 0.0})
    pd.testing.assert_series_equal(a.mu, b.mu)
    df2 = league(rb1_weeks=range(1, 6))
    c = model.walk_forward(df2, model.league_priors(df2), s, 202606)
    d = model.walk_forward(df2, model.league_priors(df2), s, 202606, rho={"rush": 0.0, "rec": 0.0, "pass": 0.0})
    pd.testing.assert_series_equal(c.mu, d.mu)               # rho of zero is a no-op


# ---------- live: the upcoming week ----------
def test_upcoming_projections_lift_teammates_of_players_ruled_out():
    df = league(rb1_weeks=range(1, 9))                       # rb1 has played every game through week 8
    s, pri = sched(), model.league_priors(df)
    dist = {k: dict(mu=[1.0, 200.0], sd=[10.0, 10.0], z=[float(z) for z in np.linspace(-2, 2, 41)]) for k in ("rush", "rec", "pass", "rr")}
    roster = {pid: "AAA" for pid in ("rb1", "rb2", "qb", "wr")}
    rho = {"rush": 0.7, "rec": 0.0, "pass": 0.0}

    def rb2(**kw):
        p = model.upcoming_projections(df, s, pri, dist, 202609, roster, **kw)
        return float(p[(p.player_id == "rb2") & (p.kind == "rush")].mu.iloc[0]), p

    healthy, _ = rb2(rho=rho, absent_ids=set())
    out, p_out = rb2(rho=rho, absent_ids={"rb1"})
    off, _ = rb2(rho=None, absent_ids={"rb1"})
    assert out > healthy * 1.3                                # rb1 ruled out: rb2 picks up his carries
    assert off == pytest.approx(healthy)                      # without redistribution nothing moves
    assert float(p_out[(p_out.player_id == "qb") & (p_out.kind == "rush")].mu.iloc[0]) == pytest.approx(
        float(rb2(rho=rho, absent_ids=set())[1].query("player_id == 'qb' and kind == 'rush'").mu.iloc[0]))   # QB untouched


# ---------- quarterbacks: the replacement takes over ----------
def qb_league(qb1_weeks, weeks=range(1, 9)):
    """AAA: a 33-attempt starter (qb1) who only plays qb1_weeks, a backup (qb2) who throws 2 a game and a third-stringer (qb3) 1."""
    rows = []
    for w in weeks:
        if w in qb1_weeks:
            rows.append(row("qb1", "QB", w, carries=3, attempts=33))
        rows += [row("qb2", "QB", w, attempts=2), row("qb3", "QB", w, attempts=1), row("rb", "RB", w, carries=15, targets=3),
                 row("wr", "WR", w, targets=8)]
        rows.append(row("zz", "QB", w, attempts=30, team="CCC"))
    return model.prep(pd.DataFrame(rows, columns=COLS))


def test_a_missing_starting_qbs_attempts_are_not_summed_or_discounted():
    hist = pd.DataFrame({"position": ["QB"]})
    comp = lambda h: {"pass": (230.0, 33.0, 7.0)}
    assert rd.lost_volume([("a", hist, 0)], comp) == {("pass", "QB"): 33.0}
    assert rd.lost_volume([("a", hist, 4)], comp) == {("pass", "QB"): 33.0}               # no discount for time out
    two = rd.lost_volume([("a", hist, 0), ("b", hist, 0)], lambda h: {"pass": (200.0, 30.0, 7.0)})
    assert two == {("pass", "QB"): 30.0}                                                  # one replacement plays, so max not sum


def member(pid, pos, vol, mu, kind="pass"):
    return dict(pid=pid, pos=pos, comp={kind: (mu, vol, 7.0)}, row=None)


def test_the_lead_replacement_qb_takes_over_and_the_rest_of_the_depth_chart_does_not():
    lost = {("pass", "QB"): 30.0}
    qb2, qb3 = member("qb2", "QB", 2.0, 14.0), member("qb3", "QB", 1.0, 7.0)
    model._lift_members([qb2, qb3], lost, rho={"rush": 0.5, "rec": 0.0, "pass": 0.0})
    assert qb2["comp"]["pass"] == (pytest.approx(14.0 * 15), 30.0, 7.0)                    # 2 -> 30 attempts, yards scale with them
    assert qb3["comp"]["pass"] == (7.0, 1.0, 7.0)                                         # third string unchanged
    ready = member("qb2", "QB", 40.0, 280.0)                                              # an established starter already throws more
    model._lift_members([ready], lost, rho={"rush": 0.5, "rec": 0.0, "pass": 0.0})
    assert ready["comp"]["pass"] == (280.0, 40.0, 7.0)
    off = member("qb2", "QB", 2.0, 14.0)
    model._lift_members([off], lost, rho=None)                                            # redistribution off: nothing moves
    assert off["comp"]["pass"] == (14.0, 2.0, 7.0)
    only = member("qb2", "QB", 2.0, 14.0); other = member("qb3", "QB", 1.0, 7.0)
    model._lift_members([only, other], lost, rho={"rush": 0.5, "rec": 0.0, "pass": 0.0}, only={"qb3"})
    assert only["comp"]["pass"][1] == 2.0 and other["comp"]["pass"][1] == 30.0            # a flagged-out QB can't be the replacement


def test_in_the_backtest_the_backup_throws_the_starters_attempts_when_the_starter_is_out():
    df = qb_league(qb1_weeks=range(1, 6))                          # qb1 is out from week 6
    s, pri = sched(), model.league_priors(df)
    base = model.walk_forward(df, pri, s, 202606, rho=None, records=[])
    moved = model.walk_forward(df, pri, s, 202606, rho={"rush": 0.0, "rec": 0.0, "pass": 0.0})

    def passrow(frame, pid):
        r = frame[(frame.player_id == pid) & (frame.t == 202606) & (frame.kind == "pass")]
        return None if r.empty else float(r.mu.iloc[0])

    assert passrow(base, "qb2") is None                                  # two attempts a game: not enough to project
    assert passrow(moved, "qb2") is not None and passrow(moved, "qb2") > 150          # now a starter's workload
    assert passrow(moved, "qb3") is None                                 # still a third-stringer
    assert passrow(moved, "zz") == pytest.approx(passrow(base, "zz"))    # another team untouched


def test_when_the_starter_is_healthy_the_backup_stays_a_backup():
    df = qb_league(qb1_weeks=range(1, 9))
    s, pri = sched(), model.league_priors(df)
    moved = model.walk_forward(df, pri, s, 202606, rho={"rush": 0.6, "rec": 0.0, "pass": 0.0})
    assert moved[(moved.player_id == "qb2") & (moved.kind == "pass")].empty


def test_live_a_ruled_out_starter_makes_his_backup_the_projected_starter():
    df = qb_league(qb1_weeks=range(1, 9))                          # qb1 has started every game so far
    s, pri = sched(), model.league_priors(df)
    dist = {k: dict(mu=[1.0, 400.0], sd=[40.0, 40.0], z=[float(z) for z in np.linspace(-2, 2, 41)]) for k in ("rush", "rec", "pass", "rr")}
    roster = {pid: "AAA" for pid in ("qb1", "qb2", "qb3", "rb", "wr")}
    rho = {"rush": 0.5, "rec": 0.0, "pass": 0.0}

    def passes(**kw):
        p = model.upcoming_projections(df, s, pri, dist, 202609, roster, **kw)
        return {r.player_id: r.mu for r in p[p.kind == "pass"].itertuples()}

    healthy, out = passes(rho=rho, absent_ids=set()), passes(rho=rho, absent_ids={"qb1"})
    assert "qb2" not in healthy and "qb1" in healthy
    assert out["qb2"] > 150 and "qb3" not in out                  # qb2 is projected for a starter's workload, qb3 is not
    assert passes(rho=None, absent_ids={"qb1"}).get("qb2") is None  # off means off
