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

export const isDirectLink = (l: Pick<Leg, "link">, state: string) =>
  !!l.link && !(/\{state\}/.test(l.link) && !state.trim()) && !fill(l.link, state).includes("{");

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

export interface BookOption { book: string; odds: number; prob: number; ev: number; link: string | null; eventLink: string | null; alt: boolean }

/** Every book that offers this leg's exact line and side, best price first. */
export function bookOptions(ladder: Ladder | undefined, leg: Pick<Leg, "line" | "side">): BookOption[] {
  const best = new Map<string, BookOption>();
  for (const r of ladder?.quotes ?? []) {
    const q = leg.side === "Over" ? r.over : r.under;
    if (r.line !== leg.line || !q) continue;
    const cur = best.get(r.book);
    if (!cur || q.odds > cur.odds)
      best.set(r.book, { book: r.book, odds: q.odds, prob: q.prob, ev: q.ev, link: q.link, eventLink: r.event_link, alt: r.alt });
  }
  return [...best.values()].sort((a, b) => b.odds - a.odds);
}

/** The same bet placed at a different book. */
export function rebook(leg: Leg, o: BookOption): Leg {
  const next = { ...leg, book: o.book, odds: o.odds, prob: o.prob, ev: o.ev, link: o.link, eventLink: o.eventLink, alt: o.alt };
  return { ...next, id: legId(next) };
}

/** Books that could carry every leg, with how many legs each can take. */
export function bookCoverage(options: Record<string, BookOption[]>): { book: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const opts of Object.values(options)) for (const o of opts) counts.set(o.book, (counts.get(o.book) ?? 0) + 1);
  return [...counts.entries()].map(([book, count]) => ({ book, count })).sort((a, b) => b.count - a.count || a.book.localeCompare(b.book));
}
