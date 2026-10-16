import type { MoneylineGame, MoneylineSide } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { americanOdds, kickoff, pct, signedPct } from "../format";
import { legLink } from "../slip";
import { matchupColors, shadeVars } from "../teams";

/** "LV by 3.0" from a home margin; "Pick'em" near zero. */
export function favored(g: MoneylineGame, m: number, digits = 1) {
  const [away, home] = g.sides;
  return Math.abs(m) < 0.05 ? "Pick'em" : `${(m > 0 ? home : away).team} by ${Math.abs(m).toFixed(digits)}`;
}

function SideRow({ s }: { s: MoneylineSide }) {
  const { state } = useBetSlip();
  const url = s.book ? legLink({ link: s.link, eventLink: s.event_link, book: s.book }, state) : null;
  return (
    <tr>
      <td className="ml-team"><b>{s.team}</b> <span className="mut ml-name">{s.home ? "home" : "away"}</span><span className="mut ml-name"><br />{s.name}</span></td>
      <td data-label="Model">{pct(s.p_model, 0)}</td>
      <td data-label="Market">{s.p_mkt == null ? <span className="mut">–</span> : pct(s.p_mkt, 0)}</td>
      <td data-label="Win prob"><b>{pct(s.prob)}</b></td>
      <td data-label="Best price">
        {s.odds == null ? <span className="mut">no line</span> : <>
          {url ? <a className="link strong" href={url} target="_blank" rel="noopener noreferrer" title={`Open at ${s.book}`}>{americanOdds(s.odds)} ↗</a> : americanOdds(s.odds)}
          <br /><span className="mut">{s.book}</span></>}
      </td>
      <td data-label="EV">{s.ev == null ? "–" : <span className={s.ev > 0 ? "ev-pill" : "mut"}>{signedPct(s.ev)}</span>}</td>
    </tr>
  );
}

/** One game: both teams' win chances as a bar, then each side's model, market and blended chance with the best price. */
export function MoneylineCard({ g }: { g: MoneylineGame }) {
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
          <tbody><SideRow s={away} /><SideRow s={home} /></tbody>
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
