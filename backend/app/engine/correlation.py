"""Same-game correlations, for pricing parlays whose legs share a game.

Legs in one game aren't independent: a quarterback's passing yards and his receivers' yards rise and fall together, the
two teams' lead backs pull apart (the team ahead runs, the one behind throws). Multiplying their chances misprices those
parlays by 25-50%. A Gaussian copula fixes most of that while keeping each leg's own calibrated chance: each leg is a
latent standard normal that "hits" below the threshold Phi^-1(p), and legs share a correlation that depends only on
who they are relative to each other:

    key = relation | market:position | market:position     relation: same (player), team (mates) or opp (onents)

e.g. "team|pass:QB|rec:WR". Each key's latent correlation is fitted on the walk-forward backtest's own results (what
happened against what was projected), so the projection's skill is already taken out:
  * both markets yardage-like: Spearman's rho of the standardized misses, as a normal correlation 2 sin(pi rho / 6)
  * either a touchdown market: the tetrachoric correlation of the two yes/no outcomes (over the projection, or scored)
and is shrunk toward 0 by its sample size. An Under flips its leg's sign. First TD is left out: two players can't both
score first, which no correlation can express (and parlays never use it). The frontend prices parlays with the same
table and the same approximation (parlays.ts), so this module's joint_prob is the reference for its tests.
"""
import itertools

import numpy as np
import pandas as pd
from scipy import stats as st

from . import model
from .td import YES_NO

MIN_PAIRS = 40        # a key needs this many backtested pairs to get a correlation at all
SHRINK_K = 20.0       # pseudo-pairs of zero correlation mixed in: rho * n / (n + K); 20 had the best held-out Brier
HOLDOUT_SHARE = 0.35  # the latest share of backtest weeks held out to check the fitted table
POS = {"FB": "RB"}


def leg_desc(kind: str, pos: str) -> str:
    return f"{kind}:{POS.get(pos, pos)}"


def pair_key(rel: str, a: str, b: str) -> str:
    """rel: "same", "team" or "opp"; a, b: leg_desc(...). Order doesn't matter."""
    a, b = sorted((a, b))
    return f"{rel}|{a}|{b}"


def _rows(bt: pd.DataFrame, dists: dict) -> pd.DataFrame:
    """One row per backtested player-game-market: its game, its yes/no outcome (over the projection, or scored) and, for
    yardage-like markets, its standardized miss."""
    dists = {k: v for k, v in dists.items() if isinstance(v, dict) and not k.startswith("_")}   # a run's error tables only
    d = bt[bt.kind.isin(set(dists) | {"td"})].reset_index(drop=True)
    d = d.assign(game=[f"{t}|{'|'.join(sorted((a, b)))}" for t, a, b in zip(d.t, d.team, d.opp)],
                 desc=[leg_desc(k, p) for k, p in zip(d.kind, d.pos)])
    yn = d.kind.isin(YES_NO).to_numpy()
    sd = np.array([1.0 if y else model.sd_at(m, dists[k]) for y, m, k in zip(yn, d.mu, d.kind)])
    d["z"] = np.where(yn, np.nan, (d.actual - d.mu) / sd)
    d["hit"] = np.where(yn, d.actual > 0.5, d.actual > d.mu).astype(float)
    return d


def _pairs(d: pd.DataFrame) -> pd.DataFrame:
    """Every pair of rows in the same game (each pair once), with its key."""
    d = d.assign(i=np.arange(len(d)))
    cols = ["game", "i", "player_id", "team", "desc", "kind", "z", "hit"]
    p = d[cols].merge(d[cols], on="game", suffixes=("_a", "_b"))
    p = p[p.i_a < p.i_b]
    rel = np.where(p.player_id_a == p.player_id_b, "same", np.where(p.team_a == p.team_b, "team", "opp"))
    return p.assign(key=[pair_key(r, a, b) for r, a, b in zip(rel, p.desc_a, p.desc_b)])


