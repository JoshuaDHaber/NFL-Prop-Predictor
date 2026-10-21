import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { api, type Filters, type Kind } from "./api";
import Logo from "./components/Logo";
import BetSlip from "./components/BetSlip";
import Controls from "./components/Controls";
import GameOverview from "./components/GameOverview";
import GameWeather from "./components/GameWeather";
import Games from "./components/Games";
import Injuries from "./components/Injuries";
import ModelCheck from "./components/ModelCheck";
import ParlayTiles from "./components/ParlayTiles";
import PicksTable from "./components/PicksTable";
import PlayerCompare from "./components/PlayerCompare";
import ProjectionsTable from "./components/ProjectionsTable";
import { BASE } from "./env";
import { isYesNo, KIND_LABEL, americanOdds, fmtProj, fmtSd, marketLabel, projCaption, matchup, playLabel, signedPct, timeAgo } from "./format";
import ThemeToggle from "./components/ThemeToggle";
import LeagueSwitch from "./components/LeagueSwitch";
import { useLeague } from "./LeagueContext";
import TopTiles, { type Tile } from "./components/TopTiles";
import { importOrReload } from "./staleChunk";
import { localWhen } from "./sync";
import { useDebounced } from "./useDebounced";
import { PARLAY_FILTERS, useParlayBoard } from "./useParlayBoard";

// keeps the charting library out of the first load; a tab left open across a deploy reloads to the new build
const PlayerDrawer = lazy(() => importOrReload(() => import("./components/PlayerDrawer")));
const AdminPage = lazy(() => importOrReload(() => import("./components/AdminPage")));
const NbaApp = lazy(() => importOrReload(() => import("./NbaApp")));
/** The owner's sync page lives at <base>/admin; everything else is the public app. */
const IS_ADMIN_PAGE = window.location.pathname.slice(BASE.length - 1).replace(/\/+$/, "") === "/admin";

type Tab = "games" | "picks" | "parlays" | "injuries" | "projections" | "compare" | "model" | "admin";
const TABS: [Tab, string][] = [["games", "Games"], ["picks", "Best props"], ["parlays", "Parlays"], ["injuries", "Injuries"], ["projections", "Projections"], ["compare", "Compare"], ["model", "Model check"], ["admin", "Admin"]];
/** A game's overview page lives at #game=<game_id>, so the browser's back button returns to the slate and the page can be linked. */
const gameFromHash = () => new URLSearchParams(window.location.hash.slice(1)).get("game");
/** The game page's sportsbook, remembered in this browser. */
const GAME_BOOK_KEY = "gameBook";
const PREFERRED_GAME_BOOK = "FanDuel";
const storedGameBook = () => { try { return localStorage.getItem(GAME_BOOK_KEY); } catch { return null; } };

export default function App() {
  const { league } = useLeague();
  if (IS_ADMIN_PAGE) return <Suspense fallback={null}><AdminPage /></Suspense>;
  return league === "nba" ? <Suspense fallback={<div className="wrap"><p className="mut">Reaching equilibrium…</p></div>}><NbaApp /></Suspense> : <PublicApp />;
}

