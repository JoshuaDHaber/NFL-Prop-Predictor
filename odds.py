"""Prop lines: The Odds API (needs ODDS_API_KEY) or a manual CSV.

CSV columns: player,market,line,over_odds,under_odds,book   (market: rush or rec; American odds)
"""
import os
import re
import time
import numpy as np
import pandas as pd
import requests

API = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
MARKETS = {"player_rush_yds": "rush", "player_reception_yds": "rec",
           "player_pass_yds": "pass", "player_rush_reception_yds": "rr"}


def norm(name):
    n = re.sub(r"[.'’]", "", str(name).lower())
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return " ".join(re.sub(r"[^a-z ]", " ", n).split())


def fetch_odds_api(key, kinds=None, regions="us", books=None):
    keys = [k for k, v in MARKETS.items() if kinds is None or v in kinds]
    ev = requests.get(f"{API}/events", params={"apiKey": key}, timeout=30)
    ev.raise_for_status()
    rows = []
    for e in ev.json():
        params = dict(apiKey=key, regions=regions, markets=",".join(keys), oddsFormat="american")
        if books:
            params["bookmakers"] = books
        r = requests.get(f"{API}/events/{e['id']}/odds", params=params, timeout=30)
        if r.status_code != 200:
            continue
        for bk in r.json().get("bookmakers", []):
            for m in bk["markets"]:
                for o in m["outcomes"]:
                    rows.append(dict(player=o["description"], market=MARKETS[m["key"]], side=o["name"].lower(),
                                     line=o["point"], odds=o["price"], book=bk["title"]))
    remaining = r.headers.get("x-requests-remaining") if ev.ok else None
    print(f"Odds API credits remaining: {remaining}")
    df = pd.DataFrame(rows)
    out = _pair(df)
    out["fetched_at"] = time.time()
    return out


def _pair(long):
    """long rows (player, market, side, line, odds, book) -> one row per player/market/book/line."""
    if long.empty:
        return pd.DataFrame(columns=["player", "market", "line", "over_odds", "under_odds", "book"])
    o = long[long.side == "over"].rename(columns={"odds": "over_odds"}).drop(columns="side")
    u = long[long.side == "under"].rename(columns={"odds": "under_odds"}).drop(columns="side")
    return o.merge(u, on=["player", "market", "line", "book"], how="outer")


def load_csv(path):
    return pd.read_csv(path)


def demo_lines(proj, seed=7):
    """Synthetic lines near the projection (for testing the report only)."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, p in proj.iterrows():
        line = np.round((p.mu * rng.normal(1.0, 0.12)) * 2) / 2 - 0.5 + 0.5
        line = np.floor(line) + 0.5
        rows.append(dict(player=p["name"], market=p.kind, line=float(line), over_odds=-115, under_odds=-115, book="DEMO"))
    return pd.DataFrame(rows)


def american_to_dec(a):
    a = np.asarray(a, float)
    return np.where(a > 0, 1 + a / 100, 1 + 100 / -a)


def implied(a):
    return 1 / american_to_dec(a)
