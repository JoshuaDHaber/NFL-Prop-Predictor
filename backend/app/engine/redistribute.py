"""Teammate volume redistribution when a regular player is out.

When a starter misses a game, his carries, targets or pass attempts go to his teammates, and the books
price that in. The yardage model projects each player from his own history, so without this it misses
the beneficiaries (and rates them as unders). For each team-game:

  * find absent regulars: players who were recently regular contributors (projected carries / targets /
    attempts above a floor) but have no role in this game,
  * take the volume they would have had, minus the part teammates' recent history already reflects
    (the longer someone has been out, the more of his absence is already in the teammates' recent games),
  * hand a fitted share rho of it to the active teammates in the SAME position group (running backs for
    carries, etc.), in proportion to their own projected volume.

rho per role (carries, targets, attempts) is fit in the walk-forward backtest. Only the roles where the
held-out test shows an improvement are switched on (ACTIVE_ROLES): rushing, where teammates of an absent
back averaged +8 yards over their projection and the correction removes that without hurting accuracy.
Receiving (+2 yards, overshoots) and passing (+12 yards, badly overshoots) made held-out error worse, so
they stay off.
"""
import numpy as np
import pandas as pd

ROLES = {"rush": "carries", "rec": "targets", "pass": "attempts"}   # kind -> actual volume column
MIN_REGULAR = {"rush": 8.0, "rec": 5.0, "pass": 15.0}                # projected volume that makes someone a regular
MAX_GAP = 8                    # team games; someone gone longer is fully reflected in teammates' history
HALFLIFE = 5.0                 # same decay as the yardage model
HIST_GAMES = 16
LIFT_CAP = {"rush": 2.5, "rec": 2.5, "pass": None}   # a teammate's volume can't more than 2.5x from this alone
DEFAULT_RHO = {"rush": 0.6, "rec": 0.0, "pass": 0.0}
ACTIVE_ROLES = ("rush",)       # roles redistribution is applied to (see module docstring)
# The share fitted on volume overshoots once it is turned into yards (extra carries don't all come with average
# efficiency, and projections regress toward the mean). Held-out weeks and a replay of past weeks both put the
# best share at 50-75% of the fit (bias ~0, error no worse), so the fit is shrunk by this factor.
SHRINK = 0.65


def reflected_fraction(missed_before: int) -> float:
    """Share of a missing player's absence that teammates' recency-weighted history already contains,
    given how many team games he missed before this one."""
    w = 0.5 ** (np.arange(HIST_GAMES) / HALFLIFE)
    return float(w[:min(missed_before, HIST_GAMES)].sum() / w.sum())


class Logs:
    """Fast lookups over the stats frame: each team's game list and each player's rows."""

    def __init__(self, df: pd.DataFrame):
        self.team_games = {t: np.sort(g.t.unique()) for t, g in df.groupby("team")}
        self.by_pid = {pid: g.sort_values("t").reset_index(drop=True) for pid, g in df.groupby("player_id")}
        self.pid_t = {pid: g.t.to_numpy() for pid, g in self.by_pid.items()}
        self.active_at = {t: set(g.player_id) for t, g in df.groupby("t")}


def find_absent(logs: Logs, team: str, t: int, active: set, exclude_roles=()) -> list:
    """Players whose last row before t is on this team, within MAX_GAP team games, with no role at t.

    Returns (pid, history rows before t, team games missed before this one)."""
    games = logs.team_games.get(team)
    if games is None:
        return []
    n = int(np.searchsorted(games, t, side="left"))  # team games already played before t
    out = []
    for pid, ts in logs.pid_t.items():
        if pid in active:
            continue
        j = int(np.searchsorted(ts, t, side="left")) - 1
        if j < 0:
            continue
        g = logs.by_pid[pid]
        if g.team.iat[j] != team:
            continue
        k = int(np.searchsorted(games, ts[j]))
        gap = n - k
        if 1 <= gap <= MAX_GAP:
            out.append((pid, g.iloc[: j + 1], gap - 1))
    return out


def group(kind: str, pos: str) -> str:
    """Who competes for the same volume: running backs for carries, receivers for targets, quarterbacks for attempts."""
    if kind == "rush":
        return "RB" if pos in ("RB", "FB") else ("QB" if pos == "QB" else "OTH")
    if kind == "rec":
        return "RB" if pos in ("RB", "FB") else pos
    return "QB"


def lost_volume(absent: list, comp_fn) -> dict:
    """{(role, position group): volume the absent regulars would have had, net of what teammates' history already
    shows}. Volume stays inside the absent player's own position group."""
    lost = {}
    for pid, hist, missed in absent:
        comp = comp_fn(hist)
        keep = 1.0 - reflected_fraction(missed)
        pos = hist.position.iat[-1]
        for kind in ROLES:
            c = comp.get(kind)
            if c and c[1] >= MIN_REGULAR[kind]:
                key = (kind, group(kind, pos))
                lost[key] = lost.get(key, 0.0) + c[1] * keep
    return lost


def lift(kind: str, rho: float, lost: float, active_volume: float) -> float:
    """Multiplier on every active teammate's projected volume in this role and group."""
    if lost <= 0 or active_volume <= 0:
        return 1.0
    f = 1.0 + rho * lost / active_volume
    cap = LIFT_CAP[kind]
    return min(f, cap) if cap else f


def fit_rho(records: list) -> dict:
    """Slope of teammates' extra volume on the volume we'd expect to be handed to them, per role."""
    out = dict(DEFAULT_RHO)
    for kind in ROLES:
        r = [x for x in records if x[0] == kind]
        if len(r) >= 40:
            z, obs = np.array([x[1] for x in r]), np.array([x[2] for x in r])
            if z.std() > 1e-9:
                out[kind] = float(np.clip(np.polyfit(z, obs, 1)[0], 0.0, 1.2))
    return out


def applied(rho: dict) -> dict:
    """The shares actually used: the fit, shrunk, for the active roles; zero for the rest."""
    return {k: (v * SHRINK if k in ACTIVE_ROLES else 0.0) for k, v in rho.items()}
