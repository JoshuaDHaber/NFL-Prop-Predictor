"""NBA projections: points, rebounds, assists, 3-pointers made, steals and blocks = projected minutes x per-minute rate
x opponent factor.
The combo markets (PRA, PR, PA) are the sums of their parts' projections, so they always agree with them; only their
error tables are their own (fit on the combo's walk-forward misses).

Double- and triple-doubles are yes/no markets (mu is the chance): each of points, rebounds, assists, steals and blocks
gets its chance of reaching 10 from its error table, those combine as independent events into the chance that at least
2 (or 3) do, and a logistic curve fit on the walk-forward backtest corrects for what independence misses (a big-minutes
night lifts every stat at once: independence alone underrated triple-doubles by about half).

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
from scipy.optimize import minimize
from scipy.stats import norm, poisson

from ..engine import dvp as dvp_mod
from ..engine import model as nfl_model
from . import espn

KINDS = ("pts", "reb", "ast", "threes", "stl", "blk")
COMBOS = {"pra": ("pts", "reb", "ast"), "pr": ("pts", "reb"), "pa": ("pts", "ast")}
DOUBLES = {"dd": 2, "tpl": 3}   # yes/no: at least this many of DD_STATS in double figures
DD_STATS = ("pts", "reb", "ast", "stl", "blk")
ALL_KINDS = KINDS + tuple(COMBOS) + tuple(DOUBLES)
MIN_HL = 8.0            # games: minutes follow role changes quickly
RATE_HL = 40.0          # games: per-minute production is steadier (20 and 10 did slightly worse in the backtest)
PRIOR_SEASON = 0.6      # weight on earlier seasons' games
# minutes of position-average play mixed into every rate; threes much less, since who shoots them varies a lot
# within a position (150 made centers who never shoot look like shooters; 30 had the lowest backtest error). Steals
# and blocks were tuned on the backtest's Poisson log-loss: 150 and 100 (15 to 250 differ by under 0.5%)
PSEUDO_MIN = {"pts": 150.0, "reb": 150.0, "ast": 150.0, "threes": 30.0, "stl": 150.0, "blk": 100.0}
MIN_GAMES = 5           # games played before a player is projected
MIN_MINUTES = 12.0      # projected minutes below this aren't a prop market
OPP_HL_DAYS = 45.0      # opponent factors: half-life in days
OPP_PRIOR = {"pts": 400.0, "reb": 160.0, "ast": 100.0, "threes": 50.0, "stl": 60.0, "blk": 30.0}    # pseudo-totals pulling each defense's factor toward 1
OPP_CLIP = (0.85, 1.15)
NAIVE_N = 10            # the baseline the backtest compares against: a plain last-10-games average

# team ratings
ML_HL_DAYS = 60.0
ML_RIDGE = 2.0
ML_PRIOR_SEASON = 0.5
ML_MIN_MARKET_WEIGHT = 0.8   # as for the NFL: the ratings know nothing about injuries or rest, so lean on the market


def actual(r, kind: str) -> float:
    """A game log row's value for any kind: combos summed from their parts, double- and triple-doubles 1 or 0."""
    if kind in DOUBLES:
        return float(tens(r) >= DOUBLES[kind])
    return sum(getattr(r, k) for k in COMBOS.get(kind, (kind,)))


def tens(r) -> int:
    """How many of DD_STATS a game log row has in double figures."""
    return sum(int(getattr(r, k) >= 10) for k in DD_STATS)


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


DVP_K_ROWS = 20.0      # matchup grades: player-games of par mixed into each defense's factor for a position (engine/dvp.py)


