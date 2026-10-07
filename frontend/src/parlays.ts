import type { Ladder, Pick } from "./api";
import { legId, linkStatus, toAmerican, toDecimal, type Leg } from "./slip";

/** Shortest price allowed on a leg: heavier chalk adds hit chance but almost no payout. */
export const MIN_LEG_ODDS = -300;
/** Lowest win probability a leg needs to be considered "high probability". */
export const MIN_LEG_PROB = 0.6;

/** A parlay leg: a priced pick, plus the betslip link when it came from a line ladder. */
export interface ParlayLeg extends Pick { link?: string | null; eventLink?: string | null; alt?: boolean }

export interface Parlay {
  key: string;
  title: string;
  blurb: string;
  legs: ParlayLeg[];
  /** True when two legs share a game. Their correlation isn't modelled, so the hit chance is only approximate. */
  sameGame: boolean;
  /** Chance every leg hits, treating legs as independent (exact enough for different games, approximate within one). */
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

/** Take legs in order, at most one per player (a player's other lines and markets would be the same bet twice).
 *  Several legs may share a game; the parlay is flagged `sameGame` then, since their correlation isn't modelled. */
function onePerPlayer(sorted: Pick[], n: number): Pick[] {
  const players = new Set<string>();
  const legs: Pick[] = [];
  for (const p of sorted) {
    if (players.has(p.player_id)) continue;
    players.add(p.player_id);
    legs.push(p);
    if (legs.length === n) break;
  }
  return legs;
}

export function priceParlay(legs: Pick[]): Omit<Parlay, "key" | "title" | "blurb" | "legs"> {
  if (new Set(legs.map((l) => l.book)).size > 1) throw new Error("A parlay's legs must all be at one sportsbook");
  const decimal = legs.reduce((d, l) => d * toDecimal(l.odds), 1);
  const prob = legs.reduce((q, l) => q * l.prob, 1);
  return { prob, decimal, american: toAmerican(decimal), ev: prob * decimal - 1, book: legs[0].book,
    sameGame: new Set(legs.map((l) => l.game_id)).size < legs.length };
}

const byProb = (a: Pick, b: Pick) => b.prob - a.prob || b.ev - a.ev;
const byEv = (a: Pick, b: Pick) => b.ev - a.ev || b.prob - a.prob;

/** The recommended parlays. `picks` must all be quotes from one sportsbook. A tile is dropped when there aren't enough eligible legs or it repeats an earlier tile. */
export function recommendParlays(picks: Pick[]): Parlay[] {
  const pool = candidates(picks);
  const specs: { key: string; title: string; blurb: string; n: number; legs: Pick[] }[] = [
    { key: "safest", title: "Safest 3-leg", blurb: "The three likeliest plays on the board.",
      n: 3, legs: onePerPlayer([...pool].sort(byProb), 3) },
    { key: "value", title: "Best value 3-leg", blurb: "Highest expected return among high-probability plays.",
      n: 3, legs: onePerPlayer([...pool].sort(byEv), 3) },
    { key: "overs", title: "Overs only", blurb: "Three likely overs.",
      n: 3, legs: onePerPlayer(pool.filter((p) => p.side === "Over").sort(byProb), 3) },
    { key: "payout", title: "Bigger payout 5-leg", blurb: "Five likely plays, each from a different player.",
      n: 5, legs: onePerPlayer([...pool].sort(byProb), 5) },
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

/** Keep only picks from the chosen games; an empty selection means every game. */
export function filterGames(picksByBook: Record<string, Pick[]>, gameIds: string[]): Record<string, Pick[]> {
  if (!gameIds.length) return picksByBook;
  const keep = new Set(gameIds);
  return Object.fromEntries(Object.entries(picksByBook).map(([book, ps]) => [book, ps.filter((p) => keep.has(p.game_id))]));
}

/** The book to show first: where the lead (safest) parlay has the best expected return. */
export function bestBook(byBook: Record<string, Parlay[]>): string | null {
  const books = Object.keys(byBook).sort();
  return books.sort((a, b) => byBook[b][0].ev - byBook[a][0].ev)[0] ?? null;
}

/** The book the tab opens on when it has any picks. */
export const PREFERRED_BOOK = "FanDuel";

/** The book to show first: FanDuel when it's loaded, else the best lead parlay, else the book with the most overs to ladder from. */
export function defaultBook(byBook: Record<string, Parlay[]>, picksByBook: Record<string, Pick[]>): string | null {
  if (PREFERRED_BOOK in picksByBook) return PREFERRED_BOOK;
  const best = bestBook(byBook);
  if (best) return best;
  const overs = (b: string) => (picksByBook[b] ?? []).filter((p) => p.side === "Over" && (p.kind === "rush" || p.kind === "rec")).length;
  return Object.keys(picksByBook).sort((a, b) => overs(b) - overs(a) || a.localeCompare(b))[0] ?? null;
}

// ---------- ladder parlays: likely rushing / receiving overs that stack to a modest price ----------
export const LADDER_MIN_PROB = 0.6;
/** Shortest price on a rung: heavier chalk can't help a parlay reach +100. */
export const LADDER_MIN_ODDS = -400;
/** Share of each rung's probability taken from the book's price: alternate lines are one-sided, so there is no no-vig price to blend with. */
export const LADDER_MARKET_WEIGHT = 0.35;
export const LADDER_MAX_LEGS = 4;
export const LADDER_PLAYERS = 12;
export const LADDER_PLAYERS_PER_TEAM = 6;
/** Lowest win probability for a single alternate prop to be listed on its own. */
export const LADDER_PROP_MIN_PROB = 0.65;
/** Combined-price bands, as decimal odds: +100 to +150, +150 to +225, +225 to +300. */
export const LADDER_BANDS = [
  { key: "ladder-1", title: "Ladder +100 to +150", lo: 2, hi: 2.5 },
  { key: "ladder-2", title: "Ladder +150 to +225", lo: 2.5, hi: 3.25 },
  { key: "ladder-3", title: "Ladder +225 to +300", lo: 3.25, hi: 4.0001 },
];

/** The players worth pulling a line ladder for: those whose main-line over looks likeliest (flagged plays are left out).
 *  At most `perTeam` per team, so one team's players can't crowd the other side of a game out of the ladders. */
export function ladderTargets(picks: Pick[], n = LADDER_PLAYERS, perTeam = LADDER_PLAYERS_PER_TEAM): Pick[] {
  const seen = new Set<string>();
  const teams = new Map<string, number>();
  const out: Pick[] = [];
  const overs = picks.filter((p) => p.side === "Over" && (p.kind === "rush" || p.kind === "rec") && !p.flagged);
  for (const p of overs.sort((a, b) => b.p_model - a.p_model)) {
    const team = `${p.game_id}|${p.team}`;
    if (seen.has(p.player_id) || (teams.get(team) ?? 0) >= perTeam) continue;
    seen.add(p.player_id);
    teams.set(team, (teams.get(team) ?? 0) + 1);
    out.push(p);
    if (out.length === n) break;
  }
  return out;
}

/** Likely overs at this book for one player, one per line. Only rungs with a usable betslip link count, so every ladder leg can be added at the book
 *  (main lines have none, and some books publish no links or templates the slip can't fill). */
export function ladderRungs(base: Pick, ladder: Ladder | undefined, book: string): ParlayLeg[] {
  const byLine = new Map<number, ParlayLeg>();
  for (const r of ladder?.quotes ?? []) {
    const q = r.over;
    if (r.book !== book || !q || q.odds < LADDER_MIN_ODDS || linkStatus({ link: q.link }, "xx") !== "direct") continue;
    const dec = toDecimal(q.odds);
    const prob = (1 - LADDER_MARKET_WEIGHT) * q.prob + LADDER_MARKET_WEIGHT / dec;
    if (prob < LADDER_MIN_PROB) continue;
    const cur = byLine.get(r.line);
    if (cur && cur.odds >= q.odds) continue;
    byLine.set(r.line, { ...base, side: "Over", line: r.line, odds: q.odds, book, p_model: q.prob, p_mkt: 1 / dec, prob, ev: prob * dec - 1,
      link: q.link, eventLink: r.event_link, alt: r.alt });
  }
  return [...byLine.values()].sort((a, b) => a.line - b.line);
}

type Band = { key: string; title: string; lo: number; hi: number };
type LadderEntry = { base: Pick; ladder: Ladder | undefined };

/** For each band, the likeliest combination of 2-4 different players' rungs (one rung each) whose combined price lands in it. */
function searchLadders(players: ParlayLeg[][], bands: Band[], valid: (legs: ParlayLeg[]) => boolean = () => true): (ParlayLeg[] | null)[] {
  const best: (ParlayLeg[] | null)[] = bands.map(() => null);
  const bestProb = bands.map(() => 0);
  const top = Math.max(...bands.map((b) => b.hi));
  const dfs = (from: number, chosen: ParlayLeg[], dec: number, prob: number) => {
    if (chosen.length >= 2) {
      const b = bands.findIndex((x) => dec >= x.lo && dec < x.hi);
      if (b >= 0 && prob > bestProb[b] && valid(chosen)) { best[b] = [...chosen]; bestProb[b] = prob; }
    }
    if (chosen.length === LADDER_MAX_LEGS) return;
    for (let i = from; i < players.length; i++) {
      for (const leg of players[i]) {
        const next = dec * toDecimal(leg.odds);
        if (next >= top) continue; // prices only grow as legs are added
        chosen.push(leg);
        dfs(i + 1, chosen, next, prob * leg.prob);
        chosen.pop();
      }
    }
  };
  dfs(0, [], 1, 1);
  return best;
}

const LADDER_BLURB = "Likely rushing and receiving overs, on alternate lines where needed, stacked to a modest price.";

/**
 * Ladder parlays at one book: 2-4 different players' overs whose combined price lands in each band, picking the likeliest combo per band.
 * Games may repeat (it's meant to work on a thin slate), so same-game legs are flagged on the result.
 */
export function buildLadderParlays(entries: LadderEntry[], book: string): Parlay[] {
  const players = entries.map((e) => ladderRungs(e.base, e.ladder, book)).filter((r) => r.length);
  const best = searchLadders(players, LADDER_BANDS);
  const seen = new Set<string>();
  const out: Parlay[] = [];
  LADDER_BANDS.forEach((band, i) => {
    const legs = best[i];
    if (!legs) return;
    const sig = legs.map(pickKey).sort().join("&");
    if (seen.has(sig)) return;
    seen.add(sig);
    out.push({ key: band.key, title: band.title, blurb: LADDER_BLURB, legs, ...priceParlay(legs) });
  });
  return out;
}

/** "2026_05_TB_DAL" -> "TB @ DAL" */
export const gameLabel = (gameId: string) => { const [, , away, home] = gameId.split("_"); return `${away} @ ${home}`; };

/**
 * One ladder per game that uses both teams: the likeliest +100 to +300 combination with at least one leg from each side.
 * Plain ladders go to whichever team the model likes; this shows the other team's props too. Skips games where a side has no usable rung,
 * and any tile that repeats one in `existing`.
 */
export function buildBalancedLadders(entries: LadderEntry[], book: string, gameIds: string[], existing: Parlay[] = []): Parlay[] {
  const seen = new Set(existing.map((p) => p.legs.map(pickKey).sort().join("&")));
  const band: Band = { key: "", title: "", lo: LADDER_BANDS[0].lo, hi: LADDER_BANDS[LADDER_BANDS.length - 1].hi };
  const out: Parlay[] = [];
  for (const gameId of gameIds) {
    const players = entries.filter((e) => e.base.game_id === gameId).map((e) => ladderRungs(e.base, e.ladder, book)).filter((r) => r.length);
    const teams = [...new Set(players.map((r) => r[0].team))];
    if (teams.length < 2) continue;
    const [legs] = searchLadders(players, [band], (chosen) => teams.every((t) => chosen.some((l) => l.team === t)));
    if (!legs) continue;
    const sig = legs.map(pickKey).sort().join("&");
    if (seen.has(sig)) continue;
    seen.add(sig);
    out.push({ key: `both-${gameId}`, title: `${gameLabel(gameId)}, both teams`, blurb: "The likeliest ladder with a player from each side of the game.",
      legs, ...priceParlay(legs) });
  }
  return out;
}

/** The likeliest single alternate-line overs at this book (each player's best rung), for browsing and adding one at a time. */
export function ladderProps(entries: LadderEntry[], book: string, minProb = LADDER_PROP_MIN_PROB, n = 12): ParlayLeg[] {
  const out: ParlayLeg[] = [];
  for (const e of entries) {
    const rungs = ladderRungs(e.base, e.ladder, book).filter((r) => r.prob >= minProb);
    if (rungs.length) out.push(rungs.reduce((a, b) => (b.prob > a.prob ? b : a)));
  }
  return out.sort((a, b) => b.prob - a.prob).slice(0, n);
}

/** A pick as a betslip leg. Links aren't part of a pick; the slip's "Get links" and book switcher fill those in. */
export function pickToLeg(p: ParlayLeg): Leg {
  const base = { playerId: p.player_id, kind: p.kind, side: p.side, line: p.line, book: p.book };
  return { id: legId(base), ...base, name: p.name, team: p.team, opp: p.opp, home: p.home, odds: p.odds,
    link: p.link ?? null, eventLink: p.eventLink ?? null, alt: p.alt ?? false, prob: p.prob, ev: p.ev, gameId: p.game_id };
}
