import { useEffect, useState } from "react";
import type { Filters, Kind } from "./api";
import { BASE } from "./env";
import { KIND_LABEL } from "./format";
import type { League } from "./league";

// Where you are lives in the URL, so a refresh keeps your place, back and forward step through sections, and any view can
// be shared: /<section>?<filters> for the NFL, /nba/<section>?<filters> for the NBA, with #game=<id> on top for a game page.

const NBA = "nba";
/** The path after BASE in parts: "/nba/props" -> ["nba", "props"]. */
const parts = () => window.location.pathname.slice(BASE.length).split("/").filter(Boolean);

/** The league the path names, or null on the site's front page (which shows the league last viewed). */
export const leagueFromPath = (): League | null => {
  const p = parts();
  return p[0] === NBA ? "nba" : p.length ? "nfl" : null;
};
/** The section's slug in the path ("" on a league's front page). */
export const sectionFromPath = () => {
  const p = parts();
  return (p[0] === NBA ? p[1] : p[0]) ?? "";
};
export const leaguePath = (l: League, section = "") => BASE + [l === "nba" ? NBA : "", section].filter(Boolean).join("/");
export const param = (k: string) => new URLSearchParams(window.location.search).get(k);

/** Swap the query string for `params` (empty values dropped), keeping the path and any #game. Doesn't add a history entry. */
export function setParams(params: Record<string, string | null | undefined>) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const search = qs.toString() ? `?${qs}` : "";
  if (search !== window.location.search) window.history.replaceState(null, "", window.location.pathname + search + window.location.hash);
}

/** The section on screen, read from the path, and a way to go to another one (a new history entry, filters and #game cleared). */
export function useSection<T extends string>(slugs: Record<T, string>, league: League, fallback: T) {
  const fromPath = () => (Object.keys(slugs) as T[]).find((t) => slugs[t] === sectionFromPath()) ?? fallback;
  const [section, setSection] = useState<T>(fromPath);
  useEffect(() => {
    const sync = () => setSection(fromPath());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const go = (t: T) => {
    const path = leaguePath(league, slugs[t]);
    if (path !== window.location.pathname || window.location.search || window.location.hash) window.history.pushState(null, "", path);
    setSection(t);
  };
  return [section, go] as const;
}

export const DEFAULT_FILTERS: Filters = { kind: "all", side: "all", game: "all", book: "all", q: "", minEv: 0.03, marketWeight: null, flagged: false };

/** A shared link's Best props / Projections filters: ?market=rec&side=Over&game=<id>&book=DraftKings&q=name. */
export function filtersFromUrl(): Filters {
  const kind = param("market");
  const side = param("side");
  return { ...DEFAULT_FILTERS, kind: kind && kind in KIND_LABEL ? (kind as Kind) : "all", side: side === "Over" || side === "Under" ? side : "all",
    game: param("game") ?? "all", book: param("book") ?? "all", q: param("q") ?? "" };
}

/** The query string for those filters (side and book only mean something on Best props). */
export const filterParams = (f: Filters, picks: boolean) => ({
  market: f.kind !== "all" ? f.kind : null, side: picks && f.side !== "all" ? f.side : null, game: f.game !== "all" ? f.game : null,
  book: picks && f.book !== "all" ? f.book : null, q: f.q.trim() || null,
});
