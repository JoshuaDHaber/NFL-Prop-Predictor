import { getToken } from "./auth";
import { getLeague } from "./league";

/** NFL markets, then the NBA's points, rebounds, assists and 3-pointers made. */
export type Kind = "rush" | "rec" | "pass" | "rr" | "td" | "recs" | "ptd" | "lng" | "rlng" | "ftd" | "pts" | "reb" | "ast" | "threes" | "pra" | "pr" | "pa" | "stl" | "blk" | "dd" | "tpl";
export type NbaKind = "pts" | "reb" | "ast" | "threes" | "pra" | "pr" | "pa" | "stl" | "blk" | "dd" | "tpl";
const NBA_KIND_SET = new Set<Kind>(["pts", "reb", "ast", "threes", "pra", "pr", "pa", "stl", "blk", "dd", "tpl"]);

export interface CalibrationBin { predicted: number; actual: number; n: number }
/** Yardage kinds report mean absolute error in yards; anytime TD reports Brier scores (metric: "brier"). */
/** What moving an absent regular's volume to his teammates did in the backtest. */
export interface Redistribution {
  rho: Record<string, number>;       // shares actually applied (0 = that role is switched off)
  rho_fit: Record<string, number>;   // shares the data suggested for every role
  active_roles: string[];
  replace_roles?: string[];          // roles where a replacement takes over outright (quarterback attempts)
  by_kind: Record<string, { n: number; bias_before: number; bias_after: number; mae_before: number; mae_after: number }>;
  summary: string;
}

/** The sync schedule's state for the admin page. Times are UTC without a zone suffix, like the rest of the API. */
export interface AutoSync { enabled: boolean; next_at: string | null; next_label: string | null }
export interface KeyBalance { key_name: string; key_hint: string; remaining: number | null; error: string | null }
export interface CreditStatus { remaining: number | null; floor: number; low: boolean; key_hint: string | null; key_name?: string | null; rotate?: string[]; others?: KeyBalance[]; checked_at: string | null; error: string | null }
export interface SyncRun {
  id: number; slot: string; label: string; trigger: "schedule" | "catch-up" | "manual";
  scheduled_for: string | null; started_at: string; finished_at: string | null;
  status: "running" | "ok" | "partial" | "error" | "skipped" | "interrupted";
  odds_mode: string; full: boolean; season: number | null; week: number | null;
  games_fetched: number; credits_before: number | null; credits_after: number | null; summary: string; error: string | null;
}
export interface SyncRunDetail extends SyncRun { log: string[] }
export interface ScheduleSlot { id: string; label: string; league?: "nfl" | "nba"; when: string; odds_mode: string; full: boolean; why: string; next_at: string; last_run: SyncRun | null }
export interface AdminState { auto_sync: AutoSync; timezone: string; credits: CreditStatus; credits_nba?: CreditStatus | null; slots: ScheduleSlot[]; runs: SyncRun[]; job: JobStatus; can_run_projections: boolean;
  /** Offshore books (licensed in no US state) are kept off every list and price. */
  hide_offshore: boolean }

