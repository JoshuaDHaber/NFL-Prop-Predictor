"""Team moneyline: ratings, win probability, odds parsing and pricing; and the receptions market's stale-line rule."""
import numpy as np
import pandas as pd

from app.engine import moneyline as mlm
from app.engine import odds
from app.engine.picks import build_picks

GID = "2026_07_KC_LV"


def schedule(n_weeks=10, seed=3):
    """AAA is much better than everyone; the last week is unplayed."""
    rng = np.random.default_rng(seed)
    teams, strength = ["AAA", "BBB", "CCC", "DDD"], {"AAA": 10, "BBB": 0, "CCC": 0, "DDD": -10}
    rows = []
    for week in range(1, n_weeks + 1):
        perm = rng.permutation(teams)
        for home, away in ((perm[0], perm[1]), (perm[2], perm[3])):
            played = week < n_weeks
            m = strength[home] - strength[away] + 2 + rng.normal(0, 10)
            rows.append(dict(season=2026, week=week, game_id=f"2026_{week:02d}_{away}_{home}", home_team=home, away_team=away,
                             home_score=float(20 + round(m / 2)) if played else np.nan,
                             away_score=float(20 - round(m / 2)) if played else np.nan, gameday=f"2026-10-{week:02d}",
                             gametime="13:00", spread_line=np.nan, location="Home"))
    return pd.DataFrame(rows)


def test_ratings_rank_the_strong_team_first_and_find_home_field():
    s = schedule(n_weeks=18)
    r, hfa = mlm.ratings(s[s.home_score.notna()], 2026, 18)
    assert max(r, key=r.get) == "AAA" and min(r, key=r.get) == "DDD"
    assert -5 < hfa < 10


def test_win_probability_follows_the_predicted_margin_and_is_never_certain():
    assert mlm.win_prob(0, 15) == 0.5
    assert mlm.win_prob(7, 15) > 0.6 and mlm.win_prob(-7, 15) < 0.4
    assert mlm.win_prob(500, 15) == 0.99


def test_walk_forward_and_fit_give_a_sane_curve_and_scorecard():
    s = schedule(n_weeks=18)
    s = pd.concat([s.assign(season=2025, game_id=s.game_id.str.replace("2026", "2025"), home_score=s.home_score.fillna(20.0),
                            away_score=s.away_score.fillna(17.0)), s], ignore_index=True)
    bt = mlm.walk_forward(s, 2026, 18)
    assert len(bt) > 40 and bt.p_mkt.isna().all()      # no moneyline columns in this schedule
    sigma = mlm.fit_sigma(bt)
    assert mlm.SIGMA_GRID[0] <= sigma <= mlm.SIGMA_GRID[-1]
    summ = mlm.summary(bt, sigma)
    assert summ["metric"] == "brier" and summ["mae_model"] < summ["mae_naive"] and summ["mae_market"] is None
    proj = mlm.project(s, 2026, 18, sigma)
    assert len(proj) == 2 and all(0 < g["p_home"] < 1 for g in proj.values())


def test_h2h_outcomes_become_over_under_rows_with_the_opponents_price_as_the_under():
    bk = {"title": "DraftKings", "link": "https://dk/event"}
    long = pd.DataFrame(odds._moneyline_rows([{"name": "Kansas City Chiefs", "price": -200, "link": "kc"},
                                              {"name": "Las Vegas Raiders", "price": 170, "link": "lv"}], bk))
    paired = odds.pair_with_links(long).set_index("player")
    kc, lv = paired.loc["Kansas City Chiefs"], paired.loc["Las Vegas Raiders"]
    assert (kc.over_odds, kc.under_odds, kc.over_link, kc.market, kc.line) == (-200, 170, "kc", "ml", 0.0)
    assert (lv.over_odds, lv.under_odds, lv.over_link) == (170, -200, "lv")


def ml_lines():
    rows = []
    for book, kc, lv in (("DraftKings", -200, 170), ("FanDuel", -190, 160)):
        rows += [dict(player="Kansas City Chiefs", market="ml", line=0.0, over_odds=kc, under_odds=lv, book=book, over_link=f"{book}-kc",
                      under_link=None, event_link=None, game_id=GID),
                 dict(player="Las Vegas Raiders", market="ml", line=0.0, over_odds=lv, under_odds=kc, book=book, over_link=f"{book}-lv",
                      under_link=None, event_link=None, game_id=GID)]
    return pd.DataFrame(rows)


GAMES = {GID: dict(home="LV", away="KC", gameday="2026-10-18", gametime="16:25", margin=-3.0, p_home=0.42, spread=-6.5)}


def test_pricing_blends_toward_the_market_and_takes_the_best_price():
    out = mlm.price(GAMES, ml_lines(), market_weight=0.35)
    assert len(out) == 1 and out[0]["label"] == "KC @ LV"
    away, home = out[0]["sides"]
    assert (away["team"], home["team"]) == ("KC", "LV") and away["books"] == 2
    assert abs(away["p_model"] + home["p_model"] - 1) < 1e-9
    assert abs(away["p_mkt"] + home["p_mkt"] - 1) < 1e-9 and 0.6 < away["p_mkt"] < 0.7
    w = mlm.ML_MIN_MARKET_WEIGHT   # the slider's 35% is below the floor
    assert abs(away["prob"] - ((1 - w) * away["p_model"] + w * away["p_mkt"])) < 1e-9
    assert (away["odds"], away["book"], away["link"]) == (-190, "FanDuel", "FanDuel-kc")   # best price for KC
    assert (home["odds"], home["book"]) == (170, "DraftKings")
    dec = 1 + 170 / 100
    assert abs(home["ev"] - (home["prob"] * (dec - 1) - (1 - home["prob"]))) < 1e-9


def test_a_book_filter_keeps_that_books_price_but_the_whole_markets_consensus():
    every, one = mlm.price(GAMES, ml_lines()), mlm.price(GAMES, ml_lines(), only_book="DraftKings")
    assert one[0]["sides"][0]["odds"] == -200 and one[0]["sides"][0]["p_mkt"] == every[0]["sides"][0]["p_mkt"]


def test_a_game_without_prices_still_shows_the_models_chance():
    away, home = mlm.price(GAMES, pd.DataFrame())[0]["sides"]
    assert away["p_mkt"] is None and away["odds"] is None and away["prob"] == away["p_model"]


def test_moneyline_quotes_never_reach_the_player_props_board():
    proj = pd.DataFrame([dict(player_id="p1", name="Kansas City Chiefs", pos="WR", team="KC", opp="LV", home=False, kind="rec",
                              mu=50.0, sd=20.0, status="", game_id=GID, gameday="", gametime="", wx=1.0)])
    assert build_picks(proj, ml_lines()).empty


def test_a_receptions_quote_two_catches_off_the_consensus_is_ignored_as_stale():
    proj = pd.DataFrame([dict(player_id="p1", name="Test Receiver", pos="WR", team="KC", opp="LV", home=False, kind="recs",
                              mu=5.0, sd=2.0, status="", game_id=GID, gameday="", gametime="", wx=1.0)])
    lines = pd.DataFrame([dict(player="Test Receiver", market="recs", line=ln, over_odds=-110, under_odds=-110, book=b, game_id=GID)
                          for ln, b in ((4.5, "A"), (4.5, "B"), (4.5, "C"), (6.5, "D"))])
    picks = build_picks(proj, lines)
    assert not picks.empty and set(picks.line) == {4.5}