function PublicApp() {
  const [tab, setTab] = useState<Tab>("games");
  const [gameId, setGameId] = useState<string | null>(gameFromHash);
  // true while a game page sits on top of the slate in history, so "All games" can go back instead of stacking another entry
  const pushedGame = useRef(false);
  useEffect(() => {
    const sync = () => { const id = gameFromHash(); pushedGame.current = !!id; setGameId(id); if (id) setTab("games"); };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  const openGame = (id: string | null) => {
    if (id === gameId) return;
    pushedGame.current = !!id;
    const url = window.location.pathname + window.location.search + (id ? `#game=${encodeURIComponent(id)}` : "");
    if (id) window.history.pushState(null, "", url); else window.history.replaceState(null, "", url);
    setGameId(id);
    window.scrollTo({ top: 0 });
  };
  const goTab = (t: Tab) => { openGame(null); setTab(t); };
  const [filters, setFilters] = useState<Filters>({ kind: "all", side: "all", game: "all", book: "all", q: "", minEv: 0.03, marketWeight: 0.35, flagged: false });
  const [selected, setSelected] = useState<{ id: string; kind: Kind } | null>(null);
  const [gameBook, setGameBookState] = useState<string>(() => storedGameBook() ?? PREFERRED_GAME_BOOK);
  const setGameBook = (b: string) => { setGameBookState(b); try { localStorage.setItem(GAME_BOOK_KEY, b); } catch { /* private mode: not remembered */ } };
  const debounced = useDebounced(filters, 250);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  // a game page counts as open only for a game still on the slate (assumed so until the slate loads)
  const gameOpen = !!gameId && (!meta.data || meta.data.games.some((g) => g.game_id === gameId));
  // an old link (#game=<a game no longer on the slate>) drops the hash and lands on the slate
  useEffect(() => {
    if (!gameId || !meta.data || meta.data.games.some((g) => g.game_id === gameId)) return;
    pushedGame.current = false;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setGameId(null);
  }, [gameId, meta.data]);
  const picks = useQuery({ queryKey: ["picks", debounced], queryFn: () => api.picks(debounced), enabled: tab === "picks", placeholderData: (p) => p });
  const [parlayGames, setParlayGames] = useState<string[]>([]);
  // only games still on the slate count; every parlay and ladder is built from the chosen games' picks
  const chosenGames = useMemo(() => parlayGames.filter((id) => meta.data?.games.some((g) => g.game_id === id)), [parlayGames, meta.data]);
  const board = useParlayBoard(meta.data?.books ?? [], chosenGames, tab === "parlays" && !gameOpen);
  // positive-EV plays across the slate, for the game tiles' top prop and counts
  const slatePicks = useQuery({ queryKey: ["slate-picks", debounced.book, debounced.marketWeight],
    queryFn: () => api.picks({ ...PARLAY_FILTERS, book: debounced.book, marketWeight: debounced.marketWeight, minEv: 0 }, 1000), enabled: tab === "games" && !gameOpen });
  const moneylines = useQuery({ queryKey: ["moneylines", debounced.book, debounced.marketWeight], queryFn: () => api.moneylines(debounced.book, debounced.marketWeight),
    enabled: tab === "games" && !gameOpen, placeholderData: (p) => p });
  const injuries = useQuery({ queryKey: ["injuries"], queryFn: api.injuries, enabled: tab === "injuries" || (tab === "games" && !gameOpen), refetchInterval: 15 * 60_000 });
  const projections = useQuery({ queryKey: ["projections", debounced], queryFn: () => api.projections(debounced), enabled: tab === "projections", placeholderData: (p) => p });

  if (meta.isLoading) return (
    <div className="wrap">
      <p className="mut">Reaching equilibrium…</p>
    </div>
  );
  if (meta.error || !meta.data) return (
    <div className="wrap">
      <p className="err">{window.location.hostname === "localhost" ? "Can't reach the API. Is the backend running on port 8000?" : "The reaction stalled: can't reach the API right now. Try again in a minute."}</p>
    </div>
  );
  const m = meta.data;
  const tiles: Tile[] = tab === "picks"
    ? [...(picks.data ?? [])].sort((a, b) => b.ev - a.ev).slice(0, 3).map((p) => ({
      key: `${p.player_id}-${p.kind}-${p.side}`, label: KIND_LABEL[p.kind], name: p.name, meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`,
      value: <>{playLabel(p.kind, p.side, p.line)} <em>{signedPct(p.ev)} EV</em></>, caption: `${americanOdds(p.odds)} at ${p.book}`,
      onClick: () => setSelected({ id: p.player_id, kind: p.kind }),
    }))
    : tab === "games" || tab === "parlays" || tab === "admin" || tab === "injuries" || tab === "compare" ? []
    : tab === "projections"
      ? (filters.kind === "all" ? (["pass", "rush", "rec", "recs"] as Kind[]).map((k) => (projections.data ?? []).filter((p) => p.kind === k).sort((a, b) => b.mu - a.mu)[0])
        : [...(projections.data ?? [])].sort((a, b) => b.mu - a.mu).slice(0, 3)).filter(Boolean).map((p) => ({
        key: `${p.player_id}-${p.kind}`, label: filters.kind === "all" ? `Top ${KIND_LABEL[p.kind]}` : KIND_LABEL[p.kind], name: p.name, meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`,
        value: <>{fmtProj(p.kind, p.mu)} {!isYesNo(p.kind) && <em>{fmtSd(p.kind, p.sd)}</em>}</>, caption: projCaption(p.kind),
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
  const openedGame = gameId ? m.games.find((g) => g.game_id === gameId) : undefined;
  // a remembered book that has no lines this week falls back to FanDuel, then the first book loaded
  const pageBook = gameBook === "all" || m.books.includes(gameBook) ? gameBook
    : m.books.includes(PREFERRED_GAME_BOOK) ? PREFERRED_GAME_BOOK : m.books[0] ?? "all";
  // the player drawer follows the game page's book while one is open, else the tabs' filter
  const drawerBook = openedGame ? pageBook : filters.book;
  const setDrawerBook = (b: string) => (openedGame ? setGameBook(b) : setFilters({ ...filters, book: b }));
  const hasOdds = Object.keys(m.odds).length > 0;
  const latestOdds = Object.values(m.odds).map((o) => o.fetched_at).sort().at(-1);

  return (
    <div className="wrap">
      <ThemeToggle />
      <header>
        <div>
          <h1><Logo /> <span>The Haber <span className="grad">Process</span></span></h1>
          <div className="sub">
            {m.run ? `${m.run.season} Week ${m.run.week} · projections ${timeAgo(m.run.created_at)}` : "No projections yet"}
            {latestOdds && ` · odds ${timeAgo(latestOdds)}`}
            {m.auto_sync?.enabled && m.auto_sync.next_at && ` · next update ${localWhen(m.auto_sync.next_at)}`}
          </div>
        </div>
        <div className="head-actions">
          <LeagueSwitch />
        </div>
      </header>

      {!m.run && <div className="banner">No projections yet. They appear after the next scheduled sync{m.auto_sync?.next_at ? ` (${localWhen(m.auto_sync.next_at)})` : ""}.</div>}
      {m.run && !hasOdds && (tab === "games" || tab === "picks" || tab === "parlays") && (
        <div className="banner">No sportsbook lines are loaded yet, so there are no picks. Books post props mid-week; the scheduled syncs fetch them as they appear.</div>
      )}

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => goTab(k)}>{label}</button>
        ))}
      </nav>

      {openedGame ? (
        <GameOverview key={openedGame.game_id} game={openedGame} books={m.books} book={pageBook} onBook={setGameBook} marketWeight={debounced.marketWeight} fit={m.weather}
          onBack={() => (pushedGame.current ? window.history.back() : openGame(null))}
          onSelect={(id, kind) => setSelected({ id, kind })} />
      ) : <>
      <TopTiles tiles={tiles} />

      {tab === "games" && <Games games={m.games} picks={slatePicks.data ?? []} moneylines={moneylines.data ?? []} injuries={injuries.data} onOpen={openGame} />}
      {tab !== "games" && tab !== "model" && tab !== "parlays" && tab !== "admin" && tab !== "injuries" && tab !== "compare" && <Controls filters={filters} onChange={setFilters} games={m.games} books={m.books} showPickControls={tab === "picks"} />}
      {(tab === "picks" || tab === "projections") && selectedGame && <GameWeather game={selectedGame} fit={m.weather} />}

      {tab === "picks" && (picks.isLoading ? <p className="mut">Balancing the equation…</p> :
        <PicksTable picks={picks.data ?? []} weather={weatherByGame} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "parlays" && (board.loading ? <p className="mut">Building parlays…</p> :
        <ParlayTiles books={m.books} book={board.book} onBook={board.setBook} games={m.games} selectedGames={chosenGames} onGames={setParlayGames} parlays={board.parlays} tdParlays={board.tdParlays}
          ladders={board.ladders} altProps={board.altProps} laddersLoading={board.laddersLoading} />)}
      {tab === "injuries" && (injuries.isLoading ? <p className="mut">Loading the injury report…</p> : injuries.error ? <p className="err">Couldn't load the injury report.</p> :
        <Injuries report={injuries.data!} games={m.games} onSelect={(id, kind) => setSelected({ id, kind })} />)}
      {tab === "projections" && (projections.isLoading ? <p className="mut">Loading…</p> :
        <ProjectionsTable rows={projections.data ?? []} weather={weatherByGame} onSelect={(p) => setSelected({ id: p.player_id, kind: p.kind })} />)}
      {tab === "compare" && <PlayerCompare weather={weatherByGame} onSelect={(id, kind) => setSelected({ id, kind })} />}
      {tab === "model" && <ModelCheck meta={m} />}
      {tab === "admin" && <Suspense fallback={<p className="mut">Loading…</p>}><AdminPage embedded /></Suspense>}
      </>}

      <footer>
        Yards (and receptions) = volume × efficiency, recency-weighted and shrunk to position means, adjusted for opponent, game
        script and, at outdoor stadiums, kickoff wind and cold. Win probabilities come from the backtest's own error distribution, blended with the
        market's no-vig price. Team win chances come from point-margin ratings and lean heavily on the moneyline market. Large edges usually mean the model is missing context. Not betting advice.
        <span className="signoff">Bread from air, picks from stats. Built by JD Haber.</span>
      </footer>

      {selected && (
        <Suspense fallback={null}>
          <PlayerDrawer playerId={selected.id} initialKind={selected.kind} marketWeight={debounced.marketWeight}
            book={drawerBook} onBookChange={setDrawerBook}
            onClose={() => setSelected(null)} />
        </Suspense>
      )}
      <BetSlip />
    </div>
  );
}
