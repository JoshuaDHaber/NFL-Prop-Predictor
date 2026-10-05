/** Phone-only sort chips: the table header (and its sortable columns) is hidden when rows become cards. */
export default function SortBar({ options, toggle, arrow }: { options: [string, string][]; toggle: (k: string) => void; arrow: (k: string) => string }) {
  return (
    <div className="sortbar" role="group" aria-label="Sort by">
      <span className="mut">Sort</span>
      {options.map(([k, label]) => (
        <button key={k} className={arrow(k) ? "on" : ""} onClick={() => toggle(k)}>{label}{arrow(k)}</button>
      ))}
    </div>
  );
}
