import type { Pick } from "./api";
import { legId, toAmerican, toDecimal, type Leg } from "./slip";

/** Shortest price allowed on a leg: heavier chalk adds hit chance but almost no payout. */
export const MIN_LEG_ODDS = -300;
/** Lowest win probability a leg needs to be considered "high probability". */
export const MIN_LEG_PROB = 0.6;

export interface Parlay {
  key: string;
  title: string;
  blurb: string;
  legs: Pick[];
  /** Chance every leg hits, treating legs as independent (they come from different games, so that's reasonable). */
  prob: number;
  decimal: number;
  american: number;
  /** Expected profit per $1 staked at the legs' best prices. */
  ev: number;
  /** The sportsbook every leg is priced at, so the parlay can be placed as shown. */
  book: string;
}

export const pickKey = (p: Pick) => `${p.player_id}|${p.kind}|${p.side}|${p.line}|${p.book}`;

/** High-probability, sanely priced plays that the model and market don't disagree wildly on. */
export function candidates(picks: Pick[]): Pick[] {
  return picks.filter((p) => !p.flagged && p.kind !== "td" && p.prob >= MIN_LEG_PROB && p.odds >= MIN_LEG_ODDS);
}

/** Take legs in order, skipping any whose game is already used (same-game legs are correlated, so their odds multiply wrongly). */
function oneLegPerGame(sorted: Pick[], n: number): Pick[] {
  const games = new Set<string>();
  const legs: Pick[] = [];
  for (const p of sorted) {
    if (games.has(p.game_id)) continue;
    games.add(p.game_id);
    legs.push(p);
    if (legs.length === n) break;
  }
  return legs;
}

export function priceParlay(legs: Pick[]): Omit<Parlay, "key" | "title" | "blurb" | "legs"> {
  if (new Set(legs.map((l) => l.book)).size > 1) throw new Error("A parlay's legs must all be at one sportsbook");
  const decimal = legs.reduce((d, l) => d * toDecimal(l.odds), 1);
  const prob = legs.reduce((q, l) => q * l.prob, 1);
  return { prob, decimal, american: toAmerican(decimal), ev: prob * decimal - 1, book: legs[0].book };
}

const byProb = (a: Pick, b: Pick) => b.prob - a.prob || b.ev - a.ev;
const byEv = (a: Pick, b: Pick) => b.ev - a.ev || b.prob - a.prob;

/** The recommended parlays. `picks` must all be quotes from one sportsbook. A tile is dropped when there aren't enough eligible legs or it repeats an earlier tile. */
export function recommendParlays(picks: Pick[]): Parlay[] {
  const pool = candidates(picks);
  const specs: { key: string; title: string; blurb: string; n: number; legs: Pick[] }[] = [
    { key: "safest", title: "Safest 3-leg", blurb: "The three likeliest plays on the board, one per game.",
      n: 3, legs: oneLegPerGame([...pool].sort(byProb), 3) },
    { key: "value", title: "Best value 3-leg", blurb: "Highest expected return among high-probability plays.",
      n: 3, legs: oneLegPerGame([...pool].sort(byEv), 3) },
    { key: "overs", title: "Overs only", blurb: "Three likely overs, one per game.",
      n: 3, legs: oneLegPerGame(pool.filter((p) => p.side === "Over").sort(byProb), 3) },
    { key: "payout", title: "Bigger payout 5-leg", blurb: "Five likely plays from five different games.",
      n: 5, legs: oneLegPerGame([...pool].sort(byProb), 5) },
  ];
  const seen = new Set<string>();
  const out: Parlay[] = [];
  for (const s of specs) {
    if (s.legs.length < s.n) continue;
    const sig = s.legs.map(pickKey).sort().join("&");
    if (seen.has(sig)) continue;
    seen.add(sig);
    out.push({ key: s.key, title: s.title, blurb: s.blurb, legs: s.legs, ...priceParlay(s.legs) });
  }
  return out;
}

/** Recommended parlays at each sportsbook (`picksByBook`: that book's priced picks), keyed by book. Books with none are left out. */
export function parlaysByBook(picksByBook: Record<string, Pick[]>): Record<string, Parlay[]> {
  const out: Record<string, Parlay[]> = {};
  for (const [book, picks] of Object.entries(picksByBook)) {
    const ps = recommendParlays(picks.filter((p) => p.book === book));
    if (ps.length) out[book] = ps;
  }
  return out;
}

/** The book to show first: where the lead (safest) parlay has the best expected return. */
export function bestBook(byBook: Record<string, Parlay[]>): string | null {
  const books = Object.keys(byBook).sort();
  return books.sort((a, b) => byBook[b][0].ev - byBook[a][0].ev)[0] ?? null;
}

/** A pick as a betslip leg. Links aren't part of a pick; the slip's "Get links" and book switcher fill those in. */
export function pickToLeg(p: Pick): Leg {
  const base = { playerId: p.player_id, kind: p.kind, side: p.side, line: p.line, book: p.book };
  return { id: legId(base), ...base, name: p.name, team: p.team, opp: p.opp, home: p.home, odds: p.odds,
    link: null, eventLink: null, alt: false, prob: p.prob, ev: p.ev, gameId: p.game_id };
}
