"""The week's injury report for the UI: who is out, doubtful, questionable or practicing hurt, plus reserve lists.

Built from nflverse's injury file (one row per player per week: the final game status and that week's practice
participation) and the roster file's reserve statuses (IR, PUP, ...), which never appear on the weekly report.
ESPN's injury feed adds the latest news line, an estimated return and, where nflverse has nothing current, the status."""
import pandas as pd

from .odds import norm

OFFENSE = ["QB", "RB", "FB", "WR", "TE", "T", "OT", "G", "OG", "C", "OL"]
DEFENSE = ["DE", "EDGE", "DT", "NT", "DL", "LB", "OLB", "ILB", "MLB", "CB", "DB", "S", "FS", "SS", "SAF"]
POS_ORDER = {p: i for i, p in enumerate(OFFENSE + DEFENSE + ["K", "P", "LS"])}
# report status first, then players with no status who still missed or were limited in practice
STATUS_ORDER = {"Out": 0, "Suspension": 0, "Doubtful": 1, "Questionable": 2, "": 3}
GAME_STATUSES = {"Out", "Suspension", "Doubtful", "Questionable"}
# ESPN statuses that mean something for Sunday ("Active" entries are only news)
ESPN_STATUS = {"Out": "Out", "Suspension": "Suspension", "Doubtful": "Doubtful", "Questionable": "Questionable",
               "Injured Reserve": "IR"}
PRACTICE = {"Did Not Participate In Practice": "DNP", "Limited Participation in Practice": "Limited",
            "Full Participation in Practice": "Full"}
# roster status_description_abbr codes for reserve lists; anything else on reserve is shown as "Reserve"
RESERVE = {"R01": "IR", "R48": "IR", "R04": "PUP", "R05": "NFI"}
RESERVED = set(RESERVE.values()) | {"Reserve"}


def side(pos: str) -> str:
    return "off" if pos in OFFENSE else "def" if pos in DEFENSE else "st"


def _text(v) -> str:
    return "" if pd.isna(v) else str(v)


def _merge_espn(rows: list, espn: pd.DataFrame, espn_ids: dict, stale: bool) -> None:
    """Attach ESPN's news line, estimated return and update time to the matching players (by ESPN id through the
    roster, else name and team). ESPN's status wins where nflverse has no current game status: a practice-only listing,
    a reserve list the roster file hasn't caught up on, or last week's report. Players ESPN lists with a status that
    nflverse doesn't are added."""
    by_id = {r["player_id"]: r for r in rows}
    by_name = {(norm(r["name"]), r["team"]): r for r in rows}
    for e in espn.itertuples():
        gid = espn_ids.get(str(e.espn_id)) if e.espn_id else None
        r = by_id.get(gid) if gid else None
        r = r or by_name.get((norm(e.name), e.team))
        status = ESPN_STATUS.get(e.status)
        if r is None:
            if not status:
                continue
            r = dict(player_id=gid or f"espn:{e.espn_id or norm(e.name)}", name=e.name, pos=e.pos, team=e.team,
                     status=status, injury=e.injury, practice="", rest=False)
            rows.append(r)
            by_name[(norm(e.name), e.team)] = r
        elif status and (stale or r["status"] not in GAME_STATUSES) and not (status == "IR" and r["status"] in RESERVED):
            r["status"] = status
            if stale:
                r["practice"] = ""   # last week's practice notes don't describe this week
        if not r.get("injury") and not r.get("rest"):
            r["injury"] = e.injury
        # game-day inactives come with a one-word "news" line ("inactive", "questionable") that repeats the badge
        r.update(comment=e.comment if len(str(e.comment).split()) >= 4 else "", return_date=e.return_date if isinstance(e.return_date, str) else None,
                 updated=e.updated if isinstance(e.updated, str) else None)


def build(inj: pd.DataFrame, reserve: pd.DataFrame, week: int, teams=None, props: dict = None,
          espn: pd.DataFrame = None, espn_ids: dict = None) -> dict:
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
    if espn is not None and not espn.empty:
        _merge_espn(rows, espn, espn_ids or {}, stale=report_week is None or report_week < week)
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
