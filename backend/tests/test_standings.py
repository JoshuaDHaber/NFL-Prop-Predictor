import os

from app import standings


def _entry(team, total, home="0-0", road="0-0"):
    return {"team": {"abbreviation": team}, "stats": [
        {"type": "wins", "displayValue": "1"}, {"name": "overall", "type": "total", "summary": total},
        {"name": "Home", "type": "home", "summary": home}, {"name": "Road", "type": "road", "summary": road}]}


JS = {"children": [{"standings": {"entries": [_entry("KC", "5-1-1", "3-0", "2-1-1"), _entry("WSH", "2-4", "1-2", "1-2")]}},
                   {"standings": {"entries": [_entry("LAR", "0-0")]}}]}


def test_parse_reads_records_maps_teams_and_skips_teams_yet_to_play():
    assert standings.parse(JS, {"WSH": "WAS", "LAR": "LA"}) == {
        "KC": dict(overall="5-1-1", home="3-0", road="2-1-1"), "WAS": dict(overall="2-4", home="1-2", road="1-2")}


def test_records_are_cached_on_disk_and_survive_a_failed_fetch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(standings, "_download", lambda url: calls.append(url) or JS)
    assert standings.records("football/nfl", 2026, str(tmp_path))["KC"]["overall"] == "5-1-1"
    assert calls == ["https://site.api.espn.com/apis/v2/sports/football/nfl/standings?season=2026"]

    def down(url):
        raise standings.espn.requests.ConnectionError("down")
    monkeypatch.setattr(standings, "_download", down)
    [path] = tmp_path.iterdir()
    os.utime(path, (0, 0))   # the copy on disk is stale: the fetch fails, the copy stands
    standings._records.cache_clear()
    assert standings.records("football/nfl", 2026, str(tmp_path))["WSH"]["overall"] == "2-4"
    assert standings.records("football/nfl", 2025, str(tmp_path)) == {}   # nothing on disk at all
