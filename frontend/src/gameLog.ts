import type { GameLogEntry } from "./api";

/** One bar on the player drawer's game-log chart: a game, or a stretch of weeks he didn't play (a bye, injury or inactive). */
export interface LogBar {
  label: string;
  /** The short axis label: "W11" (NFL), or the label as it came (NBA dates). */
  tick: string;
  opp: string;
  /** The stat; null for weeks without a game. */
  yards: number | null;
  /** The NFL season, for marking where one season gives way to the next. */
  season: number | null;
  missed?: boolean;
}

const NFL_WEEK = /^(\d{4}) W(\d+)$/;

/** The game log as bars, with a placeholder wherever a season skips weeks so a bye or an absence reads as a gap, not as nothing. */
export function withGaps(logs: GameLogEntry[]): LogBar[] {
  const out: LogBar[] = [];
  let prev: [number, number] | null = null;
  for (const g of logs) {
    const m = NFL_WEEK.exec(g.label);
    const at: [number, number] | null = m ? [Number(m[1]), Number(m[2])] : null;
    if (at && prev && at[0] === prev[0] && at[1] - prev[1] > 1) {
      const a = prev[1] + 1, b = at[1] - 1;
      out.push({ label: a === b ? `${at[0]} W${a}` : `${at[0]} W${a}–${b}`, tick: a === b ? `W${a}` : `W${a}–${b}`, opp: "", yards: null, season: at[0], missed: true });
    }
    out.push({ label: g.label, tick: at ? `W${at[1]}` : g.label, opp: g.opp, yards: g.yards, season: at?.[0] ?? null });
    if (at) prev = at;
  }
  return out;
}

/** The first bar of each season after the first, where the chart draws a season divider. */
export const seasonStarts = (bars: LogBar[]) =>
  bars.filter((b, i) => i > 0 && b.season != null && bars[i - 1].season != null && b.season !== bars[i - 1].season);

export const hits = (yards: number, side: "Over" | "Under", line: number) => (side === "Over" ? yards > line : yards < line);

/** How often a play would have cashed over the logged games, and over the last five. */
export function hitRate(bars: LogBar[], side: "Over" | "Under", line: number) {
  const played = bars.filter((b) => b.yards != null).map((b) => hits(b.yards!, side, line));
  const last5 = played.slice(-5);
  return { n: played.length, hit: played.filter(Boolean).length, n5: last5.length, hit5: last5.filter(Boolean).length };
}

export interface Split { label: string; n: number; hit: number }

/** How often a play would have cashed in slices of the player's games (oldest first): the last 5, 10 and 20, this
 *  season, last season, against this opponent, and (when the log says) at home or on the road like this game. Empty
 *  slices are left out, and the last 10 and 20 only show once there are that many games. */
export function hitSplits(logs: GameLogEntry[], side: "Over" | "Under", line: number, ctx: { opp: string; home: boolean }): Split[] {
  const rate = (label: string, games: GameLogEntry[]): Split => ({ label, n: games.length, hit: games.filter((g) => hits(g.yards, side, line)).length });
  const out: Split[] = [];
  for (const n of [5, 10, 20]) {
    if (logs.length >= n || (n === 5 && logs.length > 0)) out.push(rate(`Last ${Math.min(n, logs.length)}`, logs.slice(-n)));
  }
  const seasons = [...new Set(logs.map((g) => g.season).filter((s): s is number => s != null))].sort((a, b) => b - a);
  if (seasons.length) {
    out.push(rate("Season", logs.filter((g) => g.season === seasons[0])));
    if (seasons.length > 1) out.push(rate("Last season", logs.filter((g) => g.season === seasons[1])));
  }
  if (ctx.opp) out.push(rate(`vs ${ctx.opp}`, logs.filter((g) => g.opp === ctx.opp)));
  if (logs.some((g) => g.home != null)) out.push(rate(ctx.home ? "Home" : "Away", logs.filter((g) => g.home === ctx.home)));
  return out.filter((s) => s.n > 0);
}
