"""Price every quote for one player's market (main + alternate lines) with the model's own probabilities."""
import pandas as pd

from . import odds
from .model import prob_over_under
from .td import TD_ASSUMED_HOLD, TD_MIN_MARKET_WEIGHT


def price_quote(mu: float, sd: float, line: float, side: str, american: float, kind: str = ""):
    """(model win probability, EV per $1 staked) for one side of one quote. No market blending: alt lines
    are usually one-sided so there is no no-vig price to blend with. For anytime TD, mu is already P(>=1 TD)."""
    po, pu = (mu, 1 - mu) if kind == "td" else prob_over_under(mu, line, sd * sd)
    p = po if side == "over" else pu
    dec = float(odds.american_to_dec(american))
    return p, p * (dec - 1) - (1 - p)


def build_ladder(mu: float, sd: float, quotes: pd.DataFrame, max_abs_odds: float = 0, kind: str = "") -> list[dict]:
    """quotes columns: line, book, alt, over_odds, under_odds, over_link, under_link, event_link.

    max_abs_odds > 0 hides prices outside -max..+max (American), e.g. 300 hides -400 locks and +900 longshots.
    It doesn't apply to anytime TD, where +400 to +2000 are ordinary prices."""
    out = []
    # anytime TD: lean on the market's chance (the lone Yes prices, margin stripped), as the Best props board does
    td_market = None
    if kind == "td" and quotes.over_odds.notna().any():
        td_market = float((odds.implied(quotes.over_odds.dropna()) / (1 + TD_ASSUMED_HOLD)).mean())
    for q in quotes.itertuples():
        row = dict(line=float(q.line), book=q.book, alt=bool(q.alt), event_link=_none(q.event_link), over=None, under=None)
        for side in ("over", "under"):
            odd = getattr(q, f"{side}_odds")
            if pd.notna(odd) and (kind == "td" or not max_abs_odds or -max_abs_odds <= odd <= max_abs_odds):
                p, ev = price_quote(mu, sd, q.line, side, odd, kind)
                if td_market is not None and side == "over":
                    p = (1 - TD_MIN_MARKET_WEIGHT) * mu + TD_MIN_MARKET_WEIGHT * td_market
                    ev = p * (float(odds.american_to_dec(odd)) - 1) - (1 - p)
                row[side] = dict(odds=int(odd), prob=p, ev=ev, link=_none(getattr(q, f"{side}_link")))
        if row["over"] or row["under"]:
            out.append(row)
    return sorted(out, key=lambda r: (r["line"], r["book"]))


def _none(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v
