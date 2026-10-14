import { useQueries, useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useMemo, useState } from "react";
import { api, type Filters, type Kind } from "./api";
import BetSlip from "./components/BetSlip";
import Controls from "./components/Controls";
import GameWeather from "./components/GameWeather";
import ModelCheck from "./components/ModelCheck";
import Moneylines from "./components/Moneylines";
import ParlayTiles from "./components/ParlayTiles";
import PicksTable from "./components/PicksTable";
import ProjectionsTable from "./components/ProjectionsTable";
import { useWaking } from "./auth";
import { API_URL, BASE, IS_STATIC } from "./env";
import { KIND_LABEL, americanOdds, fmtProj, fmtSd, isCount, marketLabel, matchup, pct, playLabel, signedPct, timeAgo } from "./format";
import ThemeToggle from "./components/ThemeToggle";
import TopTiles, { type Tile } from "./components/TopTiles";
import { buildBalancedLadders, buildLadderParlays, buildTdParlays, defaultBook, filterGames, ladderProps, ladderTargets, parlaysByBook } from "./parlays";
import { importOrReload } from "./staleChunk";
import { localWhen } from "./sync";
import { useDebounced } from "./useDebounced";

// keeps the charting library out of the first load; a tab left open across a deploy reloads to the new build
const PlayerDrawer = lazy(() => importOrReload(() => import("./components/PlayerDrawer")));
const AdminPage = lazy(() => importOrReload(() => import("./components/AdminPage")));
/** The owner's sync page lives at <base>/admin; everything else is the public app. */
const IS_ADMIN_PAGE = !IS_STATIC && window.location.pathname.slice(BASE.length - 1).replace(/\/+$/, "") === "/admin";

type Tab = "picks" | "parlays" | "moneyline" | "projections" | "model";
const TABS: [Tab, string][] = [["picks", "Best props"], ["parlays", "Parlays"], ["moneyline", "Moneyline"], ["projections", "Projections"], ["model", "Model check"]];
// Parlays rank by win probability, not EV, so they price every play (any EV) at the default market weight
const PARLAY_FILTERS: Filters = { kind: "all", side: "all", game: "all", book: "all", q: "", minEv: -1, marketWeight: 0.35, flagged: false };

export default function App() {
  return IS_ADMIN_PAGE ? <Suspense fallback={null}><AdminPage /></Suspense> : <PublicApp />;
}

