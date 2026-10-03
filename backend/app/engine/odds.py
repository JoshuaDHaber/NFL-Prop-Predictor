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
ALT_MARKETS = {k + "_alternate": v for k, v in MARKETS.items()}

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers", "LA": "Los Angeles Rams", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


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
        params = dict(apiKey=key, regions=regions, markets=",".join(keys), oddsFormat="american", includeLinks="true")
        if books:
            params["bookmakers"] = books
        r = requests.get(f"{API}/events/{e['id']}/odds", params=params, timeout=30)
        if r.status_code != 200:
            continue
        for bk in r.json().get("bookmakers", []):
            for m in bk["markets"]:
                for o in m["outcomes"]:
                    rows.append(dict(player=o["description"], market=MARKETS[m["key"]], alt=False, side=o["name"].lower(),
                                     line=o["point"], odds=o["price"], book=bk["title"], link=o.get("link"),
                                     event_link=bk.get("link")))
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


def find_event_id(key, away, home):
    """Odds API event id for a game given nflverse team abbreviations (the /events call is free)."""
    r = requests.get(f"{API}/events", params={"apiKey": key}, timeout=30)
    r.raise_for_status()
    for e in r.json():
        if e["away_team"] == TEAM_NAMES.get(away) and e["home_team"] == TEAM_NAMES.get(home):
            return e["id"]
    return None


def fetch_game_odds(key, event_id, kinds, regions="us"):
    """Main + alternate yardage lines for one game, with bookmaker betslip links where offered.

    Returns (long DataFrame, credits_remaining). Costs 2 credits per kind (main + alternate market).
    """
    keys = [k for k, v in {**MARKETS, **ALT_MARKETS}.items() if v in kinds]
    r = requests.get(f"{API}/events/{event_id}/odds", timeout=30, params=dict(
        apiKey=key, regions=regions, markets=",".join(keys), oddsFormat="american", includeLinks="true"))
    r.raise_for_status()
    rows = []
    for bk in r.json().get("bookmakers", []):
        for m in bk["markets"]:
            kind = {**MARKETS, **ALT_MARKETS}[m["key"]]
            for o in m["outcomes"]:
                rows.append(dict(player=o["description"], market=kind, alt=m["key"].endswith("_alternate"),
                                 side=o["name"].lower(), line=o["point"], odds=o["price"], book=bk["title"],
                                 link=o.get("link"), event_link=bk.get("link")))
    return pd.DataFrame(rows), r.headers.get("x-requests-remaining")


def pair_with_links(long):
    """long rows -> one row per (player, market, alt, book, line) with over/under odds and links."""
    cols = ["player", "market", "alt", "book", "line", "event_link", "over_odds", "under_odds", "over_link", "under_link"]
    if long.empty:
        return pd.DataFrame(columns=cols)
    keys = ["player", "market", "alt", "book", "line"]
    o = long[long.side == "over"].rename(columns={"odds": "over_odds", "link": "over_link"}).drop(columns="side")
    u = long[long.side == "under"].rename(columns={"odds": "under_odds", "link": "under_link"}).drop(columns=["side", "event_link"])
    out = o.merge(u, on=keys, how="outer")
    return out.drop_duplicates(keys)[cols]