def dvp(hist: pd.DataFrame, at: date, pos_group: dict) -> dict:
    """kind -> {(defense, G/F/C): (factor, rank, teams)} for the matchup grades: what each defense allowed each
    position group against those players' usual per-minute rates, weighted like opp_factors. Combos included."""
    h = hist[hist["min"] > 0]
    if h.empty:
        return {}
    days = (pd.Timestamp(at) - pd.to_datetime(h.date)).dt.days.to_numpy()
    frame = pd.DataFrame({"opp": h.opp.to_numpy(), "grp": h.player_id.map(pos_group).fillna("G").to_numpy(),
                          "w": 0.5 ** (days / OPP_HL_DAYS) * np.where(h.season.to_numpy() < espn.season_for(at), 0.5, 1.0)})
    mins = h.groupby("player_id")["min"].sum()
    for k in KINDS + tuple(COMBOS):
        val = h[list(COMBOS.get(k, (k,)))].sum(axis=1, min_count=1)
        rate = val.groupby(h.player_id).sum() / mins
        frame[f"act_{k}"] = val.to_numpy()
        frame[f"exp_{k}"] = h.player_id.map(rate).to_numpy() * h["min"].to_numpy()
    return dvp_mod.ranks(dvp_mod.factors(frame, KINDS + tuple(COMBOS), DVP_K_ROWS))


def player_state(g: pd.DataFrame, season: int, prior: dict) -> dict:
    """Projected minutes and shrunk per-minute rates from one player's games (oldest first, minutes > 0)."""
    wm, wr = _weights(g, season, MIN_HL), _weights(g, season, RATE_HL)
    mins = g["min"].to_numpy()
    out = dict(min=float((wm * mins).sum() / wm.sum()), n=len(g))
    for k in KINDS:
        out[k] = float(((wr * g[k].to_numpy()).sum() + PSEUDO_MIN[k] * prior[k]) / ((wr * mins).sum() + PSEUDO_MIN[k]))
        out["naive_" + k] = float(g[k].tail(NAIVE_N).mean())
        out["last5_" + k] = [float(x) for x in g[k].tail(5)]
    for c, parts in COMBOS.items():
        out["naive_" + c] = sum(out["naive_" + k] for k in parts)
        out["last5_" + c] = [float(x) for x in g[list(parts)].sum(axis=1).tail(5)]
    n10 = (g[list(DD_STATS)] >= 10).sum(axis=1)
    for k, need in DOUBLES.items():
        hit = (n10 >= need).astype(float)
        out["naive_" + k] = float(hit.tail(NAIVE_N).mean())
        out["last5_" + k] = [float(x) for x in hit.tail(5)]
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
    """kind -> (mu, per-minute rate after the opponent factor) for one player and opponent; combos sum their parts."""
    out = {k: (st["min"] * st[k] * opp[k].get(team_opp, 1.0), st[k] * opp[k].get(team_opp, 1.0)) for k in KINDS}
    for c, parts in COMBOS.items():
        out[c] = (sum(out[k][0] for k in parts), sum(out[k][1] for k in parts))
    return out


# ---------- teammates out ----------
# Each player is projected from his own recent games, so the projection carries his team's usual mix of absences:
# with every regular playing he's over-projected (in the 2025-26 walk-forward, players on a full-strength team went
# over their points projection 37% of the time), and with a star out under-projected (57% over when 15-30% of the
# team's projected points were missing, 84% over 30%). So every stat is scaled by 1 + a x (the share of the team's
# projected production that's missing) + b, with a and b fit on the backtest per stat (b < 0: it centers the
# correction on the usual absences). After it the over rates run 40-46% at every level of absence up to 30%.
# Fitting on 2024-25 and testing on 2025-26 cut points MAE 0.75% and minutes 1.7% (rebounds 0.4%, threes 0.7%).
TM_REG_MIN = 25.0     # projected minutes that make an absent player's production count as missing
TM_MAX_GAP = 20       # team games: someone out longer is fully in his teammates' recent games
TM_A, TM_B = (0.0, 1.5), (-0.15, 0.05)   # bounds on the fitted slope and intercept
TM_MULT = (0.75, 1.6)  # bounds on any one player's multiplier
TM_MIN_ROWS = 200     # player-games with someone missing needed to fit a stat; fewer and it's left alone
_TM_W = 0.5 ** (np.arange(60) / MIN_HL)
_TM_CUM = np.concatenate([[0.0], np.cumsum(_TM_W)]) / _TM_W.sum()


def tm_kept(missed: int) -> float:
    """Share of an absent player's production still missing from his teammates' projections after he's already missed
    `missed` team games: those games are in their recent minutes (weighted as player_state weights minutes)."""
    return float(1.0 - _TM_CUM[min(int(missed), len(_TM_W))])


