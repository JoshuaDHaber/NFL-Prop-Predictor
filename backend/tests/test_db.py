from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import OddsLine, make_engine


def test_sqlite_file_uses_wal_so_reads_continue_during_a_sync(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/app.db")
    with eng.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    writer, reader = Session(eng), Session(eng)
    writer.add(OddsLine(fetched_at=datetime(2026, 10, 13), player="A", market="rush", line=1.5, book="B"))
    writer.flush()  # a write transaction is open, as during a refresh
    assert reader.scalars(select(OddsLine)).all() == []  # the reader isn't blocked and sees the last committed state
    writer.commit()
    reader.close()
    with Session(eng) as s:
        assert len(s.scalars(select(OddsLine)).all()) == 1


def test_postgres_stores_nan_in_json_as_null():
    from app.db import _json_dumps
    assert _json_dumps({"a": float("nan"), "b": [1.5, float("inf")], "c": "NaN"}) == '{"a": null, "b": [1.5, null], "c": "NaN"}'
