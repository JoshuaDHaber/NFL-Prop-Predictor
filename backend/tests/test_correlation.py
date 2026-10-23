"""Same-game correlations: the joint-chance approximation, the fitted table, and the endpoint that serves it."""
import numpy as np
import pandas as pd
import pytest
from scipy import stats as st

from app.engine import correlation as cm


def mc(probs, signs, rho, n=400_000, seed=0):
    r = np.array(rho, float) * np.outer(signs, signs)
    np.fill_diagonal(r, 1.0)
    x = np.random.default_rng(seed).normal(size=(n, len(probs))) @ np.linalg.cholesky(r).T
    return float((x < st.norm.ppf(probs)).all(axis=1).mean())


def test_independent_legs_multiply():
    assert cm.joint_prob([0.6, 0.5, 0.3], [1, -1, 1], np.eye(3)) == pytest.approx(0.6 * 0.5 * 0.3)
    assert cm.joint_prob([0.42], [1], [[1.0]]) == pytest.approx(0.42)
    assert cm.joint_prob([], [], []) == 1.0


def test_correlated_overs_hit_together_more_and_an_under_flips_it():
    rho = [[1, 0.4], [0.4, 1]]
    both = cm.joint_prob([0.5, 0.5], [1, 1], rho)
    assert both == pytest.approx(0.25 + np.arcsin(0.4) / (2 * np.pi), abs=0.003)   # the exact orthant chance
    assert cm.joint_prob([0.5, 0.5], [1, -1], rho) == pytest.approx(0.5 - both, abs=0.003)


def test_the_approximation_matches_simulation_for_a_bigger_parlay():
    rho = np.array([[1, 0.36, 0.35, -0.19], [0.36, 1, 0.04, 0.0], [0.35, 0.04, 1, 0.0], [-0.19, 0.0, 0.0, 1]])
    probs, signs = [0.62, 0.55, 0.7, 0.58], [1, 1, -1, 1]
    assert cm.joint_prob(probs, signs, rho) == pytest.approx(mc(probs, signs, rho), abs=0.005)


def test_tetrachoric_recovers_the_latent_correlation_of_two_yes_no_outcomes():
    x = np.random.default_rng(1).multivariate_normal([0, 0], [[1, 0.5], [0.5, 1]], size=40_000)
    assert cm.tetrachoric(x[:, 0] < -0.3, x[:, 1] < 0.8) == pytest.approx(0.5, abs=0.03)
    assert cm.tetrachoric(np.zeros(10), np.ones(10)) == 0.0   # no variation: nothing to measure


def test_keys_ignore_order_and_fold_fullbacks_into_backs():
    assert cm.pair_key("team", cm.leg_desc("rec", "WR"), cm.leg_desc("pass", "QB")) == "team|pass:QB|rec:WR"
    assert cm.leg_desc("rush", "FB") == "rush:RB"


def backtest(n_games=120, seed=2):
    """Each game: a QB whose passing yards move with his WR's receiving yards, a back on each team pulled apart."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        t = 202500 + g
        qb, wr = rng.multivariate_normal([0, 0], [[1, 0.6], [0.6, 1]])
        rb_a, rb_b = rng.multivariate_normal([0, 0], [[1, -0.4], [-0.4, 1]])
        for pid, pos, team, opp, kind, z in (("qb", "QB", "AAA", "BBB", "pass", qb), ("wr", "WR", "AAA", "BBB", "rec", wr),
                                             ("rba", "RB", "AAA", "BBB", "rush", rb_a), ("rbb", "RB", "BBB", "AAA", "rush", rb_b)):
            rows.append(dict(pos=pos, team=team, opp=opp, player_id=pid, name=pid, kind=kind, t=t, mu=50.0, actual=50.0 + 10 * z))
    return pd.DataFrame(rows)


DISTS = {k: dict(mu=[10.0, 90.0], sd=[10.0, 10.0], z=[float(x) for x in np.linspace(-3, 3, 41)]) for k in ("pass", "rec", "rush")}


def test_the_fitted_table_finds_stacks_and_game_script():
    out = cm.fit(backtest(), DISTS)
    pairs = out["pairs"]
    assert pairs["team|pass:QB|rec:WR"][0] == pytest.approx(0.6 * 120 / (120 + cm.SHRINK_K), abs=0.12)
    assert pairs["opp|rush:RB|rush:RB"][0] < -0.2
    assert out["check"]["positive"]["n"] > 0 and out["holdout_from"] > 202500


def test_rare_pairs_get_no_correlation():
    assert cm.fit(backtest(n_games=cm.MIN_PAIRS - 1), DISTS)["pairs"] == {}


def test_gathering_pairs_a_few_at_a_time_fits_the_same_table(monkeypatch):
    whole = cm.fit(backtest(), DISTS)
    monkeypatch.setattr(cm, "PAIR_BATCH", 5)   # a handful of keys per pass over the games
    assert cm.fit(backtest(), DISTS) == whole
