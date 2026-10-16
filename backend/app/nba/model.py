"""NBA projections: points, rebounds, assists and 3-pointers made = projected minutes x per-minute rate x opponent factor.

- Minutes: recency-weighted average of the player's recent games (half-life MIN_HL games), so a new role shows quickly.
- Rate: per-minute production with a longer half-life (RATE_HL games), shrunk toward the position group's average
  (guards, forwards, centers) by PSEUDO_MIN minutes of league-average play, so a small sample can't run away.
- Last season counts PRIOR_SEASON as much as this one (rosters and roles turn over in the summer).
- Opponent: how much each defense allows relative to what its opponents' players usually produce, shrunk to 1.
- Win probabilities for the over/under come from the walk-forward backtest's own errors (engine.model.fit_dist).

Team win chances use a ridge regression of point margins on (home rating - away rating + home court), recency-weighted
by days, as engine/moneyline.py does by weeks for the NFL.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..engine import model as nfl_model
from . import espn

KINDS = ("pts", "reb", "ast", "threes")
MIN_HL = 8.0            # games: minutes follow role changes quickly
RATE_HL = 40.0          # games: per-minute production is steadier (20 and 10 did slightly worse in the backtest)
PRIOR_SEASON = 0.6      # weight on earlier seasons' games
# minutes of position-average play mixed into every rate; threes much less, since who shoots them varies a lot
# within a position (150 made centers who never shoot look like shooters; 30 had the lowest backtest error)
PSEUDO_MIN = {"pts": 150.0, "reb": 150.0, "ast": 150.0, "threes": 30.0}
MIN_GAMES = 5           # games played before a player is projected
MIN_MINUTES = 12.0      # projected minutes below this aren't a prop market
OPP_HL_DAYS = 45.0      # opponent factors: half-life in days
OPP_PRIOR = {"pts": 400.0, "reb": 160.0, "ast": 100.0, "threes": 50.0}    # pseudo-totals pulling each defense's factor toward 1
OPP_CLIP = (0.85, 1.15)
NAIVE_N = 10            # the baseline the backtest compares against: a plain last-10-games average

# team ratings
ML_HL_DAYS = 60.0
ML_RIDGE = 2.0
ML_PRIOR_SEASON = 0.5
ML_MIN_MARKET_WEIGHT = 0.8   # as for the NFL: the ratings know nothing about injuries or rest, so lean on the market


def _weights(g: pd.DataFrame, season: int, hl: float) -> np.ndarray:
    """Per row: 0.5 ** (games ago / hl), times PRIOR_SEASON for earlier seasons. g is one player's games, oldest first."""
    ago = np.arange(len(g))[::-1]
    return 0.5 ** (ago / hl) * np.where(g.season.to_numpy() < season, PRIOR_SEASON, 1.0)


def priors(hist: pd.DataFrame, pos_group: dict) -> dict:
    """Position group -> per-minute rate of each stat (minute-weighted), from the games in hist."""
    h = hist[hist["min"] > 0]
    grp = h.player_id.map(pos_group).fillna("G")
    out = {}
    for g in ("G", "F", "C"):
        sel = h[grp == g]
        tot = sel["min"].sum()
        out[g] = {k: float(sel[k].sum() / tot) if tot else float(h[k].sum() / max(h["min"].sum(), 1)) for k in KINDS}
    return out


def opp_factors(hist: pd.DataFrame, at: date) -> dict:
    """kind -> {team: factor}: what a defense allows against each opponent player's usual per-minute rate."""
    h = hist[hist["min"] > 0]
    if h.empty:
        return {k: {} for k in KINDS}
    days = (pd.Timestamp(at) - pd.to_datetime(h.date)).dt.days.to_numpy()
    w = 0.5 ** (days / OPP_HL_DAYS) * np.where(h.season.to_numpy() < espn.season_for(at), 0.5, 1.0)
    out = {}
    for k in KINDS:
        rate = h.groupby("player_id")[k].sum() / h.groupby("player_id")["min"].sum()
        exp = h.player_id.map(rate).to_numpy() * h["min"].to_numpy()
        frame = pd.DataFrame({"opp": h.opp.to_numpy(), "act": h[k].to_numpy() * w, "exp": exp * w})
        s = frame.groupby("opp")[["act", "exp"]].sum()
        f = (s.act + OPP_PRIOR[k]) / (s.exp + OPP_PRIOR[k])
        out[k] = {t: float(np.clip(v, *OPP_CLIP)) for t, v in f.items()}
    return out


def player_state(g: pd.DataFrame, season: int, prior: dict) -> dict:
    """Projected minutes and shrunk per-minute rates from one player's games (oldest first, minutes > 0)."""
    wm, wr = _weights(g, season, MIN_HL), _weights(g, season, RATE_HL)
    mins = g["min"].to_numpy()
    out = dict(min=float((wm * mins).sum() / wm.sum()), n=len(g))
    for k in KINDS:
        out[k] = float(((wr * g[k].to_numpy()).sum() + PSEUDO_MIN[k] * prior[k]) / ((wr * mins).sum() + PSEUDO_MIN[k]))
        out["naive_" + k] = float(g[k].tail(NAIVE_N).mean())
        out["last5_" + k] = [float(x) for x in g[k].tail(5)]
    return out


def states(hist: pd.DataFrame, pos_group: dict, season: int, prior: dict) -> dict:
    """player_id -> player_state, for everyone with at least MIN_GAMES games in hist."""
    out = {}
    played = hist[hist["min"] > 0]
    for pid, g in played.groupby("player_id", sort=False):
        if len(g) >= MIN_GAMES:
            out[pid] = player_state(g, season, prior[pos_group.get(pid, "G")])
    return out