class Rosters:
    """Who played for whom, from the game logs: enough to tell how many team games a player has missed."""

    def __init__(self, logs: pd.DataFrame):
        played = logs[logs["min"] > 0].sort_values("date")
        self.team_dates = {t: np.sort(g.date.unique()) for t, g in played.groupby("team")}
        self.by_pid = {p: (g.date.to_numpy(), g.team.to_numpy()) for p, g in played.groupby("player_id")}
        self.at = {(t, d): set(g.player_id) for (t, d), g in played.groupby(["team", "date"])}

    def missed(self, pid: str, team: str, day: str):
        """Team games before `day` this player has missed since his last game, if that game was for `team` and he's
        missed fewer than TM_MAX_GAP; else None."""
        dates, teams = self.by_pid.get(pid, ((), ()))
        j = int(np.searchsorted(dates, day)) - 1
        if j < 0 or teams[j] != team:
            return None
        td = self.team_dates[team]
        n = int(np.searchsorted(td, day)) - int(np.searchsorted(td, dates[j])) - 1
        return n if n < TM_MAX_GAP else None

    def recent(self, team: str, day: str) -> set:
        """Everyone who played for `team` in its last TM_MAX_GAP games before `day`."""
        td = self.team_dates.get(team, ())
        i = int(np.searchsorted(td, day))
        return set().union(*(self.at[(team, d)] for d in td[max(0, i - TM_MAX_GAP):i]))


def missing(absent: list, opp: dict, team_opp: str) -> dict:
    """kind (and "min") -> projected production of a team's absent regulars, net of what's already in their
    teammates' recent games. absent: (player_state, team games missed) pairs."""
    out = {k: 0.0 for k in ("min",) + KINDS}
    for s, n in absent:
        if s["min"] < TM_REG_MIN:
            continue
        keep = tm_kept(n)
        out["min"] += s["min"] * keep
        for k, (mu, _) in project_rows(s, opp, team_opp).items():
            if k in out:
                out[k] += mu * keep
    return out


def tm_mults(fit: dict, lost: dict, active: dict) -> dict:
    """kind (and "min") -> multiplier on each active player's projection. active: kind -> the team's total projected
    production among the players who'll play."""
    out = {}
    for k, f in fit.items():
        frac = lost.get(k, 0.0) / max(lost.get(k, 0.0) + active.get(k, 0.0), 1e-9)
        out[k] = float(np.clip(1.0 + f["a"] * frac + f["b"], *TM_MULT))
    return out


def walk_forward(logs: pd.DataFrame, pos_group: dict, start: date, end: date, step_days: int = 7) -> pd.DataFrame:
    """Every game played from start to end, projected with only the games before its week. Columns: kind, mu,
    actual, naive5 (the last-10 average, named like the NFL backtest's baseline), min_proj, min_actual, date, and for the
    same-game correlations (engine/correlation.py) team, opp, pos (G/F/C) and t (the date's ordinal: one game per team a day).
    frac and frac_min: the share of the team's projected production of that row's stat (and minutes) missing, for
    fit_teammates; mu is before that correction (apply_teammates)."""
    logs = logs[logs["min"] > 0]
    ros = Rosters(logs)
    rows = []
    d = start
    while d <= end:
        nxt = d + timedelta(days=step_days)
        ds, dn = d.isoformat(), nxt.isoformat()
        hist, todo = logs[logs.date < ds], logs[(logs.date >= ds) & (logs.date < dn)]
        if len(todo) and len(hist):
            season = espn.season_for(d)
            games = []
            for (team, day), g in todo.groupby(["team", "date"], sort=False):
                active = set(g.player_id)
                out = [(p, n) for p in ros.recent(team, day) - active if (n := ros.missed(p, team, day)) is not None]
                games.append((g, out))
            need = set(todo.player_id) | {p for _, out in games for p, _ in out}
            st = states(hist[hist.player_id.isin(need)], pos_group, season, priors(hist, pos_group))
            opp = opp_factors(hist, d)
            for g, out in games:
                o = g.opp.iat[0]
                lost = missing([(st[p], n) for p, n in out if p in st], opp, o)
                proj = [(r, st[r.player_id], project_rows(st[r.player_id], opp, o)) for r in g.itertuples()
                        if r.player_id in st and st[r.player_id]["min"] >= MIN_MINUTES]
                tot = {k: sum(pr[k][0] for _, _, pr in proj) for k in KINDS}
                tot["min"] = sum(s["min"] for _, s, _ in proj)
                frac = {k: lost[k] / max(lost[k] + tot[k], 1e-9) for k in tot}
                for r, s, pr in proj:
                    ctx = (r.team, r.opp, pos_group.get(r.player_id, "G"), date.fromisoformat(r.date[:10]).toordinal())
                    for k, (mu, _) in pr.items():
                        rows.append((r.date, r.player_id, k, mu, actual(r, k), s["naive_" + k], s["min"], r.min, *ctx,
                                     frac.get(k, np.nan), frac["min"]))
                    for k in DOUBLES:   # chances come from the other rows' error tables (calibrate), so mu is left empty here
                        rows.append((r.date, r.player_id, k, np.nan, actual(r, k), s["naive_" + k], s["min"], r.min, *ctx,
                                     np.nan, frac["min"]))
        d = nxt
    return pd.DataFrame(rows, columns=["date", "player_id", "kind", "mu", "actual", "naive5", "min_proj", "min_actual",
                                       "team", "opp", "pos", "t", "frac", "frac_min"])


