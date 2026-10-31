"""Defense vs position: how much each defense gives up to each position group, for the matchup grades.

A raw "points allowed to guards" mostly measures which guards a defense happened to face, so each game is compared
with what those same players usually produce (the NBA: their per-minute rate x that game's minutes; the NFL: their
average per game). A defense's factor for a position and stat is (what they produced against it + K rows of par) /
(what they usually produce + K rows of par), so a handful of games can't make a defense look extreme. Rank 1 is the
softest matchup: the defense that lets that position beat its usual numbers by the most.

The grades are context. The models price one factor per defense and stat (no position split), and in the backtests the
position-level factor added little or nothing on top of it: NBA points, rebounds, assists, threes and PRA went over
their projections 43-47% of the time from the softest fifth of defenses to the toughest, with no MAE gain at any
strength; NFL rushing and receiving were noise, and passing yards the one hint (softest fifth 61% over, toughest 52%,
0.3% MAE at half strength) on 1,079 QB games, too few to build in.
"""
import numpy as np
import pandas as pd

GRADES = "ABCDF"   # fifths of the league, softest first


def factors(frame: pd.DataFrame, kinds, k_rows: float) -> dict:
    """kind -> {(defense, position group): factor}. frame: one row per player-game with columns opp, grp, w (recency
    weight) and act_<kind> / exp_<kind> (what he did, what he usually does)."""
    out = {}
    for k in kinds:
        f = frame.dropna(subset=[f"act_{k}", f"exp_{k}"])
        if f.empty:
            out[k] = {}
            continue
        par = float(np.average(f[f"exp_{k}"], weights=f.w)) * k_rows   # K rows of a typical player's production
        g = f.assign(a=f[f"act_{k}"] * f.w, e=f[f"exp_{k}"] * f.w).groupby(["opp", "grp"])[["a", "e"]].sum()
        out[k] = {key: float((r.a + par) / (r.e + par)) for key, r in g.iterrows()}
    return out


def ranks(fac: dict) -> dict:
    """kind -> {(defense, group): (factor, rank, teams ranked)}, rank 1 the softest within each position group."""
    out = {}
    for k, by in fac.items():
        out[k] = {}
        for grp in {g for _, g in by}:
            teams = sorted(((f, t) for (t, g), f in by.items() if g == grp), reverse=True)
            for i, (f, t) in enumerate(teams, 1):
                out[k][(t, grp)] = (f, i, len(teams))
    return out


def grade(rank: int, n: int) -> str:
    """A for the softest fifth of the league's defenses against this position, F for the toughest."""
    return GRADES[min(int((rank - 1) * len(GRADES) / max(n, 1)), len(GRADES) - 1)]
