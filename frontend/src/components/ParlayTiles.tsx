import type { Game } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { americanOdds, pct, signedPct, KIND_LABEL } from "../format";
import { getLeague } from "../league";
import { pickToLeg, type Parlay, type ParlayLeg } from "../parlays";
import { toAmerican } from "../slip";
import Avatar from "./Avatar";
import GamePills from "./GamePills";
import { Star } from "./icons";
import Info from "./Info";
import SidePill from "./SidePill";

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
        <span className="tile-label">{lead && <Star />}{p.title}</span>
        <span className="mut">{p.legs.length} legs</span>
      </header>
      <div className="parlay-odds">{americanOdds(p.american)}<small>{p.sameGame ? "legs multiplied" : "combined odds"}</small></div>
      <dl className="parlay-stats">
        <div><dt>Hit chance <Info term="hit" /></dt><dd>{pct(p.prob, 0)}</dd></div>
        {p.sameGame
          // a same-game parlay is paid at the book's own price, not the legs multiplied, so an EV here would be made up
          ? <div><dt>Fair odds <Info term="fair" /></dt><dd>{americanOdds(toAmerican(1 / Math.max(p.prob, 1e-6)))}</dd></div>
          : <div><dt>Model EV <Info term="modelEv" /></dt><dd className={p.ev >= 0 ? "pos" : "under"}>{signedPct(p.ev)}</dd></div>}
        <div><dt>${STAKE} pays{p.sameGame ? ", legs multiplied" : ""}</dt><dd>${(STAKE * p.decimal).toFixed(2)}</dd></div>
      </dl>
      <ul className="parlay-legs">
        {p.legs.map((l) => (
          <li key={`${l.player_id}-${l.kind}-${l.side}-${l.line}`}>
            <Avatar name={l.name} size={26} />
            <span className="leg-main"><b>{l.name}</b> <SidePill kind={l.kind} side={l.side} line={l.line} />
              {l.alt && <span className="alt">alt</span>}
              <small>{`${KIND_LABEL[l.kind]} · `}{pct(l.prob, 0)} · {l.team} {l.home ? "vs" : "@"} {l.opp}</small></span>
            <span className="leg-odds">{americanOdds(l.odds)}</span>
          </li>
        ))}
      </ul>
      <p className="mut parlay-note">{p.blurb} Every leg is at {p.book}, so these are the odds you'd get there.
        {p.sameGame && " Some legs share a game: the hit chance counts how they move together (fitted on past games), but the book prices same-game parlays its own way, usually below the legs multiplied. Take it if the book's price beats the fair odds."}</p>
      <button className="primary" onClick={addAll} disabled={added}>{added ? "On your slip" : "Add all to slip"}</button>
    </article>
  );
}