function PublicApp() {
  const waking = useWaking();
  const [tab, setTab] = useState<Tab>("picks");
  const [filters, setFilters] = useState<Filters>({ kind: "all", side: "all", game: "all", book: "all", q: "", minEv: 0.03, marketWeight: 0.35, flagged: false });
  const [selected, setSelected] = useState<{ id: string; kind: Kind } | null>(null);
  const debounced = useDebounced(filters, 250);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const picks = useQuery({ queryKey: ["picks", debounced], queryFn: () => api.picks(debounced), enabled: tab === "picks", placeholderData: (p) => p });
  // one pricing per sportsbook, so every parlay's legs sit at a single book
  const books = meta.data?.books ?? [];
  const parlayQueries = useQueries({
    queries: books.map((book) => ({ queryKey: ["parlay-picks", book], queryFn: () => api.picks({ ...PARLAY_FILTERS, book }, 1000), enabled: tab === "parlays" })),
  });
  // anytime-TD picks per book (the plain picks above leave TDs out)
  const tdQueries = useQueries({
    queries: books.map((book) => ({ queryKey: ["parlay-td", book], queryFn: () => api.picks({ ...PARLAY_FILTERS, kind: "td", book }, 1000), enabled: tab === "parlays" })),
  });
  const parlaysLoading = parlayQueries.some((q) => q.isLoading);
  const [parlayBook, setParlayBook] = useState<string | null>(null);
  const parlayStamp = parlayQueries.map((q) => q.dataUpdatedAt).join();
  const allPicksByBook = useMemo(() => Object.fromEntries(books.map((b, i) => [b, parlayQueries[i]?.data ?? []])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [books.join(), parlayStamp]);
  const [parlayGames, setParlayGames] = useState<string[]>([]);
  // only games still on the slate count; every parlay and ladder is built from the chosen games' picks
  const chosenGames = useMemo(() => parlayGames.filter((id) => meta.data?.games.some((g) => g.game_id === id)), [parlayGames, meta.data]);
  const gamePicks = useMemo(() => filterGames(allPicksByBook, chosenGames), [allPicksByBook, chosenGames]);
  const byBook = useMemo(() => parlaysByBook(gamePicks), [gamePicks]);
  const activeBook = parlayBook && books.includes(parlayBook) ? parlayBook : defaultBook(byBook, gamePicks);
  // ladder parlays need each likely player's line ladder (alternate lines); shares the drawer's and slip's query cache
  const targets = useMemo(() => ladderTargets(activeBook ? gamePicks[activeBook] ?? [] : [], Math.min(24, Math.max(12, chosenGames.length * 8))), [activeBook, gamePicks, chosenGames]);
  const ladderQueries = useQueries({
    queries: targets.map((t) => ({ queryKey: ["ladder", t.player_id, t.kind, 0], queryFn: () => api.lines(t.player_id, t.kind, 0), enabled: tab === "parlays" })),
  });
  const ladderStamp = ladderQueries.map((q) => q.dataUpdatedAt).join();
  const ladderEntries = useMemo(() => targets.map((base, i) => ({ base, ladder: ladderQueries[i]?.data })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [targets, ladderStamp]);
  const ladderParlays = useMemo(() => activeBook ? buildLadderParlays(ladderEntries, activeBook) : [], [activeBook, ladderEntries]);
  // with games chosen, one more ladder per game that uses both teams
  const balancedLadders = useMemo(() => activeBook ? buildBalancedLadders(ladderEntries, activeBook, chosenGames.slice(0, 4), ladderParlays) : [],
    [activeBook, ladderEntries, chosenGames, ladderParlays]);
  const tdStamp = tdQueries.map((q) => q.dataUpdatedAt).join();
  const tdParlays = useMemo(() => {
    const i = books.indexOf(activeBook ?? "");
    return activeBook && i >= 0 ? buildTdParlays(tdQueries[i]?.data ?? [], activeBook, chosenGames) : [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBook, books, chosenGames, tdStamp]);
  const altProps = useMemo(() => activeBook ? ladderProps(ladderEntries, activeBook) : [], [activeBook, ladderEntries]);
  const moneylines = useQuery({ queryKey: ["moneylines", debounced.book, debounced.marketWeight], queryFn: () => api.moneylines(debounced.book, debounced.marketWeight),
    enabled: tab === "moneyline", placeholderData: (p) => p });
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
  const tiles: Tile[] = tab === "picks"
    ? [...(picks.data ?? [])].sort((a, b) => b.ev - a.ev).slice(0, 3).map((p) => ({
      key: `${p.player_id}-${p.kind}-${p.side}`, label: KIND_LABEL[p.kind], name: p.name, meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`,
      value: <>{playLabel(p.kind, p.side, p.line)} <em>{signedPct(p.ev)} EV</em></>, caption: `${americanOdds(p.odds)} at ${p.book}`,
      onClick: () => setSelected({ id: p.player_id, kind: p.kind }),
    }))
    : tab === "parlays" ? []
    : tab === "moneyline"
      ? (moneylines.data ?? []).flatMap((g) => g.sides.map((s) => ({ g, s }))).filter(({ s }) => s.ev != null && s.ev > 0)
        .sort((a, b) => b.s.ev! - a.s.ev!).slice(0, 3).map(({ g, s }) => ({
          key: `${g.game_id}-${s.team}`, label: "Moneyline", name: s.name, meta: `${g.label} · ${s.home ? "home" : "away"}`,
          value: <>{pct(s.prob, 0)} <em>{signedPct(s.ev!)} EV</em></>, caption: `${americanOdds(s.odds!)} at ${s.book}`,
        }))
    : tab === "projections"
      ? (filters.kind === "all" ? (["pass", "rush", "rec", "recs"] as Kind[]).map((k) => (projections.data ?? []).filter((p) => p.kind === k).sort((a, b) => b.mu - a.mu)[0])
        : [...(projections.data ?? [])].sort((a, b) => b.mu - a.mu).slice(0, 3)).filter(Boolean).map((p) => ({
        key: `${p.player_id}-${p.kind}`, label: filters.kind === "all" ? `Top ${KIND_LABEL[p.kind]}` : KIND_LABEL[p.kind], name: p.name, meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`,
        value: <>{fmtProj(p.kind, p.mu)} {p.kind !== "td" && <em>{fmtSd(p.kind, p.sd)}</em>}</>, caption: p.kind === "td" ? "chance to score" : isCount(p.kind) ? "projected receptions" : "projected yards",
        onClick: () => setSelected({ id: p.player_id, kind: p.kind }),
      }))
      // the moneyline beats a naive baseline but not the market, so it isn't held up as a "best" market
      : Object.entries(m.backtest).filter(([k]) => k !== "ml").map(([k, b]) => ({ k, b, gain: (b.mae_naive - b.mae_model) / b.mae_naive * 100 }))
        .sort((a, b) => b.gain - a.gain).slice(0, 3).map(({ k, b, gain }) => ({
          key: k, label: "Best backtested market", name: marketLabel(k), meta: `${b.n.toLocaleString()} games`,
          value: <>{gain.toFixed(1)}% <em>better</em></>, caption: "than the naive baseline",
        }));
  const weatherByGame = Object.fromEntries(m.games.map((g) => [g.game_id, g.weather]));
  const selectedGame = m.games.find((g) => g.game_id === filters.game);
  const hasOdds = Object.keys(m.odds).length > 0;
  const latestOdds = Object.values(m.odds).map((o) => o.fetched_at).sort().at(-1);

  return (
    <div className="wrap">
      <ThemeToggle />
      <header>
        <div>
          <h1><span className="logo">🏈</span> NFL Prop <span className="grad">Predictor</span></h1>
          <div className="sub">
            {m.run ? `${m.run.season} Week ${m.run.week} · projections ${timeAgo(m.run.created_at)}` : "No projections yet"}
            {latestOdds && ` · odds ${timeAgo(latestOdds)}`}
            {m.auto_sync?.enabled && m.auto_sync.next_at && ` · next update ${localWhen(m.auto_sync.next_at)}`}
          </div>
        </div>
        <div className="head-actions">
          {IS_STATIC && <div className="demo-tag" title="This page reads a saved snapshot, not a live server">Demo snapshot</div>}
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

      {!IS_STATIC && !m.run && <div className="banner">No projections yet. They appear after the next scheduled sync{m.auto_sync?.next_at ? ` (${localWhen(m.auto_sync.next_at)})` : ""}.</div>}
      {!IS_STATIC && m.run && !hasOdds && (tab === "picks" || tab === "parlays" || tab === "moneyline") && (
        <div className="banner">No sportsbook lines are loaded yet, so there are no picks. Books post props mid-week; the scheduled syncs fetch them as they appear.</div>
      )}

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>

      <TopTiles tiles={tiles} />

      {tab !== "model" && tab !== "parlays" && tab !== "moneyline" && <Controls filters={filters} onChange={setFilters} games={m.games} books={m.books} showPickControls={tab === "picks"} />}
      {(tab === "picks" || tab === "projections") && selectedGame && <GameWeather game={selectedGame} fit={m.weather} />}

      {tab === "picks" && (picks.isLoading ? <p className="mut">Pricing plays…</p> :
        <PicksTable picks={picks.data ?? []} weather={weatherByGame} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "parlays" && (parlaysLoading ? <p className="mut">Building parlays…</p> :
        <ParlayTiles books={books} book={activeBook} onBook={setParlayBook} games={m.games} selectedGames={chosenGames} onGames={setParlayGames} parlays={(activeBook && byBook[activeBook]) || []} tdParlays={tdParlays}
          ladders={[...ladderParlays, ...balancedLadders]} altProps={altProps} laddersLoading={ladderQueries.some((q) => q.isLoading)} />)}
      {tab === "moneyline" && (moneylines.isLoading ? <p className="mut">Pricing moneylines…</p> :
        <Moneylines games={moneylines.data ?? []} books={m.books} book={filters.book} marketWeight={filters.marketWeight}
          onBook={(b) => setFilters({ ...filters, book: b })} onMarketWeight={(w) => setFilters({ ...filters, marketWeight: w })} />)}
      {tab === "projections" && (projections.isLoading ? <p className="mut">Loading…</p> :
        <ProjectionsTable rows={projections.data ?? []} weather={weatherByGame} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "model" && <ModelCheck meta={m} />}

      <footer>
        Yards (and receptions) = volume × efficiency, recency-weighted and shrunk to position means, adjusted for opponent, game
        script and, at outdoor stadiums, kickoff wind and cold. Win probabilities come from the backtest's own error distribution, blended with the
        market's no-vig price. Team win chances come from point-margin ratings and lean heavily on the moneyline market. Large edges usually mean the model is missing context. Not betting advice.
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
