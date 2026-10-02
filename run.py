"""Build the prop-picks report.   python run.py [--week 2026-04] [--lines-csv f.csv] [--demo-lines]"""
import argparse
import os
import time
import numpy as np
import pandas as pd

import data
import model
import odds
import report

def load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Load KEY=VALUE lines from .env without overriding real environment variables."""
    if os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k and not k.startswith("#") and v:
                os.environ.setdefault(k, v.strip("\"'"))


ODDS_CACHE = os.path.join(data.CACHE, "odds_latest.csv")
MARKET_WEIGHT = 0.35    # blend of market no-vig probability into model probability
MIN_EV = 0.03


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--lines-csv")
    ap.add_argument("--cached-odds", action="store_true", help="reuse the last fetched odds (no API credits)")
    ap.add_argument("--demo-lines", action="store_true", help="synthetic lines to preview the report")
    ap.add_argument("--out", default="report.html")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="NAME", help='players to drop, e.g. --exclude "Breece Hall"')
    ap.add_argument("--keep-dnp", action="store_true", help="keep players who did not practice (no game status yet)")
    ap.add_argument("--min-ev", type=float, default=MIN_EV)
    ap.add_argument("--market-weight", type=float, default=MARKET_WEIGHT)
    a = ap.parse_args()

    sched = data.load_schedule()
    played = sched[sched.home_score.notna()]
    cur = sched[sched.home_score.isna()].sort_values(["season", "week"]).iloc[0]
    season, week = a.season or int(cur.season), a.week or int(cur.week)
    week_t = season * 100 + week
    print(f"Target: {season} week {week}")

    stats = model.prep(data.load_stats([season - 2, season - 1, season]))
    priors = model.league_priors(stats)

    print("Walk-forward backtest (fits variance, checks accuracy)...")
    bt = model.walk_forward(stats, priors, played, start_t=(season - 1) * 100 + 6)
    bt = bt[bt.t < week_t]
    bt_sum = model.backtest_summary(bt)
    var_params = model.fit_variance(bt)
    for k, v in bt_sum.items():
        print(f"  {k}: n={v['n']} MAE model={v['mae_model']:.1f} vs last-5 avg={v['mae_naive']:.1f} bias={v['bias']:+.1f}")

    proj = model.upcoming_projections(stats, sched, priors, var_params, week_t, data.load_roster(season))

    # injuries: drop Out/Doubtful, DNP in practice (no game status posted yet), and manual --exclude
    inj = data.load_injuries(season)
    status = {}
    if not inj.empty:
        cur_inj = inj[inj.week == week]
        dnp = cur_inj.practice_status.fillna("").str.startswith("Did Not") & cur_inj.report_status.isna()
        status = dict(zip(cur_inj.gsis_id, cur_inj.report_status.where(~dnp, "DNP")))
    proj["status"] = proj.player_id.map(status).fillna("")
    manual = proj["name"].map(odds.norm).isin([odds.norm(n) for n in a.exclude])
    proj.loc[manual, "status"] = "Out"
    drop = {"Out", "Doubtful"} | (set() if a.keep_dnp else {"DNP"})
    gone = proj[proj.status.isin(drop)]
    if len(gone):
        print("Excluded:", ", ".join(sorted({f"{n} ({s})" for n, s in zip(gone['name'], gone.status)})))
    proj = proj[~proj.status.isin(drop)].reset_index(drop=True)

    lines = None
    if a.lines_csv:
        lines = odds.load_csv(a.lines_csv)
    elif a.cached_odds or os.environ.get("ODDS_API_KEY"):
        lines = get_odds(a.cached_odds)
    elif a.demo_lines:
        lines = odds.demo_lines(proj)

    picks = build_picks(proj, lines, a.min_ev, a.market_weight) if lines is not None and len(lines) else None
    report.write(a.out, season, week, proj, picks, bt_sum, var_params, demo=a.demo_lines and not a.lines_csv and not os.environ.get("ODDS_API_KEY"))
    print(f"Wrote {a.out}  ({len(proj)} projections, {0 if picks is None else len(picks)} picks)")


def get_odds(use_cache):
    """Cached odds when asked; fetch only the markets the cache is missing (or everything on a fresh run)."""
    key = os.environ.get("ODDS_API_KEY")
    cache = pd.read_csv(ODDS_CACHE) if use_cache and os.path.exists(ODDS_CACHE) else None
    if cache is not None:
        cache["fetched_at"] = cache.get("fetched_at", pd.Series(dtype=float)).fillna(os.path.getmtime(ODDS_CACHE))
    wanted = set(odds.MARKETS.values())
    missing = wanted - set(cache.market) if cache is not None else wanted
    if missing and key:
        new = odds.fetch_odds_api(key, kinds=missing)
        print(f"Fetched {sorted(missing)} from the API")
        cache = pd.concat([cache, new], ignore_index=True) if cache is not None else new
        cache.to_csv(ODDS_CACHE, index=False)
    elif cache is None:
        raise SystemExit("No cached odds and no ODDS_API_KEY.")
    if "fetched_at" in cache:
        for m, g in cache.groupby("market"):
            print(f"  {m}: odds {(time.time() - g.fetched_at.max()) / 60:.0f} min old")
    return cache


def build_picks(proj, lines, min_ev, w):
    from model import prob_over_under
    lines = lines.copy()
    lines["key"] = lines.player.map(odds.norm)
    proj = proj.copy()
    proj["key"] = proj["name"].map(odds.norm)
    pm = {(r.key, r.kind): r for r in proj.itertuples()}
    # market no-vig consensus per player/market/line
    lines["ip_o"] = odds.implied(lines.over_odds)
    lines["ip_u"] = odds.implied(lines.under_odds)
    lines["nv_o"] = lines.ip_o / (lines.ip_o + lines.ip_u)
    cons = lines.groupby(["key", "market"]).agg(line=("line", "median"), nv_o=("nv_o", "mean"), books=("book", "nunique"))
    out = []
    for r in lines.itertuples():
        p = pm.get((r.key, r.market))
        if p is None or pd.isna(r.line):
            continue
        var = p.sd ** 2
        po, pu = prob_over_under(p.mu, r.line, var)
        c = cons.loc[(r.key, r.market)]
        # compare against the consensus market probability at *this* line (shift by line gap using model slope)
        mk_over = c.nv_o
        if abs(c.line - r.line) > 1e-9:
            po_c, _ = prob_over_under(p.mu, c.line, var)
            mk_over = float(np.clip(c.nv_o + (po - po_c), 0.02, 0.98))
        for side, odd, pm_side, mk in (("Over", r.over_odds, po, mk_over), ("Under", r.under_odds, pu, 1 - mk_over)):
            if pd.isna(odd):
                continue
            prob = (1 - w) * pm_side + w * mk
            dec = float(odds.american_to_dec(odd))
            ev = prob * (dec - 1) - (1 - prob)
            kelly = max(0.0, ev / (dec - 1)) / 4
            out.append(dict(name=p.name, pos=p.pos, team=p.team, opp=p.opp, home=p.home, kind=r.market, mu=p.mu, sd=p.sd,
                            status=p.status, last5=p.last5, game_id=p.game_id, gameday=p.gameday, gametime=p.gametime, side=side,
                            line=float(r.line), odds=int(odd), book=r.book, p_model=pm_side, p_mkt=mk, prob=prob,
                            ev=ev, kelly=kelly, books=int(c.books), edge_yds=(p.mu - r.line) * (1 if side == "Over" else -1)))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    # keep best price per player/market/side
    df = df.sort_values("ev", ascending=False).drop_duplicates(["name", "kind", "side"])
    return df[df.ev >= min_ev].sort_values("ev", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    main()
