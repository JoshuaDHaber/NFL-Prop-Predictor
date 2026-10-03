"""Price every quote for one player's market (main + alternate lines) with the model's own probabilities."""
import pandas as pd

from . import odds
from .model import prob_over_under


def price_quote(mu: float, sd: float, line: float, side: str, american: float):
    """(model win probability, EV per $1 staked) for one side of one quote. No market blending: alt lines
    are usually one-sided so there is no no-vig price to blend with."""
    po, pu = prob_over_under(mu, line, sd * sd)
    p = po if side == "over" else pu
    dec = float(odds.american_to_dec(american))
    return p, p * (dec - 1) - (1 - p)


def build_ladder(mu: float, sd: float, quotes: pd.DataFrame) -> list[dict]:
    """quotes columns: line, book, alt, over_odds, under_odds, over_link, under_link, event_link."""
    out = []
    for q in quotes.itertuples():
        row = dict(line=float(q.line), book=q.book, alt=bool(q.alt), event_link=_none(q.event_link), over=None, under=None)
        for side in ("over", "under"):
            odd = getattr(q, f"{side}_odds")
            if pd.notna(odd):
                p, ev = price_quote(mu, sd, q.line, side, odd)
                row[side] = dict(odds=int(odd), prob=p, ev=ev, link=_none(getattr(q, f"{side}_link")))
        if row["over"] or row["under"]:
            out.append(row)
    return sorted(out, key=lambda r: (r["line"], r["book"]))


def _none(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v