export interface BacktestStat {
  n: number; mae_model: number; mae_naive: number; bias: number; metric?: "mae" | "brier"; calibration?: CalibrationBin[];
  mae_market?: number | null; mae_model_market_games?: number | null; n_market?: number | null;  // moneyline: vs the closing line
}
/** Kickoff weather at the stadium (outdoor games), and the multiplier it puts on each market's yardage. */
export interface GameWeather {
  stadium: string; roof: string; indoor: boolean;
  source: "forecast" | "indoor" | "none";
  temp: number | null; wind: number | null; gust: number | null;   // °F and mph, three hours from kickoff
  wind_dir?: number | null;   // degrees the wind blows FROM (0 = north)
  sky?: string | null;        // "Partly cloudy", "Rain showers", ...
  precip_prob: number | null; precip: number | null; snow: number | null;  // shown, not applied
  fetched_at: string | null;
  provider?: string | null;   // Open-Meteo, or the National Weather Service as a US fallback
  factors: Partial<Record<"rush" | "rec" | "pass", number>>;
}
/** The fitted weather effect (per mph of wind over wind_from, per degree under cold_from) and what it did in the backtest. */
export interface WeatherFit {
  coef: Record<string, { wind: number; cold: number; wind_raw: number; cold_raw: number; wind_se: number | null; cold_se: number | null; n: number; shared?: boolean }>;
  wind_from: number; cold_from: number;
  by_kind: Record<string, { n: number; bias_before: number; bias_after: number; mae_before: number; mae_after: number }>;
}
export interface Game { game_id: string; label: string; gameday: string; gametime: string; weather?: GameWeather | null }
export interface JobStatus {
  state: "idle" | "running" | "done" | "error";
  started_at: string | null; finished_at: string | null; log: string[]; error: string | null;
  stage?: string | null;      // what it is doing now
  step?: number; steps?: number;
  detail?: string | null;     // latest sub-step, e.g. "game 3 of 15"
  progress?: number | null;   // 0..1 through the odds step
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
  redistribution?: Redistribution | null;
  weather?: WeatherFit | null;
  calibration?: { at: string; season: number; week: number; reused_from_run?: number } | null;
  can_write: boolean;
  can_run_projections: boolean;
  auto_sync?: AutoSync | null;
}
export interface Projection {
  player_id: string; name: string; pos: string; team: string; opp: string; home: boolean; kind: Kind;
  mu: number; sd: number; vol: number; eff: number; spread: number; status: string;
  game_id: string; gameday: string; gametime: string; last5: number[];
  wx?: number | null;   // weather multiplier already in mu (1 or null: none)
  /** Thin history (a rookie, or back from IR): shown for reference, never priced. Older snapshots lack it. */
  thin?: boolean | null;
}
export interface Pick {
  player_id: string; name: string; pos: string; team: string; opp: string; home: boolean; kind: Kind;
  mu: number; sd: number; status: string; game_id: string; gameday: string; gametime: string;
  side: "Over" | "Under"; line: number; odds: number; book: string;
  p_model: number; p_mkt: number; prob: number; ev: number; kelly: number; books: number;
  edge_yds: number; flagged: boolean; last5: number[];
  wx?: number | null;
  /** Why it's flagged (hidden by default): "large gap". Older snapshots lack it. */
  flag?: "" | "large gap";
  /** Same-position rotation receivers in their first game out (receiving yards). Context only, not a flag. */
  teammate_out?: string;
}
/** A player search hit: an active player; projected is false for players on bye, off the NBA slate, or without a projection. */
export interface PlayerHit { player_id: string; name: string; pos: string; team: string; headshot?: string | null; projected: boolean }
export interface GameLogEntry { label: string; opp: string; yards: number; volume: number }
export interface PlayerDetail {
  player_id: string; name: string; pos: string; team: string; headshot?: string | null;
  projections: Projection[]; picks: Pick[]; logs: Record<string, GameLogEntry[]>;
}

