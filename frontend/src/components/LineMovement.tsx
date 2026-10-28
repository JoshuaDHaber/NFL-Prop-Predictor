import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Kind } from "../api";
import { americanOdds, isYesNo, pct, signedPts } from "../format";
import Info from "./Info";

const when = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString(undefined, { weekday: "short", hour: "numeric" });

/** How a player's market moved through the week: the consensus line, and the books' fair chance of the over at today's line
 *  (so a moved line and a moved price read on one scale). A note in its place with only one odds fetch. */
export default function LineMovement({ playerId, kind }: { playerId: string; kind: Kind }) {
  const { data } = useQuery({ queryKey: ["history", playerId, kind], queryFn: () => api.history(playerId, kind) });
  const pts = (data ?? []).filter((p) => p.p_now_line != null);
  if (!pts.length) return null;
  // one fetch has nothing to compare: a line says so, rather than the section coming and going from player to player
  if (pts.length < 2) return (
    <section className="line-move">
      <h3>Line movement <Info term="move" /></h3>
      <p className="mut">One odds fetch so far ({when(pts[0].at)}), so no movement yet. It shows here after the next sync.</p>
    </section>
  );
  const first = pts[0], last = pts[pts.length - 1];
  const yes = isYesNo(kind);
  const move = last.p_now_line! - first.p_now_line!;
  const rows = pts.map((p) => ({ ...p, label: when(p.at), chance: Math.round(p.p_now_line! * 1000) / 10 }));
  return (
    <section className="line-move">
      <h3>Line movement <Info term="move" /></h3>
      <p className="mut">
        {yes ? "Yes" : `Over ${last.line}`}: the books' fair chance went from <b>{pct(first.p_now_line!)}</b> to <b>{pct(last.p_now_line!)}</b>
        {" "}(<span className={Math.abs(move) < 0.02 ? "" : move > 0 ? "over" : "under"}>{signedPts(move)}</span>) over {pts.length} odds fetches
        {!yes && first.line !== last.line && <>; the line moved from {first.line} to {last.line}</>}.
      </p>
      <div className="chart">
        <ResponsiveContainer width="100%" height={170}>
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--line)" />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--mut)" }} />
            <YAxis yAxisId="p" domain={["dataMin - 3", "dataMax + 3"]} tickFormatter={(v: number) => `${Math.round(v)}%`} tick={{ fontSize: 11, fill: "var(--mut)" }} />
            {!yes && <YAxis yAxisId="l" orientation="right" domain={["dataMin - 1", "dataMax + 1"]} tick={{ fontSize: 11, fill: "var(--mut)" }} width={36} />}
            <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", color: "var(--ink)" }}
              formatter={(v: number, name: string, item) => name === "chance"
                ? [`${v}%${item.payload.best_over != null ? ` · best ${yes ? "Yes" : "Over"} ${americanOdds(item.payload.best_over)}` : ""}`, yes ? "Fair chance of Yes" : `Fair chance of Over ${last.line}`]
                : [`${v} (${item.payload.books} books)`, "Consensus line"]} />
            <Line yAxisId="p" dataKey="chance" stroke="var(--acc2)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            {!yes && <Line yAxisId="l" dataKey="line" type="stepAfter" stroke="var(--mut)" strokeDasharray="4 3" dot={false} isAnimationActive={false} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
