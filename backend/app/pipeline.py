"""Pipeline: nflverse data -> backtest -> projections -> DB; and odds refresh -> DB."""
import os
import time
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from . import config
from .db import OddsLine, Projection, Run, SessionLocal
from .engine import data, model, odds

Log = Callable[[str], None]
ALL_MARKETS = set(odds.MARKETS.values())


def run_projections(exclude=(), keep_dnp=False, season=None, week=None, log: Log = print) -> int:
    """Compute projections for the next unplayed week and store them. Returns the run id."""
    sched = data.load_schedule()
    played = sched[sched.home_score.notna()]
    cur = sched[sched.home_score.isna()].sort_values(["season", "week"]).iloc[0]
    season, week = season or int(cur.season), week or int(cur.week)
    week_t = season * 100 + week
    log(f"Target: {season} week {week}")

    stats = model.prep(data.load_stats([season - 2, season - 1, season]))
    priors = model.league_priors(stats)
    log("Walk-forward backtest (fits variance, checks accuracy)...")
    bt = model.walk_forward(stats, priors, played, start_t=(season - 1) * 100 + 6)
    bt = bt[bt.t < week_t]
    bt_sum, var_params = model.backtest_summary(bt), model.fit_variance(bt)

    log("Projecting upcoming games...")
    proj = model.upcoming_projections(stats, sched, priors, var_params, week_t, data.load_roster(season))

    inj = data.load_injuries(season)
    status = {}
    if not inj.empty:
        cur_inj = inj[inj.week == week]
        dnp = cur_inj.practice_status.fillna("").str.startswith("Did Not") & cur_inj.report_status.isna()
        status = dict(zip(cur_inj.gsis_id, cur_inj.report_status.where(~dnp, "DNP")))
    proj["status"] = proj.player_id.map(status).fillna("")
    manual = proj["name"].map(odds.norm).isin([odds.norm(n) for n in exclude])
    proj.loc[manual, "status"] = "Out"
    drop = {"Out", "Doubtful"} | (set() if keep_dnp else {"DNP"})
    gone = proj[proj.status.isin(drop)]
    excluded = sorted({f"{n} ({s})" for n, s in zip(gone["name"], gone.status)})
    proj = proj[~proj.status.isin(drop)]

    with SessionLocal() as s:
        run = Run(season=season, week=week, backtest=bt_sum, variance={k: list(v) for k, v in var_params.items()},
                  excluded=excluded)
        run.projections = [
            Projection(player_id=r.player_id, name=r.name, pos=r.pos, team=r.team, opp=r.opp, home=bool(r.home),
                       kind=r.kind, mu=float(r.mu), sd=float(r.sd), vol=float(r.vol), eff=float(r.eff),
                       spread=float(r.spread), status=r.status, game_id=r.game_id, gameday=str(r.gameday),
                       gametime="" if pd.isna(r.gametime) else str(r.gametime), last5=[float(x) for x in r.last5])
            for r in proj.itertuples()]
        s.add(run)
        s.commit()
        log(f"Stored run {run.id}: {len(run.projections)} projections, {len(excluded)} players excluded")
        return run.id


def store_lines(df: pd.DataFrame, session) -> int:
    fetched = df["fetched_at"] if "fetched_at" in df else pd.Series(time.time(), index=df.index)
    for market, g in df.groupby("market"):
        t = datetime.utcfromtimestamp(float(fetched[g.index].max()))
        session.add_all(OddsLine(fetched_at=t, player=r.player, market=market, line=float(r.line),
                                 over_odds=None if pd.isna(r.over_odds) else float(r.over_odds),
                                 under_odds=None if pd.isna(r.under_odds) else float(r.under_odds), book=r.book)
                        for r in g.itertuples())
    session.commit()
    return len(df)


def refresh_odds(mode: str = "missing", log: Log = print) -> None:
    """mode: 'all' refetch every market, 'missing' fetch only markets we hold no lines for, 'none' skip."""
    if mode == "none":
        return
    key = config.ODDS_API_KEY()
    with SessionLocal() as s:
        have = {m for (m,) in s.query(OddsLine.market).distinct()}
        wanted = ALL_MARKETS if mode == "all" else ALL_MARKETS - have
        if not wanted:
            log("Odds cache already covers every market")
            return
        if not key:
            log("No ODDS_API_KEY set; skipping odds fetch")
            return
        log(f"Fetching odds for {sorted(wanted)} (uses API credits)...")
        df = odds.fetch_odds_api(key, kinds=wanted)
        log(f"Stored {store_lines(df, s)} lines")


def seed_odds_from_csv(path: str, session) -> int:
    """One-time import of the legacy .cache/odds_latest.csv so existing credits aren't re-spent."""
    if not os.path.exists(path) or session.query(OddsLine).count():
        return 0
    df = pd.read_csv(path)
    if "fetched_at" not in df:
        df["fetched_at"] = os.path.getmtime(path)
    df["fetched_at"] = df["fetched_at"].fillna(os.path.getmtime(path))
    return store_lines(df, session)