def fit_teammates(bt: pd.DataFrame) -> dict:
    """kind (and "min") -> {a, b}: each player's actual - projection regressed on (projection x missing share,
    projection), from a walk-forward frame (before apply_teammates). A stat with too few games with someone missing
    gets a = b = 0 (no change)."""
    out = {}
    if bt.empty or "frac" not in bt:
        return out
    base = bt[bt.kind == "pts"]
    sets = {"min": (base.min_proj.to_numpy(), base.min_actual.to_numpy(), base.frac_min.to_numpy())}
    for k in KINDS:
        b = bt[bt.kind == k]
        sets[k] = (b.mu.to_numpy(), b.actual.to_numpy(), b.frac.to_numpy())
    for k, (mu, act, frac) in sets.items():
        ok = np.isfinite(mu) & np.isfinite(act) & np.isfinite(frac)
        mu, act, frac = mu[ok], act[ok], frac[ok]
        if (frac > 0).sum() < TM_MIN_ROWS:
            out[k] = dict(a=0.0, b=0.0)
            continue
        a, b = np.linalg.lstsq(np.c_[mu * frac, mu], act - mu, rcond=None)[0]
        out[k] = dict(a=float(np.clip(a, *TM_A)), b=float(np.clip(b, *TM_B)))
    return out


def apply_teammates(bt: pd.DataFrame, fit: dict) -> pd.DataFrame:
    """The walk-forward frame with every stat's projection scaled for missing teammates (tm_mults' formula), minutes
    too, and the combos re-summed from their parts."""
    if bt.empty or not fit:
        return bt
    bt = bt.copy()
    for k in KINDS:
        f = fit.get(k)
        sel = bt.kind == k
        if f and sel.any():
            bt.loc[sel, "mu"] = bt.mu[sel] * np.clip(1 + f["a"] * bt.frac[sel] + f["b"], *TM_MULT)
    if "min" in fit:
        bt["min_proj"] = bt.min_proj * np.clip(1 + fit["min"]["a"] * bt.frac_min + fit["min"]["b"], *TM_MULT)
    parts = bt[bt.kind.isin(KINDS)].set_index(["date", "player_id", "kind"]).mu
    for c, ks in COMBOS.items():
        sel = bt.kind == c
        idx = pd.MultiIndex.from_frame(bt.loc[sel, ["date", "player_id"]])
        bt.loc[sel, "mu"] = sum(parts.xs(k, level="kind").reindex(idx).to_numpy() for k in ks)
    return bt


POISSON_KINDS = ("threes", "stl", "blk")   # priced as Poisson counts (engine.model.prob_over_under_dist), not from the error table


