"""Who's hot: players whose last few games cleared the line they're posted at now.

A streak is the reader's question, not the model's: the projections already weight recent games (and, in the backtests,
leaning on them harder did worse), so each row carries the board's price and EV beside it to say whether the run is
already in the number."""
import math
from typing import Mapping, Optional, Sequence

import pandas as pd

MIN_RATE = 0.6   # cleared the line in at least this share of the window to count as on a run
YES_NO = {"td", "ftd", "dd", "tpl"}   # 1/0 per game: "Over" is yes; an Under ("no TD in 5") is most players, so left out


def clears(value: float, side: str, line: float) -> bool:
    """A push (exactly the line) counts as not clearing, as the drawer's hit rates do."""
    return value > line if side == "Over" else value < line


def streak(values: Sequence[float], side: str, line: float) -> int:
    """Games in a row, most recent back, that cleared the line."""
    n = 0
    for v in reversed(values):
        if not clears(v, side, line):
            break
        n += 1
    return n


def hot_rows(picks: pd.DataFrame, logs: Mapping[tuple, Sequence[float]], window: int, min_rate: float = MIN_RATE) -> list[dict]:
    """picks: the priced board (one row per player, market and side, with its line). logs: (player_id, kind) -> his
    values in that market, oldest first. One row per pick whose last `window` games cleared its line at least min_rate
    of the time, best run first: most games cleared, then the longer current streak, then the bigger margin over the line.
    Players with fewer than `window` games are left out: 3 of 4 isn't the run the reader asked for."""
    need = max(1, math.ceil(round(window * min_rate, 6)))   # rounded first: 0.6 * 5 is 3.0000000000000004, which would ceil to 4
    out = []
    for p in picks.to_dict("records"):
        if p["kind"] in YES_NO and p["side"] == "Under":
            continue
        values = list(logs.get((p["player_id"], p["kind"]), ()))
        if len(values) < window:
            continue
        recent, before = values[-window:], values[:-window]
        hits = sum(clears(v, p["side"], p["line"]) for v in recent)
        if hits < need:
            continue
        avg = sum(recent) / window
        prior: Optional[float] = sum(before) / len(before) if before else None
        sign = 1 if p["side"] == "Over" else -1
        out.append({**p, "window": window, "hits": hits, "streak": streak(recent, p["side"], p["line"]), "recent": [float(v) for v in recent],
                    "avg": avg, "prior_avg": prior, "margin": sign * (avg - p["line"]) / max(abs(p["line"]), 1.0)})
    out.sort(key=lambda r: (-r["hits"], -r["streak"], -r["margin"], -r["ev"]))
    return out