export interface QuoteSide { odds: number; prob: number; ev: number; link: string | null }
export interface LadderRow { line: number; book: string; alt: boolean; event_link: string | null; over: QuoteSide | null; under: QuoteSide | null }
export interface Ladder { kind: Kind; mu: number; sd: number; game_id: string; alt_fetched_at: string | null; quotes: LadderRow[] }
/** One team's side of a game: win chance from the team model, the market (no-vig) and the blend, and the best moneyline. */
export interface MoneylineSide {
  team: string; name: string; home: boolean;
  p_model: number; p_mkt: number | null; prob: number; books: number;
  odds: number | null; book: string | null; ev: number | null; kelly: number | null; link: string | null; event_link: string | null;
}
/** NBA: the chance a game is decided by `margin`+ points, either way and by each team. */
export interface BlowoutChance { margin: number; p: number; p_home: number; p_away: number }
export interface MoneylineGame {
  game_id: string; label: string; gameday: string; gametime: string; margin: number; spread: number | null; total?: number | null; sides: MoneylineSide[];
  blowout?: { games: number; chances: BlowoutChance[] } | null;
}
/** This week's injury report per team (both sides of the ball) plus reserve lists. Times are UTC without a zone suffix. */
export interface InjuredPlayer {
  player_id: string; name: string; pos: string; team: string; side: "off" | "def" | "st";
  status: string;     // Out | Doubtful | Questionable | "" (no game status) | IR | PUP | NFI | Reserve
  injury: string; practice: "DNP" | "Limited" | "Full" | ""; rest: boolean;
  kind: Kind | null;  // a market the app projects for him (opens his drawer)
  comment?: string;            // ESPN: the latest news line
  return_date?: string | null; // ESPN: estimated return, YYYY-MM-DD
  updated?: string | null;     // ESPN: when the status changed (UTC ISO)
}
export interface InjuryReport {
  season: number | null; week: number | null; report_week: number | null; fetched_at: string | null;
  news_fetched_at?: string | null;  // NFL: when ESPN's feed (news, return dates) was last read
  teams: Record<string, InjuredPlayer[]>;
}
/** /api/nba/meta: the NBA slate (the next two game dates), its odds and the model's backtest. */
export interface NbaMeta {
  league: "nba";
  run: { id: number; season: number; slate: string[]; created_at: string; excluded: string[] } | null;
  backtest: Record<string, BacktestStat>;
  odds: Record<string, { fetched_at: string; lines: number }>;
  games: Game[];
  has_odds_key: boolean;
  books: string[];
  auto_sync?: AutoSync | null;
  can_write: boolean;
  supports_alt: boolean;
}
export interface AltFetchResult { kinds: string[]; alt_quotes: number; linked: number; credits_remaining: string | null }

/** fetch against the API (same origin), with the admin password when one is saved. */
export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = { ...(init.headers as Record<string, string>), ...(token ? { Authorization: `Bearer ${encodeURIComponent(token)}` } : {}) };
  return fetch(path, { ...init, headers });
}

