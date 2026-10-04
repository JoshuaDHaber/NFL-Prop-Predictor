"""Projection model for rushing and receiving yards.

yards = volume (carries | targets) x efficiency (yds/carry | yds/target)
  * volume: exponentially recency-weighted average, shrunk toward a low prior
  * efficiency: recency-weighted, heavily shrunk toward the position mean
  * opponent: shrunk yards-allowed-per-game factor vs. league average
  * game script: team spread nudges rush volume up (favorites) / pass volume down
The spread and shape of outcomes come from the walk-forward backtest of this same model: the typical error
(a robust spread, binned by projection size) and the empirical distribution of standardized errors. So the
chance of beating a line matches how often actual yardage beat the projection, including skew and blow-up
games. (Older runs used an assumed gamma curve, kept as a fallback in prob_over_under.)
"""
import numpy as np
import pandas as pd
from scipy import stats as st

from . import td as tdm

HALFLIFE = 5.0          # games
VOL_PRIOR_K = {"rush": 0.5, "rec": 0.5, "pass": 0.2}   # pseudo-games of shrinkage on volume (QB volume is stable)
EFF_K = {"rush": 40.0, "rec": 30.0, "pass": 120.0}   # pseudo-attempts of shrinkage on efficiency
OPP_SHRINK_GAMES = 8.0
OPP_STRENGTH = 0.5      # fraction of the (shrunk) opponent deviation applied
SCRIPT_RUSH = 0.012     # per spread point (favorite = positive)
SCRIPT_REC = -0.006
SCRIPT_PASS = -0.006

CFG = {
    "rush": dict(vol="carries", yds="rushing_yards", min_vol=4.0),
    "rec": dict(vol="targets", yds="receiving_yards", min_vol=3.0),
    "pass": dict(vol="attempts", yds="passing_yards", min_vol=15.0),
}
POSITIONS = {"rush": ("QB", "RB", "WR", "TE", "FB"), "rec": ("RB", "WR", "TE", "FB"), "pass": ("QB",)}
SCRIPT = {"rush": SCRIPT_RUSH, "rec": SCRIPT_REC, "pass": SCRIPT_PASS}


def prep(stats):
    df = stats.sort_values(["season", "week"]).copy()
    df["t"] = df.season * 100 + df.week
    return df


def league_priors(df):
    pri = {}
    for kind, c in CFG.items():
        d = df[df[c["vol"]] > 0]
        for pos, g in d.groupby("position"):
            if pos not in POSITIONS[kind]:
                continue
            pri[(kind, pos)] = g[c["yds"]].sum() / g[c["vol"]].sum()
    return pri


def opp_table(df, upto_t):
    """Yards allowed per game by defense, split by stat kind, relative to league avg."""
    d = df[df.t < upto_t]
    out = {}
    for kind, c in CFG.items():
        per_game = d.groupby(["opponent_team", "season", "week"])[c["yds"]].sum()
        per_def = per_game.groupby("opponent_team").agg(["mean", "count"])
        lg = per_game.mean()
        shrunk = (per_def["mean"] * per_def["count"] + lg * OPP_SHRINK_GAMES) / (per_def["count"] + OPP_SHRINK_GAMES)
        out[kind] = (shrunk / lg - 1.0).to_dict()
    return out


def project_player(hist, kind, prior_eff, opp_dev=0.0, spread=0.0):
    """hist: that player's prior games (sorted). Returns (mu, vol_hat, eff_hat) or None."""
    c = CFG[kind]
    h = hist[hist[c["vol"]] > 0]
    if h.empty:
        return None
    # age in the player's own games, measured over ALL his team-games in hist (including 0-usage)
    ages = np.arange(len(hist))[::-1]
    w_all = 0.5 ** (ages / HALFLIFE)
    vol_all = hist[c["vol"]].to_numpy(float)
    vol_hat = (w_all * vol_all).sum() / (w_all.sum() + VOL_PRIOR_K[kind])
    w = w_all[(hist[c["vol"]] > 0).to_numpy()]
    yds, vol = h[c["yds"]].to_numpy(float), h[c["vol"]].to_numpy(float)
    eff_hat = ((w * yds).sum() + EFF_K[kind] * prior_eff) / ((w * vol).sum() + EFF_K[kind])
    script = SCRIPT[kind]
    vol_adj = vol_hat * float(np.clip(1 + script * spread, 0.85, 1.15))
    mu = vol_adj * eff_hat * (1 + OPP_STRENGTH * opp_dev)
    return mu, vol_adj, eff_hat


