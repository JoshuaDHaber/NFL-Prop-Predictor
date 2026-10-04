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
