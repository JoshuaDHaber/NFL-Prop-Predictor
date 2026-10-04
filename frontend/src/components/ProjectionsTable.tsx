import type { Projection } from "../api";
import { KIND_LABEL, fmtProj, matchup, signed } from "../format";
import { useSort } from "../useSort";
import Spark from "./Spark";

export default function ProjectionsTable({ rows, onSelect }: { rows: Projection[]; onSelect: (p: Projection) => void }) {
  const { sorted, toggle, arrow } = useSort(rows, "mu");
  const th = (key: string, label: string, title?: string) => (
    <th scope="col" onClick={() => toggle(key)} title={title} className="sortable">{label}{arrow(key)}</th>
  );
  if (!rows.length) return <div className="card empty">No projections match the current filters.</div>;
  return (
    <div className="card scroll">
      <table>
        <thead>
          <tr>
            {th("name", "Player")}<th scope="col">Market</th><th scope="col">Game</th>
            {th("mu", "Proj")}{th("sd", "SD")}{th("vol", "Volume", "Projected carries / targets / attempts")}
            {th("eff", "Yds/att · E[TD]", "Yards per carry/target/attempt; for anytime TD, expected touchdowns")}{th("spread", "Spread", "Team spread (positive = favorite)")}<th scope="col">Last 5</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={`${p.player_id}-${p.kind}`} className="clickable" onClick={() => onSelect(p)} tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(p)}>
              <td><b>{p.name}</b> <span className="mut">{p.pos} {p.team}</span>{p.status && <span className="q"> {p.status}</span>}</td>
              <td>{KIND_LABEL[p.kind]}</td>
              <td>{matchup(p.opp, p.home)}</td>
              <td><b>{fmtProj(p.kind, p.mu)}</b></td>
              <td>{p.kind === "td" ? "–" : `±${p.sd.toFixed(0)}`}</td>
              <td>{p.vol.toFixed(1)}</td>
              <td>{p.eff.toFixed(2)}</td>
              <td>{signed(p.spread)}</td>
              <td><Spark values={p.last5} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
