import numpy as np
import pandas as pd
import pytest

from app.engine import model, odds


def test_probabilities_are_complementary_on_half_lines():
    po, pu = model.prob_over_under(60, 40.5, 30 ** 2)
    assert po + pu == pytest.approx(1.0)
    assert po > 0.5  # projection well above the line


def test_whole_number_lines_leave_room_for_a_push():
    po, pu = model.prob_over_under(60, 60, 30 ** 2)
    assert po + pu < 1.0


def test_higher_projection_raises_over_probability():
    assert model.prob_over_under(80, 60.5, 900)[0] > model.prob_over_under(50, 60.5, 900)[0]


def _hist(yards, vols):
    return pd.DataFrame({"rushing_yards": yards, "carries": vols})


def test_efficiency_is_shrunk_toward_the_prior():
    # one huge game on 2 carries should not project a monster yards-per-carry
    hist = _hist([60, 40, 50, 45], [20, 18, 2, 20]) 
    mu, vol, eff = model.project_player(hist, "rush", prior_eff=4.2)
    assert 3.0 < eff < 5.5
    assert mu == pytest.approx(vol * eff)


def test_recent_games_weigh_more():
    up = _hist([10, 10, 10, 90], [10, 10, 10, 20])
    down = _hist([90, 10, 10, 10], [20, 10, 10, 10])
    assert model.project_player(up, "rush", 4.2)[1] > model.project_player(down, "rush", 4.2)[1]


def test_game_script_moves_volume_the_expected_way():
    hist = _hist([50] * 6, [12] * 6)
    fav = model.project_player(hist, "rush", 4.2, spread=10)[1]
    dog = model.project_player(hist, "rush", 4.2, spread=-10)[1]
    assert fav > dog


def test_player_with_no_usage_is_not_projected():
    assert model.project_player(_hist([0, 0], [0, 0]), "rush", 4.2) is None


def _backtest(kind="rush", n=3000, seed=0):
    rng = np.random.default_rng(seed)
    mu = rng.uniform(20, 100, n)
    return pd.DataFrame({"kind": kind, "mu": mu, "actual": rng.gamma(4, mu / 4)})  # a right-skewed outcome around mu


def test_error_distribution_is_fit_per_kind_with_a_spread_and_standardized_quantiles():
    d = model.fit_dist(_backtest())["rush"]
    assert len(d["mu"]) == len(d["sd"]) >= 3 and all(s > 0 for s in d["sd"])
    assert d["sd"][-1] > d["sd"][0]  # bigger projections have bigger errors here
    assert len(d["z"]) == len(model.Z_PROBS) and d["z"] == sorted(d["z"])


def test_empirical_probabilities_are_calibrated_where_the_gamma_assumption_was_not():
    """Lines set at each outcome's true median should see ~50% overs; the fitted table must reproduce that."""
    bt = _backtest(n=6000)
    dist = model.fit_dist(bt)["rush"]
    from scipy import stats as st
    medians = st.gamma(4, scale=bt.mu / 4).median()
    overs = [model.prob_over_under_dist(m, med, dist)[0] for m, med in zip(bt.mu[:400], medians[:400])]
    assert np.mean(overs) == pytest.approx(0.5, abs=0.04)


def test_dist_probabilities_behave_like_probabilities():
    dist = model.fit_dist(_backtest())["rush"]
    po, pu = model.prob_over_under_dist(50, 40.5, dist)
    assert po + pu == pytest.approx(1.0) and po > 0.5
    po_i, pu_i = model.prob_over_under_dist(50, 40, dist)  # whole-number line: a push is possible
    assert po_i + pu_i < 1.0
    assert model.prob_over_under_dist(80, 40.5, dist)[0] > model.prob_over_under_dist(50, 40.5, dist)[0]
    assert 0.01 <= model.prob_over_under_dist(50, 1000.5, dist)[0] <= 0.99  # never certain


def test_name_normalisation_matches_sportsbook_styles():
    assert odds.norm("Marvin Harrison Jr.") == odds.norm("marvin harrison")
    assert odds.norm("D'Andre Swift") == odds.norm("DAndre Swift")


