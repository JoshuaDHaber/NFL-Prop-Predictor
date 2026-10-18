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


ESPN = pd.DataFrame([
    ("e-q1", "Q Receiver", "AAA", "WR", "Questionable", "Ankle", "Limited in practice again Friday.", "2026-10-18", "2026-10-17T01:00Z"),
    ("e-l1", "Sore Back", "AAA", "RB", "Out", "Back", "Ruled out Saturday.", "2026-10-25", "2026-10-18T01:00Z"),
    ("e-ir1", "Long Term", "AAA", "OL", "Injured Reserve", "Knee", "inactive", "2027-09-01", None),
    ("e-new", "New Name", "BBB", "S", "Out", "Hamstring", "Won't play Sunday.", None, None),
    ("e-act", "Just News", "BBB", "RB", "Active", "", "Elevated from the practice squad.", None, None),
    (None, "Doubtful End", "BBB", "DE", "Active", "", "Expected to sit out Sunday.", None, None),
], columns=["espn_id", "name", "team", "pos", "status", "injury", "comment", "return_date", "updated"])
IDS = {"e-q1": "q1", "e-l1": "l1", "e-ir1": "ir1"}


def test_espn_adds_news_and_fills_statuses_nflverse_lacks():
    rep = injm.build(REPORT, RESERVE, 6, espn=ESPN, espn_ids=IDS)
    aaa = {p["player_id"]: p for p in rep["teams"]["AAA"]}
    assert (aaa["q1"]["status"], aaa["q1"]["comment"], aaa["q1"]["return_date"]) == ("Questionable", "Limited in practice again Friday.", "2026-10-18")
    assert aaa["l1"]["status"] == "Out" and aaa["l1"]["practice"] == "Limited"   # practice-only listing gets ESPN's status
    assert aaa["ir1"]["status"] == "IR" and aaa["ir1"]["injury"] == "Knee"
    assert aaa["ir1"]["comment"] == ""                                              # a one-word note repeats the badge
    bbb = {p["name"]: p for p in rep["teams"]["BBB"]}
    assert bbb["New Name"]["status"] == "Out" and bbb["New Name"]["player_id"] == "espn:e-new"
    assert "Just News" not in bbb                                                   # news alone doesn't list a player
    assert bbb["Doubtful End"]["status"] == "Doubtful" and bbb["Doubtful End"]["comment"] == "Expected to sit out Sunday."  # matched by name
    assert [p["name"] for p in rep["teams"]["AAA"]][:2] == ["Out Corner", "Sore Back"]   # re-sorted with the new status


def test_espn_status_replaces_last_weeks_report():
    rep = injm.build(REPORT[REPORT.week == 5], RESERVE, 6, espn=ESPN.assign(name="Last Week", espn_id=None).head(1))
    p = next(p for p in rep["teams"]["AAA"] if p["player_id"] == "old")
    assert (p["status"], p["practice"], p["comment"]) == ("Questionable", "", "Limited in practice again Friday.")