def calibrate(bt: pd.DataFrame) -> tuple[dict, dict]:
    """(backtest summary per kind, error tables per kind) from a walk-forward frame. The tables also carry
    "_doubles": the double- and triple-double calibration curves (fit_doubles)."""
    if bt.empty:
        return {}, {k: {"poisson": True} for k in POISSON_KINDS}
    stats = bt[~bt.kind.isin(DOUBLES)]
    dists = {**nfl_model.fit_dist(stats[~stats.kind.isin(POISSON_KINDS)]), **{k: {"poisson": True} for k in POISSON_KINDS}}
    curves, summary = fit_doubles(bt, dists)
    return {**nfl_model.backtest_summary(stats), **summary}, {**dists, "_doubles": curves}


def p_ten(mu: np.ndarray, dist: dict) -> np.ndarray:
    """P(stat >= 10) at each projection. Unlike prob_over_under_dist, no 1% floor: most players' assist or rebound
    chances really are tiny, and a floor on five of them would add up to a double-double chance nobody has."""
    mu = np.asarray(mu, float)
    if dist.get("poisson"):
        return poisson.sf(9, np.maximum(mu, 1e-6))
    sd = np.interp(mu, dist["mu"], dist["sd"])
    return 1 - np.interp((9.5 - mu) / sd, dist["z"], nfl_model.Z_PROBS, left=0.0, right=1.0)


def _at_least(ps: list, n: int) -> np.ndarray:
    """P(at least n of independent events happen), row by row (each of ps is an array of chances)."""
    dist = np.zeros((len(ps[0]), len(ps) + 1))
    dist[:, 0] = 1.0
    for p in ps:
        nxt = dist * (1 - p)[:, None]
        nxt[:, 1:] += dist[:, :-1] * p[:, None]
        dist = nxt
    return dist[:, n:].sum(axis=1)


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def doubles(mus: dict, dists: dict, curves: dict) -> dict:
    """kind -> (chance, expected stats in double figures) for one player, from his projections (kind -> mu)."""
    ps = [p_ten([mus[k]], dists[k]) for k in DD_STATS]
    out = {}
    for k, need in DOUBLES.items():
        c = curves.get(k, {"a": 0.0, "b": 1.0})
        p = float(1 / (1 + np.exp(-(c["a"] + c["b"] * _logit(_at_least(ps, need)[0])))))
        out[k] = (float(np.clip(p, 0.001, 0.99)), float(sum(x[0] for x in ps)))
    return out


def fit_doubles(bt: pd.DataFrame, dists: dict) -> tuple[dict, dict]:
    """(kind -> logistic curve {a, b} on the logit of the independent chance, kind -> Brier-score backtest summary
    against the player's own last-10 rate) from a walk-forward frame."""
    mu = bt[bt.kind.isin(DD_STATS)].pivot_table(index=["date", "player_id"], columns="kind", values="mu")
    if mu.empty or not all(k in mu and k in dists for k in DD_STATS):
        return {}, {}
    ps = [p_ten(mu[k].to_numpy(), dists[k]) for k in DD_STATS]
    curves, summary = {}, {}
    for k, need in DOUBLES.items():
        y = bt[bt.kind == k].set_index(["date", "player_id"]).reindex(mu.index)
        ok = y.actual.notna().to_numpy()
        x, hit, naive = _logit(_at_least(ps, need))[ok], y.actual.to_numpy()[ok], y.naive5.to_numpy()[ok]
        if not ok.any() or hit.min() == hit.max():
            continue
        nll = lambda ab: float(np.mean(np.logaddexp(0, ab[0] + ab[1] * x) - hit * (ab[0] + ab[1] * x)))  # noqa: E731
        a, b = minimize(nll, [0.0, 1.0]).x
        curves[k] = dict(a=float(a), b=float(b))
        p = 1 / (1 + np.exp(-(a + b * x)))
        cal = pd.DataFrame({"p": p, "y": hit}).assign(bin=lambda d: pd.qcut(d.p.rank(method="first"), 5, labels=False)) \
            .groupby("bin").agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
        summary[k] = dict(n=int(len(hit)), mae_model=float(np.mean((p - hit) ** 2)), mae_naive=float(np.mean((naive - hit) ** 2)),
                          bias=float(np.mean(hit - p)), metric="brier",
                          calibration=[dict(predicted=float(r.p), actual=float(r.y), n=int(r.n)) for r in cal.itertuples()])
    return curves, summary


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
