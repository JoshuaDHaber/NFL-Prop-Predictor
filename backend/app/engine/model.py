"""Projection model for rushing and receiving yards.

yards = volume (carries | targets) x efficiency (yds/carry | yds/target)
  * volume: exponentially recency-weighted average, shrunk toward a low prior
  * efficiency: recency-weighted, heavily shrunk toward the position mean
  * opponent: shrunk yards-allowed-per-game factor vs. league average
  * game script: team spread nudges rush volume up (favorites) / pass volume down
  * weather: at outdoor stadiums, wind and cold scale yardage by factors fitted on the backtest (engine/weather.py)
The spread and shape of outcomes come from the walk-forward backtest of this same model: the typical error
(a robust spread, binned by projection size) and the empirical distribution of standardized errors. So the
chance of beating a line matches how often actual yardage beat the projection, including skew and blow-up
games. (Older runs used an assumed gamma curve, kept as a fallback in prob_over_under.)
"""
import numpy as np
import pandas as pd
from scipy import stats as st

from . import td as tdm
from . import weather as wxm

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


def components(hist, pos, priors, opp, spread, wx=None):
    """Per-kind (mu, vol, eff) for one player, no volume floor applied. wx: per-kind weather multipliers on mu
    (volume is left alone, so touchdown and redistribution math don't change)."""
    out = {}
    for kind in CFG:
        pe = priors.get((kind, pos))
        if pe is None:
            continue
        res = project_player(hist, kind, pe, opp[kind].get(hist.attrs["opp"], 0.0), spread)
        if res:
            f = (wx or {}).get(kind, 1.0)
            out[kind] = (res[0] * f, res[1], res[2]) if f != 1.0 else res
    return out


def wx_ratio(kind, comp, wx):
    """The weather multiplier a projection carries; for rush + rec, its parts' factors weighted by their yards."""
    if not wx:
        return 1.0
    if kind != "rr":
        return wx.get(kind, 1.0)
    adj = comp["rush"][0] + comp["rec"][0]
    raw = comp["rush"][0] / wx.get("rush", 1.0) + comp["rec"][0] / wx.get("rec", 1.0)
    return adj / raw if raw > 0 else 1.0


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


def _lift_members(members, lost, rho, records=None, t=None, affected=None, only=None):
    """Hand lost volume to active teammates of the same position group (in place on each member's comp).

    members: dicts with pid, pos, comp (and row, for fitting). only: pids allowed to receive (default: all).
    With records, collect (role, expected extra volume, observed extra volume, t) to fit rho."""
    from . import redistribute as rd
    receivers = [c for c in members if only is None or c["pid"] in only]
    active_vol = {}
    for c in receivers:
        for kind in rd.ROLES:
            if kind in c["comp"]:
                key = (kind, rd.group(kind, c["pos"]))
                active_vol[key] = active_vol.get(key, 0.0) + c["comp"][kind][1]
    for c in receivers:
        for kind, col in rd.ROLES.items():
            key = (kind, rd.group(kind, c["pos"]))
            if kind not in c["comp"] or lost.get(key, 0) <= 0 or active_vol.get(key, 0) <= 0:
                continue
            if affected is not None:
                affected.add((c["pid"], t))
            vol = c["comp"][kind][1]
            if records is not None:
                records.append((kind, lost[key] * vol / active_vol[key], float(c["row"][col]) - vol, t))
            if rho is not None and rho.get(kind, 0.0) > 0:
                f = rd.lift(kind, rho[kind], lost[key], active_vol[key])
                mu, v, eff = c["comp"][kind]
                c["comp"][kind] = (mu * f, v * f, eff)


