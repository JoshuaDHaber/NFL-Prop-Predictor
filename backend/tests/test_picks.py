import pandas as pd
import pytest

from app.engine.picks import build_picks


def proj(**kw):
    base = dict(player_id="p1", name="Test Back", pos="RB", team="AAA", opp="BBB", home=True, kind="rush",
                mu=80.0, sd=30.0, status="", game_id="2026_04_BBB_AAA", gameday="2026-10-04", gametime="13:00")
    base.update(kw)
    return pd.DataFrame([base])


def lines(rows):
    return pd.DataFrame(rows, columns=["player", "market", "line", "over_odds", "under_odds", "book"])


def test_big_projection_gap_makes_the_over_the_best_play():
    p = proj(mu=90)
    picks = build_picks(p, lines([("Test Back", "rush", 60.5, -110, -110, "A")]), market_weight=0.0)
    over = picks[picks.side == "Over"].iloc[0]
    assert over.ev > 0.1 and over.p_model > 0.65
    assert picks[picks.side == "Under"].iloc[0].ev < 0


def test_market_weight_pulls_probability_toward_the_market():
    p = proj(mu=90)
    ln = lines([("Test Back", "rush", 60.5, -110, -110, "A")])
    model_only = build_picks(p, ln, 0.0).query("side == 'Over'").iloc[0].prob
    blended = build_picks(p, ln, 1.0).query("side == 'Over'").iloc[0].prob
    assert blended == pytest.approx(0.5, abs=0.01)
    assert model_only > blended


def test_best_price_across_books_is_kept():
    ln = lines([("Test Back", "rush", 60.5, -120, -110, "Worse"), ("Test Back", "rush", 60.5, -105, -110, "Better")])
    over = build_picks(proj(mu=90), ln).query("side == 'Over'")
    assert len(over) == 1 and over.iloc[0].book == "Better"


def test_alternate_lines_far_from_consensus_are_ignored():
    ln = lines([("Test Back", "rush", 60.5, -110, -110, "A"), ("Test Back", "rush", 61.5, -110, -110, "B"),
                ("Test Back", "rush", 62.5, -110, -110, "C"), ("Test Back", "rush", 9.5, -300, 220, "Stale")])
    assert "Stale" not in set(build_picks(proj(mu=90), ln).book)


def test_large_model_market_disagreement_is_flagged():
    ln = lines([("Test Back", "rush", 30.5, -110, -110, "A")])
    assert build_picks(proj(mu=80), ln).flagged.all()
    assert not build_picks(proj(mu=33), ln).flagged.any()


def test_unmatched_players_and_empty_inputs_are_safe():
    assert build_picks(proj(), lines([("Someone Else", "rush", 50.5, -110, -110, "A")])).empty
    assert build_picks(proj(), lines([])).empty


def test_one_sided_quotes_still_price_without_crashing():
    ln = lines([("Test Back", "rush", 60.5, -110, None, "A")])
    picks = build_picks(proj(mu=90), ln)
    assert list(picks.side) == ["Over"]
