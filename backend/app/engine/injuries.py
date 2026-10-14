"""The week's injury report for the UI: who is out, doubtful, questionable or practicing hurt, plus reserve lists.

Built from nflverse's injury file (one row per player per week: the final game status and that week's practice
participation) and the roster file's reserve statuses (IR, PUP, ...), which never appear on the weekly report."""
import pandas as pd

OFFENSE = ["QB", "RB", "FB", "WR", "TE", "T", "OT", "G", "OG", "C", "OL"]
DEFENSE = ["DE", "EDGE", "DT", "NT", "DL", "LB", "OLB", "ILB", "MLB", "CB", "DB", "S", "FS", "SS", "SAF"]
POS_ORDER = {p: i for i, p in enumerate(OFFENSE + DEFENSE + ["K", "P", "LS"])}
# report status first, then players with no status who still missed or were limited in practice
STATUS_ORDER = {"Out": 0, "Doubtful": 1, "Questionable": 2, "": 3}
PRACTICE = {"Did Not Participate In Practice": "DNP", "Limited Participation in Practice": "Limited",
            "Full Participation in Practice": "Full"}
# roster status_description_abbr codes for reserve lists; anything else on reserve is shown as "Reserve"
RESERVE = {"R01": "IR", "R48": "IR", "R04": "PUP", "R05": "NFI"}


def side(pos: str) -> str:
    return "off" if pos in OFFENSE else "def" if pos in DEFENSE else "st"


def _text(v) -> str:
    return "" if pd.isna(v) else str(v)


def build(inj: pd.DataFrame, reserve: pd.DataFrame, week: int, teams=None, props: dict = None) -> dict:
    """Per team, the players worth knowing about this week.

    Uses the target week's report; before it is published (reports start on Wednesday) the latest earlier week is used
    and `report_week` says which. A player with no game status who practiced fully is healthy and left out.
    props maps player_id -> a market the app projects for him, so the UI can open his drawer."""
    props = props or {}
    report_week = None
    rows = []
    if not inj.empty:
        weeks = inj.week[inj.week <= week]
        if len(weeks):
            report_week = int(weeks.max())
            cur = inj[inj.week == report_week]
            for r in cur.itertuples():
                status, practice = _text(r.report_status), PRACTICE.get(_text(r.practice_status), "")
                if status not in STATUS_ORDER or (not status and practice in ("", "Full")):
                    continue
                injury = _text(r.report_primary_injury) or _text(r.practice_primary_injury)
                rest = "resting" in injury.lower() or "not injury related" in injury.lower()
                rows.append(dict(player_id=r.gsis_id, name=r.full_name, pos=_text(r.position), team=r.team, status=status,
                                 injury="Rest" if rest else injury, practice=practice, rest=rest))
    listed = {r["player_id"] for r in rows}
    if not reserve.empty:
        for r in reserve.itertuples():
            if r.gsis_id not in listed:
                rows.append(dict(player_id=r.gsis_id, name=r.full_name, pos=_text(r.position), team=r.team,
                                 status=RESERVE.get(_text(r.status_description_abbr), "Reserve"), injury="", practice="", rest=False))
    out = {}
    for r in rows:
        if teams is not None and r["team"] not in teams:
            continue
        r["side"] = side(r["pos"])
        r["kind"] = props.get(r["player_id"])
        out.setdefault(r["team"], []).append(r)
    for players in out.values():
        players.sort(key=lambda p: (STATUS_ORDER.get(p["status"], 9), p["rest"], {"DNP": 0, "Limited": 1}.get(p["practice"], 2),
                                    POS_ORDER.get(p["pos"], 99), p["name"]))
    return dict(report_week=report_week, teams=out)
