import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Filters, type GameWeather, type HotPick } from "../api";
import { isYesNo, KIND_LABEL, americanOdds, fmtProj, kickoff, matchup, pct, playLabel, signedPct } from "../format";
import { getLeague } from "../league";
import { useSort } from "../useSort";
import Avatar from "./Avatar";
import { BookName } from "./BookBadge";
import HowToRead from "./HowToRead";
import Info, { type Term } from "./Info";
import MatchupGrade from "./MatchupGrade";
import SidePill from "./SidePill";
import Skeleton from "./Skeleton";
import SortBar from "./SortBar";
import Spark from "./Spark";
import type { Tile } from "./TopTiles";
import WeatherChip from "./WeatherChip";

/** How far back to look: an NFL season is short, so its windows are too. */
const WINDOWS = { nfl: [3, 5, 8], nba: [5, 10, 15] } as const;
const DEFAULT_WINDOW = { nfl: 5, nba: 10 } as const;

/** "Over 6 straight", "4 of 5": a row's run in words. */
export function runText(r: HotPick) {
  if (r.streak === r.window) return `${r.window} straight`;
  return `${r.hits} of ${r.window}${r.streak >= 2 ? ` · last ${r.streak} in a row` : ""}`;
}

/** Who's Hot: players whose last few games cleared the line they're posted at now (or, on the Cold side, stayed under it),
 *  with the board's price beside the run. A streak isn't an edge by itself: the projections already lean on recent games,
 *  so the EV says whether the run is in the price. */
