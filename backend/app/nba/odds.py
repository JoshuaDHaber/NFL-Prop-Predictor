"""NBA lines from The Odds API (key: ODDS_API_KEY_NBA): moneylines for the whole slate in one call, and points,
rebounds, assists and 3-pointers-made props one game at a time (one credit per market per game)."""
import pandas as pd
import requests

from ..engine import odds as nfl_odds

API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
PROP_MARKETS = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "threes"}
MARKETS = {**PROP_MARKETS, "h2h": "ml"}
PROP_KINDS = tuple(PROP_MARKETS.values())

# ESPN abbreviation -> The Odds API's team name
TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GS": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NO": "New Orleans Pelicans", "NY": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SA": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTAH": "Utah Jazz", "WSH": "Washington Wizards",
}


def list_events(key):
    """Upcoming NBA events {id, away, home, commence} (free)."""
    return nfl_odds.list_events(key, api=API, names=TEAM_NAMES)


def fetch_props(key, event_id, kinds):
    """(long DataFrame, credits_remaining) of one game's points/rebounds/assists quotes, with betslip links."""
    return nfl_odds.fetch_game_odds(key, event_id, kinds, api=API, markets=PROP_MARKETS, alt_markets={})


def fetch_moneylines(key, regions="us"):
    """({event_id: long DataFrame of moneyline rows}, credits_remaining) for every upcoming game: one credit in all."""
    r = requests.get(f"{API}/odds", timeout=30, params=dict(apiKey=key, regions=regions, markets="h2h",
                                                            oddsFormat="american", includeLinks="true"))
    r.raise_for_status()
    out = {}
    for e in r.json():
        rows = []
        for bk in e.get("bookmakers", []):
            for m in bk.get("markets", []):
                if m["key"] == "h2h" and len(m.get("outcomes", [])) == 2:
                    rows.extend(nfl_odds._moneyline_rows(m["outcomes"], bk))
        out[e["id"]] = pd.DataFrame(rows)
    return out, r.headers.get("x-requests-remaining")
