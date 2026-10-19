import type { Pick } from "./api";

export type GroupedPick = Pick & { related: Pick[] };

/** Each player's best pick by EV, carrying his other picks (best first) as `related`.
 *  A player's picks move together (his receptions Under and his receiving yards Under win or lose as one), so listing
 *  them all as separate bets overstates how many independent edges the board holds. */
export function onePerPlayer(picks: Pick[]): GroupedPick[] {
  const groups = new Map<string, Pick[]>();
  for (const p of picks) {
    const key = `${p.player_id}|${p.game_id}`;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  return [...groups.values()].map((g) => {
    const [best, ...related] = [...g].sort((a, b) => b.ev - a.ev);
    return { ...best, related };
  });
}
