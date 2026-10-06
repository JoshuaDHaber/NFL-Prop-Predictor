"""Run the pipeline without the web app:  python -m app.cli [--odds none|missing|all] [--exclude "Name" ...]"""
import argparse

from . import pipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds", choices=["none", "missing", "thin", "all"], default="missing")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="NAME")
    ap.add_argument("--keep-dnp", action="store_true")
    ap.add_argument("--full", action="store_true", help="refit the calibration instead of reusing the saved one")
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    a = ap.parse_args()
    pipeline.run_projections(exclude=a.exclude, keep_dnp=a.keep_dnp, season=a.season, week=a.week, full=a.full)
    pipeline.refresh_odds(a.odds)


if __name__ == "__main__":
    main()
