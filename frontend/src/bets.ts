import type { Kind } from "./api";
import type { Leg } from "./slip";

// Tracked bets (backend app/bets.py): the bets a signed-in visitor placed at a book, settled from the box scores. Private
// to their owner; the session cookie identifies them, so these calls carry no admin password.

export type BetStatus = "open" | "won" | "lost" | "push" | "void";
export interface TrackedLeg {
  id: number; game_id: string; gameday: string; kickoff: string; player_id: string; name: string; team: string; opp: string;
  kind: Kind; side: "Over" | "Under"; line: number; odds: number; alt: boolean; prob: number | null; ev: number | null;
  actual: number | null; result: "win" | "loss" | "push" | "void" | null;
}
export interface TrackedBet {
  id: number; league: "nfl" | "nba"; book: string; kind: "single" | "parlay"; stake: number; odds: number; status: BetStatus;
  payout: number | null; profit: number | null; to_pay: number; settled_by: "grading" | "user" | null; notes: string | null; tags: string[];
  placed_at: string; settled_at: string | null; started: boolean; legs: TrackedLeg[];
}
export interface BetSummary {
  wins: number; losses: number; pushes: number; open: number; open_stake: number; staked: number; profit: number;
  roi: number | null; curve: [string, number][];
}
/** A view of My bets: one league, one sportsbook, one tag and the last 1, 3 or 12 months (unset: everything). */
export interface BetFilters { league?: "nfl" | "nba"; book?: string; tag?: string; months?: 1 | 3 | 12 }

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/me/${path}`, {
    ...init, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", ...(init.headers as Record<string, string>) },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Try again.");
  return body as T;
}

export const myBets = (f: BetFilters) => {
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)]));
  return call<{ bets: TrackedBet[]; summary: BetSummary; books: string[]; tags: string[] }>(`bets${qs.size ? `?${qs}` : ""}`);
};

const legBody = (l: Leg) => ({ game_id: l.gameId, player_id: l.playerId, kind: l.kind, side: l.side, line: l.line, odds: l.odds, alt: l.alt, prob: l.prob, ev: l.ev });

/** Track a slip group as one parlay (with the price recorded at the book), or each leg as a single at `stake`. */
export async function trackBets(book: string, legs: Leg[], asParlay: boolean, stake: number, parlayOdds: number, tags: string[] = []) {
  if (asParlay) return [await call<TrackedBet>("bets", { method: "POST", body: JSON.stringify({ book, kind: "parlay", stake, odds: parlayOdds, tags, legs: legs.map(legBody) }) })];
  const out: TrackedBet[] = [];
  for (const l of legs) out.push(await call<TrackedBet>("bets", { method: "POST", body: JSON.stringify({ book, kind: "single", stake, tags, legs: [legBody(l)] }) }));
  return out;
}

export const editBet = (id: number, patch: { stake?: number; odds?: number; notes?: string; status?: BetStatus; tags?: string[] }) =>
  call<TrackedBet>(`bets/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deleteBet = (id: number) => call<void>(`bets/${id}`, { method: "DELETE" });

/** The leagues' markets don't overlap, so a leg's market says which league it's from (as the server works it out). */
const NBA_KINDS = new Set<string>(["pts", "reb", "ast", "threes", "pra", "pr", "pa", "stl", "blk", "dd", "tpl"]);
export const legLeague = (kind: Kind) => (NBA_KINDS.has(kind) ? "nba" : "nfl");

/** American odds typed by hand: "+250", "250" or "-110"; null if it isn't a real price. */
export function parseOdds(text: string): number | null {
  const n = Number(text.trim().replace(/^\+/, ""));
  return Number.isInteger(n) && Math.abs(n) >= 100 && Math.abs(n) <= 100_000 ? n : null;
}

export const money = (n: number) => `${n < 0 ? "−" : ""}$${Math.abs(n).toFixed(2)}`;
export const signedMoney = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}$${Math.abs(n).toFixed(2)}`;

export const MAX_TAGS = 6, TAG_LEN = 24;
/** Add a typed tag to a list as the server keeps them: trimmed, at most TAG_LEN long, no repeat ignoring case. */
export function addTag(tags: string[], text: string): string[] {
  const t = text.split(/\s+/).filter(Boolean).join(" ").slice(0, TAG_LEN);
  return !t || tags.length >= MAX_TAGS || tags.some((x) => x.toLowerCase() === t.toLowerCase()) ? tags : [...tags, t];
}
