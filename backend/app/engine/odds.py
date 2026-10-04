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
YARD_MARKETS = {"player_rush_yds": "rush", "player_reception_yds": "rec",
                "player_pass_yds": "pass", "player_rush_reception_yds": "rr"}
# anytime TD has no line or alternates: books post a "Yes" price per player (some also "No")
MARKETS = {**YARD_MARKETS, "player_anytime_td": "td"}
ALT_MARKETS = {k + "_alternate": v for k, v in YARD_MARKETS.items()}
TD_LINE = 0.5  # stored as an "Over 0.5": Yes is the over side, No (if posted) the under side

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


def list_events(key):
    """Upcoming events as {id, away, home} with nflverse team abbreviations (this call is free)."""
    r = requests.get(f"{API}/events", params={"apiKey": key}, timeout=30)
    r.raise_for_status()
    by_name = {v: k for k, v in TEAM_NAMES.items()}
    return [dict(id=e["id"], away=by_name.get(e["away_team"]), home=by_name.get(e["home_team"])) for e in r.json()]


def find_event_id(key, away, home):
    """Odds API event id for a game given nflverse team abbreviations."""
    return next((e["id"] for e in list_events(key) if e["away"] == away and e["home"] == home), None)


def fetch_game_odds(key, event_id, main_kinds, alt_kinds=(), regions="us"):
    """Main and/or alternate yardage lines for one game, with bookmaker betslip links where offered.

    Returns (long DataFrame, credits_remaining). Costs one credit per market requested.
    """
    keys = [k for k, v in MARKETS.items() if v in main_kinds] + [k for k, v in ALT_MARKETS.items() if v in alt_kinds]
    r = requests.get(f"{API}/events/{event_id}/odds", timeout=30, params=dict(
        apiKey=key, regions=regions, markets=",".join(keys), oddsFormat="american", includeLinks="true"))
    r.raise_for_status()
    rows = []
    for bk in r.json().get("bookmakers", []):
        for m in bk["markets"]:
            kind = {**MARKETS, **ALT_MARKETS}[m["key"]]
            for o in m["outcomes"]:
                is_td = kind == "td"
                rows.append(dict(player=o["description"], market=kind, alt=m["key"].endswith("_alternate"),
                                 side={"yes": "over", "no": "under"}.get(o["name"].lower(), o["name"].lower()) if is_td else o["name"].lower(),
                                 line=TD_LINE if is_td else o["point"], odds=o["price"], book=bk["title"],
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
