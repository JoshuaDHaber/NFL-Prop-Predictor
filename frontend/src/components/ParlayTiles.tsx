import { useBetSlip } from "../BetSlipContext";
import { americanOdds, pct, playLabel, signedPct, KIND_LABEL } from "../format";
import { pickToLeg, type Parlay } from "../parlays";
import Avatar from "./Avatar";

const STAKE = 10;

function ParlayCard({ p, lead }: { p: Parlay; lead: boolean }) {
  const slip = useBetSlip();
  const added = p.legs.every((l) => slip.has(pickToLeg(l).id));
  const addAll = () => {
    p.legs.map(pickToLeg).filter((l) => !slip.has(l.id)).forEach(slip.toggle);
    slip.setOpen(true);
  };
  return (
    <article className={`parlay${lead ? " lead" : ""}`}>
      <header>
        <span className="tile-label">{lead ? "★ " : ""}{p.title}</span>
        <span className="mut">{p.legs.length} legs</span>
      </header>
      <div className="parlay-odds">{americanOdds(p.american)}<small>combined odds</small></div>
      <dl className="parlay-stats">
        <div><dt>Hit chance</dt><dd>{pct(p.prob, 0)}</dd></div>
        <div><dt>Model EV</dt><dd className={p.ev >= 0 ? "pos" : "under"}>{signedPct(p.ev)}</dd></div>
        <div><dt>${STAKE} pays</dt><dd>${(STAKE * p.decimal).toFixed(2)}</dd></div>
      </dl>
      <ul className="parlay-legs">
        {p.legs.map((l) => (
          <li key={`${l.player_id}-${l.kind}-${l.side}-${l.line}`}>
            <Avatar name={l.name} size={26} />
            <span className="leg-main"><b>{l.name}</b> <span className={`side-pill ${l.side === "Over" ? "over" : "under"}`}>{playLabel(l.kind, l.side, l.line)}</span>
              {l.alt && <span className="alt">alt</span>}
              <small>{`${KIND_LABEL[l.kind]} · `}{pct(l.prob, 0)} · {l.team} {l.home ? "vs" : "@"} {l.opp}</small></span>
            <span className="leg-odds">{americanOdds(l.odds)}</span>
          </li>
        ))}
      </ul>
      <p className="mut parlay-note">{p.blurb} Every leg is at {p.book}, so these are the odds you'd get there.
        {p.sameGame && " Some legs share a game, and their correlation isn't modelled."}</p>
      <button className="primary" onClick={addAll} disabled={added}>{added ? "On your slip" : "Add all to slip"}</button>
    </article>
  );
}

interface Props {
  books: string[]; book: string | null; onBook: (b: string) => void;
  parlays: Parlay[]; ladders: Parlay[]; laddersLoading: boolean;
}

/** Recommended parlays at one sportsbook: tiles of high-probability plays, then ladder-style tiles, each with the combined odds. */
export default function ParlayTiles({ books, book, onBook, parlays, ladders, laddersLoading }: Props) {
  return (
    <>
      <div className="seg parlay-books" role="group" aria-label="Sportsbook">
        {books.map((b) => (
          <button key={b} className={b === book ? "on" : ""} aria-pressed={b === book} onClick={() => onBook(b)}>{b}</button>
        ))}
      </div>

      <h2 className="parlay-h">Likely plays</h2>
      {parlays.length
        ? <section className="parlays" aria-label="Recommended parlays">{parlays.map((p, i) => <ParlayCard key={p.key} p={p} lead={i === 0} />)}</section>
        : <div className="card empty">Not enough likely plays from different games at {book ?? "one sportsbook"} to build one. These take one leg per game, so they need a few games on the slate.</div>}

      <h2 className="parlay-h">Ladders <small>rushing and receiving overs stacked to +100 to +300</small></h2>
      {ladders.length
        ? <section className="parlays" aria-label="Ladder parlays">{ladders.map((p, i) => <ParlayCard key={p.key} p={p} lead={i === 0} />)}</section>
        : <div className="card empty">{laddersLoading ? "Loading alternate lines…" : `No rushing or receiving over combinations at ${book ?? "this sportsbook"} land between +100 and +300. Try another book.`}</div>}

      <p className="td-note">Hit chance multiplies each leg's win probability (the model blended with the book's price). Models miss context and parlays compound that: expect these to lose most of the time. Not betting advice.</p>
    </>
  );
}
