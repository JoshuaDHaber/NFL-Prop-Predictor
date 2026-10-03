"""Copy the local database into another one (e.g. a hosted Postgres):

    DATABASE_URL=postgresql://user:pass@host/db python -m app.copy_db [--from sqlite:///path/app.db]

Reads the source, creates the tables in the target if needed, and replaces the target's rows, so the odds you
already paid API credits for travel with the projections. Safe to re-run.
"""
import argparse
import os
import sys

from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from . import config
from .db import AltLine, Base, OddsLine, Projection, Run, ensure_columns, make_engine

# parents first so foreign keys are satisfied; children are cleared first for the same reason
TABLES = [Run, Projection, OddsLine, AltLine]


def copy(source_url: str, target_url: str, log=print) -> dict:
    if source_url == target_url:
        raise SystemExit("Source and target are the same database.")
    src, dst = make_engine(source_url), make_engine(target_url)
    Base.metadata.create_all(dst)
    ensure_columns(dst)
    counts = {}
    with Session(src) as s, Session(dst) as d:
        for model in reversed(TABLES):
            d.execute(model.__table__.delete())
        for model in TABLES:
            rows = [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in s.query(model).all()]
            for i in range(0, len(rows), 2000):
                d.execute(insert(model.__table__), rows[i:i + 2000])
            counts[model.__tablename__] = len(rows)
            log(f"  {model.__tablename__}: {len(rows)} rows")
        # keep autoincrement counters ahead of the copied ids (Postgres sequences don't follow explicit ids)
        if dst.dialect.name == "postgresql":
            for model in TABLES:
                t = model.__tablename__
                d.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 1))"))
        d.commit()
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", default=f"sqlite:///{os.path.join(config.BASE_DIR, 'data', 'app.db')}")
    ap.add_argument("--to", dest="target", default=None, help="defaults to $DATABASE_URL")
    a = ap.parse_args()
    target = config.normalize_db_url(a.target or os.environ.get("DATABASE_URL", ""))
    if not target or target.startswith("sqlite"):
        sys.exit("Set DATABASE_URL (or --to) to the hosted database URL.")
    print("Copying to", target.split("@")[-1])
    print(copy(a.source, target))
