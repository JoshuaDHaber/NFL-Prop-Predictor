import { useState } from "react";
import type { Game, InjuredPlayer, InjuryReport, Kind } from "../api";
import { kickoff, timeAgo } from "../format";

interface Props {
  report: InjuryReport;
  games: Game[];
  onSelect: (id: string, kind: Kind) => void;
}

type Side = "all" | "off" | "def";
const SIDES: [Side, string][] = [["all", "Both sides"], ["off", "Offense"], ["def", "Defense"]];
const GROUPS: [InjuredPlayer["side"], string][] = [["off", "Offense"], ["def", "Defense"], ["st", "Special teams"]];
const RESERVE = new Set(["IR", "PUP", "NFI", "Reserve"]);

/** The badge: game status if there is one, else how he practiced ("DNP", "Limited"), or "Rest" for a veteran's day off. */
function badge(p: InjuredPlayer): { text: string; cls: string; title: string } {
  if (p.status === "Out") return { text: "Out", cls: "out", title: "Ruled out" };
  if (p.status === "Doubtful") return { text: "Doubtful", cls: "doubt", title: "Doubtful: rarely plays" };
  if (p.status === "Questionable") return { text: "Questionable", cls: "quest", title: "Questionable: a game-time decision" };
  if (RESERVE.has(p.status)) return { text: p.status, cls: "out", title: p.status === "IR" ? "Injured reserve" : p.status === "PUP" ? "Physically unable to perform list" : p.status === "NFI" ? "Non-football injury list" : "Reserve list" };
  if (p.rest) return { text: "Rest", cls: "rest", title: "Not injury related: a veteran's rest day" };
  return { text: p.practice === "DNP" ? "DNP" : "Limited", cls: "banged", title: `No game status yet; ${p.practice === "DNP" ? "did not practice" : "limited in practice"}` };
}

function summary(players: InjuredPlayer[]): string {
  const n = (f: (p: InjuredPlayer) => boolean) => players.filter(f).length;
  const parts: [number, string][] = [
    [n((p) => p.status === "Out"), "out"], [n((p) => p.status === "Doubtful"), "doubtful"], [n((p) => p.status === "Questionable"), "questionable"],
    [n((p) => !p.status && !p.rest), "limited/DNP"],
  ];
  return parts.filter(([c]) => c).map(([c, l]) => `${c} ${l}`).join(" · ") || "Nobody on the report";
}

function Row({ p, onSelect }: { p: InjuredPlayer; onSelect: Props["onSelect"] }) {
  const b = badge(p);
  const practice = p.status && !RESERVE.has(p.status) && p.practice ? p.practice : "";
  return (
    <li className="inj-row">
      <span className={`inj-badge ${b.cls}`} title={b.title}>{b.text}</span>
      <span className="pos-pill">{p.pos}</span>
      <span className="inj-name">
        {p.kind ? <button className="link strong" onClick={() => onSelect(p.player_id, p.kind as Kind)} title="Open his projections and props">{p.name}</button> : p.name}
        {(p.injury || practice) && <span className="mut"> {[p.rest ? "" : p.injury, practice && `${practice} in practice`].filter(Boolean).join(" · ")}</span>}
      </span>
    </li>
  );
}

function Team({ team, home, players, side, showReserve, onSelect }: {
  team: string; home: boolean; players: InjuredPlayer[]; side: Side; showReserve: boolean; onSelect: Props["onSelect"];
}) {
  const bySide = players.filter((p) => side === "all" || p.side === side);
  const report = bySide.filter((p) => !RESERVE.has(p.status));
  const reserve = bySide.filter((p) => RESERVE.has(p.status));
  const shown = showReserve ? bySide : report;
  return (
    <section className="inj-team">
      <h4><b>{team}</b> <span className="mut">{home ? "home" : "away"}</span></h4>
      <p className="mut inj-sum">{summary(report)}{!showReserve && reserve.length > 0 && ` · ${reserve.length} on IR/reserve`}</p>
      {GROUPS.filter(([g]) => side === "all" || g === side).map(([g, label]) => {
        const list = shown.filter((p) => p.side === g);
        if (!list.length) return null;
        return (
          <div key={g}>
            {side === "all" && <h5>{label}</h5>}
            <ul className="inj-list">{list.map((p) => <Row key={p.player_id} p={p} onSelect={onSelect} />)}</ul>
          </div>
        );
      })}
    </section>
  );
}

export default function Injuries({ report, games, onSelect }: Props) {
  const [game, setGame] = useState("all");
  const [side, setSide] = useState<Side>("all");
  const [showReserve, setShowReserve] = useState(false);
  const shown = games.filter((g) => game === "all" || g.game_id === game);
  const stale = report.report_week != null && report.week != null && report.report_week < report.week;
  return (
    <div className="stack">
      <section className="controls" aria-label="Injury filters">
        <div className="row">
          <select value={game} onChange={(e) => setGame(e.target.value)} aria-label="Game">
            <option value="all">All games</option>
            {games.map((g) => <option key={g.game_id} value={g.game_id}>{g.label}</option>)}
          </select>
          <div className="seg small">
            {SIDES.map(([k, label]) => <button key={k} className={side === k ? "on" : ""} onClick={() => setSide(k)}>{label}</button>)}
          </div>
          <label className="check"><input type="checkbox" checked={showReserve} onChange={(e) => setShowReserve(e.target.checked)} /> Show IR / PUP</label>
        </div>
        <p className="td-note">
          {report.report_week == null ? <>No injury report is available yet.</>
            : stale ? <><b>Week {report.week}'s report isn't out yet</b> (teams start reporting Wednesday). Showing week {report.report_week}'s final statuses, which may have changed.</>
            : <><b>Week {report.week} injury report:</b> game statuses come out Friday (Saturday for Monday games); until then, practice participation is the tell.</>}
          {report.fetched_at && <> Checked {timeAgo(report.fetched_at)} (nflverse).</>} Players with props link to their projections.
        </p>
      </section>
      {!shown.length ? <div className="card empty">No games on the slate.</div> : (
        <div className="inj-grid">
          {shown.map((g) => {
            const [, , away, home] = g.game_id.split("_");
            return (
              <article className="card inj-card" key={g.game_id}>
                <header className="ml-head"><b>{g.label}</b><span className="mut">{kickoff(g.gameday, g.gametime)}</span></header>
                <div className="inj-teams">
                  <Team team={away} home={false} players={report.teams[away] ?? []} side={side} showReserve={showReserve} onSelect={onSelect} />
                  <Team team={home} home players={report.teams[home] ?? []} side={side} showReserve={showReserve} onSelect={onSelect} />
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
