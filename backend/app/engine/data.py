"""Data loading: nflverse weekly player stats, schedules, injuries (cached on disk)."""
import io
import os
import time
import pandas as pd
import requests

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
CACHE = os.environ.get("NFLPROPS_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".cache")
os.makedirs(CACHE, exist_ok=True)


def _get_csv(url, name, max_age_hours=6, usecols=None):
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_hours * 3600:
        return pd.read_csv(path, low_memory=False, usecols=usecols)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return pd.read_csv(io.BytesIO(r.content), low_memory=False, usecols=usecols)


def load_stats(seasons, usecols=None):
    """usecols trims the ~150 stat columns when only a few are needed (keeps a small server's memory down)."""
    frames = []
    for s in seasons:
        try:
            frames.append(_get_csv(f"{BASE}/stats_player/stats_player_week_{s}.csv", f"stats_{s}.csv", usecols=usecols))
        except requests.HTTPError:
            pass
    df = pd.concat(frames, ignore_index=True)
    df = df[df.season_type == "REG"]
    return df[df.position.isin(["QB", "RB", "WR", "TE", "FB"])].copy()


def load_schedule():
    g = _get_csv(f"{BASE}/schedules/games.csv", "games.csv")
    return g[g.game_type == "REG"].copy()


def load_injuries(season):
    try:
        return _get_csv(f"{BASE}/injuries/injuries_{season}.csv", f"injuries_{season}.csv", max_age_hours=1)
    except requests.HTTPError:
        return pd.DataFrame()


def load_roster(season):
    """Current active roster: gsis_id -> team (latest week in the file, status ACT)."""
    r = _get_csv(f"{BASE}/rosters/roster_{season}.csv", f"roster_{season}.csv", max_age_hours=3)
    r = r[r.week == r.week.max()]
    return dict(zip(r[r.status == "ACT"].gsis_id, r[r.status == "ACT"].team))
