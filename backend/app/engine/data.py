"""Data loading: nflverse weekly player stats, schedules, injuries (cached on disk)."""
import functools
import json
import re
from datetime import datetime
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


# the only stat columns the model reads; loading ~17 of nflverse's ~150 keeps a full refresh within a small server's memory
PIPELINE_COLUMNS = ["player_id", "player_display_name", "position", "season", "week", "season_type", "team", "opponent_team",
                    "carries", "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
                    "attempts", "passing_yards", "passing_tds"]
PBP_COLUMNS = ["season", "week", "season_type", "receiver_player_id", "complete_pass", "receiving_yards"]


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


def load_catches(seasons):
    """Every regular-season catch (player_id, season, week, yards) from nflverse play-by-play: the weekly stats have no
    longest reception. The ~20 MB play-by-play file is cut down to its catches once per download and that is cached too."""
    frames = []
    current = max(seasons)
    for s in seasons:
        max_age = 6 if s == current else 24 * 365   # a finished season's plays don't change
        raw, small = os.path.join(CACHE, f"pbp_{s}.csv.gz"), os.path.join(CACHE, f"catches_{s}.csv")
        fresh = os.path.exists(raw) and time.time() - os.path.getmtime(raw) < max_age * 3600
        if fresh and os.path.exists(small) and os.path.getmtime(small) >= os.path.getmtime(raw):
            frames.append(pd.read_csv(small))
            continue
        try:
            p = _get_csv(f"{BASE}/pbp/play_by_play_{s}.csv.gz", f"pbp_{s}.csv.gz", max_age_hours=max_age, usecols=PBP_COLUMNS)
        except requests.HTTPError:
            continue
        p = p[(p.season_type == "REG") & (p.complete_pass == 1) & p.receiver_player_id.notna()]
        c = pd.DataFrame({"player_id": p.receiver_player_id, "season": p.season, "week": p.week,
                          "yards": p.receiving_yards.fillna(0).astype(float)})
        c.to_csv(small, index=False)
        frames.append(c)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["player_id", "season", "week", "yards"])


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


def load_reserve(season):
    """Players on a reserve list (IR, PUP, ...), from each team's latest week in the roster file. Empty if unavailable."""
    try:
        r = _get_csv(f"{BASE}/rosters/roster_{season}.csv", f"roster_{season}.csv", max_age_hours=3,
                     usecols=["team", "week", "status", "status_description_abbr", "gsis_id", "full_name", "position"])
    except Exception:
        return pd.DataFrame()
    r = r[r.week == r.groupby("team").week.transform("max")]
    return r[r.status == "RES"].copy()


def load_espn_ids(season):
    """espn_id (as a string) -> gsis_id from the roster file, to match ESPN's injury feed. Empty if unavailable."""
    try:
        r = _get_csv(f"{BASE}/rosters/roster_{season}.csv", f"roster_{season}.csv", max_age_hours=3,
                     usecols=["gsis_id", "espn_id"]).dropna()
    except Exception:
        return {}
    return {str(int(e)) if isinstance(e, float) else str(e): g for e, g in zip(r.espn_id, r.gsis_id)}


ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
ESPN_COLUMNS = ["espn_id", "name", "team", "pos", "status", "injury", "comment", "return_date", "updated"]
# ESPN's abbreviations that differ from nflverse's
ESPN_TEAMS = {"WSH": "WAS", "LAR": "LA"}


def load_espn_injuries(max_age_hours=0.25):
    """ESPN's league-wide injury feed (no key): every player with a status or recent injury news, with the latest
    news line and an estimated return. Cached on disk; a failed fetch falls back to the last good copy, and with no
    copy at all an empty frame (ESPN only adds detail to nflverse's report). Returns (frame, fetched_at naive-UTC ISO)."""
    path = os.path.join(CACHE, "espn_injuries.json")
    js = None
    if not (os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_hours * 3600):
        try:
            r = requests.get(ESPN_INJURIES, timeout=20, headers={"User-Agent": "Mozilla/5.0 (props model)"})
            r.raise_for_status()
            js = r.json()
            with open(path + ".tmp", "w") as f:
                json.dump(js, f)
            os.replace(path + ".tmp", path)
        except (requests.RequestException, ValueError):
            pass
    if js is None:
        if not os.path.exists(path):
            return pd.DataFrame(columns=ESPN_COLUMNS), None
        with open(path) as f:
            js = json.load(f)
    fetched = datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat()
    real = lambda v: v if v not in (None, "", "Not Specified") else ""  # noqa: E731
    rows = []
    for t in js.get("injuries", []):
        for i in t.get("injuries", []):
            a = i.get("athlete") or {}
            link = next((m.group(1) for m in (re.search(r"/id/(\d+)", x.get("href", "")) for x in a.get("links", [])) if m), None)
            d = i.get("details") or {}
            team = (a.get("team") or {}).get("abbreviation", "")
            rows.append(dict(espn_id=link, name=a.get("displayName", ""), team=ESPN_TEAMS.get(team, team),
                             pos=(a.get("position") or {}).get("abbreviation", ""), status=i.get("status", ""),
                             injury=" ".join(x for x in (real(d.get("side")), real(d.get("type")), real(d.get("detail"))) if x),
                             comment=i.get("shortComment") or "", return_date=d.get("returnDate"), updated=i.get("date")))
    return pd.DataFrame(rows, columns=ESPN_COLUMNS), fetched


OFFENSE = ("QB", "RB", "FB", "WR", "TE")


def load_active_players(season):
    return _active_players(season, int(time.time() // 3600))


@functools.lru_cache(maxsize=2)
def _active_players(season, _hour):
    """Every active offensive skill player (QB, RB, FB, WR, TE) on a roster in each team's latest week, for player
    search: gsis_id, name, pos, team, headshot. Empty when the roster can't be loaded."""
    cols = ["team", "week", "status", "position", "full_name", "gsis_id", "headshot_url"]
    try:
        r = _get_csv(f"{BASE}/rosters/roster_{season}.csv", f"roster_{season}.csv", max_age_hours=3, usecols=cols)
    except Exception:
        return pd.DataFrame(columns=["player_id", "name", "pos", "team", "headshot"])
    r = r[(r.week == r.groupby("team").week.transform("max")) & (r.status == "ACT") & r.position.isin(OFFENSE)].dropna(subset=["gsis_id"])
    r = r.drop_duplicates("gsis_id", keep="last")
    return pd.DataFrame(dict(player_id=r.gsis_id, name=r.full_name.fillna(""), pos=r.position, team=r.team,
                             headshot=r.headshot_url.where(r.headshot_url.notna(), None))).reset_index(drop=True)


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
