"""The injury report shown in the UI: who's listed, what's left out, ordering and the reserve lists."""
import pandas as pd

from app.engine import injuries as injm

COLS = ["week", "team", "gsis_id", "full_name", "position", "report_status", "report_primary_injury",
        "practice_primary_injury", "practice_status"]


def inj(rows):
    return pd.DataFrame(rows, columns=COLS)


DNP, LTD, FULL = "Did Not Participate In Practice", "Limited Participation in Practice", "Full Participation in Practice"
REPORT = inj([
    (5, "AAA", "old", "Last Week", "WR", "Out", "Knee", "Knee", DNP),
    (6, "AAA", "q1", "Q Receiver", "WR", "Questionable", "Ankle", "Ankle", LTD),
    (6, "AAA", "o1", "Out Corner", "CB", "Out", "Hamstring", "Hamstring", DNP),
    (6, "AAA", "h1", "Healthy Guard", "G", None, None, "Toe", FULL),
    (6, "AAA", "l1", "Sore Back", "RB", None, None, "Back", LTD),
    (6, "AAA", "v1", "Vet Rest", "QB", None, None, "Not injury related - resting player", DNP),
    (6, "BBB", "d1", "Doubtful End", "DE", "Doubtful", "Shoulder", "Shoulder", DNP),
])
RESERVE = pd.DataFrame([("AAA", "ir1", "Long Term", "OL", "R01"), ("AAA", "o1", "Out Corner", "CB", "R01"),
                        ("CCC", "pup", "Other Team", "TE", "R04")],
                       columns=["team", "gsis_id", "full_name", "position", "status_description_abbr"])


def test_lists_this_weeks_statuses_and_practice_limits_but_not_healthy_players():
    rep = injm.build(REPORT, RESERVE, 6, props={"q1": "rec"})
    assert rep["report_week"] == 6
    aaa = rep["teams"]["AAA"]
    assert [p["name"] for p in aaa] == ["Out Corner", "Q Receiver", "Sore Back", "Vet Rest", "Long Term"]
    q = aaa[1]
    assert (q["status"], q["practice"], q["side"], q["kind"]) == ("Questionable", "Limited", "off", "rec")
    assert aaa[0]["side"] == "def" and aaa[0]["status"] == "Out"   # on the report: not repeated from the reserve list
    assert aaa[3]["rest"] and aaa[3]["injury"] == "Rest"
    assert aaa[4]["status"] == "IR"
    assert rep["teams"]["CCC"][0]["status"] == "PUP"


def test_falls_back_to_the_last_report_until_this_weeks_is_out_and_filters_teams():
    rep = injm.build(REPORT[REPORT.week == 5], RESERVE, 6, teams={"AAA"})
    assert rep["report_week"] == 5 and set(rep["teams"]) == {"AAA"}
    assert injm.build(pd.DataFrame(), pd.DataFrame(), 6) == dict(report_week=None, teams={})