def test_american_odds_conversion():
    assert float(odds.american_to_dec(100)) == pytest.approx(2.0)
    assert float(odds.american_to_dec(-200)) == pytest.approx(1.5)
    assert float(odds.implied(-110)) == pytest.approx(110 / 210)


def test_longest_catch_grows_with_catches_and_stays_between_one_catch_and_the_total():
    yards = np.random.default_rng(0).exponential(11.0, 5000)
    table = model.long_table(yards)
    assert table[0] == pytest.approx(0.0)                          # no catches: longest is 0
    assert all(b >= a for a, b in zip(table, table[1:]))           # more catches, longer longest
    e1 = np.interp(1.0, model.LNG_LAMBDA, table)
    assert 0.5 < e1 < 1.0           # one expected catch (Poisson: sometimes none) averages under one full catch
    assert np.interp(6.0, model.LNG_LAMBDA, table) < 6.0             # the best of six is less than all six


def test_longest_reception_follows_catches_and_yards_per_catch():
    table = model.long_table(np.random.default_rng(0).exponential(11.0, 5000))
    comp = {"rec": (66.0, 8.0, 8.25), "recs": (5.0, 8.0, 0.625)}   # 5 catches for 66 yards on 8 targets
    mu, lam, ypc = model.long_reception(comp, table)
    assert lam == pytest.approx(5.0) and ypc == pytest.approx(13.2)
    assert ypc < mu < 66.0
    bigger = model.long_reception({"rec": (99.0, 8.0, 12.4), "recs": (5.0, 8.0, 0.625)}, table)
    assert bigger[0] > mu                                          # same catches, longer ones
    assert model.long_reception({"rec": (10.0, 1.0, 10.0), "recs": (0.6, 1.0, 0.6)}, table) is None   # no real role


def test_add_longest_takes_each_games_best_catch_and_zero_without_one():
    df = pd.DataFrame({"player_id": ["a", "a", "b"], "season": [2026] * 3, "week": [1, 2, 1]})
    catches = pd.DataFrame({"player_id": ["a", "a", "b"], "season": [2026] * 3, "week": [1, 1, 3], "yards": [12.0, 31.0, 9.0]})
    assert model.add_longest(df, catches).receiving_long.tolist() == [31.0, 0.0, 0.0]


def test_longest_rush_follows_carries_and_yards_per_carry():
    table = model.long_table(np.random.default_rng(0).exponential(4.4, 5000), model.RLNG_LAMBDA)
    mu, lam, ypc = model.long_rush({"rush": (88.0, 20.0, 4.4)}, table)
    assert lam == pytest.approx(20.0) and ypc == pytest.approx(4.4)
    assert ypc < mu < 88.0
    assert model.long_rush({"rush": (66.0, 15.0, 4.4)}, table)[0] < mu      # fewer carries, shorter longest
    assert model.long_rush({"rush": (12.0, 3.0, 4.0)}, table) is None       # no real rushing role


def test_add_longest_adds_each_games_best_carry_too():
    df = pd.DataFrame({"player_id": ["a", "a"], "season": [2026] * 2, "week": [1, 2]})
    catches = pd.DataFrame(columns=["player_id", "season", "week", "yards"])
    rushes = pd.DataFrame({"player_id": ["a", "a"], "season": [2026] * 2, "week": [1, 1], "yards": [-2.0, 17.0]})
    out = model.add_longest(df, catches, rushes)
    assert out.rushing_long.tolist() == [17.0, 0.0] and out.receiving_long.tolist() == [0.0, 0.0]


def test_add_first_td_marks_only_the_games_first_scorer():
    df = pd.DataFrame({"player_id": ["a", "a", "b"], "season": [2026] * 3, "week": [1, 2, 1]})
    first = pd.DataFrame({"player_id": ["a"], "season": [2026], "week": [1], "game_id": ["2026_01_X_Y"]})
    assert model.add_first_td(df, first).first_td.tolist() == [1.0, 0.0, 0.0]