/** The likeliest single alternate-line overs, each with a button to put just that prop on the slip. */
function AltProps({ props }: { props: ParlayLeg[] }) {
  const slip = useBetSlip();
  return (
    <section className="card altprops" aria-label="Likely alternate props">
      <ul className="parlay-legs">
        {props.map((l) => {
          const leg = pickToLeg(l);
          const on = slip.has(leg.id);
          return (
            <li key={leg.id}>
              <Avatar name={l.name} size={26} />
              <span className="leg-main"><b>{l.name}</b> <SidePill kind={l.kind} side={l.side} line={l.line} />{l.alt && <span className="alt">alt</span>}
                <small>{KIND_LABEL[l.kind]} · {l.team} {l.home ? "vs" : "@"} {l.opp}</small></span>
              <span className="leg-odds">{americanOdds(l.odds)}<small>{pct(l.prob, 0)} chance</small></span>
              <button className={`add ${on ? "on" : ""}`} onClick={() => slip.toggle(leg)} aria-label={on ? "Remove from slip" : "Add to slip"} aria-pressed={on}>{on ? "✓" : "+"}</button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Ladder tiles split into rows by type (mixed markets, threes only, both teams), in the order they came. */
function ladderRows(ladders: Parlay[], nba: boolean): { key: string; label: string; tiles: Parlay[] }[] {
  const type = (k: string) => (k.startsWith("threes-") ? "threes" : k.startsWith("both-") ? "both" : "mixed");
  const labels: Record<string, string> = { mixed: nba ? "Mixed markets" : "Rushing and receiving", threes: "Threes only", both: "Both teams" };
  const rows = new Map<string, Parlay[]>();
  for (const p of ladders) rows.set(type(p.key), [...(rows.get(type(p.key)) ?? []), p]);
  return [...rows].map(([key, tiles]) => ({ key, label: labels[key], tiles }));
}

interface Props {
  book: string | null;
  games: Game[]; selectedGames: string[];
  /** Omit to hide the game picker (a single game's page builds from that game only). */
  onGames?: (ids: string[]) => void;
  parlays: Parlay[]; tdParlays: Parlay[]; ladders: Parlay[]; altProps: ParlayLeg[]; laddersLoading: boolean;
  /** Likely-play parlays per book, and a way to switch book, so an empty section can point at a book that has some. */
  parlayCounts?: Record<string, number>;
  onBook?: (b: string) => void;
}

/** "Try DraftKings (3 parlays)": the book with the most likely-play parlays, as a button, when it isn't the one on screen. */
function TryBook({ book, counts, onBook }: { book: string | null; counts?: Record<string, number>; onBook?: (b: string) => void }) {
  const best = Object.entries(counts ?? {}).filter(([b, n]) => b !== book && n > 0).sort((a, b) => b[1] - a[1])[0];
  if (!best || !onBook) return null;
  return <> <button className="link" onClick={() => onBook(best[0])}>Try {best[0]} ({best[1]} parlay{best[1] === 1 ? "" : "s"})</button></>;
}

/** Recommended parlays at one sportsbook: tiles of high-probability plays, then ladder-style tiles, each with the combined odds. */
export default function ParlayTiles({ book, games, selectedGames, onGames, parlays, tdParlays, ladders, altProps, laddersLoading, parlayCounts, onBook }: Props) {
  const nba = getLeague() === "nba";
  const ladderMarkets = nba ? "points, rebounds, assists, threes, combos, steals and blocks" : "rushing and receiving";
  return (
    <>
      {onGames && <GamePills games={games} selected={selectedGames} onChange={onGames} multi label="Games to build from" />}

      <h2 className="parlay-h">Likely plays</h2>
      {parlays.length
        ? <section className="parlays" aria-label="Recommended parlays">{parlays.map((p, i) => <ParlayCard key={p.key} p={p} lead={i === 0} />)}</section>
        : <div className="card empty">Not enough likely plays at {book ?? "one sportsbook"} to build one. These need at least three high-probability plays from different players{selectedGames.length ? " in the selected games" : ""}.<TryBook book={book} counts={parlayCounts} onBook={onBook} /></div>}

      {!nba && <>
      <h2 className="parlay-h">Touchdowns <small>the likeliest anytime scorers, parlayed</small></h2>
      {tdParlays.length
        ? <section className="parlays" aria-label="Touchdown parlays">{tdParlays.map((p, i) => <ParlayCard key={p.key} p={p} lead={i === 0} />)}</section>
        : <div className="card empty">No anytime-TD prices at {book ?? "this sportsbook"} to parlay{selectedGames.length === 1 ? " for this game" : ""} yet. Books usually post them a day or two before kickoff.</div>}
      </>}

      <h2 className="parlay-h">Ladders <small>{ladderMarkets} overs stacked to +100 to +300</small></h2>
      {ladders.length
        ? ladderRows(ladders, nba).map((row, r, rows) => (
          <section key={row.key} aria-label={`${row.label} ladders`}>
            {rows.length > 1 && <h3 className="ladder-row-h">{row.label} <small>{row.tiles.length}</small></h3>}
            <div className="parlay-row">{row.tiles.map((p, i) => <ParlayCard key={p.key} p={p} lead={r === 0 && i === 0} />)}</div>
          </section>))
        : <div className="card empty">{laddersLoading ? "Loading alternate lines…" : `No ${ladderMarkets} over combinations with betslip links at ${book ?? "this sportsbook"} land between +100 and +300. ${nba ? "NBA alternate lines come with the day-of props syncs. " : ""}Not every book publishes links for alternate lines; try another book.`}</div>}

      {altProps.length > 0 && <>
        <h2 className="parlay-h">Likely alternate props <small>each player's likeliest linked over, on its own</small></h2>
        <AltProps props={altProps} />
      </>}

      <p className="td-note">Hit chance multiplies each leg's win probability (the model blended with the book's price){nba ? "" : ", except legs in the same game, which are priced with how they moved together in past games (Model check has the details)"}. Models miss context and parlays compound that: expect these to lose most of the time. Not betting advice.</p>
    </>
  );
}
