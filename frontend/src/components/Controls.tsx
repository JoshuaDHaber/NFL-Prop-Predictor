import type { Filters, Game, Kind } from "../api";
import { IS_STATIC } from "../env";
import { KIND_SHORT, pct, signedPct } from "../format";

const KINDS: (Kind | "all")[] = ["all", "rush", "rec", "pass", "rr"];

interface Props {
  filters: Filters;
  onChange: (f: Filters) => void;
  games: Game[];
  books: string[];
  showPickControls: boolean;
}

export default function Controls({ filters, onChange, games, books, showPickControls }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  return (
    <section className="controls" aria-label="Filters">
      <div className="seg" role="tablist" aria-label="Market">
        {KINDS.map((k) => (
          <button key={k} role="tab" aria-selected={filters.kind === k} className={filters.kind === k ? "on" : ""}
            onClick={() => set({ kind: k })}>
            {k === "all" ? "All markets" : KIND_SHORT[k]}
          </button>
        ))}
      </div>
      <div className="row">
        <select value={filters.game} onChange={(e) => set({ game: e.target.value })} aria-label="Game">
          <option value="all">All games</option>
          {games.map((g) => <option key={g.game_id} value={g.game_id}>{g.label}</option>)}
        </select>
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
            <label className="slider" title="Minimum expected value per $1 staked">
              <span>Min EV <b>{signedPct(filters.minEv)}</b></span>
              <input type="range" min={0} max={0.2} step={0.01} value={filters.minEv}
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
    </section>
  );
}
