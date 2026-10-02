# NFL rush/receiving yard prop model

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py                       # projections only
ODDS_API_KEY=... .venv/bin/python run.py      # + live lines from The Odds API -> ranked picks
.venv/bin/python run.py --lines-csv lines.csv # manual lines: player,market(rush|rec),line,over_odds,under_odds,book
.venv/bin/python run.py --demo-lines          # synthetic lines, to preview the report layout
```
Open `report.html`. Data (nflverse) is cached in `.cache/`. Tunables are constants at the top of `model.py` and `run.py`.

Put your key in `.env` (`ODDS_API_KEY=...`); `run.py` loads it automatically. `.env` is git-ignored.

`--cached-odds` re-runs the model on the last fetched odds without spending API credits (every normal run with a key saves them to `.cache/odds_latest.csv`).