def _apply_redistribution(ctx, logs, priors, opp_cache, spread_map, rho, records):
    """Backtest: move absent regulars' volume to their active teammates in every team-game."""
    from . import redistribute as rd
    groups = {}
    for c in ctx:
        groups.setdefault((c["team"], c["t"]), []).append(c)
    affected = set()
    for (team, t), members in groups.items():
        opp_team, sp = members[0]["opp"], members[0]["sp"]
        absent = rd.find_absent(logs, team, t, logs.active_at.get(t, set()))
        if not absent:
            continue

        def comp_fn(hist, _opp=opp_team, _sp=sp):  # only volume is read from these, so weather doesn't matter
            hist = hist.copy()
            hist.attrs["opp"] = _opp
            return components(hist, hist.position.iat[-1], priors, opp_cache[t], _sp)

        lost = rd.lost_volume(absent, comp_fn)
        if lost:
            _lift_members(members, lost, rho, records, t, affected)
    return affected


def walk_forward(df, priors, sched, start_t, td_priors=None, rho=None, records=None, wx_coef=None):
    """Project every historical player-game from t >= start_t using only prior data.

    With td_priors, anytime-TD rows are added too (kind "td": mu = unscaled P(>=1 TD), actual = 0/1).
    With rho (per-role redistribution shares), absent regulars' volume is handed to their teammates.
    With records (a list), the data to fit rho is collected instead/as well. Rows carry an `affected` flag:
    True when a teammate was absent in that game (computed only when rho or records is given).
    Rows also carry the game's weather (wx_temp, wx_wind: NaN indoors) and wx, the multiplier applied with wx_coef.
    """
    spread_map = _spread_lookup(sched)
    wx_hist = wxm.history(sched)
    implied_map = tdm.implied_points(sched)
    opp_cache = {t: opp_table(df, t) for t in sorted(df[df.t >= start_t].t.unique())}
    ctx = []
    for pid, g in df.groupby("player_id"):
        g = g.reset_index(drop=True)
        for i in range(3, len(g)):
            r = g.iloc[i]
            if r.t < start_t:
                continue
            hist = g.iloc[:i]  # a view: copying every player-game's history is what made full refreshes big
            hist.attrs["opp"] = r.opponent_team
            sp = spread_map.get((r.season, r.week, r.team), 0.0)
            temp, wind = wx_hist.get((r.season, r.week, r.team), (np.nan, np.nan))
            wx = wxm.factors(wx_coef, temp, wind) if wx_coef and not np.isnan(temp) else None
            ctx.append(dict(pid=pid, name=r.player_display_name, pos=r.position, team=r.team, opp=r.opponent_team, season=r.season,
                            week=r.week, t=r.t, hist=hist, sp=sp, row=r, one=g.iloc[[i]], temp=temp, wind=wind, wx=wx,
                            comp=components(hist, r.position, priors, opp_cache[r.t], sp, wx)))
    affected = set()
    if rho is not None or records is not None:
        from . import redistribute as rd
        affected = _apply_redistribution(ctx, rd.Logs(df), priors, opp_cache, spread_map, rho, records)
    rows = []
    for c in ctx:
        pid, hist, one, r = c["pid"], c["hist"], c["one"], c["row"]
        aff = (pid, c["t"]) in affected
        for kind, (mu, vol, eff) in all_kinds(hist, c["pos"], priors, opp_cache[c["t"]], c["sp"], c["comp"]).items():
            rows.append((pid, c["name"], kind, c["t"], mu, float(actual_hist(one, kind).iloc[0]),
                         float(actual_hist(hist, kind).tail(5).mean()), aff, c["temp"], c["wind"], wx_ratio(kind, c["comp"], c["wx"])))
        if td_priors is not None:
            res = tdm.project_td(hist, c["comp"], c["pos"], td_priors, implied_map.get((c["season"], c["week"], c["team"])))
            if res:
                rows.append((pid, c["name"], "td", c["t"], res[0], float(tdm.td_count(one).iloc[0] >= 1),
                             float((tdm.td_count(hist).tail(8) >= 1).mean()), aff, c["temp"], c["wind"], 1.0))
    return pd.DataFrame(rows, columns=["player_id", "name", "kind", "t", "mu", "actual", "naive5", "affected", "wx_temp", "wx_wind", "wx"])


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


