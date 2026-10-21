"""Anytime touchdown probability (rushing or receiving TD; passing TDs don't count for this market).

For each player the expected number of TDs in the game is
    lambda = carries x TD-per-carry  +  targets x TD-per-target
with both rates recency-weighted and shrunk toward the position average, and then scaled by how many
points the team is expected to score (from the spread and total). P(at least one TD) = 1 - exp(-lambda),
the Poisson chance of a non-zero count. A single scale factor is fit in the walk-forward backtest so the
average predicted rate matches the average actual rate.

First touchdown scorer reuses those expected TDs. If every touchdown in a game (both teams, defense and returns too)
arrives as its own Poisson stream, the first one belongs to a player in proportion to his share of the game's
expected touchdowns:  P(first) = lambda / LAMBDA x (1 - exp(-LAMBDA)),  with LAMBDA the game's expected touchdowns
from its total (TDS_PER_POINT). A second scale is fit in the backtest, as for anytime TD.
"""
import numpy as np
import pandas as pd

HALFLIFE = 5.0                   # games, same decay as the yardage model
TD_K = {"rush": 80.0, "rec": 60.0}   # pseudo-opportunities of shrinkage toward the position rate
MIN_TOUCHES = {"rush": 4.0, "rec": 3.0}
LEAGUE_IMPLIED = 22.5            # typical points a team scores
SCORING_CLIP = (0.7, 1.35)
TD_ASSUMED_HOLD = 0.10  # books post anytime-TD as a lone "Yes" price; this strips a typical margin to estimate the true chance
# The TD model is a weak signal next to the market (it lacks red-zone usage), so a TD play always leans at least this
# much on the market's chance, whatever the "trust market" slider says.
TD_MIN_MARKET_WEIGHT = 0.6
# markets posted as a "Yes" price per player, some books adding "No" (stored as an Over 0.5); mu is a probability.
# NBA double- and triple-doubles too (nba/model.py)
YES_NO = ("td", "ftd", "dd", "tpl")
# the least a yes/no play leans on the market's chance, by market: the NBA's double-double model holds up in its
# backtest, so it follows the "trust market" slider like any other market
MIN_MARKET_WEIGHT = {"td": TD_MIN_MARKET_WEIGHT, "ftd": TD_MIN_MARKET_WEIGHT}
# touchdowns of every kind (rushing, receiving, defense and returns) per point scored: 2022-26 regular seasons, 2.49 a
# team-game at 22.45 points
TDS_PER_POINT = 0.111
# first-TD prices carry a much bigger margin than anytime TD: each book prices 30+ players for one outcome. A guess
# until enough posted prices are logged to measure it (sum of a game's Yes chances against the model's)
FTD_ASSUMED_HOLD = 0.25
# NBA double- and triple-double Yes prices: guesses too; long-shot triple-double prices carry the bigger margin
DD_ASSUMED_HOLD = 0.10
TPL_ASSUMED_HOLD = 0.20
_COLS = {"rush": ("carries", "rushing_tds"), "rec": ("targets", "receiving_tds")}


def td_priors(df: pd.DataFrame) -> dict:
    """League TD rate per carry / per target, by position."""
    pri = {}
    for pos, g in df.groupby("position"):
        carries, targets = g.carries.sum(), g.targets.sum()
        if carries > 0:
            pri[("rush", pos)] = g.rushing_tds.sum() / carries
        if targets > 0:
            pri[("rec", pos)] = g.receiving_tds.sum() / targets
    return pri


def player_rate(hist: pd.DataFrame, kind: str, prior: float) -> float:
    """Recency-weighted TD rate per opportunity, shrunk toward the position prior."""
    vol_col, td_col = _COLS[kind]
    w = 0.5 ** (np.arange(len(hist))[::-1] / HALFLIFE)
    vol, tds = hist[vol_col].fillna(0).to_numpy(float), hist[td_col].fillna(0).to_numpy(float)
    return float(((w * tds).sum() + TD_K[kind] * prior) / ((w * vol).sum() + TD_K[kind]))


def scoring_factor(implied) -> float:
    if implied is None or pd.isna(implied):
        return 1.0
    return float(np.clip(implied / LEAGUE_IMPLIED, *SCORING_CLIP))


