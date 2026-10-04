"""Anytime touchdown: the model, its pricing, and the odds feed's Yes-only format."""
import numpy as np
import pandas as pd
import pytest

from app.engine import odds, td
from app.engine.ladder import build_ladder, price_quote
from app.engine.picks import TD_ASSUMED_HOLD, TD_MIN_MARKET_WEIGHT, build_picks

PRI = {("rush", "RB"): 0.035, ("rec", "RB"): 0.03, ("rush", "WR"): 0.03, ("rec", "WR"): 0.05, ("rec", "QB"): 0.2, ("rush", "QB"): 0.05}


def hist(rush_tds, carries=15, targets=4, rec_tds=0, n=6):
    return pd.DataFrame({"carries": [carries] * n, "targets": [targets] * n,
                         "rushing_tds": rush_tds if isinstance(rush_tds, list) else [rush_tds] * n, "receiving_tds": [rec_tds] * n})


def comp(rush_vol=15.0, rec_vol=4.0):
    return {"rush": (60.0, rush_vol, 4.0), "rec": (30.0, rec_vol, 7.0)}


def test_probability_is_poisson_of_expected_tds():
    p, lam, touches = td.project_td(hist(0), comp(), "RB", PRI)
    assert p == pytest.approx(1 - np.exp(-lam)) and 0 < p < 1
    assert touches == pytest.approx(19.0)


def test_a_scorer_beats_a_non_scorer_and_volume_matters():
    scorer = td.project_td(hist(1), comp(), "RB", PRI)[0]
    cold = td.project_td(hist(0), comp(), "RB", PRI)[0]
    assert scorer > cold
    assert td.project_td(hist(0), comp(rush_vol=22), "RB", PRI)[0] > td.project_td(hist(0), comp(rush_vol=8), "RB", PRI)[0]


def test_rates_are_shrunk_toward_the_position_so_a_hot_streak_is_not_taken_at_face_value():
    raw_rate = 1 / 15  # a TD every game on 15 carries
    shrunk = td.player_rate(hist(1), "rush", PRI[("rush", "RB")])
    assert PRI[("rush", "RB")] < shrunk < raw_rate


def test_the_teams_expected_scoring_moves_the_probability_and_is_capped():
    base = td.project_td(hist(0), comp(), "RB", PRI)[0]
    assert td.project_td(hist(0), comp(), "RB", PRI, implied=29)[0] > base > td.project_td(hist(0), comp(), "RB", PRI, implied=16)[0]
    assert td.scoring_factor(100) == td.SCORING_CLIP[1] and td.scoring_factor(None) == 1.0


def test_players_without_a_real_role_get_no_projection_and_qb_targets_are_ignored():
    assert td.project_td(hist(0, carries=1, targets=1), {"rush": (4, 1.0, 4), "rec": (7, 1.0, 7)}, "RB", PRI) is None
    qb = td.project_td(hist(0, carries=5, targets=1), {"rush": (20, 5.0, 4), "rec": (7, 1.0, 7)}, "QB", PRI)
    assert qb[2] == pytest.approx(5.0)  # the lone target is not counted


def test_scale_fit_matches_the_observed_rate_and_summary_reports_calibration():
    lams = np.random.default_rng(0).uniform(0.1, 0.9, 4000)
    actual = (np.random.default_rng(1).random(4000) < 1 - np.exp(-1.3 * lams)).astype(float)
    s = td.fit_scale(lams, actual)
    assert s == pytest.approx(1.3, abs=0.12)
    bt = pd.DataFrame({"mu": 1 - np.exp(-lams), "actual": actual})
    out = td.summary(bt, s)
    assert out["metric"] == "brier" and out["mae_model"] < out["mae_naive"]
    assert abs(out["bias"]) < 0.01 and len(out["calibration"]) == 5


def test_implied_points_split_the_total_by_the_spread():
    sched = pd.DataFrame([dict(season=2026, week=4, home_team="HOM", away_team="AWY", total_line=45.0, spread_line=3.0)])
    m = td.implied_points(sched)
    assert m[(2026, 4, "HOM")] == 24.0 and m[(2026, 4, "AWY")] == 21.0


# ---------- pricing ----------
def proj(mu=0.5):
    return pd.DataFrame([dict(player_id="p1", name="Test Back", pos="RB", team="AAA", opp="BBB", home=True, kind="td", mu=mu, sd=0.0,
                              status="", game_id="2026_04_BBB_AAA", gameday="2026-10-04", gametime="13:00")])


def yes_lines(prices):
    return pd.DataFrame([("Test Back", "td", 0.5, p, None, b) for b, p in prices.items()],
                        columns=["player", "market", "line", "over_odds", "under_odds", "book"])


