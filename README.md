# NFL Prop Predictor

A Python pipeline that projects NFL player yardage, compares those projections to live sportsbook prop lines, and publishes a ranked, filterable HTML report of the best bets of the week.

**Markets covered:** rushing yards, receiving yards, passing yards, and rush + receiving yards.

Each run does the following:

1. Pulls play-by-play-derived weekly player stats, schedules, rosters and injury reports from [nflverse](https://github.com/nflverse/nflverse-data).
2. Projects every relevant player in the upcoming week's games.
3. Backtests the model on past games, then uses the backtest residuals to fit the model's uncertainty.
4. Fetches player-prop lines from [The Odds API](https://the-odds-api.com).
5. Converts each projection into a win probability, compares it to the market price, and ranks plays by expected value.
6. Writes a single self-contained `report.html` (no server required).

> This is a modeling and software project, not betting advice. See [Limitations](#limitations).

## The report

`report.html` has:

- **Best props**: ranked by expected value, with the pick (Over/Under, line, price, sportsbook), projection and standard deviation, edge in yards, model vs. market win probability, EV, quarter-Kelly stake and a last-5-games sparkline.
- **All projections**: every player's projected yards, with the volume and efficiency behind the number.
- **Filters**: tabs by market (Rushing / Receiving / Passing / Rush+Rec) plus a dropdown to filter by game. Tables are sortable.
- **Model check**: the backtest accuracy for each market, shown on the page so the numbers can be judged against the picks.
- Light and dark themes, and a layout that works on a phone.

## How the model works

### Projection

For each player and market, projected yards are **volume x efficiency**:

| Market | Volume | Efficiency |
|---|---|---|
| Rushing | carries | yards per carry |
| Receiving | targets | yards per target |
| Passing | pass attempts | yards per attempt |
| Rush + Receiving | rushing + receiving volume, summed | summed projections |

- **Recency weighting.** Games are weighted with an exponential decay (5-game half-life) that runs across seasons, so the recent past dominates but last year still anchors small samples.
- **Shrinkage.** Efficiency is shrunk toward the position average with a pseudo-count prior (e.g. 40 carries, 30 targets, 120 pass attempts), because yards per attempt is noisy over short stretches. Volume is shrunk much more lightly, since a player's role is far more stable than his efficiency.
- **Opponent adjustment.** Each defense gets a yards-allowed-per-game factor against the league average, shrunk toward neutral and applied at half strength.
- **Game script.** The point spread nudges volume: favorites run more, underdogs pass more.
- **Availability.** The active roster decides which team a player is on. Players on injured reserve or practice squads, players ruled Out or Doubtful, players who didn't practice with no game status posted yet, and offseason arrivals with no games for their new team are all excluded. Anyone can be excluded by hand with `--exclude`.

### Uncertainty and probabilities

Yardage outcomes are modeled with a **gamma distribution** (non-negative and right-skewed, like real yardage). Its variance follows `var = a*mu + b*mu^2`, with `a` and `b` fit by least squares on the squared residuals of a **walk-forward backtest**: every historical game is projected using only data available before kickoff. Whole-number lines use a continuity correction and account for pushes.

The model's win probability is blended 35% toward the market's no-vig probability, a guard against the model overstating its edge. Expected value and a quarter-Kelly stake come from that blended probability and the best available price across sportsbooks.

### Backtest results

Walk-forward, using only prior data for each game (2025 week 6 through the current week), against a naive average of the player's last 5 games:

| Market | Games | Model MAE | Last-5 MAE | Bias |
|---|---|---|---|---|
| Rushing | 1,002 | 23.2 | 25.1 | +2.1 |
| Receiving | 1,866 | 23.4 | 24.8 | +0.4 |
| Passing | 489 | 67.0 | 70.4 | +0.6 |
| Rush + Rec | 234 | 33.0 | 36.6 | +4.0 |

MAE is mean absolute error in yards; bias is the average of (actual - projection), so near zero means the model is well calibrated overall. The model beats the naive baseline in every market.

Passing initially ran about 9 yards low. Diagnosing it showed the cause was volume shrinkage pulling quarterback attempts toward zero, which is wrong for a stat that stable. A separate setting for passing removed the bias.

## Quick start

Requires Python 3.9+.

```bash
git clone https://github.com/JoshuaDHaber/NFL-Prop-Predictor.git
cd NFL-Prop-Predictor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python run.py                       # projections only (no odds needed)
```

Open `report.html` in a browser.

### Adding odds

Get a free key at [the-odds-api.com](https://the-odds-api.com) (about 500 credits a month; a full slate across all four markets costs roughly 60 credits). Save it in a `.env` file, which is git-ignored:

```
ODDS_API_KEY=your_key_here
```

```bash
.venv/bin/python run.py                         # fetch live odds, rank picks
.venv/bin/python run.py --cached-odds           # reuse the last fetch, spend no credits
.venv/bin/python run.py --lines-csv lines.csv   # bring your own lines
.venv/bin/python run.py --demo-lines            # synthetic lines, to preview the report
```

Fetched odds are saved to `.cache/`. With `--cached-odds`, only markets missing from the cache are fetched.

A CSV of your own lines needs the columns `player, market, line, over_odds, under_odds, book`, where `market` is `rush`, `rec`, `pass` or `rr` and odds are American.

### Other options

```bash
--week 5 --season 2026               # a specific week (default: next unplayed week)
--exclude "Player Name" ...          # drop players you know are out
--keep-dnp                           # keep players who did not practice and have no game status
--min-ev 0.05                        # EV threshold for picks (default 3%)
--market-weight 0.5                  # how much to trust the market vs. the model (default 0.35)
--out my_report.html
```

Tunable model constants (half-life, shrinkage strengths, opponent and script effects) sit at the top of `model.py`.

## Project layout

```
run.py       CLI entry point: orchestrates data, backtest, projections, odds, picks
data.py      nflverse loaders with on-disk caching (stats, schedule, rosters, injuries)
model.py     projection, opponent/script adjustments, walk-forward backtest, variance fit, probabilities
odds.py      The Odds API client, CSV import, name matching, odds math
report.py    self-contained HTML report (inline CSS/JS, sortable tables, filters)
```

## Limitations

- **There is no historical odds data in the backtest.** Accuracy is measured against actual results, so the model's calibration is tested but its profitability is not. A positive-EV pick is only as good as the model, and sportsbook prop markets are efficient. Large apparent edges usually mean the model is missing something.
- **No teammate redistribution.** When a starter is out, the model does not move his volume to teammates, so backups are under-projected.
- **Heuristic adjustments.** The opponent and game-script effects are reasonable but untuned, and opponent strength uses raw yards allowed without adjusting for who each defense has played.
- **Rush + Rec treats the two parts as independent**, though they are often negatively correlated. The real spread is somewhat narrower than the model assumes.
- **Small sample early in the season.** Projections lean on last season's games until enough of this year has been played.
- **Injury data is only as fresh as the nflverse feed.** Check final game-day statuses before relying on a pick.
- Parameters, including the passing fix, were tuned against the same games used to report accuracy, so the backtest numbers are somewhat optimistic.

## Ideas for next steps

- Redistribute volume to teammates when a starter is out.
- Model team-level pass/run volume explicitly, then split it among players.
- Add weather, pace and offensive line context.
- Track picks over time against closing lines (closing line value) as an out-of-sample test of the model.
- More markets: receptions, rushing attempts, longest reception, touchdowns.

## Data and credits

Player, schedule, roster and injury data come from [nflverse](https://github.com/nflverse), and prop lines from [The Odds API](https://the-odds-api.com).