def upcoming_projections(df, sched, priors, var_params, week_t, roster, td_priors=None, td_scale=1.0, rho=None, absent_ids=(),
                         game_wx=None):
    """Project all active players for games not yet played in the target week.

    With rho, volume from absent regulars (ruled out/doubtful via absent_ids, or no longer on the active roster)
    is handed to their teammates in the same position group. game_wx: game_id -> per-kind weather multipliers."""
    season, week = divmod(week_t, 100)
    games = sched[(sched.season == season) & (sched.week == week) & sched.home_score.isna()]
    opp = opp_table(df, week_t)
    implied_map = tdm.implied_points(sched)
    latest = df.sort_values("t").groupby("player_id").tail(1).set_index("player_id")
    by_player = {pid: g for pid, g in df.groupby("player_id")}
    logs = None
    if rho and any(v > 0 for v in rho.values()):
        from . import redistribute as rd
        logs = rd.Logs(df)
    rows = []
    for _, gm in games.iterrows():
        wx = (game_wx or {}).get(gm.game_id)
        for team, other, sp in ((gm.home_team, gm.away_team, gm.spread_line), (gm.away_team, gm.home_team, -gm.spread_line)):
            sp = 0.0 if pd.isna(sp) else float(sp)
            on_team = latest[latest.index.map(lambda i: roster.get(i) == team) & (latest.t >= (season - 1) * 100)]
            # skip offseason arrivals with no games for the new team: their old role doesn't carry over
            on_team = on_team[on_team.team == team]
            members = []
            for pid, p in on_team.iterrows():
                hist = by_player[pid]
                if len(hist) < 2:
                    continue
                hist = hist.iloc[:]  # a view of the player's rows; attrs are set per use
                hist.attrs["opp"] = other
                members.append(dict(pid=pid, p=p, hist=hist, pos=p.position, comp=components(hist, p.position, priors, opp, sp, wx)))
            if rho and any(v > 0 for v in rho.values()):
                from . import redistribute as rd
                # not absent: healthy members, and anyone active on another team's roster (traded away, not missing)
                active = {pid for pid, tm in roster.items() if not (tm == team and pid in absent_ids)}
                receivers = {c["pid"] for c in members if c["pid"] not in absent_ids}
                absent = rd.find_absent(logs, team, week_t, active)
                if absent:
                    def comp_fn(h, _other=other, _sp=sp):
                        h = h.copy()
                        h.attrs["opp"] = _other
                        return components(h, h.position.iat[-1], priors, opp, _sp)

                    lost = rd.lost_volume(absent, comp_fn)
                    if lost:
                        _lift_members(members, lost, rho, only=receivers)
            for c in members:
                pid, p, hist, comp = c["pid"], c["p"], c["hist"], c["comp"]
                if td_priors is not None:
                    res = tdm.project_td(hist, comp, p.position, td_priors, implied_map.get((season, week, team)), td_scale)
                    if res:  # kind "td": mu = P(>=1 TD), vol = expected touches, eff = expected TDs
                        rows.append(dict(player_id=pid, name=p.player_display_name, pos=p.position, team=team,
                                         opp=other, home=team == gm.home_team, kind="td", mu=res[0], vol=res[2], eff=res[1],
                                         sd=0.0, spread=sp, gameday=gm.gameday, gametime=gm.gametime, game_id=gm.game_id,
                                         last5=tdm.td_count(hist).tail(5).tolist(), wx=1.0))
                for kind, (mu, vol, eff) in all_kinds(hist, p.position, priors, opp, sp, comp).items():
                    rows.append(dict(player_id=pid, name=p.player_display_name, pos=p.position, team=team,
                                     opp=other, home=team == gm.home_team, kind=kind, mu=mu, vol=vol, eff=eff,
                                     sd=sd_at(mu, var_params[kind]), spread=sp,
                                     gameday=gm.gameday, gametime=gm.gametime, game_id=gm.game_id,
                                     last5=actual_hist(hist, kind).tail(5).tolist(), wx=wx_ratio(kind, comp, wx)))
    return pd.DataFrame(rows)
