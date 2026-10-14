import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type Game, type Kind, type WeatherFit } from "../api";
import { KIND_SHORT } from "../format";
import { PARLAY_FILTERS, useParlayBoard } from "../useParlayBoard";
import GameWeather from "./GameWeather";
import { GameInjuries } from "./Injuries";
import { MoneylineCard } from "./Moneylines";
import ParlayTiles from "./ParlayTiles";
import PicksTable from "./PicksTable";
import ProjectionsTable from "./ProjectionsTable";

interface Props {
  game: Game;
  books: string[];
  book: string;
  marketWeight: number;
  fit?: WeatherFit | null;
  onBack: () => void;
  onSelect: (id: string, kind: Kind) => void;
}

const KINDS: (Kind | "all")[] = ["all", "rush", "rec", "recs", "pass", "rr", "td"];
const SECTIONS: [string, string][] = [["go-props", "Best props"], ["go-parlays", "Parlays"], ["go-proj", "Projections"], ["go-inj", "Injuries"]];
/** Props shown before "Show all". */
const PROPS_SHOWN = 8;

function KindSeg({ value, onChange }: { value: Kind | "all"; onChange: (k: Kind | "all") => void }) {
  return (
    <div className="seg small" role="group" aria-label="Market">
      {KINDS.map((k) => <button key={k} className={value === k ? "on" : ""} aria-pressed={value === k} onClick={() => onChange(k)}>{k === "all" ? "All" : KIND_SHORT[k]}</button>)}
    </div>
  );
}

/** Everything about one game on a single page: weather, win chances, its best props and parlays, projections and both injury reports. */
export default function GameOverview({ game, books, book, marketWeight, fit, onBack, onSelect }: Props) {
  const id = game.game_id;
  const [propKind, setPropKind] = useState<Kind | "all">("all");
  const [projKind, setProjKind] = useState<Kind | "all">("all");
  const [allProps, setAllProps] = useState(false);
  const [showReserve, setShowReserve] = useState(false);

  const moneylines = useQuery({ queryKey: ["moneylines", book, marketWeight], queryFn: () => api.moneylines(book, marketWeight) });
  const injuries = useQuery({ queryKey: ["injuries"], queryFn: api.injuries, refetchInterval: 15 * 60_000 });
  const picks = useQuery({
    queryKey: ["game-picks", id, propKind, book, marketWeight],
    queryFn: () => api.picks({ ...PARLAY_FILTERS, kind: propKind, game: id, book, marketWeight, minEv: 0 }, 300),
    placeholderData: (p) => p,
  });
  const projections = useQuery({
    queryKey: ["game-projections", id, projKind],
    queryFn: () => api.projections({ ...PARLAY_FILTERS, kind: projKind, game: id }),
    placeholderData: (p) => p,
  });
  const chosen = useMemo(() => [id], [id]);
  const board = useParlayBoard(books, chosen, true);

  const ml = moneylines.data?.find((g) => g.game_id === id);
  const shownPicks = allProps ? picks.data ?? [] : (picks.data ?? []).slice(0, PROPS_SHOWN);
  const jump = (el: string) => document.getElementById(el)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="stack go">
      <div className="go-head">
        <button className="link go-back" onClick={onBack}>← All games</button>
        <nav className="go-jump" aria-label="Jump to section">
          {SECTIONS.map(([el, label]) => <button key={el} onClick={() => jump(el)}>{label}</button>)}
        </nav>
      </div>

      <div className="go-top">
        <GameWeather game={game} fit={fit} />
        {ml ? <MoneylineCard g={ml} /> : moneylines.isLoading ? null : <div className="card empty">No win chances for this game yet.</div>}
      </div>

      <section id="go-props" className="go-sec">
        <h2 className="parlay-h">Best props <small>positive EV for this game{book !== "all" ? ` at ${book}` : ""}</small></h2>
        <KindSeg value={propKind} onChange={(k) => { setPropKind(k); setAllProps(false); }} />
        {picks.isLoading ? <p className="mut">Pricing plays…</p> : <>
          <PicksTable picks={shownPicks} weather={{ [id]: game.weather }} empty="No positive-EV props for this game yet. Books post props mid-week; the scheduled syncs pick them up." onSelect={(p) => onSelect(p.player_id, p.kind)} />
          {(picks.data?.length ?? 0) > PROPS_SHOWN && (
            <button className="link go-more" onClick={() => setAllProps(!allProps)}>{allProps ? "Show fewer" : `Show all ${picks.data!.length} props`}</button>
          )}
        </>}
      </section>

      <section id="go-parlays" className="go-sec">
        <h2 className="parlay-h">Parlays <small>built from this game only</small></h2>
        {board.loading ? <p className="mut">Building parlays…</p> :
          <ParlayTiles books={books} book={board.book} onBook={board.setBook} games={[game]} selectedGames={chosen} parlays={board.parlays}
            tdParlays={board.tdParlays} ladders={board.ladders} altProps={board.altProps} laddersLoading={board.laddersLoading} />}
      </section>

      <section id="go-proj" className="go-sec">
        <h2 className="parlay-h">Projections</h2>
        <KindSeg value={projKind} onChange={setProjKind} />
        {projections.isLoading ? <p className="mut">Loading…</p> :
          <ProjectionsTable rows={projections.data ?? []} weather={{ [id]: game.weather }} onSelect={(p) => onSelect(p.player_id, p.kind)} />}
      </section>

      <section id="go-inj" className="go-sec">
        <h2 className="parlay-h">Injuries <label className="check go-reserve"><input type="checkbox" checked={showReserve} onChange={(e) => setShowReserve(e.target.checked)} /> Show IR / PUP</label></h2>
        {injuries.isLoading ? <p className="mut">Loading the injury report…</p> : injuries.error || !injuries.data ? <p className="err">Couldn't load the injury report.</p> :
          <GameInjuries game={game} report={injuries.data} showReserve={showReserve} onSelect={onSelect} />}
      </section>
    </div>
  );
}
