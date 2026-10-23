/** Gray placeholders shaped like what's loading, so the page doesn't jump when it arrives. */
export default function Skeleton({ kind, count }: { kind: "rows" | "cards" | "page" | "panel"; count?: number }) {
  const n = (d: number) => Array.from({ length: count ?? d }, (_, i) => i);
  return (
    <div className={`skel skel-${kind}`} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {kind === "rows" && <div className="card skel-table">{n(6).map((i) => (
        <div key={i} className="skel-row"><i className="skel-dot" /><span><i style={{ width: "42%" }} /><i style={{ width: "26%" }} /></span><i className="skel-pill" /><i className="skel-num" /></div>
      ))}</div>}
      {kind === "cards" && <div className="skel-grid">{n(3).map((i) => (
        <div key={i} className="card skel-card"><i style={{ width: "40%" }} /><i className="skel-big" /><i /><i /><i style={{ width: "70%" }} /></div>
      ))}</div>}
      {kind === "page" && <>
        <div className="skel-bar"><i className="skel-logo" /><i style={{ width: 140 }} /><span /><i className="skel-pill" /><i className="skel-pill" /></div>
        <i className="skel-title" />
        <div className="skel-grid">{n(6).map((i) => <div key={i} className="card skel-card"><i style={{ width: "50%" }} /><i className="skel-big" /><i /><i style={{ width: "60%" }} /></div>)}</div>
      </>}
      {kind === "panel" && <div className="skel-panel"><div className="skel-head"><i className="skel-avatar" /><span><i style={{ width: 180 }} /><i style={{ width: 120 }} /></span></div>
        <i className="skel-chart" />{n(4).map((i) => <i key={i} />)}</div>}
    </div>
  );
}
