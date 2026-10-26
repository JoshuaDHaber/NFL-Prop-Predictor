/** The last few games as bars, with the betting line drawn across them when there is one: bars over it cleared the line. */
export default function Spark({ values, line }: { values: number[]; line?: number }) {
  if (!values.length) return null;
  const max = Math.max(...values, line ?? 0, 1);
  const h = (v: number) => Math.max(2, (v / max) * 18);
  const over = line == null ? 0 : values.filter((v) => v > line).length;
  return (
    <span className="spark" role="img" aria-label={`Last ${values.length} games: ${values.join(", ")}${line != null ? `; over ${line} in ${over}` : ""}`}>
      {values.map((v, i) => (
        <i key={i} className={line != null && v > line ? "hit" : undefined} style={{ height: h(v) }} title={`${v.toFixed(0)}`} />
      ))}
      {line != null && <b className="spark-line" style={{ bottom: h(line) }} aria-hidden />}
    </span>
  );
}
