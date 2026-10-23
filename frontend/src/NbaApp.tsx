import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { api, type BacktestStat, type Filters, type Game, type InjuryReport, type Kind } from "./api";
import Logo from "./components/Logo";
import BetSlip from "./components/BetSlip";
import Controls from "./components/Controls";
import Games from "./components/Games";
import GradesCard from "./components/GradesCard";
import { GameInjuries } from "./components/Injuries";
import LeagueSwitch from "./components/LeagueSwitch";
import StateBooks from "./components/StateBooks";
import NbaGameOverview from "./components/NbaGameOverview";
import ParlayTiles from "./components/ParlayTiles";
import PicksTable from "./components/PicksTable";
import PlayerCompare from "./components/PlayerCompare";
import ProjectionsTable from "./components/ProjectionsTable";
import ThemeToggle from "./components/ThemeToggle";
import TopTiles, { type Tile } from "./components/TopTiles";
import { KIND_LABEL, NBA_KINDS, easternToday, isYesNo, americanOdds, fmtProj, fmtSd, matchup, playLabel, projCaption, signedPct, timeAgo } from "./format";
import { importOrReload } from "./staleChunk";
import { localWhen } from "./sync";
import { useDebounced } from "./useDebounced";
import { useParlayBoard } from "./useParlayBoard";

const PlayerDrawer = lazy(() => importOrReload(() => import("./components/PlayerDrawer")));

type Tab = "games" | "picks" | "parlays" | "injuries" | "projections" | "compare" | "check";
const TABS: [Tab, string][] = [["games", "Games"], ["picks", "Best props"], ["parlays", "Parlays"], ["injuries", "Injuries"], ["projections", "Projections"], ["compare", "Compare"],
  ["check", "Model check"]];
const gameFromHash = () => new URLSearchParams(window.location.hash.slice(1)).get("game");
const GAME_BOOK_KEY = "gameBook";
const PREFERRED_GAME_BOOK = "FanDuel";
const storedGameBook = () => { try { return localStorage.getItem(GAME_BOOK_KEY); } catch { return null; } };
/** "Tue Oct 20" from an Eastern date. */
const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

