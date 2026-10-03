import pandas as pd
import pytest

from app.engine.ladder import build_ladder, price_quote


def test_price_quote_matches_the_odds_math():
    p, ev = price_quote(mu=80, sd=30, line=60.5, side="over", american=100)
    assert ev == pytest.approx(p * 1.0 - (1 - p))  # even money
    p_under, _ = price_quote(80, 30, 60.5, "under", 100)
    assert p + p_under == pytest.approx(1.0)


def test_longshot_alt_lines_are_priced_by_the_model():
    low, _ = price_quote(60, 25, 80.5, "over", 300)
    high, _ = price_quote(60, 25, 120.5, "over", 3000)
    assert low > high > 0


def test_ladder_handles_one_sided_quotes_and_missing_links():
    q = pd.DataFrame([
        dict(line=75.5, book="B", alt=True, over_odds=400, under_odds=None, over_link="", under_link=None, event_link=None),
        dict(line=50.5, book="A", alt=False, over_odds=-110, under_odds=-110, over_link="https://x/o", under_link="https://x/u",
             event_link="https://x/e"),
    ])
    rows = build_ladder(70, 28, q)
    assert [r["line"] for r in rows] == [50.5, 75.5]  # sorted by line
    assert rows[1]["under"] is None and rows[1]["over"]["link"] is None  # '' normalised to None
    assert rows[0]["over"]["link"] == "https://x/o" and rows[0]["event_link"] == "https://x/e"


def test_odds_range_hides_prices_outside_the_window_per_side():
    q = pd.DataFrame([
        dict(line=40.5, book="A", alt=True, over_odds=-450, under_odds=330, over_link=None, under_link=None, event_link=None),
        dict(line=60.5, book="A", alt=False, over_odds=-110, under_odds=-110, over_link=None, under_link=None, event_link=None),
        dict(line=90.5, book="A", alt=True, over_odds=900, under_odds=None, over_link=None, under_link=None, event_link=None),
    ])
    rows = build_ladder(60, 25, q, max_abs_odds=300)
    assert [r["line"] for r in rows] == [60.5]  # 40.5 has no side in range, 90.5's only side is +900
    assert len(build_ladder(60, 25, q)) == 3  # 0 = no limit
    edge = pd.DataFrame([dict(line=50.5, book="A", alt=True, over_odds=-300, under_odds=300, over_link=None, under_link=None, event_link=None)])
    assert build_ladder(60, 25, edge, max_abs_odds=300)[0]["over"] and build_ladder(60, 25, edge, max_abs_odds=300)[0]["under"]  # inclusive
