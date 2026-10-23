import { timeAgo } from "../format";

const HOUR = 3600_000;

/** How old the odds are, as a colored dot: green under an hour, amber up to six, red after that (lines move; check the book). */
export default function Freshness({ at, label = "odds" }: { at: string; label?: string }) {
  const age = Date.now() - new Date(`${at}Z`).getTime();   // the API's times are UTC without the Z (as timeAgo reads them)
  const level = age < HOUR ? "fresh" : age < 6 * HOUR ? "aging" : "stale";
  const note = { fresh: "Odds are current.", aging: "Odds are a few hours old; prices may have moved.", stale: "Odds are over six hours old; check the book's price before betting." }[level];
  return (
    <span className={`fresh ${level}`} title={note}>
      <i aria-hidden />{label} {timeAgo(at)}{level === "stale" && <span className="fresh-warn"> · may be out of date</span>}
      <span className="sr-only"> ({note})</span>
    </span>
  );
}
