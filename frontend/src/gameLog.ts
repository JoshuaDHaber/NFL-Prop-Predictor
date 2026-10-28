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
