import { timeAgo } from "../format";

const HOUR = 3600_000;
export type OddsLevel = "fresh" | "aging" | "stale";

/** Green under an hour, amber up to six, red after that (lines move; check the book). */
export function oddsLevel(at: string, now = Date.now()): OddsLevel {
  const age = now - new Date(`${at}Z`).getTime();   // the API's times are UTC without the Z (as timeAgo reads them)
  return age < HOUR ? "fresh" : age < 6 * HOUR ? "aging" : "stale";
}

/** The latest fetch across a meta's markets. */
export const latestFetch = (odds: Record<string, { fetched_at: string }>) => Object.values(odds).map((o) => o.fetched_at).sort().at(-1);

/** How old the odds are, as a colored dot (the banner below carries the warning once they're stale). */
export default function Freshness({ at, label = "odds" }: { at: string; label?: string }) {
  const level = oddsLevel(at);
  const note = { fresh: "Odds are current.", aging: "Odds are a few hours old; prices may have moved.", stale: "Odds are over six hours old; check the book's price before betting." }[level];
  return (
    <span className={`fresh ${level}`} title={note}>
      <i aria-hidden />{label} {timeAgo(at)}
      <span className="sr-only"> ({note})</span>
    </span>
  );
}

/** Full width over a page of prices once they're over six hours old: the EVs and stakes below were right then, not now. */
export function StaleBanner({ at }: { at: string }) {
  return (
    <div className="banner stale-banner" role="status">
      <b>Prices are {timeAgo(at).replace(" ago", "")} old.</b> Lines have probably moved since, so the EVs and stakes below are greyed out.
      Check each price at the book before betting.
    </div>
  );
}
