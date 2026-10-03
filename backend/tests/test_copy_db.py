from datetime import datetime

from sqlalchemy.orm import Session

from app.copy_db import copy
from app.db import AltLine, OddsLine, Projection, Run, make_engine


def _seed(url):
    eng = make_engine(url)
    with Session(eng) as s:
        run = Run(season=2026, week=4, backtest={"rush": {"n": 1}}, variance={"rush": [1, 0.1]}, excluded=["X"])
        run.projections.append(Projection(player_id="p", name="A", pos="RB", team="T", opp="O", home=True, kind="rush", mu=1.0, sd=2.0,
                                          vol=3.0, eff=4.0, spread=0.0, game_id="g", gameday="d", last5=[1.0]))
        s.add(run)
        s.add(OddsLine(fetched_at=datetime(2026, 10, 3), player="A", market="rush", line=1.5, over_odds=-110, under_odds=-110,
                       book="B", over_link="https://x"))
        s.add(AltLine(fetched_at=datetime(2026, 10, 3), game_id="g", player="A", market="rush", line=2.5, over_odds=300, book="B"))
        s.commit()
    return eng


def test_copy_moves_every_table_and_replaces_the_target(tmp_path):
    src, dst = f"sqlite:///{tmp_path}/src.db", f"sqlite:///{tmp_path}/dst.db"
    _seed(src)
    stale = make_engine(dst)
    with Session(stale) as s:  # something old in the target that must not survive
        s.add(OddsLine(fetched_at=datetime(2020, 1, 1), player="Old", market="rush", line=9.5, book="Z"))
        s.commit()
    counts = copy(src, dst, log=lambda m: None)
    assert counts == {"runs": 1, "projections": 1, "odds_lines": 1, "alt_lines": 1}
    with Session(make_engine(dst)) as s:
        assert s.query(OddsLine).one().player == "A" and s.query(OddsLine).one().over_link == "https://x"
        assert s.query(Run).one().excluded == ["X"] and s.query(Projection).one().last5 == [1.0]
        assert s.query(AltLine).one().over_odds == 300


def test_copy_refuses_to_copy_a_database_onto_itself(tmp_path):
    import pytest
    url = f"sqlite:///{tmp_path}/a.db"
    _seed(url)
    with pytest.raises(SystemExit):
        copy(url, url)
