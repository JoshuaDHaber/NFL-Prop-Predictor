import type { GameWeather, Projection } from "../api";
import { KIND_LABEL, fmtProj, matchup, signed } from "../format";
import { useSort } from "../useSort";
import Avatar from "./Avatar";
import SortBar from "./SortBar";
import Spark from "./Spark";
import WeatherChip from "./WeatherChip";

export default function ProjectionsTable({ rows, onSelect, weather = {} }: { rows: Projection[]; onSelect: (p: Projection) => void; weather?: Record<string, GameWeather | null | undefined> }) {
  const { sorted, toggle, arrow } = useSort(rows, "mu");
  const th = (key: string, label: string, title?: string) => (
    <th scope="col" onClick={() => toggle(key)} title={title} className="sortable">{label}{arrow(key)}</th>
  );
  if (!rows.length) return <div className="card empty">No projections match the current filters.</div>;
  return (
    <>
    <SortBar toggle={toggle} arrow={arrow} options={[["mu", "Proj"], ["vol", "Volume"], ["eff", "Efficiency"], ["spread", "Spread"], ["name", "Name"]]} />
    <div className="card scroll cards">
      <table className="t-proj">
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
              <td>
                <div className="pcell">
                  <Avatar name={p.name} size={34} />
                  <div><b>{p.name}</b> <span className="pos-pill">{p.pos}</span> <span className="mut">{p.team}</span>{p.status && <span className="q"> {p.status}</span>}</div>
                </div>
              </td>
              <td>{KIND_LABEL[p.kind]}</td>
              <td>{matchup(p.opp, p.home)}{p.kind !== "td" && <WeatherChip weather={weather[p.game_id]} wx={p.wx} />}</td>
              <td data-label="Proj"><b>{fmtProj(p.kind, p.mu)}</b></td>
              <td data-label="SD">{p.kind === "td" ? "–" : `±${p.sd.toFixed(0)}`}</td>
              <td data-label="Volume">{p.vol.toFixed(1)}</td>
              <td data-label="Yds/att · E[TD]">{p.eff.toFixed(2)}</td>
              <td data-label="Spread">{signed(p.spread)}</td>
              <td data-label="Last 5"><Spark values={p.last5} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  );
}
