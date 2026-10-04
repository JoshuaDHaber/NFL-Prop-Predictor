import { getToken, setWaking } from "./auth";
import { API_URL, BASE, IS_STATIC } from "./env";

export type Kind = "rush" | "rec" | "pass" | "rr" | "td";

export interface CalibrationBin { predicted: number; actual: number; n: number }
/** Yardage kinds report mean absolute error in yards; anytime TD reports Brier scores (metric: "brier"). */
export interface BacktestStat { n: number; mae_model: number; mae_naive: number; bias: number; metric?: "mae" | "brier"; calibration?: CalibrationBin[] }
export interface Game { game_id: string; label: string; gameday: string; gametime: string }
export interface JobStatus {
  state: "idle" | "running" | "done" | "error";
  started_at: string | null; finished_at: string | null; log: string[]; error: string | null;
}
export interface Meta {
  run: { id: number; season: number; week: number; created_at: string; excluded: string[] } | null;
  backtest: Record<string, BacktestStat>;
  odds: Record<string, { fetched_at: string; lines: number }>;
  games: Game[];
  has_odds_key: boolean;
  job: JobStatus;
  lan_url: string | null;
  books: string[];
  snapshot_at?: string | null;
  can_write: boolean;
  can_run_projections: boolean;
}
export interface Projection {
  player_id: string; name: string; pos: string; team: string; opp: string; home: boolean; kind: Kind;
  mu: number; sd: number; vol: number; eff: number; spread: number; status: string;
  game_id: string; gameday: string; gametime: string; last5: number[];
}
export interface Pick {
  player_id: string; name: string; pos: string; team: string; opp: string; home: boolean; kind: Kind;
  mu: number; sd: number; status: string; game_id: string; gameday: string; gametime: string;
  side: "Over" | "Under"; line: number; odds: number; book: string;
  p_model: number; p_mkt: number; prob: number; ev: number; kelly: number; books: number;
  edge_yds: number; flagged: boolean; last5: number[];
}
export interface GameLogEntry { label: string; opp: string; yards: number; volume: number }
export interface PlayerDetail {
  player_id: string; name: string; pos: string; team: string; headshot?: string | null;
  projections: Projection[]; picks: Pick[]; logs: Record<string, GameLogEntry[]>;
}

export interface QuoteSide { odds: number; prob: number; ev: number; link: string | null }
export interface LadderRow { line: number; book: string; alt: boolean; event_link: string | null; over: QuoteSide | null; under: QuoteSide | null }
export interface Ladder { kind: Kind; mu: number; sd: number; game_id: string; alt_fetched_at: string | null; quotes: LadderRow[] }
export interface AltFetchResult { kinds: string[]; alt_quotes: number; linked: number; credits_remaining: string | null }

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const WAKE_TRIES = 30; // x 3 s: a sleeping free host takes up to about a minute to come back

/** fetch against the API. Reads are retried while a hosted API wakes up; writes never are (they can spend credits). */
export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = { ...(init.headers as Record<string, string>), ...(token && API_URL ? { Authorization: `Bearer ${encodeURIComponent(token)}` } : {}) };
  const canRetry = !!API_URL && (init.method ?? "GET") === "GET";
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(`${API_URL}${path}`, { ...init, headers });
      if (canRetry && [502, 503, 504].includes(res.status) && attempt < WAKE_TRIES) throw new Error("waking");
      setWaking(false);
      return res;
    } catch (e) {
      if (!canRetry || attempt >= WAKE_TRIES) { setWaking(false); throw e; }
      setWaking(true);
      await sleep(3000);
    }
  }
}

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== "all") qs.set(k, String(v));
  const res = await request(`/api/${path}${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export interface Filters { kind: Kind | "all"; side: "all" | "Over" | "Under"; game: string; book: string; q: string; minEv: number; marketWeight: number; flagged: boolean }

const liveApi = {
  meta: () => get<Meta>("meta"),
  picks: (f: Filters) =>
    get<Pick[]>("picks", { kind: f.kind, exclude_kind: f.kind === "all" ? "td" : undefined, side: f.side, game_id: f.game, book: f.book, q: f.q, min_ev: f.minEv, market_weight: f.marketWeight,
      include_flagged: f.flagged, limit: 300 }),
  projections: (f: Filters) => get<Projection[]>("projections", { kind: f.kind, exclude_kind: f.kind === "all" ? "td" : undefined, game_id: f.game, q: f.q }),
  player: (id: string, marketWeight: number) => get<PlayerDetail>(`players/${id}`, { market_weight: marketWeight }),
  /** oddsRange hides prices outside -N..+N (American); 0 shows everything. */
  lines: (id: string, kind: Kind, oddsRange = 300) => get<Ladder>(`players/${id}/lines`, { kind, odds_range: oddsRange }),
  fetchAlt: async (id: string): Promise<AltFetchResult> => {
    const res = await request(`/api/players/${id}/alt-lines`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail);
    return res.json();
  },
  refresh: async (odds: "none" | "missing" | "all"): Promise<JobStatus> => {
    const res = await request("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ odds }) });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  status: () => get<JobStatus>("refresh/status"),
};


// ---------- static demo: the same functions, backed by exported JSON ----------
const slug = (book: string) => book.replace(/[^A-Za-z0-9]+/g, "_");
async function file<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}demo/${path}`);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}
const unavailable = () => { throw new Error("Not available in the demo snapshot"); };

/** Mirrors the server's odds-range rule: hide a side priced beyond -N..+N, drop rows left with neither. */
export function limitOdds(quotes: LadderRow[], range: number, kind?: Kind): LadderRow[] {
  if (!range || kind === "td") return quotes; // anytime TD prices (+400, +1200) are ordinary, so the range never applies
  const ok = (q: QuoteSide | null) => (q && q.odds >= -range && q.odds <= range ? q : null);
  return quotes.map((r) => ({ ...r, over: ok(r.over), under: ok(r.under) })).filter((r) => r.over || r.under);
}

const staticApi: typeof liveApi = {
  meta: () => file<Meta>("meta.json"),
  picks: async (f) => {
    const all = await file<Pick[]>(`picks/${f.book === "all" ? "all" : slug(f.book)}.json`);
    const q = f.q.toLowerCase();
    return all
      .filter((p) => p.ev >= f.minEv && (f.flagged || !p.flagged) && (f.side === "all" || p.side === f.side) && (f.kind === "all" ? p.kind !== "td" : p.kind === f.kind)
        && (f.game === "all" || p.game_id === f.game) && (!q || p.name.toLowerCase().includes(q)))
      .sort((a, b) => b.ev - a.ev)
      .slice(0, 300);
  },
  projections: async (f) => {
    const q = f.q.toLowerCase();
    return (await file<Projection[]>("projections.json")).filter((p) => (f.kind === "all" ? p.kind !== "td" : p.kind === f.kind)
      && (f.game === "all" || p.game_id === f.game) && (!q || p.name.toLowerCase().includes(q)));
  },
  player: (id) => file<PlayerDetail>(`players/${id}.json`),
  lines: async (id, kind, range = 300) => {
    const l = await file<Ladder>(`ladders/${id}_${kind}.json`);
    return { ...l, quotes: limitOdds(l.quotes, range, kind) };
  },
  fetchAlt: async () => unavailable(),
  refresh: async () => unavailable(),
  status: async () => ({ state: "idle", started_at: null, finished_at: null, log: [], error: null }),
};

export const api = IS_STATIC ? staticApi : liveApi;