def components(hist, pos, priors, opp, spread):
    """Per-kind (mu, vol, eff) for one player, no volume floor applied."""
    out = {}
    for kind in CFG:
        pe = priors.get((kind, pos))
        if pe is None:
            continue
        res = project_player(hist, kind, pe, opp[kind].get(hist.attrs["opp"], 0.0), spread)
        if res:
            out[kind] = res
    return out


def combined(comp):
    """Rush+rec projection from components; needs real volume in both roles or an RB-like rush role."""
    r, c = comp.get("rush"), comp.get("rec")
    if not r or not c or r[1] < CFG["rush"]["min_vol"] or c[1] < CFG["rec"]["min_vol"]:
        return None
    return (r[0] + c[0], r[1] + c[1], (r[0] + c[0]) / (r[1] + c[1]))


def all_kinds(hist, pos, priors, opp, spread, comp=None):
    comp = comp if comp is not None else components(hist, pos, priors, opp, spread)
    res = {k: v for k, v in comp.items() if v[1] >= CFG[k]["min_vol"]}
    if pos != "QB" and (rr := combined(comp)):
        res["rr"] = rr
    return res


def actual_hist(df, kind):
    return df["rushing_yards"].fillna(0) + df["receiving_yards"].fillna(0) if kind == "rr" else df[CFG[kind]["yds"]]


def walk_forward(df, priors, sched, start_t, td_priors=None):
    """Project every historical player-game from t >= start_t using only prior data.

    With td_priors, anytime-TD rows are added too (kind "td": mu = unscaled P(>=1 TD), actual = 0/1).
    """
    spread_map = _spread_lookup(sched)
    implied_map = tdm.implied_points(sched)
    rows = []
    opp_cache = {t: opp_table(df, t) for t in sorted(df[df.t >= start_t].t.unique())}
    for pid, g in df.groupby("player_id"):
        g = g.reset_index(drop=True)
        for i in range(3, len(g)):
            r = g.iloc[i]
            if r.t < start_t:
                continue
            hist = g.iloc[:i].copy()
            hist.attrs["opp"] = r.opponent_team
            sp = spread_map.get((r.season, r.week, r.team), 0.0)
            comp = components(hist, r.position, priors, opp_cache[r.t], sp)
            for kind, (mu, vol, eff) in all_kinds(hist, r.position, priors, opp_cache[r.t], sp, comp).items():
                rows.append((pid, r.player_display_name, kind, r.t, mu, float(actual_hist(g.iloc[[i]], kind).iloc[0]),
                             float(actual_hist(hist, kind).tail(5).mean())))
            if td_priors is not None:
                res = tdm.project_td(hist, comp, r.position, td_priors, implied_map.get((r.season, r.week, r.team)))
                if res:
                    rows.append((pid, r.player_display_name, "td", r.t, res[0], float(tdm.td_count(g.iloc[[i]]).iloc[0] >= 1),
                                 float((tdm.td_count(hist).tail(8) >= 1).mean())))
    return pd.DataFrame(rows, columns=["player_id", "name", "kind", "t", "mu", "actual", "naive5"])


Z_PROBS = np.linspace(0, 1, 41)


