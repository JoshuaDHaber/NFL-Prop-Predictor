"""Weather: the fitted effect, the forecast for upcoming games, and how both reach the projections."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
import requests

from app.engine import model
from app.engine import weather as wx

COEF = {"pass": dict(wind=-0.02, cold=-0.005), "rec": dict(wind=-0.02, cold=0.0), "rush": dict(wind=0.01, cold=0.0)}


def test_calm_mild_or_unknown_weather_changes_nothing():
    assert wx.factor(COEF, "pass", 70, 8) == 1.0               # under both thresholds
    assert wx.factor(COEF, "pass", None, None) == 1.0
    assert wx.factor(COEF, "pass", np.nan, 20) == 1.0
    assert wx.factor({}, "pass", 20, 25) == 1.0                # no fitted effect


def test_wind_and_cold_scale_each_market_its_own_way():
    assert wx.factor(COEF, "pass", 70, 18) == pytest.approx(1 - 0.02 * 8)
    assert wx.factor(COEF, "rush", 70, 18) == pytest.approx(1 + 0.01 * 8)
    assert wx.factor(COEF, "pass", 35, 10) == pytest.approx(1 - 0.005 * 10)
    assert wx.factor(COEF, "pass", 0, 45) == wx.FACTOR_RANGE[0]  # a blizzard is capped, not extrapolated


def _bt(effect, n=3000, seed=0):
    """Backtest rows where wind above 10 mph really does cut passing by `effect` per mph; a third are indoors."""
    rng = np.random.default_rng(seed)
    mu = rng.uniform(150, 300, n)
    wind = rng.uniform(0, 22, n)
    temp = rng.uniform(25, 85, n)
    indoor = rng.random(n) < 0.33
    true = mu * (1 + effect * np.maximum(wind - 10, 0) * ~indoor)
    actual = true + rng.normal(0, 60, n)
    return pd.DataFrame(dict(kind="pass", mu=mu, actual=actual, wx_temp=np.where(indoor, np.nan, temp),
                             wx_wind=np.where(indoor, np.nan, wind)))


def test_fit_recovers_a_real_wind_effect():
    c = wx.fit(_bt(-0.025))["pass"]
    assert c["wind"] == pytest.approx(-0.025, abs=0.006)
    assert abs(c["cold"]) < 0.004
    assert abs(c["wind"]) <= abs(c["wind_raw"])                # shrunk, never inflated


def test_receiving_and_passing_share_one_effect():
    bt = pd.concat([_bt(-0.03, seed=1), _bt(-0.01, seed=2).assign(kind="rec")], ignore_index=True)
    c = wx.fit(bt)
    assert c["pass"]["wind"] == c["rec"]["wind"] and c["pass"]["shared"]
    assert -0.03 < c["pass"]["wind"] < -0.01                     # between the two separate fits
    assert c["pass"]["wind_raw"] != c["rec"]["wind_raw"]          # each market's own fit is kept for reference


def test_fit_finds_nothing_when_there_is_nothing():
    c = wx.fit(_bt(0.0))["pass"]
    assert abs(c["wind"]) < 0.004
    empty = wx.fit(pd.DataFrame(dict(kind=["pass"], mu=[200.0], actual=[210.0], wx_temp=[np.nan], wx_wind=[np.nan])))
    assert empty["pass"]["wind"] == 0.0 and empty["rush"]["n"] == 0


def test_history_keeps_only_outdoor_games_with_readings():
    sched = pd.DataFrame(dict(season=2025, week=[1, 1, 2], home_team=["AAA", "CCC", "AAA"], away_team=["BBB", "DDD", "CCC"],
                              roof=["outdoors", "dome", "outdoors"], temp=[40.0, 72.0, np.nan], wind=[15.0, 0.0, np.nan]))
    h = wx.history(sched)
    assert h == {(2025, 1, "AAA"): (40.0, 15.0), (2025, 1, "BBB"): (40.0, 15.0)}
    assert wx.history(sched.drop(columns=["roof"])) == {}


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status
        self.status_code = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status}", response=self)

    def json(self):
        return self.payload


def hourly(day, temps, winds):
    return {"hourly": {"time": [f"{day}T{h:02d}:00" for h in range(24)], "temperature_2m": temps, "wind_speed_10m": winds,
                       "wind_gusts_10m": [w * 1.5 for w in winds], "precipitation_probability": [10] * 24,
                       "precipitation": [0.01] * 24, "snowfall": [0.0] * 24, "wind_direction_10m": [350.0, 10.0] * 12,
                       "weather_code": [2] * 14 + [61] + [2] * 9}}


def games():
    return pd.DataFrame([
        dict(game_id="2026_06_AAA_BUF", gameday="2026-10-11", gametime="13:00", stadium_id="BUF00", stadium="Highmark", roof="outdoors"),
        dict(game_id="2026_06_CCC_DET", gameday="2026-10-11", gametime="13:00", stadium_id="DET00", stadium="Ford Field", roof="dome"),
        dict(game_id="2026_06_EEE_CHI", gameday="2026-11-30", gametime="20:20", stadium_id="CHI98", stadium="Soldier", roof="outdoors"),
    ])


def test_forecast_averages_the_three_hours_from_kickoff_and_skips_domes():
    calls = []

    def get(url, params=None, timeout=0):
        calls.append(params)
        temps = [50.0] * 24
        winds = [5.0] * 13 + [16.0, 18.0, 20.0] + [5.0] * 8           # windy from 1 pm to 4 pm only
        return FakeResp(hourly(params["start_date"], temps, winds))

    out = wx.forecast(games(), COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)
    assert len(calls) == 1                                          # the dome needs no forecast; Nov 30 is past the horizon
    buf = out["2026_06_AAA_BUF"]
    assert buf["source"] == "forecast" and buf["wind"] == pytest.approx(18.0) and buf["gust"] == pytest.approx(30.0)
    assert buf["factors"]["pass"] == pytest.approx(1 - 0.02 * 8) and buf["factors"]["rush"] == pytest.approx(1 + 0.01 * 8)
    assert buf["wind_dir"] < 5                                       # 10, 350, 10 degrees average to just east of north, not 123
    assert buf["sky"] == "Rain"                                      # the worst hour of the window
    assert out["2026_06_CCC_DET"]["indoor"] and out["2026_06_CCC_DET"]["factors"]["pass"] == 1.0
    assert out["2026_06_EEE_CHI"]["source"] == "none" and out["2026_06_EEE_CHI"]["factors"]["pass"] == 1.0


def test_a_failed_forecast_leaves_the_game_unadjusted():
    def boom(url, params=None, timeout=0):
        raise requests.ConnectionError("down")

    logs = []
    out = wx.forecast(games(), COEF, log=logs.append, today=date(2026, 10, 6), get=boom)
    assert out["2026_06_AAA_BUF"]["source"] == "none" and out["2026_06_AAA_BUF"]["factors"]["pass"] == 1.0
    assert any("unavailable" in m for m in logs)
    assert wx.forecast(games().drop(columns=["stadium_id"]), COEF) == {}


def test_mislabelled_open_air_venues_get_weather():
    assert wx.roof("PAR00", "dome") == "outdoors"
    assert wx.roof("DET00", "dome") == "dome"
    assert wx.roof("ATL97", np.nan) == "retractable"           # open or closed is decided on game day: no adjustment
    assert wx.roof("XXX00", None) == "unknown"


def test_components_scale_yards_but_not_volume():
    hist = pd.DataFrame(dict(carries=[15, 18, 12], rushing_yards=[60.0, 80.0, 50.0], targets=[3, 4, 2],
                             receiving_yards=[20.0, 30.0, 10.0], attempts=[0, 0, 0], passing_yards=[0.0] * 3, position="RB"))
    hist.attrs["opp"] = "X"
    priors = {("rush", "RB"): 4.3, ("rec", "RB"): 6.5}
    opp = {k: {} for k in model.CFG}
    base = model.components(hist, "RB", priors, opp, 0.0)
    windy = model.components(hist, "RB", priors, opp, 0.0, {"rush": 1.08, "rec": 0.84})
    assert windy["rush"][0] == pytest.approx(base["rush"][0] * 1.08) and windy["rush"][1] == base["rush"][1]
    assert windy["rec"][0] == pytest.approx(base["rec"][0] * 0.84)
    ratio = model.wx_ratio("rr", windy, {"rush": 1.08, "rec": 0.84})
    assert ratio == pytest.approx((windy["rush"][0] + windy["rec"][0]) / (base["rush"][0] + base["rec"][0]))


def nws_get(open_meteo_status=429, nws_wind="15 to 25 mph"):
    """Open-Meteo refuses (as it can for shared cloud hosts); the NWS answers with hourly periods in Central time."""
    calls = []

    def get(url, params=None, headers=None, timeout=0):
        calls.append(url)
        if "open-meteo" in url:
            return FakeResp({}, status=open_meteo_status)
        if "/points/" in url:
            return FakeResp({"properties": {"forecastHourly": "https://api.weather.gov/gridpoints/BUF/1,2/forecast/hourly"}})
        periods = [dict(startTime=f"2026-10-11T{h:02d}:00:00-05:00", temperature=40 + h, temperatureUnit="F", windSpeed=nws_wind,
                        windDirection="W", shortForecast="Mostly Sunny", probabilityOfPrecipitation={"value": 20 + h}) for h in range(6, 20)]
        return FakeResp({"properties": {"periods": periods}})
    return get, calls


def test_us_stadiums_fall_back_to_the_weather_service_when_open_meteo_refuses():
    get, calls = nws_get()
    logs = []
    out = wx.forecast(games(), COEF, log=logs.append, today=date(2026, 10, 6), get=get)
    buf = out["2026_06_AAA_BUF"]
    # 13:00-15:59 Eastern is 12:00-14:59 Central
    assert buf["source"] == "forecast" and buf["provider"] == "National Weather Service"
    assert buf["temp"] == pytest.approx(53.0) and buf["wind"] == pytest.approx(20.0) and buf["precip_prob"] == 34
    assert buf["factors"]["pass"] == pytest.approx(1 - 0.02 * 10)
    assert buf["wind_dir"] == pytest.approx(270.0) and buf["sky"] == "Mostly Sunny"
    assert any("refused this host" in m for m in logs)


def test_after_open_meteo_refuses_the_rest_of_the_run_skips_it():
    get, calls = nws_get()
    two = pd.concat([games().iloc[[0]], games().iloc[[0]].assign(game_id="2026_06_FFF_BUF")], ignore_index=True)
    wx.forecast(two, COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)
    assert sum("open-meteo" in u for u in calls) == 1


def test_an_international_game_is_located_by_its_stadium_name():
    london = pd.DataFrame([dict(game_id="2026_05_PHI_JAX", gameday="2026-10-11", gametime="09:30", stadium_id="JAX00",
                                stadium="Tottenham Hotspur Stadium", roof="outdoors")])
    seen = []

    def get(url, params=None, headers=None, timeout=0):
        seen.append(params)
        return FakeResp(hourly("2026-10-11", [55.0] * 24, [8.0] * 24))

    out = wx.forecast(london, COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)
    assert seen[0]["latitude"] == pytest.approx(51.6043)              # London, not Jacksonville
    assert out["2026_05_PHI_JAX"]["provider"] == "Open-Meteo"
    get, calls = met_get()
    out = wx.forecast(london, COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)
    assert out["2026_05_PHI_JAX"]["provider"] == "MET Norway" and not any("weather.gov" in u for u in calls)   # the NWS is US-only


def met_get():
    """Open-Meteo refuses; MET Norway answers with readings every six hours (as it does beyond two days out)."""
    calls = []

    def reading(hour, temp_c, wind_ms, direction, symbol, rain_mm):
        return {"time": f"2026-10-11T{hour:02d}:00:00Z", "data": {
            "instant": {"details": {"air_temperature": temp_c, "wind_speed": wind_ms, "wind_from_direction": direction}},
            "next_6_hours": {"summary": {"symbol_code": symbol}, "details": {"precipitation_amount": rain_mm}}}}

    def get(url, params=None, headers=None, timeout=0):
        calls.append(url)
        if "open-meteo" in url:
            return FakeResp({}, status=429)
        assert "met.no" in url and headers["User-Agent"]
        return FakeResp({"properties": {"timeseries": [reading(6, 10.0, 2.0, 270, "cloudy", 0.0),
                                                       reading(12, 14.0, 4.0, 270, "lightrainshowers_day", 2.54),
                                                       reading(18, 12.0, 10.0, 290, "rain", 5.0),
                                                       reading(23, 9.0, 8.0, 300, "cloudy", 0.0)]}})
    return get, calls


def test_met_norway_interpolates_to_mid_window_and_reads_the_block_covering_kickoff():
    get, _ = met_get()
    london = pd.DataFrame([dict(game_id="g", gameday="2026-10-11", gametime="09:30", stadium_id="LON02",
                                stadium="Tottenham Hotspur Stadium", roof="outdoors")])
    w = wx.forecast(london, COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)["g"]
    # kickoff 09:30 EDT = 13:30 UTC; the window's middle (15:00) is halfway between the 12:00 and 18:00 readings
    assert w["temp"] == pytest.approx(13.0 * 9 / 5 + 32) and w["wind"] == pytest.approx(7.0 * 2.23694)
    assert 270 < w["wind_dir"] < 290
    assert w["sky"] == "Light rain showers" and w["precip"] == pytest.approx(0.1)   # the 12:00 block covers kickoff
    assert w["factors"]["pass"] == pytest.approx(1 - 0.02 * (7.0 * 2.23694 - 10))


def test_met_norway_symbol_codes_read_as_plain_words():
    assert wx.met_sky("clearsky_night") == "Clear"
    assert wx.met_sky("heavysnowshowers_day") == "Heavy snow showers"
    assert wx.met_sky("rainandthunder") == "Thunderstorms"
    assert wx.met_sky(None) is None


def test_a_us_game_falls_through_to_met_norway_when_both_us_sources_fail():
    met, _ = met_get()

    def get(url, params=None, headers=None, timeout=0):
        if "weather.gov" in url:
            raise requests.ConnectionError("down")
        return met(url, params=params, headers=headers, timeout=timeout)

    out = wx.forecast(games().iloc[[0]], COEF, log=lambda m: None, today=date(2026, 10, 6), get=get)
    assert out["2026_06_AAA_BUF"]["provider"] == "MET Norway"
