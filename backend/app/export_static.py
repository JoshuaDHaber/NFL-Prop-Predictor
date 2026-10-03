"""Export the current data as static JSON for the GitHub Pages demo:  python -m app.export_static [--out DIR]

Everything the API would return (at its default settings) is written as files the React app can fetch
without a server: meta, projections, priced picks per sportsbook, every player's detail and line ladder.
"""
import argparse
import json
import os
import re
from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import select

from .db import Projection, SessionLocal
from .main import all_picks, build_ladder_out, build_meta, build_player_detail, latest_run
from .schemas import PickOut

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "public", "demo")
MARKET_WEIGHT = 0.35


def slug(name: str) -> str:
    """File-name-safe sportsbook name; the front end applies the same rule."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name)


def _write(path: str, obj) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    with open(path, "w") as f:
        f.write(text)
    return len(text)


def export(out: str) -> dict:
    with SessionLocal() as db:
        run = latest_run(db)
        if not run:
            raise SystemExit("No projections yet: run ./run.sh refresh first.")
        meta = build_meta(db, None)
        meta.has_odds_key, meta.snapshot_at = False, datetime.utcnow().isoformat()
        meta_dict = json.loads(meta.model_dump_json())
        meta_dict["job"] = dict(state="idle", started_at=None, finished_at=None, log=[], error=None)
        total = _write(os.path.join(out, "meta.json"), meta_dict)

        projs = db.scalars(select(Projection).where(Projection.run_id == run.id).order_by(Projection.mu.desc())).all()
        from .schemas import ProjectionOut
        total += _write(os.path.join(out, "projections.json"),
                        TypeAdapter(list[ProjectionOut]).dump_json([ProjectionOut.model_validate(p, from_attributes=True) for p in projs]).decode())

        adapter = TypeAdapter(list[PickOut])
        for book in [None, *meta.books]:
            df = all_picks(db, run, MARKET_WEIGHT, book)
            rows = [PickOut(**r) for r in df.where(df.notna(), None).to_dict("records")] if not df.empty else []
            total += _write(os.path.join(out, "picks", f"{slug(book) if book else 'all'}.json"), adapter.dump_json(rows).decode())

        players = {p.player_id for p in projs}
        for pid in sorted(players):
            detail = build_player_detail(db, run, pid, MARKET_WEIGHT)
            total += _write(os.path.join(out, "players", f"{pid}.json"), detail.model_dump_json())
        for p in projs:
            total += _write(os.path.join(out, "ladders", f"{p.player_id}_{p.kind}.json"), build_ladder_out(db, p, 0).model_dump_json())
    return dict(players=len(players), projections=len(projs), bytes=total, out=out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    print(export(a.out))