export default function HotBoard({ board, onSelect, weather = {} }: { board: ReturnType<typeof useHotBoard>; onSelect: (r: HotPick) => void; weather?: Record<string, GameWeather | null | undefined> }) {
  const { league, games, setGames, side, setSide, query: hot } = board;
  const rows = hot.data ?? [];
  // the server's order (games cleared, then streak, then margin) is the default; "rank" keeps it
  const ranked = rows.map((r, i) => ({ ...r, rank: -i }));
  const { sorted, toggle, arrow } = useSort(ranked, "rank");
  const th = (key: string, label: string, term?: Term) => (
    <th scope="col" onClick={() => toggle(key)} aria-sort="none" className="sortable">{label}{arrow(key)}{term && <> <Info term={term} /></>}</th>
  );
  return (
    <>
      <div className="hot-bar">
        <div className="seg small" role="group" aria-label="Side">
          <button className={side === "Over" ? "on" : ""} aria-pressed={side === "Over"} onClick={() => setSide("Over")}>Hot: over the line</button>
          <button className={side === "Under" ? "on" : ""} aria-pressed={side === "Under"} onClick={() => setSide("Under")}>Cold: under it</button>
        </div>
        <div className="seg small" role="group" aria-label="Games">
          <span className="mut seg-label">Last</span>
          {WINDOWS[league].map((n) => <button key={n} className={games === n ? "on" : ""} aria-pressed={games === n} onClick={() => setGames(n)}>{n} games</button>)}
        </div>
      </div>
      <HowToRead storageKey="how-to-read-hot-dismissed">
        <ol>
          <li>Each row is a player whose last games {side === "Over" ? "beat" : "stayed under"} the line he's posted at now: at least 6 in 10 of them{league === "nfl" ? ", reaching into last season when this one runs short" : ""}. Bars that cleared the line are green.</li>
          <li><b>Avg</b> is those games' average, with his average in the games before them underneath.</li>
          <li>A run isn't an edge on its own: the projections already weight recent games. <b>EV</b> <Info term="ev" /> says whether the run is in the price.</li>
        </ol>
      </HowToRead>
      {hot.isLoading ? <Skeleton kind="rows" /> : hot.error ? <p className="err">Couldn't load who's hot.</p> : !rows.length ? (
        <div className="card empty">Nobody on the board has {side === "Over" ? "cleared" : "stayed under"} their line that often lately. Try a shorter stretch or another market.</div>
      ) : <>
        <SortBar toggle={toggle} arrow={arrow} options={[["rank", "Hottest"], ["streak", "Streak"], ["ev", "EV"], ["name", "Name"]]} />
        <div className="card scroll cards">
          <table className="t-hot">
            <thead>
              <tr>
                {th("name", "Player")}<th scope="col">Market</th><th scope="col">Line</th>
                {th("rank", `Last ${games}`, "hitRates")}{th("avg", "Avg")}{th("prob", "Win prob", "winProb")}{th("ev", "EV", "ev")}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={`${r.player_id}-${r.kind}-${r.side}`} onClick={() => onSelect(r)} className="clickable" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onSelect(r)}>
                  <td>
                    <div className="pcell">
                      <Avatar name={r.name} size={34} />
                      <div>
                        <b>{r.name}</b> <span className="pos-pill">{r.pos}</span> <span className="mut">{r.team}</span>
                        {r.status && <span className="q"> {r.status}</span>}
                        {r.flagged && <span className="flag" title="Model and market disagree strongly, so Best props hides this price">large gap</span>}
                        <br /><span className="mut">{matchup(r.opp, r.home)} · {kickoff(r.gameday, r.gametime)}</span>
                        {!isYesNo(r.kind) && <WeatherChip weather={weather[r.game_id]} wx={r.wx} />}
                        <MatchupGrade kind={r.kind} pos={r.pos} opp={r.opp} rank={r.dvp_rank} n={r.dvp_n} side={r.side} quiet />
                      </div>
                    </div>
                  </td>
                  <td className="c-market">{KIND_LABEL[r.kind]}</td>
                  <td><SidePill kind={r.kind} side={r.side} line={r.line} /><br /><span className="mut">{americanOdds(r.odds)} · <BookName book={r.book} size={14} /></span></td>
                  <td data-label={`Last ${games}`} className="c-run">
                    <Spark values={r.recent} line={isYesNo(r.kind) ? undefined : r.line} side={r.side} />
                    <br /><b className={r.streak === r.window ? "run-full" : undefined}>{runText(r)}</b>
                  </td>
                  <td data-label="Avg">{isYesNo(r.kind) ? <span className="mut">—</span> : <>
                    <b>{fmtProj(r.kind, r.avg)}</b>
                    {r.prior_avg != null && <><br /><span className="mut" title={`His average in the games before these ${games}`}>{fmtProj(r.kind, r.prior_avg)} before</span></>}
                  </>}</td>
                  <td data-label="Win prob"><b>{pct(r.prob)}</b><span className="meter" aria-hidden><i style={{ width: `${Math.min(100, r.prob * 100)}%` }} /></span>
                    <span className="mut">proj {fmtProj(r.kind, r.mu)}</span></td>
                  <td className="c-ev"><span className={`ev-pill${r.ev < 0 ? " neg" : ""}`}>{signedPct(r.ev)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>}
    </>
  );
}

/** The board's state (which side, how many games) and its rows, kept by the league shell so the top tiles can read them. */
export function useHotBoard(filters: Filters, enabled: boolean) {
  const league = getLeague();
  const [games, setGames] = useState<number>(DEFAULT_WINDOW[league]);
  const [side, setSide] = useState<"Over" | "Under">("Over");
  const query = useQuery({ queryKey: ["hot", league, filters, games, side], queryFn: () => api.hot(filters, games, side), enabled, placeholderData: (p) => p });
  return { league, games, setGames, side, setSide, query };
}

/** The three hottest runs, as the tiles above the board. */
export const hotTiles = (rows: HotPick[], onSelect: (r: HotPick) => void): Tile[] => rows.slice(0, 3).map((r) => ({
  key: `${r.player_id}-${r.kind}-${r.side}`, label: KIND_LABEL[r.kind], name: r.name, meta: `${r.pos} ${r.team} ${matchup(r.opp, r.home)}`,
  value: <>{playLabel(r.kind, r.side, r.line)} <em>{r.hits}/{r.window}</em></>, caption: `${runText(r)} · ${signedPct(r.ev)} EV`,
  onClick: () => onSelect(r),
}));
