"""Weather at outdoor stadiums: what it did to yardage in the backtest, and the forecast for upcoming games.

History comes from the nflverse schedule (game-time temperature and wind for outdoor games). The effect is fitted on
the walk-forward backtest's own misses: per market, the relative miss is regressed on wind above WIND_FROM mph and
cold below COLD_FROM degrees F, and each slope is shrunk toward zero by its own noise (b * b^2 / (b^2 + se^2)), so a
weak signal moves projections little. Receiving yards are passing yards split among receivers, so those two markets
share one effect (their fits averaged by precision). In the 2024-26 backtest, strong wind came with clearly fewer passing and
receiving yards and somewhat more rushing yards; cold took a few percent off passing.

Forecasts come from Open-Meteo (free, no key): the average temperature and wind over the three hours from kickoff,
plus gusts and precipitation. Open-Meteo may refuse shared cloud hosts (rate limits), so US stadiums fall back to the
National Weather Service's hourly forecast (also free; about a week ahead, without gusts or amounts), and any stadium,
international ones included, finally to MET Norway (free, worldwide, about nine days ahead; 6-hourly beyond two days). Precipitation is
shown but not applied: nflverse has no history of it to fit against. Domes and closed retractable roofs get no adjustment.
"""
import re
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

WIND_FROM = 10.0       # mph: wind below this has no measurable effect
COLD_FROM = 45.0       # degrees F
FACTOR_RANGE = (0.75, 1.25)
KINDS = ("rush", "rec", "pass")
OUTDOOR = {"outdoors", "open"}
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16     # Open-Meteo's horizon
NWS_URL = "https://api.weather.gov"
NWS_HEADERS = {"User-Agent": "nfl-prop-predictor (github.com/JoshuaDHaber/NFL-Prop-Predictor)", "Accept": "application/geo+json"}
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
MET_HEADERS = {"User-Agent": NWS_HEADERS["User-Agent"]}  # MET Norway requires an identifying User-Agent

# (latitude, longitude) per nflverse stadium_id
STADIUMS = {
    "ATL97": (33.7554, -84.4008), "BAL00": (39.2780, -76.6227), "BOS00": (42.0909, -71.2643), "BUF00": (42.7738, -78.7870),
    "CAR00": (35.2258, -80.8528), "CHI98": (41.8623, -87.6167), "CIN00": (39.0955, -84.5161), "CLE00": (41.5061, -81.6995),
    "DAL00": (32.7473, -97.0945), "DEN00": (39.7439, -105.0201), "DET00": (42.3400, -83.0456), "GNB00": (44.5013, -88.0622),
    "HOU00": (29.6847, -95.4107), "IND00": (39.7601, -86.1639), "JAX00": (30.3239, -81.6373), "KAN00": (39.0489, -94.4839),
    "LAX01": (33.9535, -118.3392), "MIA00": (25.9580, -80.2389), "MIN01": (44.9737, -93.2577), "NAS00": (36.1665, -86.7713),
    "NOR00": (29.9511, -90.0812), "NYC01": (40.8135, -74.0745), "PHI00": (39.9008, -75.1675), "PHO00": (33.5276, -112.2626),
    "PIT00": (40.4468, -80.0158), "SEA00": (47.5952, -122.3316), "SFO01": (37.4030, -121.9700), "TAM00": (27.9759, -82.5033),
    "VEG00": (36.0909, -115.1833), "WAS00": (38.9077, -76.8645),
    # international venues
    "GER00": (48.2188, 11.6247), "MUN01": (48.2188, 11.6247), "LON00": (51.5560, -0.2796), "LON02": (51.6043, -0.0664),
    "MAD01": (40.4531, -3.6883), "MEL00": (-37.8200, 144.9834), "MEX00": (19.3029, -99.1505), "PAR00": (48.9245, 2.3602),
    "RIO00": (-22.9122, -43.2302), "SAO00": (-23.5453, -46.4742),
}
INTERNATIONAL = {"GER00", "MUN01", "LON00", "LON02", "MAD01", "MEL00", "MEX00", "PAR00", "RIO00", "SAO00"}
# nflverse sometimes gives an international game its home team's stadium_id but the real stadium name
VENUE_BY_NAME = (("tottenham", "LON02"), ("wembley", "LON00"), ("bayern", "MUN01"), ("allianz", "MUN01"), ("bernab", "MAD01"),
                 ("stade de france", "PAR00"), ("melbourne", "MEL00"), ("maracan", "RIO00"), ("corinthians", "SAO00"),
                 ("banorte", "MEX00"), ("azteca", "MEX00"))