def project_rows(st: dict, opp: dict, team_opp: str) -> dict:
    """kind -> (mu, per-minute rate after the opponent factor) for one player and opponent."""
    return {k: (st["min"] * st[k] * opp[k].get(team_opp, 1.0), st[k] * opp[k].get(team_opp, 1.0)) for k in KINDS}


def walk_forward(logs: pd.DataFrame, pos_group: dict, start: date, end: date, step_days: int = 7) -> pd.DataFrame:
    """Every game played from start to end, projected with only the games before its week. Columns: kind, mu,
    actual, naive5 (the last-10 average, named like the NFL backtest's baseline), min_proj, min_actual, date."""
    logs = logs[logs["min"] > 0]
    rows = []
    d = start
    while d <= end:
        nxt = d + timedelta(days=step_days)
        ds, dn = d.isoformat(), nxt.isoformat()
        hist, todo = logs[logs.date < ds], logs[(logs.date >= ds) & (logs.date < dn)]
        if len(todo) and len(hist):
            season = espn.season_for(d)
            st = states(hist[hist.player_id.isin(set(todo.player_id))], pos_group, season, priors(hist, pos_group))
            opp = opp_factors(hist, d)
            for r in todo.itertuples():
                s = st.get(r.player_id)
                if not s or s["min"] < MIN_MINUTES:
                    continue
                for k, (mu, _) in project_rows(s, opp, r.opp).items():
                    rows.append((r.date, r.player_id, k, mu, getattr(r, k), s["naive_" + k], s["min"], r.min))
        d = nxt
    return pd.DataFrame(rows, columns=["date", "player_id", "kind", "mu", "actual", "naive5", "min_proj", "min_actual"])


POISSON_KINDS = ("threes",)   # priced as Poisson counts (engine.model.prob_over_under_dist), not from the error table


def calibrate(bt: pd.DataFrame) -> tuple[dict, dict]:
    """(backtest summary per kind, error tables per kind) from a walk-forward frame."""
    if bt.empty:
        return {}, {k: {"poisson": True} for k in POISSON_KINDS}
    dists = nfl_model.fit_dist(bt[~bt.kind.isin(POISSON_KINDS)])
    return nfl_model.backtest_summary(bt), {**dists, **{k: {"poisson": True} for k in POISSON_KINDS}}


# ---------- team ratings and win probability ----------
def ratings(games: pd.DataFrame, at: date) -> tuple[dict, float]:
    """(team -> rating in points, home-court points) from games before `at` in this and the previous season."""
    season = espn.season_for(at)
    hist = games[(games.date < at.isoformat()) & (games.season >= season - 1)]
    if hist.empty:
        return {}, 0.0
    teams = sorted(set(hist.home_team) | set(hist.away_team))
    ti = {t: i for i, t in enumerate(teams)}
    n, rows = len(teams), np.arange(len(hist))
    x = np.zeros((len(hist), n + 1))
    x[rows, hist.home_team.map(ti).to_numpy()] = 1.0
    x[rows, hist.away_team.map(ti).to_numpy()] = -1.0
    x[:, n] = 1.0
    y = (hist.home_score - hist.away_score).to_numpy(float)
    days = (pd.Timestamp(at) - pd.to_datetime(hist.date)).dt.days.to_numpy()
    w = 0.5 ** (days / ML_HL_DAYS) * np.where(hist.season.to_numpy() < season, ML_PRIOR_SEASON, 1.0)
    reg = np.eye(n + 1) * ML_RIDGE
    reg[n, n] = 0.01
    with np.errstate(all="ignore"):
        beta = np.linalg.solve(x.T @ (x * w[:, None]) + reg, x.T @ (w * y))
    return {t: float(beta[i]) for t, i in ti.items()}, float(beta[n])


def ml_walk_forward(games: pd.DataFrame, start: date, end: date, step_days: int = 7) -> pd.DataFrame:
    """Every game from start to end with the margin predicted from earlier games only (columns as engine/moneyline)."""
    out = []
    d = start
    while d <= end:
        nxt = d + timedelta(days=step_days)
        todo = games[(games.date >= d.isoformat()) & (games.date < nxt.isoformat())]
        if len(todo):
            r, hfa = ratings(games, d)
            if r:
                for g in todo.itertuples():
                    m = r.get(g.home_team, 0.0) - r.get(g.away_team, 0.0) + hfa
                    out.append((g.season, d.isoformat(), m, float(g.home_score - g.away_score), np.nan))
        d = nxt
    return pd.DataFrame(out, columns=["season", "week", "margin", "result", "p_mkt"])


def ml_project(games: pd.DataFrame, slate: list[dict], sigma: float, at: date) -> dict:
    """game_id -> the model's view of each slate game, in the shape engine/moneyline.price reads."""
    r, hfa = ratings(games, at)
    out = {}
    for g in slate:
        m = r.get(g["home"], 0.0) - r.get(g["away"], 0.0) + (0.0 if g.get("neutral") else hfa)
        out[g["game_id"]] = dict(home=g["home"], away=g["away"], gameday=g["gameday"], gametime=g["gametime"], margin=m,
                                 p_home=float(np.clip(norm.cdf(m / sigma), 0.01, 0.99)),
                                 home_rating=r.get(g["home"], 0.0), away_rating=r.get(g["away"], 0.0),
                                 spread=g.get("spread_line"), total=g.get("total"))
    return out
