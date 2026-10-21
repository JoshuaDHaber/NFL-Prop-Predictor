"""Price every quote for one player's market (main + alternate lines) with the model's own probabilities."""
import pandas as pd

from . import odds
from .model import prob_over_under, prob_over_under_dist
from .picks import HOLD
from .td import MIN_MARKET_WEIGHT, YES_NO


def price_quote(mu: float, sd: float, line: float, side: str, american: float, kind: str = "", dist: dict = None):
    """(model win probability, EV per $1 staked) for one side of one quote. No market blending: alt lines
    are usually one-sided so there is no no-vig price to blend with. For anytime and first TD, mu is already the chance."""
    if kind in YES_NO:
        po, pu = mu, 1 - mu
    elif dist:
        po, pu = prob_over_under_dist(mu, line, dist)
    else:
        po, pu = prob_over_under(mu, line, sd * sd)
    p = po if side == "over" else pu
    dec = float(odds.american_to_dec(american))
    return p, p * (dec - 1) - (1 - p)


def build_ladder(mu: float, sd: float, quotes: pd.DataFrame, max_abs_odds: float = 0, kind: str = "", dist: dict = None) -> list[dict]:
    """quotes columns: line, book, alt, over_odds, under_odds, over_link, under_link, event_link.

    max_abs_odds > 0 hides prices outside -max..+max (American), e.g. 300 hides -400 locks and +900 longshots.
    It doesn't apply to anytime or first TD, where +400 to +2000 are ordinary prices."""
    out = []
    # anytime TD: lean on the market's chance (the lone Yes prices, margin stripped), as the Best props board does
    td_market, floor = None, MIN_MARKET_WEIGHT.get(kind, 0.0)
    if floor and quotes.over_odds.notna().any():
        td_market = float((odds.implied(quotes.over_odds.dropna()) / (1 + HOLD[kind])).mean())
    for q in quotes.itertuples():
        row = dict(line=float(q.line), book=q.book, alt=bool(q.alt), event_link=_none(q.event_link), over=None, under=None)
        for side in ("over", "under"):
            odd = getattr(q, f"{side}_odds")
            if pd.notna(odd) and (kind in YES_NO or not max_abs_odds or -max_abs_odds <= odd <= max_abs_odds):
                p, ev = price_quote(mu, sd, q.line, side, odd, kind, dist)
                if td_market is not None and side == "over":
                    p = (1 - floor) * mu + floor * td_market
                    ev = p * (float(odds.american_to_dec(odd)) - 1) - (1 - p)
                row[side] = dict(odds=int(odd), prob=p, ev=ev, link=_none(getattr(q, f"{side}_link")))
        if row["over"] or row["under"]:
            out.append(row)
    return sorted(out, key=lambda r: (r["line"], r["book"]))


def _none(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v
