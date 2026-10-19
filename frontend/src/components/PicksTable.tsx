import { useMemo, useState } from "react";
import type { GameWeather, Pick } from "../api";
import { onePerPlayer, type GroupedPick } from "../onePerPlayer";
import { isYesNo, KIND_LABEL, americanOdds, fmtEdge, fmtProj, fmtSd, kickoff, matchup, pct, playLabel, signedPct } from "../format";
import { useSort } from "../useSort";
import Avatar from "./Avatar";
import SortBar from "./SortBar";
import Spark from "./Spark";
import WeatherChip from "./WeatherChip";

const GROUP_KEY = "picks-one-per-player";
const storedGrouped = () => { try { return localStorage.getItem(GROUP_KEY) !== "0"; } catch { return true; } };

/** picks arrive best EV first. limit shows only the top rows (after grouping) with a "Show all" button, as on the game pages. */
export default function PicksTable({ picks, onSelect, weather = {}, empty, limit }: { picks: Pick[]; onSelect: (p: Pick) => void; weather?: Record<string, GameWeather | null | undefined>; empty?: string; limit?: number }) {
  const [grouped, setGroupedState] = useState(storedGrouped);
  const setGrouped = (g: boolean) => { setGroupedState(g); try { localStorage.setItem(GROUP_KEY, g ? "1" : "0"); } catch { /* private mode: not remembered */ } };
  const [showAll, setShowAll] = useState(false);
  const rows: GroupedPick[] = useMemo(() => grouped ? onePerPlayer(picks) : picks.map((p) => ({ ...p, related: [] })), [picks, grouped]);
  const shown = useMemo(() => (limit && !showAll ? rows.slice(0, limit) : rows), [rows, limit, showAll]);
  const { sorted, toggle, arrow } = useSort(shown, "ev");
  const th = (key: string, label: string, title?: string) => (
    <th scope="col" onClick={() => toggle(key)} title={title} aria-sort="none" className="sortable">{label}{arrow(key)}</th>
  );
  if (!picks.length) return <div className="card empty">{empty ?? <>No plays clear the current filters. Try lowering Min EV (it can go below 0) to see the closest ones.</>}</div>;
  return (
    <>
    <label className="group-toggle mut" title="A player's picks win or lose together, so the board shows his best one and tucks the rest behind it">
      <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} /> One pick per player
      {grouped && rows.length < picks.length && <> · {picks.length - rows.length} related picks tucked away</>}
    </label>
    <SortBar toggle={toggle} arrow={arrow} options={[["ev", "EV"], ["prob", "Win prob"], ["edge_yds", "Edge"], ["mu", "Proj"], ["name", "Name"]]} />
    <div className="card scroll cards">
      <table className="t-picks">
        <thead>
          <tr>
            {th("name", "Player")}<th scope="col">Market</th><th scope="col">Pick</th>
            {th("mu", "Proj")}{th("edge_yds", "Edge", "Projection minus line in yards (catches for receptions), in the pick direction; for anytime TD, model chance minus market chance in percentage points")}
            {th("prob", "Win prob")}{th("ev", "EV")}{th("kelly", "¼ Kelly", "Quarter-Kelly stake, % of bankroll")}
            <th scope="col">Last 5</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={`${p.player_id}-${p.kind}-${p.side}`} onClick={() => onSelect(p)} className="clickable"
              tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect(p)}>
              <td>
                <div className="pcell">
                  <Avatar name={p.name} size={34} />
                  <div>
                    <b>{p.name}</b> <span className="pos-pill">{p.pos}</span> <span className="mut">{p.team}</span>
                    {p.status && <span className="q"> {p.status}</span>}
                    {p.flagged && <span className="flag" title="Model and market disagree strongly">large gap</span>}
                    {p.related.length > 0 && <span className="flag related" title={`Moves with this pick: ${p.related.map((r) => `${KIND_LABEL[r.kind]} ${playLabel(r.kind, r.side, r.line)} (${signedPct(r.ev)} EV)`).join(", ")}. Open the player for all his plays.`}>+{p.related.length} related</span>}
                    {p.teammate_out && <span className="flag" title={`${p.teammate_out} out (first game): the model doesn't hand his targets to teammates. In past games like this, receivers averaged a few more yards than projected, from occasional big games, but beat their projection no more often than usual.`}>teammate out</span>}
                    <br /><span className="mut">{matchup(p.opp, p.home)} · {kickoff(p.gameday, p.gametime)}</span>
                    {!isYesNo(p.kind) && <WeatherChip weather={weather[p.game_id]} wx={p.wx} />}
                  </div>
                </div>
              </td>
              <td className="c-market">{KIND_LABEL[p.kind]}</td>
              <td>
                <span className={`side-pill ${p.side === "Over" ? "over" : "under"}`}>{playLabel(p.kind, p.side, p.line)}</span><br /><span className="mut">{americanOdds(p.odds)} · {p.book}</span>
              </td>
              <td data-label="Proj">{fmtProj(p.kind, p.mu)}{!isYesNo(p.kind) && <><br /><span className="mut">{fmtSd(p.kind, p.sd)}</span></>}</td>
              <td data-label="Edge">{fmtEdge(p.kind, p.edge_yds)}</td>
              <td data-label="Win prob"><b>{pct(p.prob)}</b><span className="meter" aria-hidden><i style={{ width: `${Math.min(100, p.prob * 100)}%` }} /></span><span className="mut">model {pct(p.p_model, 0)} · mkt {pct(p.p_mkt, 0)}</span></td>
              <td className="c-ev"><span className="ev-pill">{signedPct(p.ev)}</span></td>
              <td data-label="¼ Kelly">{pct(p.kelly)}</td>
              <td data-label="Last 5"><Spark values={p.last5} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {limit !== undefined && rows.length > limit && (
      <button className="link go-more" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${rows.length} ${grouped ? "players" : "props"}`}</button>
    )}
    </>
  );
}
