import { describe, expect, it } from "vitest";
import type { Pick } from "./api";
import { onePerPlayer } from "./onePerPlayer";

const pick = (player_id: string, kind: Pick["kind"], ev: number, game_id = "G1"): Pick => ({
  player_id, name: player_id, pos: "WR", team: "AAA", opp: "BBB", home: true, kind, mu: 1, sd: 1, status: "", game_id,
  gameday: "2026-10-18", gametime: "13:00", side: "Under", line: 4.5, odds: -110, book: "X", p_model: 0.6, p_mkt: 0.5,
  prob: 0.55, ev, kelly: 0.01, books: 3, edge_yds: 1, flagged: false, last5: [],
});

describe("onePerPlayer", () => {
  it("keeps each player's best pick by EV and carries the rest as related, best first", () => {
    const out = onePerPlayer([pick("worthy", "recs", 0.35), pick("coker", "recs", 0.34), pick("worthy", "rec", 0.25),
      pick("worthy", "lng", 0.4), pick("solo", "rush", 0.05)]);
    expect(out.map((p) => [p.player_id, p.kind, p.related.map((r) => r.kind)])).toEqual([
      ["worthy", "lng", ["recs", "rec"]], ["coker", "recs", []], ["solo", "rush", []]]);
  });
  it("treats the same player in different games as separate", () => {
    expect(onePerPlayer([pick("a", "rec", 0.1, "G1"), pick("a", "rec", 0.2, "G2")])).toHaveLength(2);
  });
});
