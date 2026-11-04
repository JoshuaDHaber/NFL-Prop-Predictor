import type { MoneylineGame, MoneylineSide, TeamRecord } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { americanOdds, kickoff, pct, signedPct } from "../format";
import { started, sidePick } from "../moneyline";
import { pickToLeg, type ParlayLeg } from "../parlays";
import { legLink } from "../slip";
import { matchupColors, shadeVars } from "../teams";
import { BookName } from "./BookBadge";

/** "LV by 3.0" from a home margin; "Pick'em" near zero. */
export function favored(g: MoneylineGame, m: number, digits = 1) {
  const [away, home] = g.sides;
  return Math.abs(m) < 0.05 ? "Pick'em" : `${(m > 0 ? home : away).team} by ${Math.abs(m).toFixed(digits)}`;
}

/** Put a team's moneyline on the slip, or take it off. Both teams' moneylines in one game at one book clash, as a book won't
 *  take both; the button says so instead of hiding it. */
export function MoneylineAdd({ pick }: { pick: ParlayLeg | null }) {
  const slip = useBetSlip();
  if (!pick) return null;
  const leg = pickToLeg(pick);
  const on = slip.has(leg.id);
  const clash = !on && slip.wouldClash(leg);
  const what = `${pick.name} moneyline at ${pick.book}`;
  return (
    <button type="button" className={`add${on ? " on" : ""}${clash ? " clash" : ""}`} onClick={() => slip.toggle(leg)} aria-pressed={on}
      title={clash ? `The other side of this game is already on your slip at ${pick.book}: a book won't take both` : on ? "On your slip" : "Add to slip"}
      aria-label={on ? `Remove ${what} from slip` : clash ? `Add ${what} to slip. The other side of this game is already on your slip there` : `Add ${what} to slip`}>
      {on ? "✓" : "+"}
    </button>
  );
}

function SideRow({ g, s, rec }: { g: MoneylineGame; s: MoneylineSide; rec?: TeamRecord }) {
  const { state } = useBetSlip();
  const pick = started(g) ? null : sidePick(g, s);
  // the record that matters for this game's venue: the home team's at home, the away team's on the road
  const venue = s.home ? rec?.home : rec?.road;
  const url = s.book ? legLink({ link: s.link, eventLink: s.event_link, book: s.book }, state) : null;
  return (
    <tr>
      <td className="ml-team"><b>{s.team}</b>{rec && <> <span className="ml-rec">{rec.overall}</span></>} <span className="mut ml-name">{s.home ? "home" : "away"}{venue && ` ${venue}`}</span><span className="mut ml-name"><br />{s.name}</span></td>
      <td data-label="Model">{pct(s.p_model, 0)}</td>
      <td data-label="Market">{s.p_mkt == null ? <span className="mut">–</span> : pct(s.p_mkt, 0)}</td>
      <td data-label="Win prob"><b>{pct(s.prob)}</b></td>
      <td data-label="Best price">
        {s.odds == null ? <span className="mut">no line</span> : <>
          {url ? <a className="link strong" href={url} target="_blank" rel="noopener noreferrer" title={`Open at ${s.book}`}>{americanOdds(s.odds)} ↗</a> : americanOdds(s.odds)}
          {s.book && <><br /><span className="mut"><BookName book={s.book} size={14} /></span></>}</>}
      </td>
      <td data-label="EV" className="ml-ev">{s.ev == null ? "–" : <span className={s.ev > 0 ? "ev-pill" : "mut"}>{signedPct(s.ev)}</span>}<MoneylineAdd pick={pick} /></td>
    </tr>
  );
}

/** One game: both teams' win chances as a bar, then each side's record, model, market and blended chance with the best price. */
export function MoneylineCard({ g, records }: { g: MoneylineGame; records?: Record<string, TeamRecord> }) {
  const [away, home] = g.sides;
  const [awayColor, homeColor] = matchupColors(away.team, home.team);
  return (
    <article className="card ml-card">
      <header className="ml-head">
        <b>{g.label}</b><span className="mut">{kickoff(g.gameday, g.gametime)}</span>
      </header>
      <div className="ml-bar" role="img" aria-label={`${away.team} ${pct(away.prob, 0)}, ${home.team} ${pct(home.prob, 0)}`}>
        <i className="away tbar" style={{ width: `${away.prob * 100}%`, ...shadeVars(awayColor) }}>{away.team} {pct(away.prob, 0)}</i>
        <i className="home tbar" style={{ width: `${home.prob * 100}%`, ...shadeVars(homeColor) }}>{home.team} {pct(home.prob, 0)}</i>
      </div>
      <div className="scroll">
        <table className="ml-table">
          <thead><tr><th>Team</th><th title="The team-rating model alone">Model</th><th title="No-vig consensus across every book">Market</th>
            <th title="Chance to win: the blend used for EV">Win %</th><th title="Best moneyline">Price</th><th>EV</th></tr></thead>
          <tbody><SideRow g={g} s={away} rec={records?.[away.team]} /><SideRow g={g} s={home} rec={records?.[home.team]} /></tbody>
        </table>
      </div>
      <p className="mut ml-foot">
        Model margin: {favored(g, g.margin)}
        {g.spread != null && <> · market spread: {favored(g, g.spread)}</>}
        {away.books > 0 && <> · {away.books} book{away.books === 1 ? "" : "s"}</>}
      </p>
    </article>
  );
}
