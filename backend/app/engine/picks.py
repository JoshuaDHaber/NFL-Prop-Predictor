"""Turn projections + sportsbook lines into priced picks (win probability, EV, Kelly)."""
import numpy as np
import pandas as pd

from . import odds
from .model import prob_over_under, prob_over_under_dist
from .td import TD_ASSUMED_HOLD, TD_MIN_MARKET_WEIGHT  # noqa: F401  (re-exported for callers and tests)



PICK_COLUMNS = [
    "player_id", "name", "pos", "team", "opp", "home", "kind", "mu", "sd", "status", "game_id", "gameday", "gametime",
    "side", "line", "odds", "book", "p_model", "p_mkt", "prob", "ev", "kelly", "books", "edge_yds", "flagged",
]


def build_picks(proj: pd.DataFrame, lines: pd.DataFrame, market_weight: float = 0.35, only_book: str = None,
                dists: dict = None) -> pd.DataFrame:
    """All priced Over/Under candidates (flagged = model and market disagree by >40-67%: usually a model blind spot).
    only_book keeps just that sportsbook's quotes in the output; the market consensus still uses every book.
    dists: per-kind error tables from the backtest (model.fit_dist); without one, the older gamma curve is used., best book per player/market/side, sorted by EV (no EV filter)."""
    if proj.empty or lines.empty:
        return pd.DataFrame(columns=PICK_COLUMNS)
    lines = lines.copy()
    lines["key"] = lines.player.map(odds.norm)
    proj = proj.copy()
    proj["key"] = proj["name"].map(odds.norm)
    if "game_id" in lines:
        # a line belongs to one game: last week's quote for a player is never priced against this week's projection
        lines = lines[lines.game_id == lines.key.map(dict(zip(proj.key, proj.game_id)))]
        if lines.empty:
            return pd.DataFrame(columns=PICK_COLUMNS)
    pm = {(r.key, r.kind): r for r in proj.itertuples()}

    # market no-vig consensus per player/market
    lines["nv_o"] = odds.implied(lines.over_odds) / (odds.implied(lines.over_odds) + odds.implied(lines.under_odds))
    td_only = (lines.market == "td") & lines.under_odds.isna()
    lines.loc[td_only, "nv_o"] = odds.implied(lines.loc[td_only, "over_odds"]) / (1 + TD_ASSUMED_HOLD)
    cons = lines.groupby(["key", "market"]).agg(line=("line", "median"), nv_o=("nv_o", "mean"), books=("book", "nunique"))

    out = []
    for r in lines.itertuples():
        p = pm.get((r.key, r.market))
        if p is None or pd.isna(r.line):
            continue
        c = cons.loc[(r.key, r.market)]
        if abs(r.line - c.line) > max(8.0, 0.3 * c.line):
            continue  # alternate / stale line far from the market consensus
        if only_book and r.book != only_book:
            continue
        var = p.sd ** 2
        is_td = r.market == "td"
        if is_td:
            po, pu = p.mu, 1 - p.mu  # mu already is P(>=1 TD)
        elif dists and r.market in dists:
            po, pu = prob_over_under_dist(p.mu, r.line, dists[r.market])
        else:
            po, pu = prob_over_under(p.mu, r.line, var)
        mk_over = c.nv_o
        if not is_td and pd.notna(mk_over) and abs(c.line - r.line) > 1e-9:
            # shift the consensus probability to this book's line using the model's own slope
            po_c = (prob_over_under_dist(p.mu, c.line, dists[r.market]) if dists and r.market in dists
                    else prob_over_under(p.mu, c.line, var))[0]
            mk_over = float(np.clip(c.nv_o + (po - po_c), 0.02, 0.98))
        for side, odd, p_side, mk in (("Over", r.over_odds, po, mk_over), ("Under", r.under_odds, pu, 1 - mk_over)):
            if pd.isna(odd):
                continue
            mk = p_side if pd.isna(mk) else mk  # only one side posted: no market view to blend
            w = max(market_weight, TD_MIN_MARKET_WEIGHT) if is_td else market_weight
            prob = (1 - w) * p_side + w * mk
            dec = float(odds.american_to_dec(odd))
            ev = prob * (dec - 1) - (1 - prob)
            # yardage: projection minus line in yards; TD: model minus market chance in percentage points
            edge = (p_side - mk) * 100 if is_td else (p.mu - r.line) * (1 if side == "Over" else -1)
            flagged = (not (0.6 <= p_side / max(mk, 1e-6) <= 1.67)) if is_td else not (0.6 <= p.mu / max(c.line, 0.5) <= 1.67)
            out.append(dict(
                player_id=p.player_id, name=p.name, pos=p.pos, team=p.team, opp=p.opp, home=bool(p.home), kind=r.market,
                mu=p.mu, sd=p.sd, status=p.status, game_id=p.game_id, gameday=p.gameday, gametime=p.gametime,
                side=side, line=float(r.line), odds=int(odd), book=r.book, p_model=p_side, p_mkt=mk, prob=prob, ev=ev,
                kelly=max(0.0, ev / (dec - 1)) / 4, books=int(c.books),
                edge_yds=edge, flagged=flagged))
    df = pd.DataFrame(out, columns=PICK_COLUMNS)
    if df.empty:
        return df
    return df.sort_values("ev", ascending=False).drop_duplicates(["name", "kind", "side"]).reset_index(drop=True)
