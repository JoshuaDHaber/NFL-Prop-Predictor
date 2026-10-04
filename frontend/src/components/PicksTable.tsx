import type { Pick } from "../api";
import { KIND_LABEL, americanOdds, fmtEdge, fmtProj, kickoff, matchup, pct, playLabel, signedPct } from "../format";
import { useSort } from "../useSort";
import Spark from "./Spark";

export default function PicksTable({ picks, onSelect }: { picks: Pick[]; onSelect: (p: Pick) => void }) {
  const { sorted, toggle, arrow } = useSort(picks, "ev");
  const th = (key: string, label: string, title?: string) => (
    <th scope="col" onClick={() => toggle(key)} title={title} aria-sort="none" className="sortable">{label}{arrow(key)}</th>
  );
  if (!picks.length) return <div className="card empty">No plays clear the current filters.</div>;
  return (
    <div className="card scroll">
      <table>
        <thead>
          <tr>
            {th("name", "Player")}<th scope="col">Market</th><th scope="col">Pick</th>
            {th("mu", "Proj")}{th("edge_yds", "Edge", "Projection minus line in yards, in the pick direction; for anytime TD, model chance minus market chance in percentage points")}
            {th("prob", "Win prob")}{th("ev", "EV")}{th("kelly", "¼ Kelly", "Quarter-Kelly stake, % of bankroll")}
            <th scope="col">Last 5</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={`${p.player_id}-${p.kind}-${p.side}`} onClick={() => onSelect(p)} className="clickable"
              tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect(p)}>
              <td>
                <b>{p.name}</b> <span className="mut">{p.pos} {p.team}</span>
                {p.status && <span className="q"> {p.status}</span>}
                {p.flagged && <span className="flag" title="Model and market disagree strongly">large gap</span>}
                <br /><span className="mut">{matchup(p.opp, p.home)} · {kickoff(p.gameday, p.gametime)}</span>
              </td>
              <td>{KIND_LABEL[p.kind]}</td>
              <td className={`pick ${p.side === "Over" ? "over" : "under"}`}>
                {playLabel(p.kind, p.side, p.line)}<br /><span className="mut">{americanOdds(p.odds)} · {p.book}</span>
              </td>
              <td>{fmtProj(p.kind, p.mu)}{p.kind !== "td" && <><br /><span className="mut">±{p.sd.toFixed(0)}</span></>}</td>
              <td>{fmtEdge(p.kind, p.edge_yds)}</td>
              <td>{pct(p.prob)}<br /><span className="mut">model {pct(p.p_model, 0)} · mkt {pct(p.p_mkt, 0)}</span></td>
              <td className="pos">{signedPct(p.ev)}</td>
              <td>{pct(p.kelly)}</td>
              <td><Spark values={p.last5} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
