"""Teams' win-loss records from ESPN's standings (no key), for the game tiles and game pages, both leagues."""
import os
import time
from functools import lru_cache
from typing import Optional

from .nba import espn

URL = "https://site.api.espn.com/apis/v2/sports/{sport}/standings?season={season}"
# re-read every half hour: a record changes at most once a day
MAX_AGE_HOURS = 0.5


def parse(js: dict, rename: Optional[dict] = None) -> dict[str, dict]:
    """team -> {overall, home, road} ("5-2", "5-2-1" with ties) from one standings response. Teams that haven't
    played yet are left out: a row of 0-0 records before opening night says nothing."""
    rename = rename or {}
    out = {}
    for conf in js.get("children", []):
        for e in (conf.get("standings") or {}).get("entries", []):
            rec = {s["type"]: s.get("summary") for s in e.get("stats", []) if s.get("type") in ("total", "home", "road")}
            if not rec.get("total") or all(n == "0" for n in rec["total"].split("-")):
                continue
            t = e["team"]["abbreviation"]
            out[rename.get(t, t)] = dict(overall=rec["total"], home=rec.get("home"), road=rec.get("road"))
    return out


def _download(url: str) -> dict:
    # a short timeout: /meta waits on this when the cached copy is stale
    r = espn._session.get(url, timeout=8)
    r.raise_for_status()
    return r.json()


def records(sport: str, season: int, cache_dir: str, rename: Optional[dict] = None) -> dict[str, dict]:
    """Every team's record this season ("football/nfl", "basketball/nba"), through a JSON file in cache_dir; a failed
    fetch falls back to the last good copy, and with none at all no records (they're context, not a number the
    model uses). Tried at most once per half hour, so an ESPN outage doesn't slow every page load."""
    return _records(sport, season, cache_dir, tuple(sorted((rename or {}).items())), int(time.time() // (MAX_AGE_HOURS * 3600)))


@lru_cache(maxsize=4)
def _records(sport: str, season: int, cache_dir: str, rename: tuple, _slot: int) -> dict[str, dict]:
    path = os.path.join(cache_dir, f"standings_{sport.replace('/', '_')}_{season}.json")
    url = URL.format(sport=sport, season=season)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        return parse(espn._cached(path, MAX_AGE_HOURS, lambda: _download(url)), dict(rename))
    except Exception:
        return {}
