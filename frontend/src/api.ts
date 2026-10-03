export type Kind = "rush" | "rec" | "pass" | "rr";

export interface BacktestStat { n: number; mae_model: number; mae_naive: number; bias: number }
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
  player_id: string; name: string; pos: string; team: string;
  projections: Projection[]; picks: Pick[]; logs: Record<string, GameLogEntry[]>;
}

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== "all") qs.set(k, String(v));
  const res = await fetch(`/api/${path}${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export interface Filters { kind: Kind | "all"; game: string; q: string; minEv: number; marketWeight: number; flagged: boolean }

export const api = {
  meta: () => get<Meta>("meta"),
  picks: (f: Filters) =>
    get<Pick[]>("picks", { kind: f.kind, game_id: f.game, q: f.q, min_ev: f.minEv, market_weight: f.marketWeight,
      include_flagged: f.flagged, limit: 300 }),
  projections: (f: Filters) => get<Projection[]>("projections", { kind: f.kind, game_id: f.game, q: f.q }),
  player: (id: string, marketWeight: number) => get<PlayerDetail>(`players/${id}`, { market_weight: marketWeight }),
  refresh: async (odds: "none" | "missing" | "all"): Promise<JobStatus> => {
    const res = await fetch("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ odds }) });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  status: () => get<JobStatus>("refresh/status"),
};
