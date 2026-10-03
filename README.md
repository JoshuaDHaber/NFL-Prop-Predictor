# NFL Prop Predictor

A full-stack web app that projects NFL player yardage, prices the projections against live sportsbook prop lines, and ranks the best bets of the week.

**Markets:** rushing yards, receiving yards, passing yards, and rush + receiving yards.

- **Front end:** React + TypeScript (Vite, TanStack Query, Recharts).
- **Back end:** FastAPI + SQLAlchemy (SQLite locally, Postgres-ready).
- **Model:** pandas / SciPy projection engine with a walk-forward backtest.
- **Data:** [nflverse](https://github.com/nflverse/nflverse-data) for stats, schedules, rosters and injuries; [The Odds API](https://the-odds-api.com) for prop lines.

> A modeling and software project, not betting advice. See [Limitations](#limitations).

## What the app does

- **Best props:** every Over/Under quote is priced and ranked by expected value, using the best price across sportsbooks. Filter by market, game and sportsbook (a book filter shows only that book's lines, still priced against the all-book market consensus, and carries into the player drawer's chart and line table), search by player, and adjust **minimum EV** and **how much to trust the market** with sliders that re-price the board live.
- **Player drawer:** click any row for the last 12 games charted against the projection and the posted lines, plus every available play for that player.
- **Alternate lines:** in the drawer, a ladder shows every posted line, main and alternate, across books, priced with the model's own win probability and EV. *Load alternate lines* fetches them for that player's game on demand (about 2 API credits per stat) and also attaches sportsbook betslip links.
- **Betslip:** tap **+** on any quote to build a slip (saved in your browser). Each leg has a book switcher that lists every sportsbook offering that exact line, and "Put every leg at one book" moves the whole slip to a single book (showing how many legs it can take) so a parlay stays consistent. When that book doesn't offer a leg's exact line, the slip suggests the nearest lines the book does offer, with prices and EV, and one click swaps the leg. Selections are grouped by sportsbook with per-book parlay odds and payout, a stake box, and **Copy slip link**, which copies the same link "Open all in one tab" opens (a bare URL for one book, labelled per book otherwise) so you can open the slip on another device; **Copy phone link** copies a link that reopens the whole slip in this app on another device (the slip travels in the URL, nothing is stored on a server); tap each leg's button, or "Open all in one tab", on the phone to hand it to the sportsbook app. **Copy as text** copies a readable summary instead. **Get links** fetches missing betslip links for the slip's games on demand, **Open all in one tab** builds a single link that adds every linked leg to the slip for FanDuel and DraftKings (experimental: those multi-selection link formats are not yet confirmed against the live sites, so check the slip afterward), and each book's **Add leg N of M** button steps through its legs one new tab per click (browsers block extra pop-ups from a single click), skipping legs that have no link. **Add at book** opens the sportsbook with that selection added to its betslip where the Odds API provides a direct link (FanDuel and DraftKings do), and otherwise opens the book. The app never places bets; you sign in and confirm at the book.
- **Projections:** every projected player with the volume and efficiency behind the number, sortable.
- **Model check:** backtest accuracy per market and the freshness of projections and odds.
- **Refresh from the UI:** recompute projections and fetch odds (projections only, missing markets only, or everything) with live job status. Odds are stored in the database, so re-running the model never spends API credits.

## Architecture

```
┌────────────┐  /api   ┌──────────────────────────────┐        ┌────────────┐
│ React SPA  │ ──────▶ │ FastAPI                      │ ─────▶ │ nflverse   │ stats, schedule,
│ (Vite, TS) │ ◀────── │  routes · job runner         │        │ (CSV)      │ rosters, injuries
└────────────┘  JSON   │  engine/ model · picks · odds│ ─────▶ ├────────────┤
                       └──────────────┬───────────────┘        │ Odds API   │ prop lines
                                      │ SQLAlchemy             └────────────┘
                              ┌───────▼────────┐
                              │ SQLite/Postgres│ runs · projections · odds_lines
                              └────────────────┘
```

- **Pipeline** (`pipeline.py`): loads data, runs the backtest, projects the next unplayed week, applies injury and roster filters, and stores a `Run` with its projections. Odds are fetched separately and stored with a fetch timestamp.
- **Pricing is computed on request** (`engine/picks.py`), not stored, so the UI's sliders can re-price instantly. Results are memoized per (run, odds version, market weight).
- **Refresh jobs** run in a background task with a single-flight lock; the UI polls `/api/refresh/status`.
- In production the API serves the built React app, so it deploys as one container.

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/meta` | Current run, backtest stats, odds freshness, game list, refresh job state |
| `GET /api/picks` | Priced plays. Params: `kind`, `game_id`, `q`, `min_ev`, `market_weight`, `book`, `include_flagged`, `limit` |
| `GET /api/projections` | Projections. Params: `kind`, `game_id`, `q` |
| `GET /api/players/{id}` | One player: projections, available plays, recent game logs |
| `GET /api/players/{id}/lines?kind=` | Every main and alternate quote for one player and market, priced, with betslip links |
| `POST /api/players/{id}/alt-lines` | Fetch alternate lines and links for the player's game (spends API credits) |
| `POST /api/refresh` | Start a refresh. Body `{"odds": "none" \| "missing" \| "all"}`; `409` if one is running |
| `GET /api/refresh/status` | Progress log of the current or last refresh |

Interactive docs are at `/docs` when the API is running.

## The model

### Projection

Yards = **volume x efficiency**:

| Market | Volume | Efficiency |
|---|---|---|
| Rushing | carries | yards per carry |
| Receiving | targets | yards per target |
| Passing | pass attempts | yards per attempt |
| Rush + Receiving | both volumes, summed | summed projections |

- **Recency weighting:** exponential decay (5-game half-life) across seasons, so recent games dominate while last year anchors small samples.
- **Shrinkage:** efficiency is pulled toward the position mean with a pseudo-count prior, because yards per attempt is noisy. Volume is shrunk only lightly (and not at all for most quarterback volume), since roles are stable.
- **Opponent and game script:** a shrunk yards-allowed factor for the defense, and a point-spread nudge (favorites run more, underdogs pass more).
- **Availability:** the active roster decides a player's team. Injured reserve, Out/Doubtful, players with no practice and no game status, and offseason arrivals with no games for their new team are excluded.

### Probabilities and EV

Outcomes follow a gamma distribution (non-negative, right-skewed) whose variance `a*mu + b*mu^2` is fit on the walk-forward backtest residuals. Whole-number lines handle pushes. The model's win probability is blended (35% by default, adjustable in the UI) with the market's no-vig probability. EV and quarter-Kelly come from that blend and the best available price.

Two guards keep bad data from topping the board:
- Quotes far from the multi-book consensus line (stale or alternate lines) are ignored.
- Plays where model and market disagree by more than ~40-67% are hidden by default and tagged "large gap". These are usually model blind spots (a teammate's injury, a role change), not value.

### Backtest

Walk-forward: every game from 2025 week 6 onward is projected using only earlier data, compared with a naive last-5-games average.

| Market | Games | Model MAE | Last-5 MAE | Bias |
|---|---|---|---|---|
| Rushing | 1,002 | 23.2 | 25.1 | +2.1 |
| Receiving | 1,866 | 23.4 | 24.8 | +0.4 |
| Passing | 489 | 67.0 | 70.4 | +0.6 |
| Rush + Rec | 234 | 33.0 | 36.6 | +4.0 |

MAE is mean absolute error in yards; bias is the mean of (actual - projection). The passing market initially ran ~9 yards low because volume shrinkage pulled quarterback attempts toward zero; a per-market setting fixed it.

## Running it

Requires Python 3.9+ and Node 20+. Everything goes through one script:

```bash
./run.sh setup      # venv + npm install; creates backend/.env (add ODDS_API_KEY there, optional)
./run.sh refresh    # compute this week's projections (about a minute the first time)
./run.sh start      # app at http://localhost:8000 (API + built UI)
```

`./run.sh lan` starts the app so your phone on the same Wi-Fi can open it (other devices are read-only: refreshes and API-credit-spending fetches stay limited to this machine). Other commands: `./run.sh dev` (API with auto-reload plus the Vite dev server on :5173), `./run.sh build`, `./run.sh test`, and `./run.sh refresh --odds none --exclude "Player Name"`. Run `./run.sh help` for the list.

**Odds:** get a free key at [the-odds-api.com](https://the-odds-api.com) (about 500 credits a month; all four markets for a full slate cost roughly 60) and put it in `backend/.env`. Without a key the app still shows projections. In the UI, *Refresh data* fetches only markets that have no stored lines; *Re-fetch all odds* is the explicit paid action.

**Tests and CI:** `./run.sh test` runs the backend suite (pytest: model math, pricing logic, API behavior) and the frontend typecheck and tests. GitHub Actions runs the same on every push.

**Docker** (untested so far): `docker build -t nfl-props . && docker run -p 8000:8000 -v nfl-data:/srv/backend/data nfl-props`. Set `DATABASE_URL` to a Postgres URL (and add a driver such as `psycopg`) when deploying beyond one instance.

## Using it from your phone anywhere (Tailscale, free)

[Tailscale](https://tailscale.com) is a free private network between your own devices, so your phone can reach the app on your Mac from any network without hosting anything.

1. Install Tailscale on the Mac and on the phone ([tailscale.com/download](https://tailscale.com/download)) and sign in to the same account on both.
2. On the Mac, run `./run.sh lan`. It prints a Tailscale address like `http://100.x.y.z:8000`.
3. Open that address on the phone. The share links the app copies ("Copy phone link") use the Tailscale address automatically, so they work away from home too.

To use a Tailscale MagicDNS name instead of the numeric address, set `APP_URL=http://your-mac.your-tailnet.ts.net:8000` in `backend/.env`. The Mac must be awake and running the app. Other devices are read-only.

## Project layout

```
backend/
  app/
    main.py        FastAPI routes, job runner, static file serving
    pipeline.py    data -> backtest -> projections -> DB; odds refresh
    db.py          SQLAlchemy models (runs, projections, odds_lines, alt_lines)
    schemas.py     Pydantic response models
    cli.py         run the pipeline without the web app
    engine/        model.py (projections, backtest, probabilities) · picks.py (pricing) · ladder.py (alt-line pricing) · odds.py · data.py
  tests/           pytest suite
frontend/src/      App, components (picks table, player drawer, line ladder, betslip, controls, refresh), betslip math in slip.ts, typed API client
```

## Limitations

- **The backtest has no historical odds,** so it validates accuracy, not profitability. Sportsbook prop markets are efficient; a large apparent edge usually means the model is missing context.
- **No teammate redistribution:** when a starter is out, his volume is not moved to backups, so backups are under-projected. This is the biggest known accuracy gap.
- **Heuristic adjustments:** opponent and game-script effects are reasonable but untuned.
- **Rush + Rec** treats its two parts as independent, though they are often negatively correlated.
- **Early-season samples are small;** projections lean on last season until enough of this one is played.
- **Injury data is only as fresh as the nflverse feed.** Check game-day statuses before relying on a pick.
- Parameters were tuned on the same games used to report accuracy, so the backtest is somewhat optimistic.

## Roadmap

- Redistribute volume to teammates when a starter is out.
- Model team-level pass/run volume explicitly, then split it among players.
- Weather, pace and offensive-line context.
- Store pick history and track closing-line value as an out-of-sample test.
- Scheduled refreshes, auth for a shared deployment, more markets (receptions, attempts, touchdowns).
- Multi-leg deep links per sportsbook (today each selection opens as its own link) and correlation-aware same-game parlay pricing.