def fit_dist(bt):
    """Per kind: robust spread by projection size, plus the empirical quantiles of standardized errors.

    sd(mu) is the IQR-based spread of (actual - mu) in bins of mu, interpolated between bin centers; z is
    (actual - mu) / sd(mu), so its quantiles carry the real skew and tails.
    """
    out = {}
    for kind, g in bt.groupby("kind"):
        g = g.copy()
        nb = int(np.clip(len(g) // 60, 3, 6))
        g["bin"] = pd.qcut(g.mu, nb, duplicates="drop")
        mus, sds = [], []
        for _, b in g.groupby("bin", observed=True):
            res = b.actual - b.mu
            mus.append(float(b.mu.mean()))
            sds.append(float(max(np.subtract(*np.percentile(res, [75, 25])) / 1.349, 1e-3)))
        z = (g.actual - g.mu) / np.interp(g.mu, mus, sds)
        out[kind] = dict(mu=mus, sd=sds, z=[float(x) for x in np.quantile(z, Z_PROBS)])
    return out


def sd_at(mu, dist):
    """Typical error (standard-deviation scale) at a projection, from a fit_dist table."""
    return float(np.interp(mu, dist["mu"], dist["sd"]))


def prob_over_under_dist(mu, line, dist):
    """(p_over, p_under) from the empirical error distribution. Whole-number lines leave room for a push."""
    sd = sd_at(mu, dist)

    def cdf(y):  # P(actual <= y)
        return float(np.interp((y - mu) / sd, dist["z"], Z_PROBS))

    if float(line) == int(line):
        po, pu = 1 - cdf(line + 0.5), cdf(line - 0.5)
    else:
        po, pu = 1 - cdf(line), cdf(line)
    return min(max(po, 0.01), 0.99), min(max(pu, 0.01), 0.99)  # the data can't justify certainty


def backtest_summary(bt):
    out = {}
    for kind, g in bt.groupby("kind"):
        out[kind] = dict(
            n=len(g),
            mae_model=float((g.actual - g.mu).abs().mean()),
            mae_naive=float((g.actual - g.naive5).abs().mean()),
            bias=float((g.actual - g.mu).mean()),
        )
    return out


def _spread_lookup(sched):
    m = {}
    for _, r in sched.iterrows():
        if pd.notna(r.spread_line):
            m[(r.season, r.week, r.home_team)] = float(r.spread_line)
            m[(r.season, r.week, r.away_team)] = -float(r.spread_line)
    return m


def prob_over_under(mu, line, var):
    """Gamma outcome distribution; integer yards so continuity-correct. Returns (p_over, p_under)."""
    shape, scale = mu * mu / var, var / mu
    d = st.gamma(shape, scale=scale)
    if float(line) == int(line):                      # whole-number line: push possible
        return float(d.sf(line + 0.5)), float(d.cdf(line - 0.5))
    return float(d.sf(line)), float(d.cdf(line))


def upcoming_projections(df, sched, priors, var_params, week_t, roster, td_priors=None, td_scale=1.0):
    """Project all active players for games not yet played in the target week."""
    season, week = divmod(week_t, 100)
    games = sched[(sched.season == season) & (sched.week == week) & sched.home_score.isna()]
    opp = opp_table(df, week_t)
    implied_map = tdm.implied_points(sched)
    latest = df.sort_values("t").groupby("player_id").tail(1).set_index("player_id")
    by_player = {pid: g for pid, g in df.groupby("player_id")}
    rows = []
    for _, gm in games.iterrows():
        for team, other, sp in ((gm.home_team, gm.away_team, gm.spread_line), (gm.away_team, gm.home_team, -gm.spread_line)):
            sp = 0.0 if pd.isna(sp) else float(sp)
            on_team = latest[latest.index.map(lambda i: roster.get(i) == team) & (latest.t >= (season - 1) * 100)]
            # skip offseason arrivals with no games for the new team: their old role doesn't carry over
            on_team = on_team[on_team.team == team]
            for pid, p in on_team.iterrows():
                hist = by_player[pid]
                if len(hist) < 2:
                    continue
                hist = hist.copy()
                hist.attrs["opp"] = other
                comp = components(hist, p.position, priors, opp, sp)
                if td_priors is not None:
                    res = tdm.project_td(hist, comp, p.position, td_priors, implied_map.get((season, week, team)), td_scale)
                    if res:  # kind "td": mu = P(>=1 TD), vol = expected touches, eff = expected TDs
                        rows.append(dict(player_id=pid, name=p.player_display_name, pos=p.position, team=team,
                                         opp=other, home=team == gm.home_team, kind="td", mu=res[0], vol=res[2], eff=res[1],
                                         sd=0.0, spread=sp, gameday=gm.gameday, gametime=gm.gametime, game_id=gm.game_id,
                                         last5=tdm.td_count(hist).tail(5).tolist()))
                for kind, (mu, vol, eff) in all_kinds(hist, p.position, priors, opp, sp, comp).items():
                    rows.append(dict(player_id=pid, name=p.player_display_name, pos=p.position, team=team,
                                     opp=other, home=team == gm.home_team, kind=kind, mu=mu, vol=vol, eff=eff,
                                     sd=sd_at(mu, var_params[kind]), spread=sp,
                                     gameday=gm.gameday, gametime=gm.gametime, game_id=gm.game_id,
                                     last5=actual_hist(hist, kind).tail(5).tolist()))
    return pd.DataFrame(rows)