def tetrachoric(x, y) -> float:
    """Latent normal correlation behind two yes/no outcomes: the one whose bivariate normal gives their joint rate."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    pa, pb, pab = x.mean(), y.mean(), (x * y).mean()
    if min(pa, pb) <= 0 or max(pa, pb) >= 1:
        return 0.0
    za, zb = st.norm.ppf(pa), st.norm.ppf(pb)
    lo, hi = -0.95, 0.95
    for _ in range(40):
        mid = (lo + hi) / 2
        if _bvn(za, zb, mid) < pab:
            lo = mid
        else:
            hi = mid
    return float((lo + hi) / 2)


def _bvn(za, zb, r):
    return float(st.multivariate_normal(mean=[0, 0], cov=[[1, r], [r, 1]]).cdf([za, zb]))


def _estimate(g: pd.DataFrame) -> float:
    if g.z_a.notna().all() and g.z_b.notna().all():
        rs = st.spearmanr(g.z_a, g.z_b).statistic
        return float(2 * np.sin(np.pi * rs / 6)) if np.isfinite(rs) else 0.0
    return tetrachoric(g.hit_a, g.hit_b)


def fit_table(pairs: pd.DataFrame, k: float = None) -> dict:
    """key -> [shrunk latent correlation, pairs]"""
    k = SHRINK_K if k is None else k
    out = {}
    for key, g in pairs.groupby("key"):
        n = len(g)
        if n < MIN_PAIRS:
            continue
        r = _estimate(g) * n / (n + k)
        if abs(r) >= 0.01:
            out[key] = [round(r, 4), n]
    return out


def joint_prob(probs, signs, rho) -> float:
    """Chance every leg hits: P(all latent X_i < Phi^-1(p_i)), X ~ N(0, R) with R_ij = s_i s_j rho_ij (an Under has s = -1).

    Mendell-Elston: condition on one leg at a time (likeliest-to-miss first), replacing the truncated normal by one with
    its mean and variance. Exact for one or two independent legs, within about half a point of simulation for the
    correlations seen here, and deterministic, so parlays can be searched and re-priced without noise."""
    p = np.clip(np.asarray(probs, float), 1e-9, 1 - 1e-9)
    n = len(p)
    if n == 0:
        return 1.0
    s = np.asarray(signs, float)
    r = np.array(rho, float) * np.outer(s, s)
    np.fill_diagonal(r, 1.0)
    order = np.argsort(p)
    z, r = st.norm.ppf(p[order]), r[np.ix_(order, order)]
    out = 1.0
    for k in range(n):
        pk = float(st.norm.cdf(z[k]))
        out *= pk
        if k == n - 1 or pk <= 0:
            break
        a = float(st.norm.pdf(z[k]) / pk)
        shrink = 1.0 - (1.0 - z[k] * a - a * a)        # variance the truncation removes: 1 - Var(X | X < z)
        rest = slice(k + 1, n)
        rk = r[k, rest]
        scale = np.sqrt(np.maximum(1.0 - rk * rk * shrink, 1e-9))
        z[rest] = (z[rest] + rk * a) / scale
        r[rest, rest] = (r[rest, rest] - np.outer(rk, rk) * shrink) / np.outer(scale, scale)
        np.fill_diagonal(r, 1.0)
    return float(out)


def _scores(pred: np.ndarray, ind: np.ndarray, y: np.ndarray) -> dict:
    if not len(y):
        return dict(n=0)
    return dict(n=int(len(y)), actual=float(y.mean()), copula=float(pred.mean()), independent=float(ind.mean()),
                brier_copula=float(np.mean((pred - y) ** 2)), brier_independent=float(np.mean((ind - y) ** 2)))


def _check(pairs: pd.DataFrame, table: dict, rates: dict, d_test: pd.DataFrame) -> dict:
    """Held-out weeks: the joint hit rate the copula and independence predict, against what happened. Each leg's chance is
    its market's base rate (the backtest has no lines). Pairs the table calls correlated (|rho| >= 0.15) are scored apart
    by sign, where the two methods differ; triples are every quarterback with two of his receivers, all overs."""
    out = {}
    rho = pairs.key.map(lambda k: table.get(k, [0.0])[0]).to_numpy()
    pa, pb = pairs.kind_a.map(rates).to_numpy(), pairs.kind_b.map(rates).to_numpy()
    y = (pairs.hit_a * pairs.hit_b).to_numpy()
    for name, sel in (("positive", rho >= 0.15), ("negative", rho <= -0.15)):
        cop = np.array([joint_prob([a, b], [1, 1], [[1, r], [r, 1]]) for a, b, r in zip(pa[sel], pb[sel], rho[sel])])
        out[name] = _scores(cop, pa[sel] * pb[sel], y[sel])
    rows = []
    for _, g in d_test.groupby(["game", "team"]):
        qb, rec = g[g.kind == "pass"], g[g.kind == "rec"]
        if qb.empty:
            continue
        for i, j in itertools.combinations(range(len(rec)), 2):
            legs = [qb.iloc[0], rec.iloc[i], rec.iloc[j]]
            R = np.eye(3)
            for x, z in ((0, 1), (0, 2), (1, 2)):
                R[x, z] = R[z, x] = table.get(pair_key("team", legs[x].desc, legs[z].desc), [0.0])[0]
            ps = [rates[x.kind] for x in legs]
            rows.append((joint_prob(ps, [1, 1, 1], R), float(np.prod(ps)), float(all(x.hit for x in legs))))
    out["triples"] = _scores(*(np.array(v) for v in zip(*rows))) if rows else dict(n=0)
    return out


def fit(bt: pd.DataFrame, dists: dict) -> dict:
    """The correlation table from the whole backtest, plus a check of a table fitted on its earlier weeks against the
    later ones (stored with the run; the Model check page shows the check)."""
    d = _rows(bt, dists)
    if d.empty:
        return dict(pairs={}, k=SHRINK_K, check={})
    weeks = np.sort(d.t.unique())
    split = weeks[int(len(weeks) * (1 - HOLDOUT_SHARE))] if len(weeks) > 3 else weeks[-1] + 1
    train, test = d[d.t < split], d[d.t >= split]
    rates = d.groupby("kind").hit.mean().to_dict()
    check = _check(_pairs(test), fit_table(_pairs(train)), rates, test) if len(test) and len(train) else {}
    table = fit_table(_pairs(d))
    return dict(pairs=table, k=SHRINK_K, min_pairs=MIN_PAIRS, check=check, holdout_from=int(split))
