import type { Filters, Game, Kind } from "../api";
import { IS_STATIC } from "../env";
import { KIND_SHORT, PROJ_GROUPS, SUB_LABEL, kickoff, pct, signedPct } from "../format";

const KINDS: (Kind | "all")[] = ["all", "rush", "rec", "recs", "pass", "rr", "td"];
const ICON: Record<Kind | "all", string> = { all: "📊", rush: "🏃", rec: "🙌", recs: "🧤", pass: "🎯", rr: "⚡", td: "🏈", ptd: "🎯", lng: "🚀" };
// the Projections tab: receiving and passing markets are folded into one sub tab each
const GROUPED: (Kind | "all" | (typeof PROJ_GROUPS)[number])[] = ["all", "rush", PROJ_GROUPS[0], PROJ_GROUPS[1], "rr", "td"];

interface Props {
  filters: Filters;
  onChange: (f: Filters) => void;
  games: Game[];
  books: string[];
  showPickControls: boolean;
  /** Fold related markets into sub tabs (Receiving, Passing), each with a pill per market. */
  grouped?: boolean;
}

export default function Controls({ filters, onChange, games, books, showPickControls, grouped = false }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const group = grouped ? PROJ_GROUPS.find((g) => (g.kinds as string[]).includes(filters.kind)) : undefined;
  return (
    <section className="controls" aria-label="Filters">
      <div className="seg" role="tablist" aria-label="Market">
        {grouped ? GROUPED.map((k) => {
          if (typeof k === "object") {
            const on = group === k;
            return (
              <button key={k.label} role="tab" aria-selected={on} className={on ? "on" : ""} onClick={() => !on && set({ kind: k.kinds[0] })}>
                <span className="ico" aria-hidden>{k.icon}</span>{k.label}
              </button>
            );
          }
          return (
            <button key={k} role="tab" aria-selected={filters.kind === k} className={filters.kind === k ? "on" : ""} onClick={() => set({ kind: k })}>
              <span className="ico" aria-hidden>{ICON[k]}</span>{k === "all" ? "All projections" : KIND_SHORT[k]}
            </button>
          );
        }) : KINDS.map((k) => (
          <button key={k} role="tab" aria-selected={filters.kind === k} className={filters.kind === k ? "on" : ""}
            onClick={() => set({ kind: k })}>
            <span className="ico" aria-hidden>{ICON[k]}</span>{k === "all" ? "All over/unders" : KIND_SHORT[k]}
          </button>
        ))}
      </div>
      {group && (
        <div className="seg sub" role="tablist" aria-label={`${group.label} market`}>
          {group.kinds.map((k) => (
            <button key={k} role="tab" aria-selected={filters.kind === k} className={filters.kind === k ? "on" : ""} onClick={() => set({ kind: k })}>
              <span className="ico" aria-hidden>{ICON[k]}</span>{SUB_LABEL[k] ?? KIND_SHORT[k]}
            </button>
          ))}
        </div>
      )}
      {showPickControls && (
        <div className="seg" role="tablist" aria-label="Over or under">
          {(["all", "Over", "Under"] as const).map((s) => (
            <button key={s} role="tab" aria-selected={filters.side === s} className={filters.side === s ? "on" : ""}
              onClick={() => set({ side: s })}>
              {s === "all" ? "Overs & unders" : filters.kind === "td" ? (s === "Over" ? "Anytime TD" : "No TD") : `${s}s`}
            </button>
          ))}
        </div>
      )}
      <div className="games" role="tablist" aria-label="Game">
        <button role="tab" aria-selected={filters.game === "all"} className={`game${filters.game === "all" ? " on" : ""}`} onClick={() => set({ game: "all" })}>
          <b>All games</b><small>{games.length} this week</small>
        </button>
        {games.map((g) => (
          <button key={g.game_id} role="tab" aria-selected={filters.game === g.game_id} className={`game${filters.game === g.game_id ? " on" : ""}`}
            onClick={() => set({ game: g.game_id })}>
            <b>{g.label}</b><small>{kickoff(g.gameday, g.gametime)}</small>
          </button>
        ))}
      </div>
      <div className="row">
        {showPickControls && (
          <select value={filters.book} onChange={(e) => set({ book: e.target.value })} aria-label="Sportsbook">
            <option value="all">All sportsbooks</option>
            {books.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        )}
        <input type="search" placeholder="Search player" value={filters.q} onChange={(e) => set({ q: e.target.value })}
          aria-label="Search player" />
        {showPickControls && (
          <>
            <label className="slider" title="Minimum expected value per $1 staked. Slide below 0 to see the closest plays that are not yet positive">
              <span>Min EV <b>{signedPct(filters.minEv)}</b></span>
              <input type="range" min={-0.1} max={0.2} step={0.01} value={filters.minEv}
                onChange={(e) => set({ minEv: Number(e.target.value) })} />
            </label>
            <label className="slider" title={IS_STATIC ? "Fixed at 35% in the demo snapshot" : "How much to blend the market's no-vig probability into the model's"}>
              <span>Trust market <b>{pct(filters.marketWeight, 0)}</b></span>
              <input type="range" min={0} max={1} step={0.05} value={filters.marketWeight} disabled={IS_STATIC}
                onChange={(e) => set({ marketWeight: Number(e.target.value) })} />
            </label>
            <label className="check" title="Show plays where the model and market disagree by 40%+ (usually model blind spots)">
              <input type="checkbox" checked={filters.flagged} onChange={(e) => set({ flagged: e.target.checked })} />
              Show large gaps
            </label>
          </>
        )}
      </div>
      {filters.kind === "td" && (
        <p className="td-note">
          <b>Anytime TD:</b> books post a single “Yes” price with a large margin, and this model doesn't see red-zone usage, so it
          always leans at least 60% on the market's chance. Treat these edges with caution; big ones usually mean the model is missing something.
        </p>
      )}
    </section>
  );
}
