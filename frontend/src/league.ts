/** Which league the page shows. One league is on screen at a time, so shared code (API paths, team colors and
 * logos) reads it from here instead of every component passing it down; main.tsx remounts the app on a switch. */
import { leagueFromPath } from "./route";

export type League = "nfl" | "nba";
const KEY = "league";
/** NBA game ids carry the date: 2027_20261020_BOS_DET (NFL ids: 2026_07_BUF_KC). */
const NBA_GAME = /^\d{4}_\d{8}_/;

function initial(): League {
  if (typeof window === "undefined") return "nfl";   // tests have no window
  const path = leagueFromPath();
  if (path) return path;   // /nba/... is the NBA, any other section the NFL; the front page falls through
  const game = new URLSearchParams(window.location.hash.slice(1)).get("game");
  if (game) return NBA_GAME.test(game) ? "nba" : "nfl";   // a shared game link opens in its own league
  try { return localStorage.getItem(KEY) === "nba" ? "nba" : "nfl"; } catch { return "nfl"; }
}

let current: League = initial();
export const getLeague = () => current;
export function setLeague(l: League) {
  current = l;
  try { localStorage.setItem(KEY, l); } catch { /* private mode: not remembered */ }
}
