"""Pipeline: nflverse data -> backtest -> projections -> DB; and odds refresh -> DB."""
import os
import time
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import pandas as pd

from . import config
from .db import AltLine, OddsLine, Projection, Run, SessionLocal
from .engine import data, model, odds
from .engine import redistribute as rd
from .engine import td as tdm

Log = Callable[[str], None]
ALL_MARKETS = set(odds.MARKETS.values())
ALT_KINDS = set(odds.ALT_MARKETS.values())  # anytime TD has no alternate market


def run_projections(exclude=(), keep_dnp=False, season=None, week=None, log: Log = print) -> int:
    """Compute projections for the next unplayed week and store them. Returns the run id."""
    sched = data.load_schedule()
    played = sched[sched.home_score.notna()]
    cur = sched[sched.home_score.isna()].sort_values(["season", "week"]).iloc[0]
    season, week = season or int(cur.season), week or int(cur.week)
    week_t = season * 100 + week
    log(f"Target: {season} week {week}")

    stats = model.prep(data.load_stats([season - 2, season - 1, season], usecols=data.PIPELINE_COLUMNS))
    priors = model.league_priors(stats)
    # who is out this week (injury report + your --exclude list): their volume goes to teammates, and they are dropped below
    inj = data.load_injuries(season)
    status = {}
    if not inj.empty:
        cur_inj = inj[inj.week == week]
        dnp = cur_inj.practice_status.fillna("").str.startswith("Did Not") & cur_inj.report_status.isna()
        status = dict(zip(cur_inj.gsis_id, cur_inj.report_status.where(~dnp, "DNP")))
    drop = {"Out", "Doubtful"} | (set() if keep_dnp else {"DNP"})
    names = {odds.norm(n) for n in exclude}
    manual_ids = set(stats[stats.player_display_name.map(odds.norm).isin(names)].player_id) if names else set()
    absent_ids = {pid for pid, s_ in status.items() if s_ in drop} | manual_ids

    log("Walk-forward backtest (fits variance, checks accuracy)...")
    td_pri = tdm.td_priors(stats)
    start_t = (season - 1) * 100 + 6
    records = []
    base = model.walk_forward(stats, priors, played, start_t=start_t, td_priors=td_pri, records=records)  # also gathers data to fit rho
    rho_fit = rd.fit_rho([x for x in records if x[3] < week_t])
    rho = rd.applied(rho_fit)
    bt = model.walk_forward(stats, priors, played, start_t=start_t, td_priors=td_pri, rho=rho)
    bt, base = bt[bt.t < week_t], base[base.t < week_t]
    bt_td, bt = bt[bt.kind == "td"], bt[bt.kind != "td"]
    bt_sum, var_params = model.backtest_summary(bt), model.fit_dist(bt)
    lam = -np.log1p(-np.clip(bt_td.mu.to_numpy(), 0, 1 - 1e-9))
    td_scale = tdm.fit_scale(lam, bt_td.actual.to_numpy()) if len(bt_td) else 1.0
    bt_sum["td"] = tdm.summary(bt_td, td_scale)
    var_params["td"] = [td_scale, 0.0]  # anytime TD: (scale on expected TDs, unused); yardage kinds hold their error tables
    var_params["_redistribution"] = _redistribution_summary(base, bt, rho_fit, rho)
    log(f"Redistribution: {var_params['_redistribution']['summary']}")

    log("Projecting upcoming games...")
    proj = model.upcoming_projections(stats, sched, priors, var_params, week_t, data.load_roster(season),
                                      td_priors=td_pri, td_scale=td_scale, rho=rho, absent_ids=absent_ids)

    proj["status"] = proj.player_id.map(status).fillna("")
    proj.loc[proj.player_id.isin(manual_ids), "status"] = "Out"
    gone = proj[proj.status.isin(drop)]
    excluded = sorted({f"{n} ({s_})" for n, s_ in zip(gone["name"], gone.status)})
    proj = proj[~proj.status.isin(drop)]

    with SessionLocal() as s:
        run = Run(season=season, week=week, backtest=bt_sum, variance=var_params,
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


def _redistribution_summary(base: pd.DataFrame, bt: pd.DataFrame, rho_fit: dict, rho: dict) -> dict:
    """What redistribution did in the backtest (in-sample): bias on teammates of absent regulars, before and after."""
    out = dict(rho_fit={k: round(v, 3) for k, v in rho_fit.items()}, rho={k: round(v, 3) for k, v in rho.items()},
               active_roles=list(rd.ACTIVE_ROLES), by_kind={})
    key = ["player_id", "t", "kind"]
    b = base[base.kind != "td"].set_index(key)
    n = bt[bt.kind != "td"].set_index(key)
    idx = b.index.intersection(n.index)
    for kind in rd.ROLES:
        sel = (idx.get_level_values("kind") == kind) & b.loc[idx, "affected"].to_numpy()
        if sel.sum() < 10:
            continue
        eb, en = (b.loc[idx, "actual"] - b.loc[idx, "mu"])[sel], (n.loc[idx, "actual"] - n.loc[idx, "mu"])[sel]
        out["by_kind"][kind] = dict(n=int(sel.sum()), bias_before=float(eb.mean()), bias_after=float(en.mean()),
                                    mae_before=float(eb.abs().mean()), mae_after=float(en.abs().mean()))
    r = out["by_kind"].get("rush")
    out["summary"] = ("rushing teammates of an absent regular: bias %+.1f -> %+.1f yds over %d games" % (r["bias_before"], r["bias_after"], r["n"])
                      if r else "no affected games")
    return out


def _s(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v) == "" else str(v)


def store_lines(df: pd.DataFrame, session) -> int:
    """Store main-market quotes. Each (market, game) is one snapshot: its older rows are replaced, so the table
    holds only current lines and a later fetch for other games never hides the ones already stored."""
    fetched = df["fetched_at"] if "fetched_at" in df else pd.Series(time.time(), index=df.index)
    gid = df["game_id"] if "game_id" in df else pd.Series([None] * len(df), index=df.index)
    df = df.assign(_gid=gid.where(gid.notna(), None))
    for (market, game_id), g in df.groupby(["market", df["_gid"].fillna("")]):
        game_id = game_id or None
        t = datetime.utcfromtimestamp(float(fetched[g.index].max()))
        session.add_all(OddsLine(fetched_at=t, player=r.player, market=market, line=float(r.line),
                                 over_odds=None if pd.isna(r.over_odds) else float(r.over_odds),
                                 under_odds=None if pd.isna(r.under_odds) else float(r.under_odds), book=r.book,
                                 over_link=_s(getattr(r, "over_link", None)), under_link=_s(getattr(r, "under_link", None)),
                                 event_link=_s(getattr(r, "event_link", None)), game_id=game_id)
                        for r in g.itertuples())
        session.flush()
        if game_id:
            session.query(OddsLine).filter(OddsLine.market == market, OddsLine.game_id == game_id,
                                           OddsLine.fetched_at < t).delete()
    session.commit()
    return len(df)


def upcoming_games() -> pd.DataFrame:
    """Unplayed games of the next week to be played (the week the projections are for)."""
    sched = data.load_schedule()
    todo = sched[sched.home_score.isna()]
    first = todo.sort_values(["season", "week"]).iloc[0]
    return todo[(todo.season == first.season) & (todo.week == first.week)]


def sync_plan(session, games: pd.DataFrame, mode: str = "missing") -> dict:
    """What a sync would fetch, game by game: the main markets with no stored lines for that game, and whether
    its alternate lines are missing. mode 'all' means everything for every game. Costs one credit per market."""
    have_main = {}
    for gid, market in session.query(OddsLine.game_id, OddsLine.market).distinct():
        have_main.setdefault(gid, set()).add(market)
    have_alt = {g for (g,) in session.query(AltLine.game_id).distinct()}
    out = []
    for g in games.itertuples():
        need_main = sorted(ALL_MARKETS if mode == "all" else ALL_MARKETS - have_main.get(g.game_id, set()))
        need_alt = mode == "all" or g.game_id not in have_alt
        if need_main or need_alt:
            out.append(dict(game_id=g.game_id, away=g.away_team, home=g.home_team, label=f"{g.away_team} @ {g.home_team}",
                            gameday=str(getattr(g, "gameday", "")), need_main=need_main, need_alt=need_alt,
                            credits=len(need_main) + (len(ALT_KINDS) if need_alt else 0)))
    first = games.iloc[0] if len(games) else None
    has = first is not None and "season" in games.columns and "week" in games.columns
    return dict(season=int(first.season) if has else None, week=int(first.week) if has else None,
                total_games=len(games), games=out, credits=sum(g["credits"] for g in out))


def refresh_odds(mode: str = "missing", log: Log = print) -> None:
    """Fetch prop lines, main and alternate, for the upcoming week's games (one API call per game).

    'missing' fetches only what each game lacks (so a new week is fetched in full and a repeat costs nothing);
    'all' refetches everything for the week; 'none' skips. Costs one credit per market per game.
    """
    if mode == "none":
        return
    key = config.ODDS_API_KEY()
    games = upcoming_games()
    with SessionLocal() as s:
        plan = sync_plan(s, games, mode)
        if not plan["games"]:
            log("Odds already cover every game")
            return
        if not key:
            log("No ODDS_API_KEY set; skipping odds fetch")
            return
        events = {(e["away"], e["home"]): e["id"] for e in odds.list_events(key)}
        todo = [(g, events.get((g["away"], g["home"]))) for g in plan["games"]]
        cost = sum(g["credits"] for g, e in todo if e)
        log(f"Fetching odds for {len(todo)} games (about {cost} API credits)...")
        mains, alts = [], []
        for g, event_id in todo:
            if not event_id:
                log(f"  no sportsbook event yet for {g['label']}")
                continue
            long, remaining = odds.fetch_game_odds(key, event_id, g["need_main"], ALT_KINDS if g["need_alt"] else ())
            paired = odds.pair_with_links(long)
            is_alt = paired.alt.astype(bool)
            mains.append(paired[~is_alt].assign(game_id=g["game_id"]))
            alts.append(paired[is_alt].assign(game_id=g["game_id"]))
            log(f"  {g['label']}: {len(paired)} quotes (credits left: {remaining})")
        now = datetime.utcnow()
        main_df = pd.concat([m for m in mains if not m.empty], ignore_index=True) if any(not m.empty for m in mains) else pd.DataFrame()
        if not main_df.empty:
            main_df["fetched_at"] = time.time()
            store_lines(main_df.drop(columns="alt"), s)
        alt_df = pd.concat([a for a in alts if not a.empty], ignore_index=True) if any(not a.empty for a in alts) else pd.DataFrame()
        if not alt_df.empty:
            for gid in alt_df.game_id.unique():
                s.query(AltLine).filter(AltLine.game_id == gid).delete()
            s.add_all(AltLine(fetched_at=now, game_id=r.game_id, player=r.player, market=r.market, line=float(r.line),
                              over_odds=None if pd.isna(r.over_odds) else float(r.over_odds),
                              under_odds=None if pd.isna(r.under_odds) else float(r.under_odds), book=r.book,
                              over_link=_s(r.over_link), under_link=_s(r.under_link), event_link=_s(r.event_link))
                      for r in alt_df.itertuples())
            s.commit()
        log(f"Stored {len(main_df)} main and {len(alt_df)} alternate quotes")


def seed_odds_from_csv(path: str, session) -> int:
    """One-time import of the legacy .cache/odds_latest.csv so existing credits aren't re-spent."""
    if not os.path.exists(path) or session.query(OddsLine).count():
        return 0
    df = pd.read_csv(path)
    if "fetched_at" not in df:
        df["fetched_at"] = os.path.getmtime(path)
    df["fetched_at"] = df["fetched_at"].fillna(os.path.getmtime(path))
    return store_lines(df, session)


def fetch_game_lines(game_id: str, kinds: list[str], log: Log = print) -> dict:
    """Fetch main + alternate lines (with betslip links) for one game and store them.

    Alternate lines go to alt_lines (replacing that game's previous alts). Main-line quotes already in
    odds_lines get their links filled in; prices there are left alone so the weekly snapshot stays consistent.
    """
    key = config.ODDS_API_KEY()
    if not key:
        raise ValueError("No ODDS_API_KEY set")
    _, _, away, home = game_id.split("_", 3)
    event_id = odds.find_event_id(key, away, home)
    if not event_id:
        raise LookupError(f"No sportsbook event found for {away} @ {home}")
    long, remaining = odds.fetch_game_odds(key, event_id, kinds, kinds)
    paired = odds.pair_with_links(long)
    now = datetime.utcnow()
    alts, mains = paired[paired.alt.astype(bool)], paired[~paired.alt.astype(bool)]
    with SessionLocal() as s:
        for m in kinds:
            s.query(AltLine).filter(AltLine.game_id == game_id, AltLine.market == m).delete()
        s.add_all(AltLine(fetched_at=now, game_id=game_id, player=r.player, market=r.market, line=float(r.line),
                          over_odds=None if pd.isna(r.over_odds) else float(r.over_odds),
                          under_odds=None if pd.isna(r.under_odds) else float(r.under_odds), book=r.book,
                          over_link=_s(r.over_link), under_link=_s(r.under_link), event_link=_s(r.event_link))
                  for r in alts.itertuples())
        patched = 0
        for r in mains.itertuples():
            patched += s.query(OddsLine).filter(
                OddsLine.player == r.player, OddsLine.market == r.market, OddsLine.book == r.book,
                OddsLine.line == float(r.line)).update(
                {"over_link": _s(r.over_link), "under_link": _s(r.under_link), "event_link": _s(r.event_link)})
        s.commit()
    log(f"{game_id}: stored {len(alts)} alternate quotes, linked {patched} main quotes")
    return {"alt_quotes": len(alts), "linked": patched, "credits_remaining": remaining}
