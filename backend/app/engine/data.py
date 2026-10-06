"""Data loading: nflverse weekly player stats, schedules, injuries (cached on disk)."""
import functools
import io
import os
import time
import pandas as pd
import requests

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
CACHE = os.environ.get("NFLPROPS_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".cache")
os.makedirs(CACHE, exist_ok=True)


def _read(src, name, usecols):
    return pd.read_csv(src, low_memory=False, usecols=usecols, compression="gzip" if name.endswith(".gz") else "infer")


def _get_csv(url, name, max_age_hours=6, usecols=None):
    """Download-and-cache a CSV (or .csv.gz). If the download fails, the last good copy is used instead of crashing,
    except a 404 (the file doesn't exist there), which the caller decides how to handle."""
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_hours * 3600:
        return _read(path, name, usecols)
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise
        if os.path.exists(path):
            return _read(path, name, usecols)
        raise
    except requests.RequestException:
        if os.path.exists(path):
            return _read(path, name, usecols)
        raise
    with open(path, "wb") as f:
        f.write(r.content)
    return _read(io.BytesIO(r.content), name, usecols)


# the only stat columns the model reads; loading ~16 of nflverse's ~150 keeps a full refresh within a small server's memory
PIPELINE_COLUMNS = ["player_id", "player_display_name", "position", "season", "week", "season_type", "team", "opponent_team",
                    "carries", "rushing_yards", "rushing_tds", "targets", "receiving_yards", "receiving_tds",
                    "attempts", "passing_yards"]


def load_stats(seasons, usecols=None):
    """usecols trims the ~150 stat columns when only a few are needed (keeps a small server's memory down).
    A list is matched by name and tolerates columns a season's file lacks."""
    if isinstance(usecols, (list, tuple, set)):
        wanted = set(usecols)
        usecols = lambda c: c in wanted  # noqa: E731
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
    """nflverse publishes the schedule as games.csv.gz (the plain games.csv was removed); the old name is a fallback."""
    try:
        g = _get_csv(f"{BASE}/schedules/games.csv.gz", "games.csv.gz")
    except requests.HTTPError:
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


def load_headshots(season):
    return _headshots(season, int(time.time() // 3600))


@functools.lru_cache(maxsize=2)
def _headshots(season, _hour):
    """gsis_id -> headshot URL from the roster file; empty when the roster can't be loaded (images are decoration)."""
    try:
        r = _get_csv(f"{BASE}/rosters/roster_{season}.csv", f"roster_{season}.csv", max_age_hours=3,
                     usecols=["gsis_id", "headshot_url"]).dropna()
    except Exception:
        return {}
    return dict(zip(r.gsis_id, r.headshot_url))