# nflverse lists some open-air international venues as domes
ROOF_OVERRIDE = {"MEL00": "outdoors", "PAR00": "outdoors", "MUN01": "outdoors"}
RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00", "MAD01"}  # open or closed is decided on game day
SHARED = ("rec", "pass")


def venue(stadium_id, stadium) -> str:
    """The stadium_id to locate a game by: the stadium's name wins for international venues."""
    name = stadium.lower() if isinstance(stadium, str) else ""
    return next((vid for key, vid in VENUE_BY_NAME if key in name), stadium_id)


def roof(stadium_id, listed) -> str:
    """outdoors | open | closed | dome | retractable (not yet decided) | unknown. Only outdoors and open get weather."""
    r = ROOF_OVERRIDE.get(stadium_id, listed)
    if isinstance(r, str) and r:
        return r
    return "retractable" if stadium_id in RETRACTABLE else "unknown"


def history(sched: pd.DataFrame) -> dict:
    """(season, week, team) -> (temp F, wind mph) for played outdoor games that recorded both."""
    if not {"roof", "temp", "wind"} <= set(sched.columns):
        return {}
    g = sched[sched.roof.isin(OUTDOOR) & sched.temp.notna() & sched.wind.notna()]
    out = {}
    for r in g.itertuples():
        for team in (r.home_team, r.away_team):
            out[(r.season, r.week, team)] = (float(r.temp), float(r.wind))
    return out


def _excess(temp, wind):
    return max(float(wind) - WIND_FROM, 0.0), max(COLD_FROM - float(temp), 0.0)


def factor(coef: dict, kind: str, temp, wind) -> float:
    """Multiplier on a yardage projection (1.0: no effect, or no weather)."""
    c = (coef or {}).get(kind)
    if not c or temp is None or wind is None or pd.isna(temp) or pd.isna(wind):
        return 1.0
    w, k = _excess(temp, wind)
    return float(np.clip(1.0 + c["wind"] * w + c["cold"] * k, *FACTOR_RANGE))


def factors(coef: dict, temp, wind) -> dict:
    return {k: factor(coef, k, temp, wind) for k in KINDS}


def _shrink(b, se):
    return float(b * b ** 2 / (b ** 2 + se ** 2)) if se and np.isfinite(se) and (b or se) else 0.0


def fit(bt: pd.DataFrame) -> dict:
    """Per market: shrunk slopes of the relative miss on wind and cold. bt needs kind, mu, actual, wx_temp, wx_wind
    (NaN when indoors); its projections must not already carry a weather adjustment."""
    out = _fit_each(bt)
    fitted = [out[k] for k in SHARED if out[k]["wind_se"]]
    for term in ("wind", "cold"):
        if not fitted:
            break
        prec = [1 / c[f"{term}_se"] ** 2 for c in fitted]
        b = sum(p * c[f"{term}_raw"] for p, c in zip(prec, fitted)) / sum(prec)
        se = min(c[f"{term}_se"] for c in fitted)  # the same games measured twice: pooling adds little certainty
        for k in SHARED:
            out[k][term] = _shrink(b, se)
            out[k]["shared"] = True
    return out


def _fit_each(bt: pd.DataFrame) -> dict:
    out = {}
    for kind in KINDS:
        g = bt[(bt.kind == kind) & bt.wx_temp.notna() & bt.wx_wind.notna()] if "wx_temp" in bt else bt.iloc[0:0]
        coef = dict(wind=0.0, cold=0.0, wind_raw=0.0, cold_raw=0.0, wind_se=None, cold_se=None, n=int(len(g)))
        all_kind = bt[bt.kind == kind]
        if len(g) >= 30:
            # indoor games as well, with zero weather, so the shared intercept (overall bias) isn't mistaken for weather
            temp = all_kind.wx_temp.fillna(COLD_FROM)
            wind = all_kind.wx_wind.fillna(0.0)
            w = np.maximum(wind - WIND_FROM, 0).to_numpy()
            k = np.maximum(COLD_FROM - temp, 0).to_numpy()
            mu = all_kind.mu.to_numpy(float)
            X = np.c_[mu, mu * w, mu * k]
            y = (all_kind.actual - all_kind.mu).to_numpy(float)
            with np.errstate(all="ignore"):  # numpy 2.0 on macOS Accelerate warns spuriously inside matmul
                ok = np.linalg.matrix_rank(X) == 3
                if ok:
                    b = np.linalg.lstsq(X, y, rcond=None)[0]
                    resid = y - X @ b
                    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * np.mean(resid ** 2))
                    ok = bool(np.isfinite(b).all() and np.isfinite(se).all() and (se[1:] > 0).all())
            if ok:
                coef.update(wind=_shrink(b[1], se[1]), cold=_shrink(b[2], se[2]), wind_raw=float(b[1]), cold_raw=float(b[2]),
                            wind_se=float(se[1]), cold_se=float(se[2]))
        out[kind] = coef
    return out


