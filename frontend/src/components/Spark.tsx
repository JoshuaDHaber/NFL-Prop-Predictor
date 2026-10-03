export default function Spark({ values }: { values: number[] }) {
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  return (
    <span className="spark" aria-label={`Last ${values.length} games: ${values.join(", ")}`}>
      {values.map((v, i) => (
        <i key={i} style={{ height: Math.max(2, (v / max) * 18) }} title={`${v.toFixed(0)}`} />
      ))}
    </span>
  );
}
