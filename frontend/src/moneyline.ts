import type { MoneylineGame, MoneylineSide, Pick } from "./api";
import { easternToDate } from "./format";
import type { ParlayLeg } from "./parlays";

/**
 * A team's moneyline as a betslip leg or parlay leg. It rides in the same shape as a player prop (kind "ml", side "Over",
 * line 0: the team wins), with the team standing in for the player. Its "player" id is the team and its game, so the same
 * abbreviation in both leagues (LAC, the Chargers and the Clippers) never collides.
 */

/** "KC@2026_09_KC_DEN": the id a moneyline leg goes by. */
export const mlPlayerId = (gameId: string, team: string) => `${team}@${gameId}`;

export function parseMlId(id: string): { team: string; gameId: string } | null {
  const m = /^([A-Z]{2,4})@(\d{4}_\d+_[A-Z]{2,4}_[A-Z]{2,4})$/.exec(id);
  return m ? { team: m[1], gameId: m[2] } : null;
}

/** NBA game ids carry the date ("2026_20261104_BOS_NYK"), NFL ones the week ("2026_09_KC_DEN"). */
export const mlLeague = (gameId: string): "nfl" | "nba" => (/^\d{4}_\d{8}_/.test(gameId) ? "nba" : "nfl");

/** One side of a game as a priced pick at its best (or chosen) book, with its betslip link; null when no book prices it. */
export function sidePick(g: MoneylineGame, s: MoneylineSide): ParlayLeg | null {
  if (s.odds == null || !s.book || s.ev == null) return null;
  const opp = g.sides.find((x) => x.team !== s.team);
  const pick: Pick = {
    player_id: mlPlayerId(g.game_id, s.team), name: s.name, pos: "", team: s.team, opp: opp?.team ?? "", home: s.home, kind: "ml",
    mu: s.prob, sd: 0, status: "", game_id: g.game_id, gameday: g.gameday, gametime: g.gametime,
    side: "Over", line: 0, odds: s.odds, book: s.book, p_model: s.p_model, p_mkt: s.p_mkt ?? s.p_model, prob: s.prob, ev: s.ev,
    kelly: s.kelly ?? 0, books: s.books, edge_yds: 0, flagged: false, last5: [],
  };
  return { ...pick, link: s.link, eventLink: s.event_link, alt: false };
}

/** Whether the game has kicked off (or tipped off): its pregame price is gone. */
export const started = (g: { gameday: string; gametime: string }, now = Date.now()) => {
  const at = easternToDate(g.gameday, g.gametime);
  return !!at && at.getTime() <= now;
};

/** Every priced side of the games still to start, as picks (see sidePick). */
export const moneylinePicks = (games: MoneylineGame[], now = Date.now()): ParlayLeg[] =>
  games.filter((g) => !started(g, now)).flatMap((g) => g.sides.map((s) => sidePick(g, s)).filter((p): p is ParlayLeg => !!p));
