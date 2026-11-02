/** The last few games as bars, with the betting line drawn across them when there is one: bars over it cleared the line
 *  (under it, for an Under). */
export default function Spark({ values, line, side = "Over" }: { values: number[]; line?: number; side?: "Over" | "Under" }) {
  if (!values.length) return null;
  const max = Math.max(...values, line ?? 0, 1);
  const h = (v: number) => Math.max(2, (v / max) * 18);
  const cleared = (v: number) => line != null && (side === "Over" ? v > line : v < line);
  const over = values.filter(cleared).length;
  return (
    <span className="spark" role="img" aria-label={`Last ${values.length} games: ${values.join(", ")}${line != null ? `; ${side.toLowerCase()} ${line} in ${over}` : ""}`}>
      {values.map((v, i) => (
        <i key={i} className={cleared(v) ? "hit" : undefined} style={{ height: h(v) }} title={`${v.toFixed(0)}`} />
      ))}
      {line != null && <b className="spark-line" style={{ bottom: h(line) }} aria-hidden />}
    </span>
  );
}
