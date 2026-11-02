import pandas as pd

from app.engine.hot import hot_rows, streak


def picks(rows):
    return pd.DataFrame([dict(player_id=pid, name=pid, kind=kind, side=side, line=line, ev=ev) for pid, kind, side, line, ev in rows])


def test_ranks_by_games_cleared_then_streak():
    logs = {("a", "rec"): [10, 80, 80, 80, 20, 80],   # 4 of the last 5 over 50.5, 1 in a row
            ("b", "rec"): [80, 20, 80, 80, 80, 80],   # 4 of 5, 4 in a row
            ("c", "rec"): [80, 80, 80, 80, 80, 80]}   # 5 of 5
    rows = hot_rows(picks([(p, "rec", "Over", 50.5, 0.0) for p in "abc"]), logs, window=5)
    assert [r["player_id"] for r in rows] == ["c", "b", "a"]
    c = rows[0]
    assert (c["hits"], c["streak"], c["recent"], c["avg"], c["prior_avg"]) == (5, 5, [80.0] * 5, 80.0, 80.0)


def test_needs_three_of_five_and_a_full_window():
    logs = {("a", "rec"): [80, 80, 20, 20, 20],   # 2 of 5: not on a run
            ("b", "rec"): [80, 80, 80, 20, 20],   # 3 of 5: just makes it
            ("c", "rec"): [80, 80, 80, 80]}       # only 4 games
    rows = hot_rows(picks([(p, "rec", "Over", 50.5, 0.0) for p in "abc"]), logs, window=5)
    assert [r["player_id"] for r in rows] == ["b"]
    assert rows[0]["prior_avg"] is None


def test_under_side_and_pushes():
    logs = {("a", "pts"): [30, 20, 20, 20, 20]}
    assert hot_rows(picks([("a", "pts", "Under", 20.0, 0.0)]), logs, window=5) == []   # pushes don't clear
    rows = hot_rows(picks([("a", "pts", "Under", 22.5, 0.0)]), logs, window=4)
    assert rows[0]["hits"] == 4 and rows[0]["margin"] > 0


def test_yes_no_unders_are_left_out():
    logs = {("a", "td"): [0, 0, 0, 0, 0]}
    assert hot_rows(picks([("a", "td", "Under", 0.5, 0.0)]), logs, window=5) == []


def test_streak_counts_back_from_the_latest_game():
    assert streak([80, 20, 80, 80], "Over", 50.5) == 2
    assert streak([80, 80, 20], "Over", 50.5) == 0
