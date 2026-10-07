import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Kind } from "../api";
import { KIND_LABEL, KIND_SHORT, fmtProj, matchup, weatherText, wxEffect } from "../format";
import Avatar from "./Avatar";
import LineLadder, { ODDS_RANGE } from "./LineLadder";

interface Props { playerId: string; initialKind: Kind; marketWeight: number; book: string; onBookChange: (b: string) => void; onClose: () => void }

export default function PlayerDrawer({ playerId, initialKind, marketWeight, book, onBookChange, onClose }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["player", playerId, marketWeight], queryFn: () => api.player(playerId, marketWeight),
  });
  const [kind, setKind] = useState<Kind>(initialKind);
  useEffect(() => setKind(initialKind), [initialKind, playerId]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const proj = data?.projections.find((p) => p.kind === kind);
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });   // already cached by the page
  const weather = meta.data?.games.find((g) => g.game_id === proj?.game_id)?.weather;
  const wxText = weatherText(weather);
  const wxAdj = kind !== "td" ? wxEffect(proj?.wx) : null;

  const logs = data?.logs[kind] ?? [];
  // main-line markers on the chart come from the same ladder the table shows, so they follow the sportsbook filter
  const ladder = useQuery({ queryKey: ["ladder", playerId, kind, ODDS_RANGE], queryFn: () => api.lines(playerId, kind, ODDS_RANGE) });
  const isTd = kind === "td";
  const lines = isTd ? [] : [...new Set((ladder.data?.quotes ?? []).filter((q) => !q.alt && (book === "all" || q.book === book)).map((q) => q.line))];

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="Player detail" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {isLoading && <p>Loading…</p>}
        {error && <p className="err">Couldn't load this player.</p>}
        {data && proj && (
          <>
            <div className="player-head">
              <Avatar name={data.name} src={data.headshot} size={84} />
              <div>
                <h2>{data.name}</h2>
                <div className="mut"><span className="pos-pill">{data.pos}</span> {data.team} {matchup(proj.opp, proj.home)}</div>
              </div>
            </div>
            {wxText && (
              <p className="wx-line mut">
                {weather?.stadium ? `${weather.stadium} · ` : ""}{wxText}
                {wxAdj ? <> · <b className={proj.wx! < 1 ? "under" : "over"}>{wxAdj} {KIND_SHORT[kind].toLowerCase()} for weather</b></>
                  : !weather?.indoor && kind !== "td" ? " · no weather adjustment" : ""}
              </p>
            )}
            <div className="seg small" role="tablist">
              {data.projections.map((p) => (
                <button key={p.kind} className={p.kind === kind ? "on" : ""} onClick={() => setKind(p.kind)}>
                  {KIND_SHORT[p.kind]}
                </button>
              ))}
            </div>
            <div className="facts">
              {isTd ? (
                <>
                  <div><span className="mut">Chance to score</span><b>{fmtProj(kind, proj.mu)}</b></div>
                  <div><span className="mut">Expected TDs</span><b>{proj.eff.toFixed(2)}</b></div>
                  <div><span className="mut">Touches</span><b>{proj.vol.toFixed(1)}</b></div>
                  <div><span className="mut">TD / touch</span><b>{(proj.eff / Math.max(proj.vol, 0.1)).toFixed(3)}</b></div>
                </>
              ) : (
                <>
                  <div><span className="mut">Projection</span><b>{proj.mu.toFixed(0)} yds</b></div>
                  <div><span className="mut">Std dev</span><b>±{proj.sd.toFixed(0)}</b></div>
                  <div><span className="mut">Volume</span><b>{proj.vol.toFixed(1)}</b></div>
                  <div><span className="mut">Yds / att</span><b>{proj.eff.toFixed(2)}</b></div>
                </>
              )}
            </div>
            <h3>Last {logs.length} games · {isTd ? "touchdowns scored" : KIND_LABEL[kind]}</h3>
            <div className="chart">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={logs} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--mut)" }} interval={0} angle={-35} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--mut)" }} />
                  <Tooltip formatter={(v: number) => (isTd ? [`${v}`, "TDs"] : [`${v} yds`, "Yards"])}
                    labelFormatter={(l, items) => `${l} ${items[0]?.payload ? "vs " + items[0].payload.opp : ""}`}
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", color: "var(--ink)" }} />
                  <Bar dataKey="yards" fill="var(--acc)" radius={[3, 3, 0, 0]} />
                  <ReferenceLine y={isTd ? proj.eff : proj.mu} stroke="var(--good)" strokeDasharray="5 3"
                    label={{ value: isTd ? `expected ${proj.eff.toFixed(2)}` : `proj ${proj.mu.toFixed(0)}`, position: "insideTopRight", fill: "var(--good)", fontSize: 11 }} />
                  {lines.map((l) => (
                    <ReferenceLine key={l} y={l} stroke="var(--bad)" strokeDasharray="2 3"
                      label={{ value: `line ${l}`, position: "insideBottomRight", fill: "var(--bad)", fontSize: 11 }} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <LineLadder kind={kind} mu={proj.mu} book={book} onBookChange={onBookChange} ctx={{ playerId: data.player_id, name: data.name, team: data.team,
              opp: proj.opp, home: proj.home, gameId: proj.game_id }} />
          </>
        )}
      </aside>
    </div>
  );
}
