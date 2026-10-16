import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type Game, type Kind, type NbaKind } from "../api";
import { KIND_SHORT, NBA_KINDS } from "../format";
import { useParlayBoard } from "../useParlayBoard";
import { GameInjuries } from "./Injuries";
import { MoneylineCard } from "./Moneylines";
import ParlayTiles from "./ParlayTiles";
import PicksTable from "./PicksTable";
import ProjectionsTable from "./ProjectionsTable";

interface Props {
  game: Game;
  books: string[];
  /** The page's sportsbook ("all" = best price anywhere): props and the moneyline follow it. */
  book: string;
  onBook: (book: string) => void;
  marketWeight: number;
  onBack: () => void;
  onSelect: (id: string, kind: Kind) => void;
}

const SECTIONS: [string, string][] = [["go-props", "Best props"], ["go-parlays", "Parlays"], ["go-proj", "Projections"], ["go-inj", "Injuries"]];
const PROPS_SHOWN = 8;

function KindSeg({ value, onChange }: { value: NbaKind | "all"; onChange: (k: NbaKind | "all") => void }) {
  return (
    <div className="seg small" role="group" aria-label="Stat">
      {(["all", ...NBA_KINDS] as const).map((k) => (
        <button key={k} className={value === k ? "on" : ""} aria-pressed={value === k} onClick={() => onChange(k)}>{k === "all" ? "All" : KIND_SHORT[k]}</button>
      ))}
    </div>
  );
}

/** One NBA game on a page: win chances and moneylines, its best props, projections and both teams' injuries. */
export default function NbaGameOverview({ game, books, book, onBook, marketWeight, onBack, onSelect }: Props) {
  const id = game.game_id;
  const [propKind, setPropKind] = useState<NbaKind | "all">("all");
  const [projKind, setProjKind] = useState<NbaKind | "all">("pts");
  const [allProps, setAllProps] = useState(false);
  const base = { side: "all", game: id, book, q: "", minEv: 0, marketWeight, flagged: false } as const;

  const moneylines = useQuery({ queryKey: ["moneylines", book, marketWeight], queryFn: () => api.moneylines(book, marketWeight) });
  const injuries = useQuery({ queryKey: ["injuries"], queryFn: api.injuries, refetchInterval: 15 * 60_000 });
  const picks = useQuery({ queryKey: ["game-picks", id, propKind, book, marketWeight], queryFn: () => api.picks({ ...base, kind: propKind }, 300), placeholderData: (p) => p });
  const projections = useQuery({ queryKey: ["game-projections", id, projKind], queryFn: () => api.projections({ ...base, kind: projKind }), placeholderData: (p) => p });

  const chosen = useMemo(() => [id], [id]);
  // parlays need one book; with "all books" they fall back to the board's own default
  const board = useParlayBoard(books, chosen, true, book === "all" ? undefined : book);
  const ml = moneylines.data?.find((g) => g.game_id === id);
  const shownPicks = allProps ? picks.data ?? [] : (picks.data ?? []).slice(0, PROPS_SHOWN);
  const jump = (el: string) => document.getElementById(el)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="stack go">
      <div className="go-head">
        <button className="link go-back" onClick={onBack}>← All games</button>
        <label className="go-book">
          <span className="mut">Sportsbook</span>
          <select value={book} onChange={(e) => onBook(e.target.value)} aria-label="Sportsbook for this page">
            {books.map((b) => <option key={b} value={b}>{b}</option>)}
            <option value="all">All books (best price)</option>
          </select>
        </label>
        <nav className="go-jump" aria-label="Jump to section">
          {SECTIONS.map(([el, label]) => <button key={el} onClick={() => jump(el)}>{label}</button>)}
        </nav>
      </div>

      {ml ? <MoneylineCard g={ml} /> : moneylines.isLoading ? null : <div className="card empty">No win chances for this game yet.</div>}

      <section id="go-props" className="go-sec">
        <h2 className="parlay-h">Best props <small>positive EV for this game{book !== "all" ? ` at ${book}` : ""}</small></h2>
        <KindSeg value={propKind} onChange={(k) => { setPropKind(k); setAllProps(false); }} />
        {picks.isLoading ? <p className="mut">Pricing plays…</p> : <>
          <PicksTable picks={shownPicks} empty="No positive-EV props for this game yet. Books post NBA props the day of the game; the 10 AM, 2 PM and 6 PM ET syncs pick them up."
            onSelect={(p) => onSelect(p.player_id, p.kind)} />
          {(picks.data?.length ?? 0) > PROPS_SHOWN && (
            <button className="link go-more" onClick={() => setAllProps(!allProps)}>{allProps ? "Show fewer" : `Show all ${picks.data!.length} props`}</button>
          )}
        </>}
      </section>

      <section id="go-parlays" className="go-sec">
        <h2 className="parlay-h">Parlays <small>built from this game only{board.book ? `, every leg at ${board.book}` : ""}</small></h2>
        {board.loading ? <p className="mut">Building parlays…</p> :
          <ParlayTiles books={books} book={board.book} games={[game]} selectedGames={chosen} parlays={board.parlays}
            tdParlays={board.tdParlays} ladders={board.ladders} altProps={board.altProps} laddersLoading={board.laddersLoading} />}
      </section>

      <section id="go-proj" className="go-sec">
        <h2 className="parlay-h">Projections</h2>
        <KindSeg value={projKind} onChange={setProjKind} />
        {projections.isLoading ? <p className="mut">Loading…</p> :
          <ProjectionsTable nba rows={projections.data ?? []} onSelect={(p) => onSelect(p.player_id, p.kind)} />}
      </section>

      <section id="go-inj" className="go-sec">
        <h2 className="parlay-h">Injuries <small>from ESPN; Out players aren't projected</small></h2>
        {injuries.isLoading ? <p className="mut">Loading the injury report…</p> : injuries.error || !injuries.data ? <p className="err">Couldn't load the injury report.</p> :
          <GameInjuries game={game} report={injuries.data} onSelect={onSelect} />}
      </section>
    </div>
  );
}