def test_td_picks_price_the_yes_side_against_the_model_probability():
    picks = build_picks(proj(0.5), yes_lines({"A": 150, "B": 130}), market_weight=0.0)
    pick = picks.iloc[0]
    assert list(picks.side) == ["Over"] and pick.book == "A"  # best Yes price, and no "No" side exists
    assert pick.p_model == pytest.approx(0.5)
    # even with the slider at 0, a TD play leans on the market at least TD_MIN_MARKET_WEIGHT
    assert pick.prob == pytest.approx((1 - TD_MIN_MARKET_WEIGHT) * 0.5 + TD_MIN_MARKET_WEIGHT * pick.p_mkt)
    assert pick.ev == pytest.approx(pick.prob * 1.5 - (1 - pick.prob))
    assert picks.iloc[0].edge_yds == pytest.approx((picks.iloc[0].p_model - picks.iloc[0].p_mkt) * 100)  # TD edge is in percentage points


def test_td_market_view_strips_a_typical_margin_from_the_lone_yes_price():
    pick = build_picks(proj(0.5), yes_lines({"A": 100}), market_weight=1.0).iloc[0]
    assert pick.p_mkt == pytest.approx(0.5 / (1 + TD_ASSUMED_HOLD))  # +100 implies 50%; some of that is margin


def test_td_picks_far_from_the_market_are_flagged_and_longshot_prices_are_kept():
    wild = build_picks(proj(0.8), yes_lines({"A": 400}), market_weight=0.35).iloc[0]
    assert bool(wild.flagged)  # model says 80%, market about 19%
    assert not bool(build_picks(proj(0.2), yes_lines({"A": 400}), market_weight=0.35).iloc[0].flagged)


def test_td_ladder_uses_the_probability_directly_and_ignores_the_odds_range():
    p, ev = price_quote(0.4, 0.0, 0.5, "over", 200, kind="td")
    assert p == pytest.approx(0.4) and ev == pytest.approx(0.4 * 2 - 0.6)
    q = pd.DataFrame([dict(line=0.5, book="A", alt=False, over_odds=900, under_odds=None, over_link=None, under_link=None, event_link=None)])
    assert len(build_ladder(0.2, 0.0, q, max_abs_odds=300, kind="td")) == 1
    assert len(build_ladder(60, 25, q, max_abs_odds=300)) == 0  # the same price is hidden for yardage


# ---------- the odds feed ----------
def test_anytime_td_feed_becomes_an_over_half_with_links(monkeypatch):
    payload = {"bookmakers": [{"title": "FanDuel", "link": "https://sportsbook.fanduel.com/e", "markets": [
        {"key": "player_anytime_td", "outcomes": [
            {"name": "Yes", "description": "Bijan Robinson", "price": -195, "link": "https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=2"},
            {"name": "Yes", "description": "Kyle Pitts", "price": 300}]}]}]}

    class Resp:
        headers = {"x-requests-remaining": "9"}
        def raise_for_status(self): pass
        def json(self): return payload

    monkeypatch.setattr(odds.requests, "get", lambda *a, **k: Resp())
    long, remaining = odds.fetch_game_odds("k", "evt", ["td"])
    assert remaining == "9" and set(long.market) == {"td"} and set(long.side) == {"over"} and set(long.line) == {0.5}
    paired = odds.pair_with_links(long)
    assert len(paired) == 2 and paired.under_odds.isna().all() and not paired.alt.any()
    assert paired[paired.player == "Bijan Robinson"].iloc[0].over_odds == -195


def test_anytime_td_has_no_alternate_market():
    assert "td" in odds.MARKETS.values() and "td" not in odds.ALT_MARKETS.values()


def test_td_ladder_blends_toward_the_markets_chance_like_the_board_does():
    q = pd.DataFrame([dict(line=0.5, book=b, alt=False, over_odds=o, under_odds=None, over_link=None, under_link=None, event_link=None)
                      for b, o in (("A", 100), ("B", 100))])
    row = build_ladder(0.8, 0.0, q, kind="td")[0]
    market = 0.5 / (1 + TD_ASSUMED_HOLD)
    expected_p = (1 - TD_MIN_MARKET_WEIGHT) * 0.8 + TD_MIN_MARKET_WEIGHT * market
    assert row["over"]["prob"] == pytest.approx(expected_p)
    assert row["over"]["ev"] == pytest.approx(expected_p * 1.0 - (1 - expected_p))  # +100 pays 1:1
    assert row["over"]["prob"] < 0.8  # the model's 80% is pulled toward the market's ~45%
