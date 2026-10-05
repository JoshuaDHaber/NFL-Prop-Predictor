import { useBetSlip } from "../BetSlipContext";
import { americanOdds, pct, playLabel, signedPct, KIND_LABEL } from "../format";
import { pickToLeg, type Parlay } from "../parlays";
import Avatar from "./Avatar";

const STAKE = 10;

/** Recommended parlays: a few tiles of high-probability plays with the combined odds. */
export default function ParlayTiles({ byBook, book, onBook }: { byBook: Record<string, Parlay[]>; book: string | null; onBook: (b: string) => void }) {
  const slip = useBetSlip();
  const parlays = (book && byBook[book]) || [];
  if (!parlays.length) {
    return <div className="card empty">Not enough high-probability plays from different games at one sportsbook to build a parlay yet. Load sportsbook lines, then check back.</div>;
  }
  const addAll = (p: Parlay) => {
    p.legs.map(pickToLeg).filter((l) => !slip.has(l.id)).forEach(slip.toggle);
    slip.setOpen(true);
  };
  return (
    <>
      <div className="seg parlay-books" role="group" aria-label="Sportsbook">
        {Object.keys(byBook).sort().map((b) => (
          <button key={b} className={b === book ? "on" : ""} aria-pressed={b === book} onClick={() => onBook(b)}>{b}</button>
        ))}
      </div>
      <section className="parlays" aria-label="Recommended parlays">
        {parlays.map((p, i) => {
          const added = p.legs.every((l) => slip.has(pickToLeg(l).id));
          return (
            <article key={p.key} className={`parlay${i === 0 ? " lead" : ""}`}>
              <header>
                <span className="tile-label">{i === 0 ? "★ " : ""}{p.title}</span>
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
                  <li key={`${l.player_id}-${l.kind}-${l.side}`}>
                    <Avatar name={l.name} size={26} />
                    <span className="leg-main"><b>{l.name}</b> <span className={`side-pill ${l.side === "Over" ? "over" : "under"}`}>{playLabel(l.kind, l.side, l.line)}</span>
                      <small>{`${KIND_LABEL[l.kind]} · `}{pct(l.prob, 0)} · {l.team} {l.home ? "vs" : "@"} {l.opp}</small></span>
                    <span className="leg-odds">{americanOdds(l.odds)}</span>
                  </li>
                ))}
              </ul>
              <p className="mut parlay-note">{p.blurb} Every leg is at {p.book}, so these are the odds you'd get there.</p>
              <button className="primary" onClick={() => addAll(p)} disabled={added}>{added ? "On your slip" : "Add all to slip"}</button>
            </article>
          );
        })}
      </section>
      <p className="td-note">Hit chance multiplies each leg's blended win probability, one leg per game so the legs are independent. Each book's plays are priced at that book only. Models miss context and parlays compound that: expect these to lose most of the time. Not betting advice.</p>
    </>
  );
}
