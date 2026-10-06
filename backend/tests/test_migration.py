"""Adding game_id to a database that already holds odds: tag the old quotes once, with the week they belong to."""
import sqlite3
from datetime import datetime

from sqlalchemy.orm import Session

from app.db import AltLine, Base, OddsLine, Projection, Run, make_engine

OLD_ODDS_TABLE = """CREATE TABLE odds_lines (id INTEGER PRIMARY KEY, fetched_at DATETIME, player VARCHAR(80), market VARCHAR(6),
    line FLOAT, over_odds FLOAT, under_odds FLOAT, book VARCHAR(40), over_link VARCHAR(500), under_link VARCHAR(500), event_link VARCHAR(500))"""


def old_database(path):
    """A database as it was before game_id existed: odds_lines has no such column."""
    url = f"sqlite:///{path}"
    eng = make_engine(f"sqlite:///{path}.scratch")             # throwaway engine just to create the other tables
    Base.metadata.create_all(eng, tables=[Run.__table__, Projection.__table__, AltLine.__table__])
    eng.dispose()
    import shutil
    shutil.move(f"{path}.scratch", path)
    con = sqlite3.connect(path)
    con.execute("DROP TABLE IF EXISTS odds_lines")
    con.execute(OLD_ODDS_TABLE)
    con.commit()
    return url, con


def add_run(url, game_id, gameday, name="Marvin Harrison Jr."):
    from sqlalchemy import create_engine
    eng = create_engine(url)                                          # plain engine: opening it must not run the migration
    with Session(eng) as s:
        run = Run(season=2026, week=4, backtest={}, variance={}, excluded=[])
        run.projections.append(Projection(player_id="x", name=name, pos="WR", team="T", opp="O", home=True, kind="rec", mu=1.0, sd=1.0,
                                          vol=1.0, eff=1.0, spread=0.0, game_id=game_id, gameday=gameday, last5=[]))
        s.add(run)
        s.commit()
    eng.dispose()


def quote(con, player, fetched):
    con.execute("INSERT INTO odds_lines (fetched_at, player, market, line, over_odds, under_odds, book) VALUES (?,?,?,?,?,?,?)",
                (fetched, player, "rec", 50.5, -110, -110, "X"))


def test_each_old_quote_is_tagged_with_the_game_that_was_upcoming_when_it_was_fetched(tmp_path):
    url, con = old_database(str(tmp_path / "old.db"))
    add_run(url, "2026_04_AAA_BBB", "2026-10-04")                          # last week's run...
    add_run(url, "2026_05_CCC_DDD", "2026-10-11")                          # ...and this week's, already the newest
    quote(con, "Marvin Harrison", "2026-10-03 12:00:00")                   # fetched before the Oct 4 game: that game
    quote(con, "Marvin Harrison", "2026-10-06 12:00:00")                   # fetched after it: the Oct 11 game
    quote(con, "Someone Unprojected", "2026-10-03 12:00:00")               # no projection anywhere: stays untagged
    con.commit(); con.close()

    eng = make_engine(url)                                                # opening the database runs the migration
    with Session(eng) as s:
        rows = sorted((str(r.fetched_at.date()), r.player, r.game_id) for r in s.query(OddsLine))
        assert rows == [("2026-10-03", "Marvin Harrison", "2026_04_AAA_BBB"), ("2026-10-03", "Someone Unprojected", None),
                        ("2026-10-06", "Marvin Harrison", "2026_05_CCC_DDD")]
    eng.dispose()

    add_run(url, "2026_06_EEE_FFF", "2026-10-18")                          # a later week arrives and the app restarts
    eng = make_engine(url)
    with Session(eng) as s:
        assert sorted(r.game_id for r in s.query(OddsLine) if r.game_id) == ["2026_04_AAA_BBB", "2026_05_CCC_DDD"]   # nothing is re-tagged
