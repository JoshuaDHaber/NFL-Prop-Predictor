"""Copy the local database into another one (e.g. a hosted Postgres):

    DATABASE_URL=postgresql://user:pass@host/db python -m app.copy_db [--from sqlite:///path/app.db] [--with-history]

or the other way, e.g. on a host whose database is a SQLite file on a volume:

    python -m app.copy_db --from postgresql://user:pass@host/db --to sqlite:////srv/backend/data/app.db

Reads the source, creates the tables in the target if needed, and replaces the target's rows, so the odds you
already paid API credits for travel with the projections. Safe to re-run.

--with-history also copies odds_history; use it to move the server's own database (the SQLite → Postgres switch).
"""
import argparse
import os
import sys

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from . import config
from .db import Base, OddsHistory, ensure_columns, make_engine

# odds_history is left out unless asked for: a copy replaces the target's rows, and the history that builds up on
# the server would be wiped by a push from a laptop that never saw those fetches.
HISTORY = {OddsHistory.__table__}
BATCH = 2000


def copy(source_url: str, target_url: str, log=print, with_history: bool = False) -> dict:
    if source_url == target_url:
        raise SystemExit("Source and target are the same database.")
    src, dst = make_engine(source_url), make_engine(target_url)
    Base.metadata.create_all(dst)
    ensure_columns(dst)
    # parents first so foreign keys are satisfied; children are cleared first for the same reason.
    tables = [t for t in Base.metadata.sorted_tables if with_history or t not in HISTORY]
    counts = {}
    with src.connect() as s, Session(dst) as d:
        for table in reversed(tables):
            d.execute(table.delete())
        for table in tables:
            n = 0
            rows = s.execute(select(table)).mappings()
            while batch := [dict(r) for r in rows.fetchmany(BATCH)]:
                d.execute(insert(table), batch)
                n += len(batch)
            counts[table.name] = n
            log(f"  {table.name}: {n} rows")
        # keep autoincrement counters ahead of the copied ids (Postgres sequences don't follow explicit ids)
        if dst.dialect.name == "postgresql":
            for table in tables:
                if "id" in table.c:
                    d.execute(text(f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                                   f"COALESCE((SELECT MAX(id) FROM {table.name}), 1))"))
        d.commit()
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", type=config.normalize_db_url, default=f"sqlite:///{os.path.join(config.BASE_DIR, 'data', 'app.db')}")
    ap.add_argument("--to", dest="target", default=None, help="defaults to $DATABASE_URL")
    ap.add_argument("--with-history", action="store_true", help="also copy odds_history (moving the server's own database)")
    a = ap.parse_args()
    target = config.normalize_db_url(a.target or os.environ.get("DATABASE_URL", ""))
    if not target or (target.startswith("sqlite") and not a.target):  # a SQLite target only when named with --to
        sys.exit("Set DATABASE_URL (or --to) to the hosted database URL.")
    print("Copying to", target.split("@")[-1])
    print(copy(a.source, target, with_history=a.with_history))
