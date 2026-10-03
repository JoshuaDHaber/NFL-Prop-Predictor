import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useState } from "react";
import { api, type Filters, type Kind } from "./api";
import BetSlip from "./components/BetSlip";
import Controls from "./components/Controls";
import ModelCheck from "./components/ModelCheck";
import PicksTable from "./components/PicksTable";
import ProjectionsTable from "./components/ProjectionsTable";
import RefreshButton from "./components/RefreshButton";
import { useWaking } from "./auth";
import AdminButton from "./components/AdminButton";
import { API_URL, IS_STATIC } from "./env";
import { timeAgo } from "./format";
import { useDebounced } from "./useDebounced";

const PlayerDrawer = lazy(() => import("./components/PlayerDrawer")); // keeps the charting library out of the first load

type Tab = "picks" | "projections" | "model";
const TABS: [Tab, string][] = [["picks", "Best props"], ["projections", "Projections"], ["model", "Model check"]];

export default function App() {
  const waking = useWaking();
  const [tab, setTab] = useState<Tab>("picks");
  const [filters, setFilters] = useState<Filters>({ kind: "all", game: "all", book: "all", q: "", minEv: 0.03, marketWeight: 0.35, flagged: false });
  const [selected, setSelected] = useState<{ id: string; kind: Kind } | null>(null);
  const debounced = useDebounced(filters, 250);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const picks = useQuery({ queryKey: ["picks", debounced], queryFn: () => api.picks(debounced), enabled: tab === "picks", placeholderData: (p) => p });
  const projections = useQuery({ queryKey: ["projections", debounced], queryFn: () => api.projections(debounced), enabled: tab === "projections", placeholderData: (p) => p });

  if (meta.isLoading) return (
    <div className="wrap">
      <p className="mut">{waking ? "Waking the server… free hosting stops idle apps, so the first visit can take up to a minute." : "Loading…"}</p>
    </div>
  );
  if (meta.error || !meta.data) return (
    <div className="wrap">
      <p className="err">{API_URL ? "Can't reach the API right now. Try again in a minute." : "Can't reach the API. Is the backend running on port 8000?"}</p>
    </div>
  );
  const m = meta.data;
  const hasOdds = Object.keys(m.odds).length > 0;
  const latestOdds = Object.values(m.odds).map((o) => o.fetched_at).sort().at(-1);

  return (
    <div className="wrap">
      <header>
        <div>
          <h1>NFL Prop Predictor</h1>
          <div className="sub">
            {m.run ? `${m.run.season} Week ${m.run.week} · projections ${timeAgo(m.run.created_at)}` : "No projections yet"}
            {latestOdds && ` · odds ${timeAgo(latestOdds)}`}
          </div>
        </div>
        <div className="head-actions">
          {IS_STATIC ? <div className="demo-tag" title="This page reads a saved snapshot, not a live server">Demo snapshot</div> : (
            <>
              {m.can_write && <RefreshButton meta={m} />}
              {API_URL && <AdminButton canWrite={m.can_write} />}
            </>
          )}
        </div>
      </header>

      {waking && <div className="banner">Waking the server… some data may take a moment to load.</div>}
      {IS_STATIC && (
        <div className="banner">
          <b>Static demo.</b> This is a frozen snapshot{m.snapshot_at ? ` from ${new Date(m.snapshot_at + "Z").toLocaleString()}` : ""}.
          Projections come from this project's model; sportsbook lines are from <a href="https://the-odds-api.com">The Odds API</a> and
          are out of date by now, as are the betslip links. Refreshing, loading new lines and the market-trust slider need the live app.
          For information only, not betting advice.
        </div>
      )}

      {!IS_STATIC && !m.run && <div className="banner">No projections yet. Click <b>Refresh data</b> to run the model (takes about a minute).</div>}
      {!IS_STATIC && m.run && !hasOdds && tab === "picks" && (
        <div className="banner">No sportsbook lines are loaded, so there are no picks. Add an <code>ODDS_API_KEY</code> and refresh.</div>
      )}

      <nav className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>

      {tab !== "model" && <Controls filters={filters} onChange={setFilters} games={m.games} books={m.books} showPickControls={tab === "picks"} />}

      {tab === "picks" && (picks.isLoading ? <p className="mut">Pricing plays…</p> :
        <PicksTable picks={picks.data ?? []} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "projections" && (projections.isLoading ? <p className="mut">Loading…</p> :
        <ProjectionsTable rows={projections.data ?? []} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "model" && <ModelCheck meta={m} />}

      <footer>
        Yards = volume × efficiency, recency-weighted and shrunk to position means, adjusted for opponent and game
        script. Win probabilities come from a gamma distribution fit on a walk-forward backtest, blended with the
        market's no-vig price. Large edges usually mean the model is missing context. Not betting advice.
      </footer>

      {selected && (
        <Suspense fallback={null}>
          <PlayerDrawer playerId={selected.id} initialKind={selected.kind} marketWeight={debounced.marketWeight}
            book={filters.book} onBookChange={(b) => setFilters({ ...filters, book: b })}
            onClose={() => setSelected(null)} />
        </Suspense>
      )}
      <BetSlip />
    </div>
  );
}