def project_td(hist, comp, pos, priors, implied=None, scale=1.0):
    """(P(>=1 TD), expected TDs, expected touches), or None if the player has no real rushing/receiving role.

    comp is model.components(...): kind -> (mu, projected volume, efficiency).
    """
    lam = touches = 0.0
    qualifies = False
    for kind in ("rush", "rec"):
        prior, c = priors.get((kind, pos)), comp.get(kind)
        if prior is None or c is None or (kind == "rec" and pos == "QB"):  # a QB's few targets are trick plays
            continue
        vol = c[1]
        touches += vol
        lam += vol * player_rate(hist, kind, prior)
        qualifies = qualifies or vol >= MIN_TOUCHES[kind]
    if not qualifies:
        return None
    lam *= scoring_factor(implied) * scale
    return float(1 - np.exp(-lam)), float(lam), float(touches)


def game_tds(implied_team, implied_opp) -> float:
    """Expected touchdowns of every kind in a game, from the points the lines expect each side to score."""
    pts = [LEAGUE_IMPLIED if x is None or pd.isna(x) else float(x) for x in (implied_team, implied_opp)]
    return TDS_PER_POINT * sum(pts)


def first_td(lam: float, game_lam: float, scale: float = 1.0) -> float:
    """Chance a player with lam expected TDs scores his game's first touchdown (see the module docstring)."""
    if game_lam <= 0:
        return 0.0
    return float(np.clip(scale * lam / game_lam * (1 - np.exp(-game_lam)), 0.0, 0.95))


def fit_ftd_scale(p: np.ndarray, actual: np.ndarray) -> float:
    """Scale on first-TD chances (linear in expected TDs) so their mean matches how often it happened."""
    p, y = np.asarray(p, float), np.asarray(actual, float)
    return float(np.clip(y.mean() / p.mean(), 0.2, 4.0)) if len(p) and p.mean() > 0 else 1.0


def td_count(df: pd.DataFrame) -> pd.Series:
    return df["rushing_tds"].fillna(0) + df["receiving_tds"].fillna(0)


def implied_points(sched: pd.DataFrame) -> dict:
    """(season, week, team) -> points the betting lines expect that team to score."""
    out = {}
    for r in sched.itertuples():
        if pd.notna(r.total_line) and pd.notna(r.spread_line):
            out[(r.season, r.week, r.home_team)] = (r.total_line + r.spread_line) / 2
            out[(r.season, r.week, r.away_team)] = (r.total_line - r.spread_line) / 2
    return out


def fit_scale(lams: np.ndarray, actual: np.ndarray) -> float:
    """Scalar s so the mean of 1-exp(-s*lambda) equals the observed TD rate (bisection)."""
    lams, target = np.asarray(lams, float), float(np.mean(actual))
    lo, hi = 0.2, 4.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if np.mean(1 - np.exp(-mid * lams)) < target:
            lo = mid
        else:
            hi = mid
    return float((lo + hi) / 2)


def summary(bt_td: pd.DataFrame, scale: float) -> dict:
    """Backtest scorecard in the same shape as the yardage kinds: mae_model/mae_naive hold Brier scores
    (model vs. always predicting the average TD rate), bias is mean(actual - predicted)."""
    if bt_td.empty:
        return brier_summary(np.array([]), np.array([]))
    lam = -np.log1p(-np.clip(bt_td.mu.to_numpy(), 0, 1 - 1e-9))
    return brier_summary(1 - np.exp(-scale * lam), bt_td.actual.to_numpy(float))


def brier_summary(p: np.ndarray, y: np.ndarray) -> dict:
    """Brier scores (model vs. always the average rate), bias and a five-bin calibration table for yes/no chances."""
    if not len(y):
        return dict(n=0, mae_model=0.0, mae_naive=0.0, bias=0.0, metric="brier", calibration=[])
    base = float(y.mean())
    cuts = pd.qcut(p, 5, duplicates="drop")
    cal = pd.DataFrame({"p": p, "y": y, "bin": cuts}).groupby("bin", observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    return dict(n=int(len(y)), mae_model=float(np.mean((p - y) ** 2)), mae_naive=float(np.mean((base - y) ** 2)),
                bias=float(np.mean(y - p)), metric="brier",
                calibration=[dict(predicted=float(r.p), actual=float(r.y), n=int(r.n)) for r in cal.itertuples()])
