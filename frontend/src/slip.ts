import type { Kind, Ladder } from "./api";
import { KIND_LABEL, americanOdds } from "./format";

export interface Leg {
  id: string;
  playerId: string; name: string; team: string; opp: string; home: boolean;
  kind: Kind; side: "Over" | "Under"; line: number; odds: number; book: string;
  link: string | null; eventLink: string | null; alt: boolean; prob: number; ev: number; gameId: string;
}

export const legId = (l: Pick<Leg, "playerId" | "kind" | "side" | "line" | "book">) =>
  `${l.playerId}|${l.kind}|${l.side}|${l.line}|${l.book}`;

export const toDecimal = (american: number) => (american > 0 ? 1 + american / 100 : 1 + 100 / -american);
export const toAmerican = (decimal: number) =>
  decimal >= 2 ? Math.round((decimal - 1) * 100) : Math.round(-100 / (decimal - 1));

/** Combined odds if every leg must win (a parlay at one book). */
export function parlay(legs: Leg[], stake: number) {
  const decimal = legs.reduce((d, l) => d * toDecimal(l.odds), 1);
  return { decimal, american: toAmerican(decimal), payout: stake * decimal, profit: stake * (decimal - 1) };
}

export const toWin = (odds: number, stake: number) => stake * (toDecimal(odds) - 1);

/** Sportsbook front pages, used only when the Odds API gave no direct link for a quote. */
const BOOK_SITES: Record<string, string> = {
  DraftKings: "https://sportsbook.draftkings.com/leagues/football/nfl",
  FanDuel: "https://sportsbook.fanduel.com/navigation/nfl",
  BetMGM: "https://sports.betmgm.com",
  "Caesars": "https://sportsbook.caesars.com",
  BetRivers: "https://www.betrivers.com",
  Bovada: "https://www.bovada.lv/sports/football/nfl",
  "BetOnline.ag": "https://www.betonline.ag/sportsbook/football/nfl",
  "ESPN BET": "https://espnbet.com",
  Fanatics: "https://sportsbook.fanatics.com",
};

const fill = (url: string, state: string) => url.replace(/\{state\}/g, state.toLowerCase());
const resolved = (url: string | null) => (url && !url.includes("{") ? url : null);

/** Best link for a leg: its own betslip link, else the game page at that book, else the book's NFL page. */
export function legLink(l: Pick<Leg, "link" | "eventLink" | "book">, state: string): string | null {
  const st = state.trim();
  const needsState = (u: string | null) => !!u && /\{state\}/.test(u) && !st;
  const direct = l.link && !needsState(l.link) ? resolved(fill(l.link, st)) : null;
  const event = l.eventLink && !needsState(l.eventLink) ? resolved(fill(l.eventLink, st)) : null;
  return direct ?? event ?? BOOK_SITES[l.book] ?? null;
}

export function groupByBook(legs: Leg[]): [string, Leg[]][] {
  const m = new Map<string, Leg[]>();
  for (const l of legs) m.set(l.book, [...(m.get(l.book) ?? []), l]);
  return [...m.entries()];
}

export const legText = (l: Leg) =>
  `${l.name} ${l.side} ${l.line} ${KIND_LABEL[l.kind]} (${l.home ? "vs" : "@"} ${l.opp}) ${americanOdds(l.odds)} @ ${l.book}`;

export function slipText(legs: Leg[]) {
  return groupByBook(legs).map(([book, ls]) => `${book}\n${ls.map((l) => `  - ${legText(l)}`).join("\n")}`).join("\n\n");
}

export const sameGame = (legs: Leg[]) => new Set(legs.map((l) => l.gameId)).size < legs.length;

export interface BookOption { book: string; line: number; odds: number; prob: number; ev: number; link: string | null; eventLink: string | null; alt: boolean }

/** Every book that offers this leg's exact line and side, best price first. */
export function bookOptions(ladder: Ladder | undefined, leg: Pick<Leg, "line" | "side">): BookOption[] {
  const best = new Map<string, BookOption>();
  for (const r of ladder?.quotes ?? []) {
    const q = leg.side === "Over" ? r.over : r.under;
    if (r.line !== leg.line || !q) continue;
    const cur = best.get(r.book);
    if (!cur || q.odds > cur.odds)
      best.set(r.book, { book: r.book, line: r.line, odds: q.odds, prob: q.prob, ev: q.ev, link: q.link, eventLink: r.event_link, alt: r.alt });
  }
  return [...best.values()].sort((a, b) => b.odds - a.odds);
}

/** The bet at another book (and, for suggestions, at that book's line). */
export function rebook(leg: Leg, o: BookOption): Leg {
  const next = { ...leg, book: o.book, line: o.line, odds: o.odds, prob: o.prob, ev: o.ev, link: o.link, eventLink: o.eventLink, alt: o.alt };
  return { ...next, id: legId(next) };
}

/** Books that could carry every leg, with how many legs each can take. */
export function bookCoverage(options: Record<string, BookOption[]>): { book: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const opts of Object.values(options)) for (const o of opts) counts.set(o.book, (counts.get(o.book) ?? 0) + 1);
  return [...counts.entries()].map(([book, count]) => ({ book, count })).sort((a, b) => b.count - a.count || a.book.localeCompare(b.book));
}

/** Lines a book offers for this player/side, nearest to the leg's line first: what to swap to when the book lacks the exact line. */
export function alternativesAtBook(ladder: Ladder | undefined, leg: Pick<Leg, "line" | "side">, book: string, n = 3): BookOption[] {
  const byLine = new Map<number, BookOption>();
  for (const r of ladder?.quotes ?? []) {
    const q = leg.side === "Over" ? r.over : r.under;
    if (r.book !== book || !q) continue;
    const cur = byLine.get(r.line);
    if (!cur || q.odds > cur.odds)
      byLine.set(r.line, { book, line: r.line, odds: q.odds, prob: q.prob, ev: q.ev, link: q.link, eventLink: r.event_link, alt: r.alt });
  }
  return [...byLine.values()]
    .sort((a, b) => Math.abs(a.line - leg.line) - Math.abs(b.line - leg.line) || a.line - b.line)
    .slice(0, n)
    .sort((a, b) => a.line - b.line);
}

export type LinkStatus = "direct" | "needs-state" | "missing";

/** Whether "Add at book" can really add this leg to the book's slip, and if not, why. */
export function linkStatus(l: Pick<Leg, "link">, state: string): LinkStatus {
  if (!l.link) return "missing";
  const filled = l.link.replace(/\{state\}/g, state.trim().toLowerCase());
  if (/\{state\}/.test(l.link) && !state.trim()) return "needs-state";
  return filled.includes("{") ? "missing" : "direct";
}