/** League data lives under /api/nba/... for the NBA; admin and sync endpoints are shared. */
const lg = (path: string) => (getLeague() === "nba" ? `nba/${path}` : path);

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== "all") qs.set(k, String(v));
  const res = await request(`/api/${path}${qs.size ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

/** Record and units (1 unit a pick at the logged price) for one slice of the graded board. */
export interface GradeLine { label: string; n: number; wins: number; losses: number; pushes: number; voids: number; units: number; roi: number | null; expected_wins: number }
/** Model projection vs posted line, per market: average miss of each, and how often the model was closer. */
export interface MarketCheck { kind: Kind; n: number; mae_model: number; mae_line: number; model_closer: number }
/** Same-game correlations (pair key -> latent correlation), for pricing parlays; see parlays.ts and backend engine/correlation.py. */
export interface Correlations { pairs: Record<string, number>; check: Record<string, { n: number; actual?: number; copula?: number; independent?: number }> }

export interface GradeReport {
  season: number | null; graded: number; pending: number; weeks: number[]; dates?: string[];
  board: GradeLine[]; by_market: GradeLine[]; by_ev: GradeLine[]; by_week: GradeLine[]; model_vs_line: MarketCheck[];
}

export interface Filters { kind: Kind | "all"; side: "all" | "Over" | "Under"; game: string; book: string; q: string; minEv: number; marketWeight: number; flagged: boolean;
  /** NBA only: one Eastern game date ("YYYY-MM-DD"), or every date when unset. */
  date?: string }

/** Books legal where the bettor is (legalBooks.ts), or null for every book. Set by main.tsx, which resets the query caches
 *  whenever it changes, so every list of books and every "best price" below only ever covers these. */
let allowed: string[] | null = null;
export const setAllowedBooks = (books: string[] | null) => { allowed = books; };
const keepBooks = (books: string[]) => (allowed ? books.filter((b) => allowed!.includes(b)) : books);
/** "all" means every allowed book (a comma list the backend understands); a book that isn't allowed falls back to the same.
 *  "none" matches no book, for a state with no legal sportsbook. */
const bookParam = (book: string) => (!allowed || (book !== "all" && allowed.includes(book)) ? book : allowed.join(",") || "none");

export const api = {
  meta: () => get<Meta>(lg("meta")).then((m) => ({ ...m, books: keepBooks(m.books) })),
  nbaMeta: () => get<NbaMeta>("nba/meta").then((m) => ({ ...m, books: keepBooks(m.books) })),
  picks: (f: Filters, limit = 300) =>
    get<Pick[]>(lg("picks"), { kind: f.kind, exclude_kind: f.kind === "all" ? "td" : undefined, side: f.side, game_id: f.game, gameday: f.date, book: bookParam(f.book), q: f.q, min_ev: f.minEv, market_weight: f.marketWeight,
      include_flagged: f.flagged, limit }),
  projections: (f: Filters) => get<Projection[]>(lg("projections"), { kind: f.kind, exclude_kind: f.kind === "all" ? "td" : undefined, game_id: f.game, gameday: f.date, q: f.q }),
  /** Every market for every projected player, anytime TD included (the player compare tab). */
  allProjections: () => get<Projection[]>(lg("projections")),
  /** The NFL's projections whatever league is on screen: the betslip reads players' positions from them. */
  nflProjections: () => get<Projection[]>("projections"),
  /** The NBA's projections whatever league is on screen, for the same reason. */
  nbaProjections: () => get<Projection[]>("nba/projections"),
  searchPlayers: (q: string) => get<PlayerHit[]>(lg("player-search"), { q }),
  player: (id: string, marketWeight: number) => get<PlayerDetail>(lg(`players/${id}`), { market_weight: marketWeight }),
  moneylines: (book: string, marketWeight: number) => get<MoneylineGame[]>(lg("moneylines"), { book: bookParam(book), market_weight: marketWeight }),
  injuries: () => get<InjuryReport>(lg("injuries")),
  grades: () => get<GradeReport>("grades"),
  correlations: () => get<Correlations>("correlations"),
  nbaCorrelations: () => get<Correlations>("nba/correlations"),
  nbaGrades: () => get<GradeReport>("nba/grades"),
  /** oddsRange hides prices outside -N..+N (American); 0 shows everything. */
  // by the market, not the league on screen: a betslip can hold legs from both
  lines: (id: string, kind: Kind, oddsRange = 300) => get<Ladder>(`${NBA_KIND_SET.has(kind) ? "nba/" : ""}players/${id}/lines`, { kind, odds_range: oddsRange })
    .then((l) => ({ ...l, quotes: l.quotes.filter((q) => !allowed || allowed.includes(q.book)) })),
  fetchAlt: async (id: string): Promise<AltFetchResult> => {
    const res = await request(`/api/players/${id}/alt-lines`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail);
    return res.json();
  },
  /** Admin page (needs the admin password). 403 means the password is missing or wrong. */
  admin: async (): Promise<AdminState> => {
    const res = await request("/api/admin");
    if (!res.ok) throw Object.assign(new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail), { status: res.status });
    return res.json();
  },
  adminRun: (id: number) => get<SyncRunDetail>(`admin/runs/${id}`),
  runSlotNow: async (slot: string): Promise<JobStatus> => {
    const res = await request(`/api/admin/run/${slot}`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail);
    return res.json();
  },
  setHideOffshore: async (hide: boolean): Promise<{ hide_offshore: boolean }> => {
    const res = await request("/api/admin/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ hide_offshore: hide }) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail);
    return res.json();
  },
  status: () => get<JobStatus>("refresh/status"),
};