def summary(bt: pd.DataFrame, coef: dict) -> dict:
    """In-sample: bias and average miss in backtested games the weather adjustment moved, before and after."""
    by_kind = {}
    if "wx" in bt:
        for kind in KINDS:
            g = bt[(bt.kind == kind) & ((bt.wx - 1).abs() > 1e-9)]
            if len(g) < 10:
                continue
            before = g.mu / g.wx
            by_kind[kind] = dict(n=int(len(g)), bias_before=float((g.actual - before).mean()), bias_after=float((g.actual - g.mu).mean()),
                                 mae_before=float((g.actual - before).abs().mean()), mae_after=float((g.actual - g.mu).abs().mean()))
    return dict(coef=coef, wind_from=WIND_FROM, cold_from=COLD_FROM, by_kind=by_kind)


# WMO weather codes (Open-Meteo) -> short sky description; the most severe code in the kickoff window is shown
WMO = [(95, "Thunderstorms"), (85, "Snow showers"), (80, "Rain showers"), (71, "Snow"), (66, "Freezing rain"), (61, "Rain"),
       (56, "Freezing drizzle"), (51, "Drizzle"), (45, "Fog"), (3, "Overcast"), (2, "Partly cloudy"), (1, "Mostly clear"), (0, "Clear")]
COMPASS = {d: i * 22.5 for i, d in enumerate("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}


def sky(code) -> str:
    return next((label for floor, label in WMO if code is not None and code >= floor), None)


def mean_direction(degrees) -> float:
    """Average of compass bearings (so 350 and 10 average to 0, not 180)."""
    d = [x for x in degrees if x is not None]
    if not d:
        return None
    r = np.radians(d)
    return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360)


def _kickoff_hour(gametime) -> int:
    try:
        return int(str(gametime).split(":")[0])
    except (ValueError, AttributeError):
        return 13


def fetch_open_meteo(lat: float, lon: float, day: str, gametime, get=requests.get) -> dict:
    """Open-Meteo forecast for three hours from kickoff (gametime is US Eastern, as in the nflverse schedule)."""
    r = get(FORECAST_URL, params=dict(
        latitude=lat, longitude=lon, start_date=day, end_date=day, timezone="America/New_York",
        hourly="temperature_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation_probability,precipitation,snowfall,weather_code",
        temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch"), timeout=15)
    r.raise_for_status()
    h = r.json()["hourly"]
    k = _kickoff_hour(gametime)
    idx = [i for i, t in enumerate(h["time"]) if k <= int(t[11:13]) < k + 3] or [min(k, len(h["time"]) - 1)]

    def pick(name, fn):
        vals = [h[name][i] for i in idx if h.get(name) and h[name][i] is not None]
        return float(fn(vals)) if vals else None

    return dict(temp=pick("temperature_2m", np.mean), wind=pick("wind_speed_10m", np.mean), gust=pick("wind_gusts_10m", max),
                precip_prob=pick("precipitation_probability", max), precip=pick("precipitation", sum), snow=pick("snowfall", sum),
                wind_dir=mean_direction([h["wind_direction_10m"][i] for i in idx]) if h.get("wind_direction_10m") else None,
                sky=sky(pick("weather_code", max)), provider="Open-Meteo")


def _eastern(dt: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # no tz database on the host: US daylight time runs roughly mid-March to early November
        utc = dt.astimezone(timezone.utc)
        return utc + timedelta(hours=-4 if 3 <= utc.month <= 10 or (utc.month == 11 and utc.day < 3) else -5)


def fetch_nws(lat: float, lon: float, day: str, gametime, get=requests.get) -> dict:
    """National Weather Service hourly forecast (US only, about a week ahead) for three hours from kickoff."""
    r = get(f"{NWS_URL}/points/{lat:.4f},{lon:.4f}", headers=NWS_HEADERS, timeout=15)
    r.raise_for_status()
    r = get(r.json()["properties"]["forecastHourly"], headers=NWS_HEADERS, timeout=15)
    r.raise_for_status()
    k = _kickoff_hour(gametime)
    rows = []
    for p in r.json()["properties"]["periods"]:
        t = _eastern(datetime.fromisoformat(p["startTime"]))
        if t.date().isoformat() == day and k <= t.hour < k + 3:
            rows.append(p)
    if not rows:
        raise ValueError("no hourly forecast for kickoff yet")

    def temp_f(p):
        return p["temperature"] * 9 / 5 + 32 if p.get("temperatureUnit") == "C" else p["temperature"]

    winds = [np.mean([float(x) for x in re.findall(r"\d+(?:\.\d+)?", p.get("windSpeed") or "")] or [np.nan]) for p in rows]
    probs = [(p.get("probabilityOfPrecipitation") or {}).get("value") for p in rows]
    probs = [x for x in probs if x is not None]
    return dict(temp=float(np.mean([temp_f(p) for p in rows])), wind=float(np.nanmean(winds)) if not np.isnan(winds).all() else None,
                gust=None, precip_prob=float(max(probs)) if probs else None, precip=None, snow=None,
                wind_dir=mean_direction([COMPASS.get(p.get("windDirection")) for p in rows]), sky=rows[0].get("shortForecast") or None,
                provider="National Weather Service")


def _kickoff_utc(day: str, gametime) -> datetime:
    """Kickoff as a UTC time (the schedule's gametime is US Eastern)."""
    hh, _, mm = str(gametime or "13:00").partition(":")
    local = datetime.fromisoformat(day) + timedelta(hours=int(hh), minutes=int(mm or 0))
    try:
        from zoneinfo import ZoneInfo
        return local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    except Exception:
        offset = 4 if 3 <= local.month <= 10 or (local.month == 11 and local.day < 3) else 5
        return (local + timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def met_sky(symbol) -> str:
    """MET Norway symbol code ("lightrainshowers_day") -> a short description ("Light rain showers")."""
    if not symbol:
        return None
    s = symbol.split("_")[0]
    fixed = {"clearsky": "Clear", "fair": "Mostly clear", "partlycloudy": "Partly cloudy", "cloudy": "Overcast", "fog": "Fog"}
    if s in fixed:
        return fixed[s]
    if "thunder" in s:
        return "Thunderstorms"
    words = []
    for part in ("light", "heavy"):
        if s.startswith(part):
            words.append(part)
            s = s[len(part):]
    for kind in ("rain", "sleet", "snow"):
        if s.startswith(kind):
            words.append(kind)
            if "showers" in s:
                words.append("showers")
            break
    return " ".join(words).capitalize() if words else s.capitalize()


def fetch_met_no(lat: float, lon: float, day: str, gametime, get=requests.get) -> dict:
    """MET Norway forecast (worldwide) at the middle of the three hours from kickoff, interpolated between its
    readings (hourly for about two days, then every six hours)."""
    r = get(MET_URL, params=dict(lat=round(lat, 4), lon=round(lon, 4)), headers=MET_HEADERS, timeout=15)
    r.raise_for_status()
    series = [(datetime.fromisoformat(t["time"].replace("Z", "+00:00")), t["data"]) for t in r.json()["properties"]["timeseries"]]
    kick = _kickoff_utc(day, gametime)
    mid = kick + timedelta(minutes=90)
    before = [x for x in series if x[0] <= mid]
    after = [x for x in series if x[0] > mid]
    if not before or not after:
        raise ValueError("kickoff is outside MET Norway's forecast range")
    (t0, d0), (t1, d1) = before[-1], after[0]
    if (t1 - t0) > timedelta(hours=7):
        raise ValueError("no MET Norway reading near kickoff")
    f = (mid - t0) / (t1 - t0)
    a, b = d0["instant"]["details"], d1["instant"]["details"]

    def lerp(key):
        return a[key] + (b[key] - a[key]) * f if key in a and key in b else a.get(key, b.get(key))

    temp_c, wind_ms = lerp("air_temperature"), lerp("wind_speed")
    # precipitation and sky: hourly blocks inside the window when there are some, else the 6-hour block covering kickoff
    hourly = [d for t, d in series if kick - timedelta(minutes=59) <= t < kick + timedelta(hours=3) and "next_1_hours" in d]
    block = hourly or [d for t, d in series if t <= kick][-1:] or [d0]
    key = "next_1_hours" if hourly else "next_6_hours"
    rain_mm = [x.get(key, {}).get("details", {}).get("precipitation_amount") for x in block]
    probs = [x.get(key, {}).get("details", {}).get("probability_of_precipitation") for x in block]
    probs = [p for p in probs if p is not None]
    symbol = (block[0].get(key) or block[0].get("next_6_hours") or {}).get("summary", {}).get("symbol_code")
    return dict(temp=None if temp_c is None else float(temp_c) * 9 / 5 + 32, wind=None if wind_ms is None else float(wind_ms) * 2.23694,
                gust=None, precip_prob=float(max(probs)) if probs else None,
                precip=float(sum(x for x in rain_mm if x is not None)) / 25.4 if any(x is not None for x in rain_mm) else None,
                snow=None, wind_dir=mean_direction([a.get("wind_from_direction"), b.get("wind_from_direction")]),
                sky=met_sky(symbol), provider="MET Norway")


def _why(e: Exception) -> str:
    code = getattr(getattr(e, "response", None), "status_code", None)
    return f"{type(e).__name__} {code}" if code else type(e).__name__


FETCH_ERRORS = (requests.RequestException, KeyError, ValueError, TypeError)


def fetch_point(lat: float, lon: float, day: str, gametime, get=requests.get, us: bool = True, state: dict = None, log=print) -> dict:
    """Open-Meteo first; then, for US stadiums, the National Weather Service; then MET Norway for any stadium. After
    Open-Meteo refuses this host (429/403), the rest of the run goes straight to the fallbacks."""
    state = state if state is not None else {}
    errors = []
    if not state.get("open_meteo_blocked"):
        try:
            return fetch_open_meteo(lat, lon, day, gametime, get=get)
        except FETCH_ERRORS as e:
            errors.append(f"Open-Meteo: {_why(e)}")
            if getattr(getattr(e, "response", None), "status_code", None) in (403, 429):
                state["open_meteo_blocked"] = True
                log(f"  Open-Meteo refused this host ({_why(e)}); using the National Weather Service (US) and MET Norway instead")
    if us:
        try:
            return fetch_nws(lat, lon, day, gametime, get=get)
        except FETCH_ERRORS as e:
            errors.append(f"NWS: {e if isinstance(e, ValueError) else _why(e)}")
    try:
        return fetch_met_no(lat, lon, day, gametime, get=get)
    except FETCH_ERRORS as e:
        errors.append(f"MET Norway: {e if isinstance(e, ValueError) else _why(e)}")
    raise ValueError("; ".join(errors) or "no forecast source")


def forecast(games: pd.DataFrame, coef: dict, log=print, today: date = None, get=requests.get) -> dict:
    """game_id -> weather for each upcoming game: roof, forecast (outdoors only) and the per-market multipliers.

    A failed or out-of-range forecast leaves that game unadjusted; it never stops a model run."""
    today = today or date.today()
    out = {}
    if "stadium_id" not in games.columns:
        return out
    fetched = datetime.utcnow().isoformat()
    state = {}
    for g in games.itertuples():
        sid = venue(getattr(g, "stadium_id", None), getattr(g, "stadium", None))
        rf = roof(sid, getattr(g, "roof", None))
        w = dict(stadium=getattr(g, "stadium", None) or "", roof=rf, indoor=rf not in OUTDOOR, source="indoor" if rf not in OUTDOOR else "none",
                 temp=None, wind=None, gust=None, wind_dir=None, sky=None, precip_prob=None, precip=None, snow=None, fetched_at=None, provider=None,
                 factors={k: 1.0 for k in KINDS})
        out[g.game_id] = w
        if w["indoor"] or sid not in STADIUMS:
            continue
        try:
            days_out = (date.fromisoformat(str(g.gameday)) - today).days
        except ValueError:
            continue
        if not 0 <= days_out < FORECAST_DAYS:
            continue
        try:
            w.update(fetch_point(*STADIUMS[sid], str(g.gameday), g.gametime, get=get, us=sid not in INTERNATIONAL, state=state, log=log),
                     source="forecast", fetched_at=fetched)
        except FETCH_ERRORS as e:
            log(f"  weather for {g.game_id} unavailable ({e if isinstance(e, ValueError) else _why(e)})")
            continue
        if w["temp"] is not None and w["wind"] is not None:
            w["factors"] = factors(coef, w["temp"], w["wind"])
        time.sleep(0.05)  # be polite to free APIs
    return out
