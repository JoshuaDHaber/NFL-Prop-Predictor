import { saveFavorites, useAuth, type FavPlayer, type LeagueFavorites } from "./auth";
import { getLeague, type League } from "./league";

/** Favorite teams (their games lead the Games tab) and players (one tap to compare), kept in the account, per league. */
export const MAX_FAV_TEAMS = 8;
export const MAX_FAV_PLAYERS = 30;
const NONE: LeagueFavorites = { teams: [], players: [] };

export interface Favorites extends LeagueFavorites {
  /** Signed in with 21+ confirmed: favorites can be saved. */
  ready: boolean;
  /** Still asking the server who's signed in. */
  loading: boolean;
}

export function useFavorites(league: League = getLeague()): Favorites {
  const auth = useAuth();
  const user = auth?.user;
  return { ...(user?.favorites?.[league] ?? NONE), ready: !!user?.age_confirmed, loading: !auth };
}

/** Games with a favorite team first, each group still in kickoff order. */
export function favoritesFirst<G extends { game_id: string }>(games: G[], teams: string[]): G[] {
  if (!teams.length) return games;
  const fav = (g: G) => gameTeams(g.game_id).some((t) => teams.includes(t));
  return [...games.filter(fav), ...games.filter((g) => !fav(g))];
}
/** [away, home] from a game id: 2026_07_BUF_KC, 2027_20261020_BOS_DET. */
export const gameTeams = (gameId: string) => gameId.split("_").slice(2, 4);

export const toggled = <T>(list: T[], item: T, same: (a: T) => boolean): T[] =>
  list.some(same) ? list.filter((x) => !same(x)) : [...list, item];

export const setFavTeams = (league: League, teams: string[]) => saveFavorites(league, { teams });
export function toggleFavPlayer(league: League, players: FavPlayer[], p: FavPlayer) {
  const { player_id, name, pos, team, headshot } = p;
  return saveFavorites(league, { players: toggled(players, { player_id, name, pos, team, headshot: headshot ?? null }, (x) => x.player_id === player_id) });
}
