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
REL = ("same", "team", "opp")
PAIR_BATCH = 500_000    # pairs held in memory at once while fitting


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


class _Pairs:
    """Every pair of rows in the same game (each pair once), keyed by an integer code for its key and generated a game at a
    time. Materialized as one merged frame of strings, the NBA backtest's ~15M pairs took over 2 GB on a 512 MB host."""
    def __init__(self, d: pd.DataFrame):
        d = d.sort_values("game", kind="stable")
        self.descs = sorted(d.desc.unique())
        self.n_desc = len(self.descs)
        self.desc = d.desc.map({x: i for i, x in enumerate(self.descs)}).to_numpy(np.int64)
        self.kind = d.kind.to_numpy()
        self.player, self.team = pd.factorize(d.player_id)[0], pd.factorize(d.team)[0]
        self.z, self.hit = d.z.to_numpy(float), d.hit.to_numpy(float)
        g = d.game.to_numpy()
        cuts = np.flatnonzero(g[1:] != g[:-1]) + 1
        self.games = list(zip(np.r_[0, cuts], np.r_[cuts, len(d)]))
        self._counts = None

    def _game(self, lo: int, hi: int):
        i, j = np.triu_indices(hi - lo, 1)
        i, j = i + lo, j + lo
        rel = np.where(self.player[i] == self.player[j], 0, np.where(self.team[i] == self.team[j], 1, 2))
        a, b = np.minimum(self.desc[i], self.desc[j]), np.maximum(self.desc[i], self.desc[j])
        return (rel * self.n_desc + a) * self.n_desc + b, i, j

    def key(self, code: int) -> str:
        rel, rest = divmod(int(code), self.n_desc ** 2)
        a, b = divmod(rest, self.n_desc)
        return pair_key(REL[rel], self.descs[a], self.descs[b])

    def kinds(self, code: int) -> tuple:
        """The two legs' markets: the first row of each desc carries it."""
        a, b = divmod(int(code) % self.n_desc ** 2, self.n_desc)
        return tuple(self.kind[np.argmax(self.desc == x)] for x in (a, b))

    def counts(self) -> np.ndarray:
        """Pairs per key code."""
        if self._counts is None:
            self._counts = np.zeros(len(REL) * self.n_desc ** 2, np.int64)
            for lo, hi in self.games:
                self._counts += np.bincount(self._game(lo, hi)[0], minlength=len(self._counts))
        return self._counts

    def groups(self, codes):
        """(code, rows a, rows b) for each listed key, gathering about PAIR_BATCH pairs at a time."""
        counts, batch, size = self.counts(), [], 0
        for c in sorted(codes):
            batch.append(c)
            size += counts[c]
            if size >= PAIR_BATCH:
                yield from self._gather(batch)
                batch, size = [], 0
        if batch:
            yield from self._gather(batch)

    def _gather(self, codes):
        want = np.zeros(len(self.counts()), bool)
        want[codes] = True
        parts = []
        for lo, hi in self.games:
            k, i, j = self._game(lo, hi)
            m = want[k]
            parts.append((k[m], i[m], j[m]))
        k, i, j = (np.concatenate(x) for x in zip(*parts))
        order = np.argsort(k, kind="stable")
        k, i, j = k[order], i[order], j[order]
        starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]]) if len(k) else np.array([], int)
        for a, b in zip(starts, np.r_[starts[1:], len(k)]):
            yield int(k[a]), i[a:b], j[a:b]


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


def _estimate(za, zb, ha, hb) -> float:
    if np.isfinite(za).all() and np.isfinite(zb).all():
        rs = st.spearmanr(za, zb).statistic
        return float(2 * np.sin(np.pi * rs / 6)) if np.isfinite(rs) else 0.0
    return tetrachoric(ha, hb)


def fit_table(pairs: _Pairs, k: float = None) -> dict:
    """key -> [shrunk latent correlation, pairs]"""
    k = SHRINK_K if k is None else k
    out = {}
    for code, i, j in pairs.groups(np.flatnonzero(pairs.counts() >= MIN_PAIRS)):
        n = len(i)
        r = _estimate(pairs.z[i], pairs.z[j], pairs.hit[i], pairs.hit[j]) * n / (n + k)
        if abs(r) >= 0.01:
            out[pairs.key(code)] = [round(r, 4), n]
    return dict(sorted(out.items()))


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


def _grouped_scores(n: np.ndarray, hits: np.ndarray, pred: np.ndarray, ind: np.ndarray) -> dict:
    """_scores for pairs grouped by prediction: n pairs per group, hits of them that both hit."""
    total = n.sum()
    if not total:
        return dict(n=0)
    brier = lambda p: float((n * p * p - 2 * p * hits + hits).sum() / total)   # sum of (p - y)^2 over a group's pairs
    return dict(n=int(total), actual=float(hits.sum() / total), copula=float((n * pred).sum() / total),
                independent=float((n * ind).sum() / total), brier_copula=brier(pred), brier_independent=brier(ind))


def _check(pairs: _Pairs, table: dict, rates: dict, d_test: pd.DataFrame) -> dict:
    """Held-out weeks: the joint hit rate the copula and independence predict, against what happened. Each leg's chance is
    its market's base rate (the backtest has no lines). Pairs the table calls correlated (|rho| >= 0.15) are scored apart
    by sign, where the two methods differ; triples are every quarterback with two of his receivers, all overs.
    A pair's prediction depends only on its key, so pairs are scored a key at a time."""
    out = {}
    codes = np.flatnonzero(pairs.counts())
    rho = {c: table.get(pairs.key(c), [0.0])[0] for c in codes}
    for name, sel in (("positive", lambda r: r >= 0.15), ("negative", lambda r: r <= -0.15)):
        n, hits, cop, ind = [], [], [], []
        for code, i, j in pairs.groups([c for c in codes if sel(rho[c])]):
            pa, pb = (rates[x] for x in pairs.kinds(code))
            n.append(len(i))
            hits.append(float((pairs.hit[i] * pairs.hit[j]).sum()))
            cop.append(joint_prob([pa, pb], [1, 1], [[1, rho[code]], [rho[code], 1]]))
            ind.append(pa * pb)
        out[name] = _grouped_scores(*(np.array(v, float) for v in (n, hits, cop, ind)))
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
    check = {}
    if len(test) and len(train):
        early = fit_table(_Pairs(train))   # one set of pairs alive at a time
        check = _check(_Pairs(test), early, rates, test)
    del train, test
    table = fit_table(_Pairs(d))
    return dict(pairs=table, k=SHRINK_K, min_pairs=MIN_PAIRS, check=check, holdout_from=int(split))
