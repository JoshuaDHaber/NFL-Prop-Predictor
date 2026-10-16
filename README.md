# NFL Prop Predictor

A full-stack web app that projects NFL player yardage, prices the projections against live sportsbook prop lines, and ranks the best bets of the week.

**Markets:** rushing yards, receiving yards, passing yards, rush + receiving yards, receptions, anytime touchdown, and team moneyline (each team's chance to win).

- **Front end:** React + TypeScript (Vite, TanStack Query, Recharts).
- **Back end:** FastAPI + SQLAlchemy (SQLite locally, Postgres-ready).
- **Model:** pandas / SciPy projection engine with a walk-forward backtest.
- **Data:** [nflverse](https://github.com/nflverse/nflverse-data) for stats, schedules (with game-time weather), rosters and injuries; [The Odds API](https://the-odds-api.com) for prop lines; [Open-Meteo](https://open-meteo.com) (free, no key) for kickoff forecasts at outdoor stadiums.

> A modeling and software project, not betting advice. See [Limitations](#limitations).

**NBA too.** A switch at the top of the page (🏈 NFL / 🏀 NBA, remembered in your browser) flips the whole site to the NBA: see [NBA](#nba).

## What the app does

- **Games** (the first tab): a tile for every game on the slate with kickoff, weather, both teams' logos and win chances (a bar in the teams' colors) and the spread, the top prop and how many props are +EV, and the injury count. Click a tile for that game's page: weather, the moneyline card (each team's chance to win from the model, the market and the blend, with the best price; this replaced the old Moneyline tab), its best props, parlays built from that game only, projections and both injury reports, all at one sportsbook picked at the top of the page (FanDuel by default; the choice is remembered in your browser and carries into the player drawer), so one page covers what used to take several tabs. The page has its own link (`#game=<game_id>`) and the browser's back button returns to the slate.
- **Best props:** every Over/Under quote is priced and ranked by expected value, using the best price across sportsbooks. Filter by market, over/under ("Overs", "Unders"; "Anytime TD"/"No TD" on the TD tab), game and sportsbook (a book filter shows only that book's lines, still priced against the all-book market consensus, and carries into the player drawer's chart and line table), search by player, and adjust **minimum EV** and **how much to trust the market** with sliders that re-price the board live.
- **Player drawer:** click any row for the last 12 games charted against the projection and the posted lines, plus every available play for that player.
- **Alternate lines:** in the drawer, a ladder shows every posted line, main and alternate, across books, priced with the model's own win probability and EV. Refreshing odds fetches main and alternate lines for every game of the week (one API call per game, one credit per market, about 5 credits per game for alternates), so they're available by default. A "−300 to +300" toggle (on by default) hides prices outside that range, such as -2500 locks and +3900 longshots. *Load alternate lines* remains as a one-game fallback.
- **Betslip:** tap **+** on any quote to build a slip (saved in your browser). Each leg has a book switcher that lists every sportsbook offering that exact line, and "Put every leg at one book" moves the whole slip to a single book (showing how many legs it can take) so a parlay stays consistent. When that book doesn't offer a leg's exact line, the slip suggests the nearest lines the book does offer, with prices and EV, and one click swaps the leg. Selections are grouped by sportsbook with per-book parlay odds and payout, a stake box, and **Copy slip link**, which copies the same link "Open all in one tab" opens (a bare URL for one book, labelled per book otherwise) so you can open the slip on another device; **Copy phone link** copies a link that reopens the whole slip in this app on another device (the slip travels in the URL, nothing is stored on a server); tap each leg's button, or "Open all in one tab", on the phone to hand it to the sportsbook app. **Copy as text** copies a readable summary instead. **Get links** fetches missing betslip links for the slip's games on demand, **Open all in one tab** builds a single link that adds every linked leg to the slip for FanDuel and DraftKings (experimental: those multi-selection link formats are not yet confirmed against the live sites, so check the slip afterward), and each book's **Add leg N of M** button steps through its legs one new tab per click (browsers block extra pop-ups from a single click), skipping legs that have no link. **Add at book** opens the sportsbook with that selection added to its betslip where the Odds API provides a direct link (FanDuel and DraftKings do), and otherwise opens the book. The app never places bets; you sign in and confirm at the book.
- **Injuries:** every game of the week with both teams' injury report, offense and defense: who's ruled Out, Doubtful or Questionable, who is practicing limited or not at all with no game status yet (veterans' rest days are marked as such), and, behind a toggle, who's on IR or PUP. Before the week's report is out (teams start reporting Wednesday) it shows last week's final statuses and says so. Players the app projects link to their drawer.
- **Projections:** every projected player with the volume and efficiency behind the number, sortable.
- **Weather:** outdoor games show the kickoff forecast; rows flag windy, cold or wet games with the adjustment made to that projection (for example "💨 19 mph · −22%"), and the player drawer spells it out.
- **Model check:** backtest accuracy per market, the fitted weather effect with this week's outdoor forecasts, and the freshness of projections and odds.
- **Scheduled syncs:** the server runs the model and fetches odds on a weekly schedule (below), so the public site has no buttons that spend credits. The header shows when the next update is due. Odds are stored in the database, so re-running the model never spends API credits.
- **Admin page** (`/admin`, behind the admin password): the schedule with each slot's next and last run and a *Run now* button, a log of every sync (trigger, week, games fetched, credits used, full output), and the Odds API key's remaining credits.

## NBA

The NBA side covers the **slate**: the next two game dates (Eastern) with games still to tip off, so before opening night it shows opening night and the day after. Games drop off the board at tip-off.

- **Games:** a tile per game with tip-off, logos, both teams' win chances, the market spread and total (from ESPN), the top prop, and the injury count. A tile opens the game page: the moneyline card, best props, projections and both teams' injury reports (ESPN's status, injury, latest news line and estimated return), at one sportsbook picked at the top.
- **Best props / Projections:** points, rebounds, assists and 3-pointers made, with the same filters, pricing, player drawer and betslip as the NFL.
- **Injuries:** ESPN's report for every slate team. *Out*, *Doubtful* and *Suspended* players aren't projected; *Day-to-day* players are, and are flagged.

**Data.** ESPN's public JSON API (no key) for the schedule, rosters, every rostered player's game logs (this season and the two before) and injuries; stats.nba.com and NBA.com's CDN refuse requests from hosting providers. Responses are cached in `backend/data/nba_cache/`, on the Railway volume, so finished seasons are fetched once (a first run takes about 25 seconds, later ones a few). Lines come from The Odds API (`basketball_nba`) with its own key, **`ODDS_API_KEY_NBA`**.

**Model** (`backend/app/nba/`). Each stat = projected minutes × per-minute rate × opponent factor. Minutes are a recency-weighted average of recent games (8-game half-life); rates use a 40-game half-life, shrunk toward the guard/forward/center average by 150 minutes of league-average play (30 for threes, since who shoots them varies so much within a position), with last season counting 60% as much as this one. The opponent factor compares what a defense allowed with what its opponents' players usually produce, shrunk to 1 and kept within ±15%. Over/under probabilities come from the walk-forward backtest's own errors, as for the NFL, except threes: they're small whole numbers, so they're priced as a Poisson count (the error table underrated their overs by 4-5 points at 1.5+ lines; Poisson came within 0.4-2.7 points at every line). Team win chances come from a ridge regression of point margins (60-day half-life, last season at half weight) through a normal curve fitted in the backtest (about 12.5 points), and always lean at least 80% on the market's no-vig chance.

Walk-forward backtest (2025-26 and the 2026 playoffs, weekly, rostered players with 12+ projected minutes):

| Stat | Games | Model MAE | Last-10 MAE | Bias |
|---|---|---|---|---|
| Points | 22,994 | 5.02 | 5.07 | -0.1 |
| Rebounds | 22,994 | 1.98 | 2.05 | +0.0 |
| Assists | 22,994 | 1.46 | 1.48 | -0.0 |
| 3-pointers made | 22,994 | 0.95 | 0.97 | +0.0 |
| Moneyline (Brier; baseline = home team's usual rate) | 1,235 | 0.206 | 0.247 | +0.006 |

The edge over a plain last-10 average is small; the books' lines are sharper still.

**NBA syncs** (on the same schedule thread and admin page as the NFL's; Eastern time, every day):

| When | Sync | Odds (NBA key) |
|---|---|---|
| 10:00 AM | Model + odds | moneylines for the slate (1 credit), props already posted for games within 20 hours (4 per game: points, rebounds, assists, threes) |
| 2:00 PM | Model + odds | moneylines, props for games that had none |
| 6:00 PM | Model + odds | moneylines, a fresh pull of props for games within 20 hours (4 per game) |

That is roughly 8 credits per game per day plus 3, about 2,000-2,700 credits a month in season, so a free 500-credit key won't last; trim the 6 PM re-pull (`nba-pregame` in `scheduler.py`) to save half. The credit floor (`ODDS_CREDIT_FLOOR`) applies to the NBA key too, and the admin page shows both keys' balances.

**NBA API:** `GET /api/nba/meta`, `/api/nba/picks`, `/api/nba/projections`, `/api/nba/moneylines`, `/api/nba/injuries`, `/api/nba/players/{id}`, `/api/nba/players/{id}/lines?kind=pts|reb|ast|threes`, with the same parameters and shapes as the NFL routes.

**NBA limitations.** A teammate's absence doesn't move anyone's minutes or usage yet (early in the season, last season's roles carry over); rookies and players with fewer than 5 NBA games aren't projected; no alternate lines; back-to-backs, rest days and blowouts aren't modeled; the static GitHub Pages demo is NFL only.

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
| `GET /api/picks` | Priced plays. Params: `kind`, `game_id`, `q`, `min_ev`, `market_weight`, `side` (Over/Under), `book`, `include_flagged`, `limit` |
| `GET /api/projections` | Projections. Params: `kind`, `game_id`, `q` |
| `GET /api/moneylines` | Both teams' win chances (model, market, blend) and best moneyline per game. Params: `book`, `market_weight` |
| `GET /api/injuries` | This week's injury report and reserve lists for every team on the slate (re-read from nflverse at most hourly) |
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
| Receptions | targets | catch rate (receptions per target) |

- **Recency weighting:** exponential decay (5-game half-life) across seasons, so recent games dominate while last year anchors small samples.
- **Shrinkage:** efficiency is pulled toward the position mean with a pseudo-count prior, because yards per attempt is noisy. Volume is shrunk only lightly (and not at all for most quarterback volume), since roles are stable.
- **Opponent and game script:** a shrunk yards-allowed factor for the defense, and a point-spread nudge (favorites run more, underdogs pass more).
- **Weather:** at outdoor stadiums, wind and cold scale the yardage projection (see below).
- **Injured teammates:** see "Injury redistribution" below.
- **Availability:** the active roster decides a player's team. Injured reserve, Out/Doubtful, players with no practice and no game status, and offseason arrivals with no games for their new team are excluded.

### Injury redistribution (rushing)

When a regular is out, his volume goes to his teammates and the books price that in. For each team-game the model finds absent regulars (ruled Out or Doubtful, sat out practice with no game status, or no longer on the active roster, and projected at 8+ carries), takes the volume they would have had, subtracts the part teammates' recent history already reflects (the longer someone has been out, the more of that is already in), and hands a fitted share of the rest to the active teammates **in the same position group** in proportion to their own projected carries. The share is fitted in the backtest (about 62% of the missing carries) and then shrunk by 35% (to about 40%), because the fit on volume overshoots once volume becomes yards; held-out weeks and a replay of past weeks both put the best share at 50-75% of the fit.

It was tested on held-out weeks, market by market. Rushing is shared as above. Receiving (targets) made held-out error worse (overshooting), so it's off. Instead, receiving plays are tagged **teammate out** when a same-position rotation receiver (4+ projected targets) is in his first game out, as context only. In the backtest those teammates average 3-5 yards over projection (about 1 otherwise; from the second game on their recent games already show it), but from a few big games: they beat their projection no more often than anyone (42.6% vs 42.7%), so neither side is flagged or adjusted. Blending in each receiver's own games without the missing teammate was tested too and raised error at every strength.

**Quarterbacks work differently: the replacement takes over.** When a starting QB is ruled out, the QB who plays throws about as many passes as the starter was projected for (a median of 29 attempts for a true backup, 32 overall, and only 5.9 yards per attempt for a true backup against about 7 for starters). A backup's own history is a handful of snaps, which projected him at 15 attempts and 104 yards when the market had him near 198; with his attempts set to the missing starter's, the backtest bias on those games goes from +132 yards to about 0 and the average miss from 135 to 68 yards. The lead active QB gets the starter's projected attempts (never fewer than his own); QBs further down the depth chart are untouched. His yards per attempt stay what his own record says (a 0.9 adjustment for backups didn't help).

**Only the expected starter is projected.** Each team's starting QB is the one who made its most recent start, looking past fill-in starts (made while another QB was ruled Out or Doubtful that week or the next, or listed Questionable and inactive) and last season's week 18 rest games. That names the actual starter in 90% of past games. Backups are dropped unless the starter is listed Questionable; projecting them used to split a team's passing between two QBs (Seattle had Drew Lock at 122 yards next to Sam Darnold). A QB's volume also leans on his starts: his relief snaps and injury exits count a third as much (`NONSTART_W = 0.35`, fitted on the backtest), which took the passing error on starters from 62.3 to 61.9 yards and their bias from +6 to +1.5 yards.

### Anytime touchdown

For each player with a real rushing or receiving role, the expected touchdowns in the game are
`carries x TD-per-carry + targets x TD-per-target`. Both rates are recency-weighted and shrunk toward the position average, and the total is scaled by how many points the team is expected to score (from the spread and total). The chance of at least one TD is the Poisson probability `1 - exp(-expected TDs)`, with one scale factor fit in the backtest so the average predicted rate matches the actual rate. Passing TDs don't count, matching the market.

The backtest scores it with a Brier score against always predicting the average TD rate, and shows a calibration table on the Model check tab. It's a weak signal: it has no red-zone or goal-line usage, and books price the market sharply. So TD plays always lean at least 60% on the market's chance (books post a lone "Yes" price with a large margin, which the app estimates and strips), are priced in their own tab rather than in "All yardage", and large edges are flagged. Prices aren't limited to -300..+300 for this market, since +400 to +2000 are ordinary.

### Receptions

Receptions use the same machinery as yardage with catches in place of yards: projected targets x a recency-weighted catch rate shrunk toward the position average (about 63% for wide receivers, 72% for tight ends, 79% for running backs), with the same opponent and game-script adjustments. Weather isn't applied (it was fitted on yards, not catches). Win probabilities come from the backtest's own errors, as for yardage; in the backtest, a predicted 48% chance of going over a line hit 48% of the time, and every band was within a few points.

### Team moneyline

Each team gets a rating in points from a ridge regression of recent games' point margins (home rating - away rating + home field), recency-weighted with a 10-week half-life, with earlier seasons counting half as much. The predicted margin becomes a win probability through a normal curve whose spread (about 14 points) is fitted on a walk-forward backtest every run; it takes a couple of seconds, so even a fast sync refits it.

It's honest about how weak that is: over the last two seasons it scores a Brier of about 0.222, against 0.249 for always giving the home team its usual win rate, but the closing moneyline scores about 0.209 on the same games, and no blend of the two beat the market alone. The ratings know nothing about injuries, quarterbacks or rest. So moneyline prices always lean at least 80% on the market's no-vig chance (the blend that came closest to the market's own score), and the Model check tab shows the comparison.

### Probabilities and EV

The chance of beating a line comes from the backtest's own errors, not an assumed curve. For each market the walk-forward backtest gives a robust spread of the errors (binned by projection size, so passing and rushing each get their own) and the empirical distribution of the standardized errors, which carries the real skew and the blow-up games. The probability of going over a line is read straight off that table, so it matches how often actual yardage beat the projection. Whole-number lines leave room for a push, and no probability is allowed to reach 0 or 100%. (An earlier version assumed a gamma curve, which was too skewed and made unders look better than they were; passing was hit hardest, with actuals beating the model's median 67% of the time instead of ~50%.) The model's win probability is then blended (35% by default, adjustable in the UI) with the market's no-vig probability. EV and quarter-Kelly come from that blend and the best available price.

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
| Receptions | 2,116 | 1.69 | 1.78 | -0.0 |
| Anytime TD (Brier score, lower is better) | 2,634 | 0.190 | 0.201 | 0.000 |
| Moneyline (Brier; baseline is the home team's usual win rate; the closing line scores 0.209) | 621 | 0.222 | 0.249 | -0.021 |

MAE is mean absolute error in yards (catches for receptions); bias is the mean of (actual - projection). The passing market initially ran ~9 yards low because volume shrinkage pulled quarterback attempts toward zero; a per-market setting fixed it.

## Running it

Requires Python 3.9+ and Node 20+. Everything goes through one script:

```bash
./run.sh setup      # venv + npm install; creates backend/.env (add ODDS_API_KEY there, optional)
./run.sh refresh    # compute this week's projections (about a minute the first time)
./run.sh start      # app at http://localhost:8000 (API + built UI)
```

`./run.sh lan` starts the app so your phone on the same Wi-Fi can open it (other devices are read-only: refreshes and API-credit-spending fetches stay limited to this machine). Other commands: `./run.sh dev` (API with auto-reload plus the Vite dev server on :5173), `./run.sh build`, `./run.sh test`, and `./run.sh refresh --odds none --exclude "Player Name"`. Run `./run.sh help` for the list.

**Odds:** get a free key at [the-odds-api.com](https://the-odds-api.com) (about 500 credits a month; a full sync costs about 12 credits per game: seven main markets, including the moneyline, plus five alternate-line markets) and put it in `backend/.env`. Without a key the app still shows projections. In the UI, *Refresh data* fetches only markets that have no stored lines; *Re-fetch all odds* is the explicit paid action.

**Tests and CI:** `./run.sh test` runs the backend suite (pytest: model math, pricing logic, API behavior) and the frontend typecheck and tests. GitHub Actions runs the same on every push.

**Docker** (untested so far): `docker build -t nfl-props . && docker run -p 8000:8000 -v nfl-data:/srv/backend/data nfl-props`. Set `DATABASE_URL` to a Postgres URL (and add a driver such as `psycopg`) when deploying beyond one instance.

## Going live: Railway (one service, no sleep)

The `Dockerfile` builds the React app and the API into one container, so on Railway the whole app is one service at one URL: no GitHub Pages, no CORS, no Neon. `railway.json` tells Railway to build the `Dockerfile` and health-check `/healthz`. Use the **Hobby** plan: the Free plan caps a service at 0.5 GB of RAM and $1 of usage a month, which this app outgrows. Leave **Serverless** off so the app never sleeps.

1. **New project → Deploy from GitHub repo** → this repo. Every push to `main` redeploys.
2. **Volume:** right-click the service → *Attach volume*, mount path `/srv/backend/data`. The SQLite database lives there and survives redeploys.
3. **Variables:** `ODDS_API_KEY` and `ADMIN_TOKEN` (your admin password, 12+ characters). Leave `DATABASE_URL` unset to use the SQLite file on the volume.
4. **Settings → Networking → Generate domain** for a public `*.up.railway.app` URL.
5. **Bring your data** (optional): in the service's *Console*, copy an existing database onto the volume so the odds you already paid for come along: `python -m app.copy_db --from 'postgresql://…' --to sqlite:////srv/backend/data/app.db`.
6. **GitHub Pages:** delete the `API_URL` repository variable so the Pages site goes back to the static demo (or turn Pages off).

**Scheduled syncs** (`backend/app/scheduler.py`) run inside the web process, on by default on Railway (`AUTO_SYNC=1`) and off elsewhere, so a laptop never spends credits by itself. Times are Eastern:

| When | Sync | Odds |
|---|---|---|
| Daily 9:00 AM | Model + top-up | games with no lines, or under 100 lines at least 3 h old |
| Tue 10:00 AM | New week: recalibrate and project | none |
| Wed, Thu 10:00 AM | Model + missing odds | games and markets with no lines yet |
| Thu 4:00 PM, Sat 10:00 AM, Sun 11:00 AM | Model only (injury reports, game statuses) | none |
| Sun 11:30 AM | Model + top-up before the early kickoffs | as the daily top-up |

A slot missed by a redeploy (within 3 hours) runs when the server comes back. Every sync, scheduled or *Run now*, is logged on the admin page.

**Credit floor and key rotation.** Before fetching odds, a sync checks the key's balance (a free call) and skips any game whose cost would take it under `ODDS_CREDIT_FLOOR` (default 75). Those syncs are logged as *Partial*, and the admin page shows a banner. To switch keys, replace `ODDS_API_KEY` in the service's *Variables* and deploy. A free key's 500 credits a month covers roughly two to three weeks of syncs (a full week is about 180 credits before top-ups), so expect to rotate keys during the season.

## Going live: Render API + GitHub Pages site

> The older setup. The *Admin* button and *Sync next week* menu described below have since been replaced by scheduled syncs and the `/admin` page (see the Railway section). On Render the free service sleeps, so the schedule would not run reliably there.

The React app is served from GitHub Pages and calls the API hosted on Render, so the public site is the real, working app. Anyone can browse; refreshing data and fetching alternate lines (which spend Odds API credits) need your **admin password**. It's the `ADMIN_TOKEN` environment variable on Render: Render generates a random one, but you can replace it with a password only you know (Environment tab → edit `ADMIN_TOKEN` → Save; use 12+ characters). Repeated wrong guesses from one client are slowed down (429), and the right password always works.

```
GitHub Pages (React)  ──HTTPS──▶  Render (FastAPI)  ──▶  Neon Postgres (free)
                                          └──▶ The Odds API
```

**Why these pieces.** Render's free web service has no persistent disk and sleeps after 15 idle minutes, so the database lives on Neon (free Postgres). The first visit after a sleep takes up to a minute; the app shows "Waking the server…" and retries by itself. The model run peaked at about 380 MB with the server (measured on a Mac; Linux may differ) after trimming it to the 16 stat columns it uses, which fits Render's 512 MB free tier with some room. If the service ever runs out of memory, set `PROJECTIONS_ON_SERVER=0` in Render: the site then only fetches odds and you run the model on your Mac against the same database.

**One-time setup** (accounts and secrets are yours to create):
1. **Neon:** create a project at [neon.tech](https://neon.tech) and copy its connection string (`postgresql://…`).
2. **Copy your data up** (keeps the odds you already paid credits for):
   ```bash
   DATABASE_URL='postgresql://…' ./run.sh push-data
   ```
3. **Render:** New → Blueprint → pick this repo (it reads `render.yaml`). When asked, set `DATABASE_URL` (the Neon string) and `ODDS_API_KEY`. After the deploy, copy the service URL (`https://nfl-prop-predictor-api.onrender.com`). Then, in the service's Environment tab, set `ADMIN_TOKEN` to your own password.
4. **GitHub:** Settings → Secrets and variables → Actions → **Variables** → new variable `API_URL` = the Render URL. Settings → Pages → Source: **GitHub Actions**. Merge to `main` (or run the "Deploy demo to GitHub Pages" workflow). If your GitHub user isn't `JoshuaDHaber`, change `CORS_ORIGINS` in Render to your Pages origin.
5. **Open the site, click Admin, enter the admin password.** Refresh controls appear for you only (it stays in that browser).

**Syncing a new week from the site (no code or push needed).** Once the API has been deployed with `PROJECTIONS_ON_SERVER=1`, open the site, unlock **Admin**, and click **Sync next week**. It works out the next week with unplayed games, shows exactly what it will do and what it costs in Odds API credits (for example "15 of 15 games, about 180 credits"), and when you confirm it runs the model, stores the new projections in Neon, and fetches odds for every game that doesn't have them yet: main lines, anytime TD, moneylines and alternate lines. A repeat costs nothing, because odds are stored per game and market and only the missing ones are bought (so a game synced before receptions and moneylines were added only buys those, about 3 credits). The menu also has "Model only" (no credits) and "Re-fetch all odds for the week". The sync shows its progress: a live timer, which step it is on ("Step 1 of 2 · Running the model"), the current sub-step, and a bar through the odds fetch.

**Fast by default.** The slow part of a model run is the walk-forward backtest that calibrates it (error tables, the touchdown scale, the injury-redistribution share, the weather effect). Those change very little from one week to the next, so a normal sync reuses the previous run's calibration and only computes the new week's projections: about 0.7 seconds instead of 14 on a laptop, with projections identical to a full run on the same data. On Render's free tier the full run took about 8 minutes, so expect this to take a fraction of that. Tick **Recalibrate the model** in the confirm step (or choose "Recalibrate model" from the menu) to refit it; it is also refit automatically if the saved calibration is missing, from another season, older than 21 days, or from before the weather model (so the first sync after this update does a full run). The weather forecast itself is fetched fresh on every run, fast or full. The Model check tab says which week the calibration was last fitted for.

**Topping up thin games.** Books post lines gradually through the week, so a sync early in the week can leave some games with few quotes. "Top up thin games" in the menu re-fetches games that have fewer than 100 stored quotes whose lines are at least 3 hours old, plus any that are missing, and shows the games and cost first. The normal sync never re-buys a game that already has lines.

**Each week, from your Mac instead (optional):** `DATABASE_URL='postgresql://…' ./run.sh refresh` runs the model (add `--full` to recalibrate) and stores projections straight into Neon; then use *Fetch odds* on the site (or the same command with `--odds missing`) to pull lines.

Without the `API_URL` variable the same workflow publishes the static snapshot demo described next.

## Public demo on GitHub Pages

GitHub Pages hosts static files only, so it can't run the API. Instead the repo publishes a **static demo**: the same React app reading a saved snapshot (`frontend/public/demo/*.json`) instead of calling the server. Browsing, filtering, the player drawer, line tables and the betslip all work; refreshing data, loading new lines and the market-trust slider (fixed at 35%) need the live app.

```bash
./run.sh refresh && ./run.sh export     # update the snapshot from your data
git add frontend/public/demo && git commit -m "Update demo snapshot" && git push
```

Pushing to `main` runs `.github/workflows/pages.yml`, which builds with `VITE_STATIC=1` and deploys. One-time setup: in the repo go to **Settings → Pages** and set **Source** to **GitHub Actions** (free Pages needs a public repo). The snapshot contains sportsbook lines from The Odds API, so check their terms on redistribution before publishing, and expect the lines and betslip links in it to be stale.

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
    export_static.py  write the data as static JSON for the Pages demo
    copy_db.py     copy the local database to a hosted Postgres (./run.sh push-data)
    engine/        model.py (projections, backtest, probabilities) · injuries.py (injury report for the UI) · td.py (anytime touchdown) · moneyline.py (team ratings, win probability) · weather.py (fitted wind/cold effect, stadium forecasts) · picks.py (pricing) · ladder.py (alt-line pricing) · odds.py · data.py
  tests/           pytest suite
frontend/src/      App, components (picks table, player drawer, line ladder, betslip, controls, refresh), betslip math in slip.ts, typed API client
```

## Limitations

- **The backtest has no historical odds,** so it validates accuracy, not profitability. Every odds fetch is now also appended to `odds_history` (never replaced, no links), so line movement and closing prices build up for grading the model against the market. Sportsbook prop markets are efficient; a large apparent edge usually means the model is missing context.
- **Teammate redistribution covers carries and quarterback attempts:** a missing back's carries move to his teammates and a missing starting QB's attempts go to his replacement, but a missing receiver's targets are not redistributed (tested, and it made held-out error worse), so receiver backups are still under-projected. A replacement QB's receivers also aren't adjusted for his weaker passing.
- **Heuristic adjustments:** opponent and game-script effects are reasonable but untuned.
- **Weather is wind and cold only.** Rain and snow aren't modeled (no history to fit), retractable roofs are assumed closed, and the forecast is as of the last model run. The weather effect is fitted on a few hundred outdoor games with strong wind, so it's noisy, and sportsbooks price wind too.
- **Rush + Rec** treats its two parts as independent, though they are often negatively correlated.
- **Early-season samples are small;** projections lean on last season until enough of this one is played.
- **Injury data is only as fresh as the nflverse feed.** Check game-day statuses before relying on a pick.
- Parameters were tuned on the same games used to report accuracy, so the backtest is somewhat optimistic.

## Roadmap

- Redistribute targets and attempts too, if a better allocation than "same position group" can be shown to help on held-out weeks.
- Model team-level pass/run volume explicitly, then split it among players.
- Pace and offensive-line context; precipitation, once there's a history of it to fit.
- Store pick history and track closing-line value as an out-of-sample test.
- More markets (attempts, touchdowns).
- A team model that knows about injuries and quarterbacks (for example, built up from the player projections), and moneylines in the betslip.
- Multi-leg deep links per sportsbook (today each selection opens as its own link) and correlation-aware same-game parlay pricing.
