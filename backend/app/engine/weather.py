"""Weather at outdoor stadiums: what it did to yardage in the backtest, and the forecast for upcoming games.

History comes from the nflverse schedule (game-time temperature and wind for outdoor games). The effect is fitted on
the walk-forward backtest's own misses: per market, the relative miss is regressed on wind above WIND_FROM mph and
cold below COLD_FROM degrees F, and each slope is shrunk toward zero by its own noise (b * b^2 / (b^2 + se^2)), so a
weak signal moves projections little. Receiving yards are passing yards split among receivers, so those two markets
share one effect (their fits averaged by precision). In the 2024-26 backtest, strong wind came with clearly fewer passing and
receiving yards and somewhat more rushing yards; cold took a few percent off passing.

Forecasts come from Open-Meteo (free, no key): the average temperature and wind over the three hours from kickoff,
plus gusts and precipitation. Precipitation is shown but not applied: nflverse has no history of it to fit against.
Domes and closed retractable roofs get no adjustment.
"""
import time
from datetime import date, datetime

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
# nflverse lists some open-air international venues as domes
ROOF_OVERRIDE = {"MEL00": "outdoors", "PAR00": "outdoors", "MUN01": "outdoors"}
RETRACTABLE = {"ATL97", "DAL00", "HOU00", "IND00", "PHO00", "MAD01"}  # open or closed is decided on game day
SHARED = ("rec", "pass")


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


def _kickoff_hour(gametime) -> int:
    try:
        return int(str(gametime).split(":")[0])
    except (ValueError, AttributeError):
        return 13


def fetch_point(lat: float, lon: float, day: str, gametime, get=requests.get) -> dict:
    """Open-Meteo forecast for three hours from kickoff (gametime is US Eastern, as in the nflverse schedule)."""
    r = get(FORECAST_URL, params=dict(
        latitude=lat, longitude=lon, start_date=day, end_date=day, timezone="America/New_York",
        hourly="temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,precipitation,snowfall",
        temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch"), timeout=15)
    r.raise_for_status()
    h = r.json()["hourly"]
    k = _kickoff_hour(gametime)
    idx = [i for i, t in enumerate(h["time"]) if k <= int(t[11:13]) < k + 3] or [min(k, len(h["time"]) - 1)]

    def pick(name, fn):
        vals = [h[name][i] for i in idx if h.get(name) and h[name][i] is not None]
        return float(fn(vals)) if vals else None

    return dict(temp=pick("temperature_2m", np.mean), wind=pick("wind_speed_10m", np.mean), gust=pick("wind_gusts_10m", max),
                precip_prob=pick("precipitation_probability", max), precip=pick("precipitation", sum), snow=pick("snowfall", sum))


def forecast(games: pd.DataFrame, coef: dict, log=print, today: date = None, get=requests.get) -> dict:
    """game_id -> weather for each upcoming game: roof, forecast (outdoors only) and the per-market multipliers.

    A failed or out-of-range forecast leaves that game unadjusted; it never stops a model run."""
    today = today or date.today()
    out = {}
    if "stadium_id" not in games.columns:
        return out
    fetched = datetime.utcnow().isoformat()
    for g in games.itertuples():
        sid = getattr(g, "stadium_id", None)
        rf = roof(sid, getattr(g, "roof", None))
        w = dict(stadium=getattr(g, "stadium", None) or "", roof=rf, indoor=rf not in OUTDOOR, source="indoor" if rf not in OUTDOOR else "none",
                 temp=None, wind=None, gust=None, precip_prob=None, precip=None, snow=None, fetched_at=None,
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
            w.update(fetch_point(*STADIUMS[sid], str(g.gameday), g.gametime, get=get), source="forecast", fetched_at=fetched)
        except (requests.RequestException, KeyError, ValueError, TypeError) as e:
            log(f"  weather for {g.game_id} unavailable ({type(e).__name__})")
            continue
        if w["temp"] is not None and w["wind"] is not None:
            w["factors"] = factors(coef, w["temp"], w["wind"])
        time.sleep(0.05)  # be polite to a free API
    return out
