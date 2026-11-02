# Bet tracker plan

Status: phase 1 built on `docs/bet-tracker-plan` (2026-11-01), with the defaults below chosen. Phases 2 and 3 not started. Builds on accounts (`docs/auth-plan.md`, PRs #50-#52).

## The idea

Signed-in bettors mark the bets they actually placed. The site grades each one automatically when the stats land, the
same way it already grades the board, and keeps a running record: wins and losses, profit, ROI, and how their prices
compared with the closing line. It's a reason to sign in that nothing else on the site gives you, and most of the hard
part (grading props against box scores) already exists.

**Out of scope:** placing bets (the site never does), syncing with sportsbook accounts, public leaderboards or sharing
records, and bets the site can't grade (anything not a player prop the site prices; see "Custom bets" for the fallback).

## What already exists to build on

- **Grading.** `app/grading.py` (NFL) and `app/nba/grading.py` (NBA) settle every board pick from box scores: nflverse
  weekly stats for the NFL (usually the Tuesday after the games), ESPN game logs for the NBA (the next morning). They
  handle pushes, and a player who didn't play is void, as the books settle it. `grading.actual_value()`,
  `nba.model.actual()` and `grading.outcome()` work from any player, game, market, side and line, so they also cover alternate
  lines, which `pick_log` doesn't hold.
- **The betslip.** Each leg already carries everything a bet needs: `playerId, gameId, kind, side, line, odds, book, alt,
  prob, ev` (`frontend/src/slip.ts`). Legs are grouped by book, with a stake per book and combined parlay odds.
- **Closing lines.** `app/market_fit.py` already works out the market's fair chance at the last fetch before kickoff for
  logged picks; the same lookup can price a tracked leg at its own line.
- **Accounts**, the 21+ check, `/api/auth/*` with its CSRF check, and the account menu and Preferences page patterns.

## How a bet gets tracked

1. **From the betslip (the main way).** Each book's group in the slip gets a **"Track this bet"** button next to
   "Place bet". It opens a small confirm sheet, prefilled from the slip:
   - **As a parlay** (default when the group has 2+ legs) or **as singles** (one bet per leg, the stake on each).
   - **Stake** (prefilled from the slip's stake for that book).
   - **Odds** per leg or for the parlay, prefilled with the site's price but editable, because the price at the book may
     have moved, or a boost or same-game-parlay price may differ.
   - **Track** saves it; a toast offers "View in My bets". The slip is left as it is (the bettor may still be placing it).
2. **From a single quote.** In the player drawer's line table, next to the existing **+** (add to slip), a "Track" action
   for a one-leg bet, opening the same sheet.
3. **Signed out:** "Track this bet" opens the sign-in sheet first, then returns to the confirm sheet.

## Grading and settlement

- **Legs.** After each model run grades the board, a new `bets.grade_legs()` grades open tracked legs with the same stats
  frames and functions (`actual_value` / `nba.model.actual` + `outcome`): win, loss, push, or void if he didn't play.
- **Bets.**
  - A single takes its leg's result.
  - A parlay loses as soon as any leg loses.
  - Void and pushed legs drop out and the parlay is re-priced on the legs that remain, as FanDuel and DraftKings settle
    them. If every leg drops out, the bet is void.
  - Payout and profit are worked out from the odds recorded on the bet.
- **Timing.** The NFL settles when nflverse publishes the week's stats (usually Tuesday). The books settle Sunday night,
  so a bet shows **"Awaiting stats"** in between. The NBA settles the next morning.
- **Manual override.** The bettor can mark a bet won, lost, push or void themselves, for when the book settled
  differently (an injury rule, a stat correction). A bet marked by hand shows "settled by you" and grading leaves it alone.
- **Custom bets** (option, below): a bet the site can't grade (a team total, a boost, another sport) can be entered as
  free text with odds and stake and settled by hand. It still counts in the record.

## The "My bets" page

A new section at `/bets` (and `/nba/bets`), opened from the account menu, between Preferences and Admin. Signed out, the
address shows the sign-in prompt. It's built from parts the site already uses:

- **Summary tiles** (the admin page's card row): record (W-L-P), profit in dollars or units, ROI, and **beat the close**
  (the share of bets priced better than the closing line, the best sign of skill over small samples).
- **Filters** (the site's pill menus): league, sportsbook, period (this week, last 30 days, this season, all), and
  singles vs parlays.
- **Open bets**: each bet as a card listing its legs (player, market, line, odds, the leg's status, live once settled),
  with stake, potential payout, and Edit or Delete.
- **Settled bets**: the same cards, newest first, with each leg's actual stat ("78 rec yds") and the bet's profit.
- **Profit over time**: a small cumulative-profit line chart (Recharts, already in the app), once there are 10+ settled
  bets.
- **Empty state**: one line explaining how to track a bet from the slip, with a link to Best props.

## Views and tags (added before phase 1 shipped)

- **Views:** My bets shows one view at a time:
  - **League:** All, NFL or NBA, as segmented buttons.
  - **Sportsbook:** every sportsbook, or one.
  - **Period:** last month, last 3 months, last 12 months or all time. These are calendar months by the date tracked, worked out
    on the server (`months=`).
  - **Tag:** one at a time, as pills.

  The tiles and lists follow the view, a "Showing NBA bets at DraftKings tagged SGP, last 3 months · Show all" line says what's
  on screen, and the view is remembered in the browser.
- **Breakdowns:** "By sportsbook" and "By tag" cards list each group's bets, record, profit and ROI within the current view.
  Tapping a row opens that group's view.
- **Tags:** the bettor's own labels ("SGP", "Sunday", "Tailing"). Rules:
  - Up to 6 per bet, 24 characters each, with no repeats ignoring case.
  - Added in the Track sheet or later from a bet's ⋯ menu (Edit stake, odds and tags), with earlier tags offered as one-tap
    suggestions.
  - Tapping a tag on a bet card shows that tag's bets.
  - Stored as a JSON list on `bets.tags`.

## Data model (`backend/app/db.py`)

```text
bets
  id               int pk
  user_id          fk users ON DELETE CASCADE, indexed
  league           'nfl' | 'nba'
  book             varchar(40)
  kind             'single' | 'parlay' | 'custom'
  stake            float          (dollars, or units: see open questions)
  odds             int            American; for a parlay, the combined price the bettor recorded
  status           'open' | 'won' | 'lost' | 'push' | 'void'
  payout           float nullable (stake back included; 0 for a loss)
  settled_by       'grading' | 'user' | null
  description      varchar(200) nullable  (custom bets: the free text)
  placed_at, settled_at, created_at
  notes            varchar(500) nullable
  tags             json list of strings (the bettor's labels)

bet_legs
  id               int pk
  bet_id           fk bets ON DELETE CASCADE, indexed
  game_id, gameday, player_id, name, team, opp, home
  kind, side, line, odds, alt
  p_model, p_mkt, ev           what the site priced it at when tracked (for "followed the model?" stats later)
  close_p                      market fair chance at the close, at this line (filled at kickoff, like pick_log)
  actual           float nullable
  result           'win' | 'loss' | 'push' | 'void' | null
  graded_at
```

## API

Under a new `/api/me/` prefix. It's added to `PUBLIC_WRITES` in `main.py`, and every route gets `require_user` plus the
same-origin check that `/api/auth/` writes have.

- `GET /api/me/bets?league=&status=&book=&since=`: bets with their legs, newest first.
- `GET /api/me/bets/summary?...same filters`: record, profit, ROI, beat-the-close, and points for the chart.
- `POST /api/me/bets`: `{league, book, kind, stake, odds, legs[]}`. Legs are checked against known games and players
  (not trusted blindly), and kickoff must still be ahead, so bets can't be backfilled after the result is known (see open
  questions).
- `PATCH /api/me/bets/{id}`: stake, odds, notes, or a manual result.
- `DELETE /api/me/bets/{id}`.

The existing account deletion also deletes bets (cascade, plus an explicit delete for SQLite).

## Frontend

- `TrackBetSheet.tsx`: the confirm sheet, opened from `BetSlip.tsx` and `PlayerDrawer.tsx`.
- `MyBets.tsx`: the page, as a section in both league shells (like Preferences), lazy-loaded.
- `AccountMenu.tsx`: a "My bets" item. The Preferences page gets a short "Tracking" card linking to it.
- `api.ts`: typed calls.
- Copy: on the Privacy page, add "Bets you track" to what's stored, and say Delete account removes them.

## Phases

1. **Track and settle** (one PR):
   - tables and API
   - "Track this bet" from the slip
   - automatic grading for NFL and NBA, with manual override
   - the My bets page with summary tiles, filters, and open and settled lists
   - Privacy page update, plus tests: settlement math (parlays with voids and pushes), grading of alternate lines,
     ownership (one user can't see or change another's bets), and the kickoff cutoff
2. **Insight**:
   - closing-line value per leg and beat-the-close
   - the profit chart
   - "Track" from the player drawer
   - CSV export
3. **Nudges** (Resend is set up): an optional email when a bet settles or a weekly summary, off by default with an
   unsubscribe link.

## Decisions (2026-11-01: the defaults)

- **Dollars.** Stakes and profit are in dollars. Units can come later as a display option.
- **No backfilling.** A bet can only be tracked before its first game starts (the server checks every leg's kickoff).
- **No custom bets in phase 1.** The tracker covers what the site can grade: player props on the board, main and
  alternate lines.
- **Fully private.** Tracked bets are never shown to anyone but their owner, including in the admin's Model check.
