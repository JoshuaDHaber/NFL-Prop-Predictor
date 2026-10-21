import type { GameWeather, Projection } from "../api";
import { isYesNo, KIND_LABEL, effText, fmtProj, fmtSd, matchup, signed } from "../format";
import { useSort } from "../useSort";
import Avatar from "./Avatar";
import SortBar from "./SortBar";
import Spark from "./Spark";
import WeatherChip from "./WeatherChip";

export const THIN_TITLE = "Only a game or two of history (a rookie, or back from IR): a rough guess, shown for reference and never priced";

export default function ProjectionsTable({ rows, onSelect, weather = {}, nba = false }: { rows: Projection[]; onSelect: (p: Projection) => void; weather?: Record<string, GameWeather | null | undefined>; nba?: boolean }) {
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
            {th("mu", "Proj")}{th("sd", "SD")}{nba ? th("vol", "Minutes", "Projected minutes") : th("vol", "Volume", "Projected carries / targets / attempts; for longest reception, expected catches")}
            {nba ? th("eff", "Per 36", "Per 36 minutes, after the opponent adjustment") : th("eff", "Yds/att · E[TD]", "Yards per carry/target/attempt; for receptions, catch rate; for passing TDs, TDs per attempt; for longest reception, yards per catch; for anytime TD, expected touchdowns")}{th("spread", "Spread", "Team spread (positive = favorite)")}<th scope="col">Last 5</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={`${p.player_id}-${p.kind}`} className="clickable" onClick={() => onSelect(p)} tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(p)}>
              <td>
                <div className="pcell">
                  <Avatar name={p.name} size={34} />
                  <div><b>{p.name}</b> <span className="pos-pill">{p.pos}</span> <span className="mut">{p.team}</span>{p.status && <span className="q"> {p.status}</span>}{p.thin && <> <span className="thin-pill" title={THIN_TITLE}>Thin history</span></>}</div>
                </div>
              </td>
              <td>{KIND_LABEL[p.kind]}</td>
              <td>{matchup(p.opp, p.home)}{!isYesNo(p.kind) && <WeatherChip weather={weather[p.game_id]} wx={p.wx} />}</td>
              <td data-label="Proj"><b>{fmtProj(p.kind, p.mu)}</b></td>
              <td data-label="SD">{isYesNo(p.kind) ? "–" : fmtSd(p.kind, p.sd)}</td>
              <td data-label={nba ? "Minutes" : "Volume"}>{p.vol.toFixed(1)}</td>
              <td data-label={nba ? "Per 36" : "Yds/att · E[TD]"}>{isYesNo(p.kind) ? (nba ? "–" : p.eff.toFixed(2)) : effText(p.kind, p.eff)[1]}</td>
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