/** The NBA side: the next two game dates' moneylines, points/rebounds/assists props and projections, and injuries. */
export default function NbaApp() {
  const [tab, setTab] = useState<Tab>("games");
  const [gameId, setGameId] = useState<string | null>(gameFromHash);
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
  const setGameBook = (b: string) => { setGameBookState(b); try { localStorage.setItem(GAME_BOOK_KEY, b); } catch { /* not remembered */ } };
  // which game date to show: null follows today (or the next date with games), "all" shows both
  const [datePick, setDatePick] = useState<string | null>(null);

  // the drawer and ladder read ["meta"] from the cache, so the NBA meta lives under the same key (this league has its own cache)
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.nbaMeta });
  const gameOpen = !!gameId && (!meta.data || meta.data.games.some((g) => g.game_id === gameId));
  useEffect(() => {
    if (!gameId || !meta.data || meta.data.games.some((g) => g.game_id === gameId)) return;
    pushedGame.current = false;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setGameId(null);
  }, [gameId, meta.data]);
  const dates = useMemo(() => [...new Set((meta.data?.games ?? []).map((g) => g.gameday))].sort(), [meta.data]);
  const today = easternToday();
  const date = datePick === "all" || (datePick && dates.includes(datePick)) ? datePick : dates.includes(today) ? today : dates[0] ?? "all";
  const dateGames = useMemo(() => (meta.data?.games ?? []).filter((g) => date === "all" || g.gameday === date), [meta.data, date]);
  const pickDate = (d: string) => { setDatePick(d); setParlayGames([]); if (filters.game !== "all") setFilters({ ...filters, game: "all" }); };
  const datedFilters = useMemo(() => ({ ...filters, date: date === "all" ? undefined : date }), [filters, date]);
  const debounced = useDebounced(datedFilters, 250);
  const onSlate = tab === "games" && !gameOpen;
  const [parlayGames, setParlayGames] = useState<string[]>([]);
  const chosenGames = useMemo(() => parlayGames.filter((id) => dateGames.some((g) => g.game_id === id)), [parlayGames, dateGames]);
  const board = useParlayBoard(meta.data?.books ?? [], chosenGames, tab === "parlays" && !gameOpen, undefined,
    date === "all" ? undefined : dateGames.map((g) => g.game_id));
  const picks = useQuery({ queryKey: ["picks", debounced], queryFn: () => api.picks(debounced), enabled: tab === "picks", placeholderData: (p) => p });
  const slatePicks = useQuery({ queryKey: ["slate-picks", debounced.book, debounced.marketWeight],
    queryFn: () => api.picks({ ...debounced, kind: "all", side: "all", game: "all", q: "", minEv: 0, flagged: false, date: undefined }, 1000), enabled: onSlate });
  const moneylines = useQuery({ queryKey: ["moneylines", debounced.book, debounced.marketWeight], queryFn: () => api.moneylines(debounced.book, debounced.marketWeight),
    enabled: onSlate, placeholderData: (p) => p });
  const injuries = useQuery({ queryKey: ["injuries"], queryFn: api.injuries, enabled: tab === "injuries" || onSlate, refetchInterval: 15 * 60_000 });
  const projections = useQuery({ queryKey: ["projections", debounced], queryFn: () => api.projections(debounced), enabled: tab === "projections", placeholderData: (p) => p });

  if (meta.isLoading) return <div className="wrap"><p className="mut">Reaching equilibrium…</p></div>;
  if (meta.error || !meta.data) return (
    <div className="wrap">
      <header><h1><Logo /> <span>The Haber <span className="grad">Process</span></span></h1><div className="head-actions"><LeagueSwitch /></div></header>
      <p className="err">The reaction stalled: can't reach the NBA API right now. Try again in a minute.</p>
    </div>
  );
  const m = meta.data;
  const select = (id: string, kind: Kind) => setSelected({ id, kind });
  const tiles: Tile[] = tab === "picks"
    // by Kelly, not EV: EV makes a 1-point edge on a +2500 long shot look like the best play on the board
    ? [...(picks.data ?? [])].sort((a, b) => b.kelly - a.kelly).slice(0, 3).map((p) => ({
      key: `${p.player_id}-${p.kind}-${p.side}`, label: KIND_LABEL[p.kind], name: p.name, meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`,
      value: <>{playLabel(p.kind, p.side, p.line)} <em>{signedPct(p.ev)} EV</em></>, caption: `${americanOdds(p.odds)} at ${p.book}`,
      onClick: () => select(p.player_id, p.kind),
    }))
    : tab === "projections"
      ? (filters.kind === "all" ? NBA_KINDS.map((k) => (projections.data ?? []).filter((p) => p.kind === k).sort((a, b) => b.mu - a.mu)[0])
        : [...(projections.data ?? [])].sort((a, b) => b.mu - a.mu).slice(0, 3)).filter(Boolean).map((p) => ({
        key: `${p.player_id}-${p.kind}`, label: filters.kind === "all" ? `Top ${KIND_LABEL[p.kind].toLowerCase()}` : KIND_LABEL[p.kind], name: p.name,
        meta: `${p.pos} ${p.team} ${matchup(p.opp, p.home)}`, value: <>{fmtProj(p.kind, p.mu)} {!isYesNo(p.kind) && <em>{fmtSd(p.kind, p.sd)}</em>}</>, caption: projCaption(p.kind),
        onClick: () => select(p.player_id, p.kind),
      }))
      : [];
  const openedGame = gameId ? m.games.find((g) => g.game_id === gameId) : undefined;
  const pageBook = gameBook === "all" || m.books.includes(gameBook) ? gameBook : m.books.includes(PREFERRED_GAME_BOOK) ? PREFERRED_GAME_BOOK : m.books[0] ?? "all";
  const drawerBook = openedGame ? pageBook : filters.book;
  const setDrawerBook = (b: string) => (openedGame ? setGameBook(b) : setFilters({ ...filters, book: b }));
  const hasLines = Object.keys(m.odds).length > 0;
  const hasProps = NBA_KINDS.some((k) => m.odds[k]?.lines);
  const latestOdds = Object.values(m.odds).map((o) => o.fetched_at).sort().at(-1);
  const seasonLabel = m.run ? `${m.run.season - 1}-${String(m.run.season).slice(2)}` : "";

  return (
    <div className="wrap">
      <ThemeToggle />
      <header>
        <div>
          <h1><Logo /> <span>The Haber <span className="grad">Process</span></span></h1>
          <div className="sub">
            {m.run ? `${seasonLabel} · ${m.run.slate.map(day).join(" & ")} · projections ${timeAgo(m.run.created_at)}` : "No projections yet"}
            {latestOdds && ` · odds ${timeAgo(latestOdds)}`}
            {m.auto_sync?.enabled && m.auto_sync.next_at && ` · next update ${localWhen(m.auto_sync.next_at)}`}
          </div>
        </div>
        <div className="head-actions"><StateBooks /><LeagueSwitch /></div>
      </header>

      {!m.run && <div className="banner">No NBA projections yet. They appear after the next scheduled sync{m.auto_sync?.next_at ? ` (${localWhen(m.auto_sync.next_at)})` : ""}.</div>}
      {m.run && !hasLines && (tab === "games" || tab === "picks" || tab === "parlays") && (
        <div className="banner">{m.has_odds_key ? "No sportsbook lines are loaded yet. Moneylines come with every sync; player props are fetched the day of each game, once books post them."
          : "No NBA odds key is set (ODDS_API_KEY_NBA), so there are projections but no lines."}</div>
      )}
      {m.run && hasLines && !hasProps && (tab === "picks" || tab === "parlays") && (
        <div className="banner">Player props aren't loaded yet. They're fetched the day of each game (10 AM, 2 PM and 6 PM ET syncs).</div>
      )}

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => goTab(k)}>{label}</button>)}
      </nav>

      {openedGame ? (
        <NbaGameOverview key={openedGame.game_id} game={openedGame} books={m.books} book={pageBook} onBook={setGameBook} marketWeight={debounced.marketWeight}
          onBack={() => (pushedGame.current ? window.history.back() : openGame(null))} onSelect={select} />
      ) : <>
        {dates.length > 1 && tab !== "compare" && tab !== "check" && (
          <div className="date-filter">
            <select value={date} onChange={(e) => pickDate(e.target.value)} aria-label="Game date">
              {dates.map((d) => <option key={d} value={d}>{d === today ? `Today, ${day(d)}` : day(d)}</option>)}
              <option value="all">All dates</option>
            </select>
          </div>
        )}
        <TopTiles tiles={tiles} />
        {tab === "games" && <Games games={dateGames} picks={slatePicks.data ?? []} moneylines={moneylines.data ?? []} injuries={injuries.data} onOpen={openGame} />}
        {(tab === "picks" || tab === "projections") && <Controls filters={filters} onChange={setFilters} games={dateGames} books={m.books} showPickControls={tab === "picks"} />}
        {tab === "picks" && (picks.isLoading ? <p className="mut">Balancing the equation…</p> :
          <PicksTable picks={picks.data ?? []} onSelect={(p) => select(p.player_id, p.kind)} />)}
        {tab === "parlays" && (board.loading ? <p className="mut">Building parlays…</p> :
          <ParlayTiles books={m.books} book={board.book} onBook={board.setBook} games={dateGames} selectedGames={chosenGames} onGames={setParlayGames} parlays={board.parlays}
            tdParlays={board.tdParlays} ladders={board.ladders} altProps={board.altProps} laddersLoading={board.laddersLoading} />)}
        {tab === "injuries" && (injuries.isLoading ? <p className="mut">Loading the injury report…</p> : injuries.error || !injuries.data ? <p className="err">Couldn't load the injury report.</p> :
          <NbaInjuries report={injuries.data} games={dateGames} onSelect={select} />)}
        {tab === "projections" && (projections.isLoading ? <p className="mut">Loading…</p> :
          <ProjectionsTable nba rows={projections.data ?? []} onSelect={(p) => select(p.player_id, p.kind)} />)}
        {tab === "compare" && <PlayerCompare onSelect={select} />}
        {tab === "check" && <div className="stack"><GradesCard nba /><NbaBacktest backtest={m.backtest} /></div>}
      </>}

      <footer>
        Points, rebounds, assists, threes, steals and blocks = projected minutes × a per-minute rate, recency-weighted and shrunk toward the position's average, adjusted for
        the opponent; PRA, PR and PA are the sums of those projections. Double- and triple-double chances combine each stat's chance of
        reaching 10, calibrated on past games. Win probabilities come from the backtest's own errors (threes, steals and blocks: Poisson counts), blended with the market's no-vig price. Team win chances come from
        point-margin ratings and lean heavily on the moneyline market. Teammates' injuries don't move a player's projection yet. Not betting advice.
        <span className="signoff">Bread from air, picks from stats. Built by JD Haber.</span>
      </footer>

      {selected && (
        <Suspense fallback={null}>
          <PlayerDrawer playerId={selected.id} initialKind={selected.kind} marketWeight={debounced.marketWeight} book={drawerBook} onBookChange={setDrawerBook}
            onClose={() => setSelected(null)} />
        </Suspense>
      )}
      <BetSlip />
    </div>
  );
}

/** Every slate game's injury report from ESPN, both teams side by side. */
function NbaInjuries({ report, games, onSelect }: { report: InjuryReport; games: Game[]; onSelect: (id: string, kind: Kind) => void }) {
  const [game, setGame] = useState("all");
  const shown = games.filter((g) => game === "all" || g.game_id === game);
  return (
    <div className="stack">
      <section className="controls" aria-label="Injury filters">
        <div className="row">
          <select value={game} onChange={(e) => setGame(e.target.value)} aria-label="Game">
            <option value="all">All games</option>
            {games.map((g) => <option key={g.game_id} value={g.game_id}>{g.label}</option>)}
          </select>
        </div>
        <p className="td-note nba-note">
          <b>Out</b> players aren't projected. <b>Day-to-day</b> players are, and are often decided close to tip-off.
          {report.fetched_at && <> Checked {timeAgo(report.fetched_at)} (ESPN).</>} Players with projections link to them.
        </p>
      </section>
      {!shown.length ? <div className="card empty">No games on the slate.</div> : (
        <div className="inj-grid">{shown.map((g) => <GameInjuries key={g.game_id} game={g} report={report} onSelect={onSelect} />)}</div>
      )}
    </div>
  );
}

/** The walk-forward backtest from the latest run (app/nba/model.py): the model's average miss against a plain last-10 average. */
function NbaBacktest({ backtest }: { backtest: Record<string, BacktestStat> }) {
  const rows = NBA_KINDS.filter((k) => backtest[k]);
  if (!rows.length) return null;
  return (
    <div className="card prose">
      <h3>Backtest</h3>
      <p>Every game since last October, projected from only the games before its week. The books' lines are sharper than either column; the graded picks above are the real test.</p>
      <table className="calib" aria-label="NBA backtest">
        <thead><tr><th>Stat</th><th>Games</th><th>Model MAE</th><th>Last-10 MAE</th><th>Bias</th></tr></thead>
        <tbody>
          {rows.map((k) => {
            const b = backtest[k];
            const d = b.metric === "brier" ? 4 : 2;   // double-doubles: Brier score of the chance, against the player's last-10 rate
            return (
              <tr key={k}><td>{KIND_LABEL[k]}{b.metric === "brier" && <span className="mut"> (Brier)</span>}</td><td>{b.n.toLocaleString()}</td>
                <td className={b.mae_model <= b.mae_naive ? "good" : ""}>{b.mae_model.toFixed(d)}</td><td>{b.mae_naive.toFixed(d)}</td>
                <td>{b.bias >= 0 ? "+" : "−"}{Math.abs(b.bias).toFixed(d)}</td></tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
