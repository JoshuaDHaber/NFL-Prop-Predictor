"""Turn projections + sportsbook lines into priced picks (win probability, EV, Kelly)."""
import numpy as np
import pandas as pd

from . import odds
from .model import prob_over_under, prob_over_under_dist
from .td import (DD_ASSUMED_HOLD, FTD_ASSUMED_HOLD, MIN_MARKET_WEIGHT, TD_ASSUMED_HOLD, TD_MIN_MARKET_WEIGHT,  # noqa: F401
                 TPL_ASSUMED_HOLD, YES_NO)  # (re-exported for callers and tests)

# margin stripped from a lone Yes price
HOLD = {"td": TD_ASSUMED_HOLD, "ftd": FTD_ASSUMED_HOLD, "dd": DD_ASSUMED_HOLD, "tpl": TPL_ASSUMED_HOLD}



PICK_COLUMNS = [
    "player_id", "name", "pos", "team", "opp", "home", "kind", "mu", "sd", "status", "game_id", "gameday", "gametime",
    "side", "line", "odds", "book", "p_model", "p_mkt", "prob", "ev", "kelly", "books", "edge_yds", "flagged", "wx",
    "flag", "teammate_out",
]
# a quote this far from the consensus line (or 30% of it) is an alternate or stale line; receptions are counted in catches,
# passing TDs in touchdowns (lines step 0.5 / 1.5 / 2.5, so a whole TD off the consensus is another line)
# NBA from pts on (threes, steals and blocks step 0.5 / 1.5 / 2.5, like passing TDs)
STALE_MIN_GAP = {"recs": 1.5, "ptd": 0.9, "pts": 4.0, "reb": 2.0, "ast": 2.0, "threes": 0.9, "pra": 6.0, "pr": 5.0, "pa": 5.0,
                 "stl": 0.9, "blk": 0.9}


def book_set(only_book: str = None):
    """A book filter ("DraftKings" or "BetMGM,DraftKings,FanDuel") as a set; None keeps every book."""
    return {b.strip() for b in only_book.split(",") if b.strip()} if only_book else None


