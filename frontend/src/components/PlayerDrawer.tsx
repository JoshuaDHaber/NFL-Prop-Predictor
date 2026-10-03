import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Kind } from "../api";
import { KIND_LABEL, KIND_SHORT, americanOdds, matchup, pct, signedPct } from "../format";

interface Props { playerId: string; initialKind: Kind; marketWeight: number; onClose: () => void }

export default function PlayerDrawer({ playerId, initialKind, marketWeight, onClose }: Props) {
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
  const picks = data?.picks.filter((p) => p.kind === kind) ?? [];
  const logs = data?.logs[kind] ?? [];
  const lines = [...new Set(picks.map((p) => p.line))];

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="Player detail" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {isLoading && <p>Loading…</p>}
        {error && <p className="err">Couldn't load this player.</p>}
        {data && proj && (
          <>
            <h2>{data.name}</h2>
            <div className="mut">{data.pos} · {data.team} {matchup(proj.opp, proj.home)}</div>
            <div className="seg small" role="tablist">
              {data.projections.map((p) => (
                <button key={p.kind} className={p.kind === kind ? "on" : ""} onClick={() => setKind(p.kind)}>
                  {KIND_SHORT[p.kind]}
                </button>
              ))}
            </div>
            <div className="facts">
              <div><span className="mut">Projection</span><b>{proj.mu.toFixed(0)} yds</b></div>
              <div><span className="mut">Std dev</span><b>±{proj.sd.toFixed(0)}</b></div>
              <div><span className="mut">Volume</span><b>{proj.vol.toFixed(1)}</b></div>
              <div><span className="mut">Yds / att</span><b>{proj.eff.toFixed(2)}</b></div>
            </div>
            <h3>Last {logs.length} games · {KIND_LABEL[kind]}</h3>
            <div className="chart">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={logs} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--line)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--mut)" }} interval={0} angle={-35} textAnchor="end" height={50} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--mut)" }} />
                  <Tooltip formatter={(v: number) => [`${v} yds`, "Yards"]}
                    labelFormatter={(l, items) => `${l} ${items[0]?.payload ? "vs " + items[0].payload.opp : ""}`}
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", color: "var(--ink)" }} />
                  <Bar dataKey="yards" fill="var(--acc)" radius={[3, 3, 0, 0]} />
                  <ReferenceLine y={proj.mu} stroke="var(--good)" strokeDasharray="5 3"
                    label={{ value: `proj ${proj.mu.toFixed(0)}`, position: "insideTopRight", fill: "var(--good)", fontSize: 11 }} />
                  {lines.map((l) => (
                    <ReferenceLine key={l} y={l} stroke="var(--bad)" strokeDasharray="2 3"
                      label={{ value: `line ${l}`, position: "insideBottomRight", fill: "var(--bad)", fontSize: 11 }} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <h3>Available plays</h3>
            {picks.length === 0 && <p className="mut">No lines posted for this market.</p>}
            {picks.map((p) => (
              <div className="playrow" key={p.side}>
                <b className={p.side === "Over" ? "over" : "under"}>{p.side} {p.line}</b>
                <span>{americanOdds(p.odds)} · {p.book}</span>
                <span>{pct(p.prob)} win</span>
                <span className={p.ev > 0 ? "pos" : "mut"}>{signedPct(p.ev)} EV</span>
              </div>
            ))}
          </>
        )}
      </aside>
    </div>
  );
}