def build_picks(proj: pd.DataFrame, lines: pd.DataFrame, market_weight: float = 0.35, only_book: str = None,
                dists: dict = None, best_only: bool = True) -> pd.DataFrame:
    """All priced Over/Under candidates. flagged (hidden by default) = model and market disagree by >40-67%, usually a
    model blind spot; `flag` names the reason ("large gap"). teammate_out is context only: a same-position rotation
    receiver in his first game out (redistribute.teammates_out). It isn't a flag: those receivers average a few yards
    over projection, but from a few big games; they beat it no more often than anyone (42.6% vs 42.7%), so their
    Unders hit as often as any.
    only_book keeps just that sportsbook's quotes in the output (or several, comma-separated: the books legal in the
    bettor's state); the market consensus still uses every book.
    dists: per-kind error tables from the backtest (model.fit_dist); without one, the older gamma curve is used., best book per player/market/side, sorted by EV (no EV filter).
    best_only=False keeps every book's quote (still sorted by EV); best_picks() then narrows it to the best one, so one
    pricing can serve every book filter."""
    if proj.empty or lines.empty:
        return pd.DataFrame(columns=PICK_COLUMNS)
    lines = lines.copy()
    lines["key"] = lines.player.map(odds.norm)
    if "thin" in proj:
        # thin-history projections are display only: the backtest's error tables don't cover them (model.THIN_GAMES)
        proj = proj[~proj.thin.fillna(False).astype(bool)]
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
    for kind, hold in HOLD.items():
        yes_only = (lines.market == kind) & lines.under_odds.isna()
        lines.loc[yes_only, "nv_o"] = odds.implied(lines.loc[yes_only, "over_odds"]) / (1 + hold)
    cons = lines.groupby(["key", "market"]).agg(line=("line", "median"), nv_o=("nv_o", "mean"), books=("book", "nunique"))

    keep = book_set(only_book)
    out = []
    chances = {}   # (player, market, line) -> (p_over, p_under): most books post the same lines

    def chance(p, market, line):
        k = (p.key, market, line)
        if k not in chances:
            chances[k] = (prob_over_under_dist(p.mu, line, dists[market]) if dists and market in dists
                          else prob_over_under(p.mu, line, p.sd ** 2))
        return chances[k]


    for r in lines.itertuples():
        p = pm.get((r.key, r.market))
        if p is None or pd.isna(r.line):
            continue
        c = cons.loc[(r.key, r.market)]
        if abs(r.line - c.line) > max(STALE_MIN_GAP.get(r.market, 8.0), 0.3 * c.line):
            continue  # alternate / stale line far from the market consensus
        if keep and r.book not in keep:
            continue
        wx = getattr(p, "wx", 1.0)
        wx = 1.0 if wx is None or pd.isna(wx) else float(wx)
        is_td = r.market in YES_NO
        if is_td:
            po, pu = p.mu, 1 - p.mu  # mu already is the chance (of any TD, or of the game's first)
        else:
            po, pu = chance(p, r.market, r.line)
        mk_over = c.nv_o
        if not is_td and pd.notna(mk_over) and abs(c.line - r.line) > 1e-9:
            # shift the consensus probability to this book's line using the model's own slope
            po_c = chance(p, r.market, c.line)[0]
            mk_over = float(np.clip(c.nv_o + (po - po_c), 0.02, 0.98))
        for side, odd, p_side, mk in (("Over", r.over_odds, po, mk_over), ("Under", r.under_odds, pu, 1 - mk_over)):
            if pd.isna(odd):
                continue
            mk = p_side if pd.isna(mk) else mk  # only one side posted: no market view to blend
            w = max(market_weight, MIN_MARKET_WEIGHT.get(r.market, 0.0))
            prob = (1 - w) * p_side + w * mk
            dec = float(odds.american_to_dec(odd))
            ev = prob * (dec - 1) - (1 - prob)
            # yardage: projection minus line in yards; yes/no (TD, double-double): model minus market chance in percentage points
            edge = (p_side - mk) * 100 if is_td else (p.mu - r.line) * (1 if side == "Over" else -1)
            # passing TDs (and NBA threes, steals, blocks) sit at 0.5 / 1.5 / 2.5, where projection-over-line ratios swing wildly, so like anytime TD they
            # compare chances instead
            by_chance = is_td or r.market in ("ptd", "threes", "stl", "blk")
            gap = (not (0.6 <= p_side / max(mk, 1e-6) <= 1.67)) if by_chance else not (0.6 <= p.mu / max(c.line, 0.5) <= 1.67)
            out_ = getattr(p, "teammate_out", "") or ""
            out_ = "" if pd.isna(out_) else str(out_)
            flag = "large gap" if gap else ""
            out.append(dict(
                player_id=p.player_id, name=p.name, pos=p.pos, team=p.team, opp=p.opp, home=bool(p.home), kind=r.market,
                mu=p.mu, sd=p.sd, status=p.status, game_id=p.game_id, gameday=p.gameday, gametime=p.gametime,
                side=side, line=float(r.line), odds=int(odd), book=r.book, p_model=p_side, p_mkt=mk, prob=prob, ev=ev,
                kelly=max(0.0, ev / (dec - 1)) / 4, books=int(c.books),
                edge_yds=edge, flagged=bool(flag), wx=wx, flag=flag, teammate_out=out_))
    df = pd.DataFrame(out, columns=PICK_COLUMNS)
    if df.empty:
        return df
    df = df.sort_values("ev", ascending=False, kind="stable")
    return best_picks(df) if best_only else df.reset_index(drop=True)


def best_picks(priced: pd.DataFrame, only_book: str = None) -> pd.DataFrame:
    """The best book per player/market/side from build_picks(..., best_only=False), within only_book's books."""
    keep = book_set(only_book)
    if keep:
        priced = priced[priced.book.isin(keep)]
    return priced.drop_duplicates(["name", "kind", "side"]).reset_index(drop=True)
