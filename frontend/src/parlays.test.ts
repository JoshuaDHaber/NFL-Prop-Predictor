import { describe, expect, it } from "vitest";
import type { Pick } from "./api";
import { bestBook, candidates, parlaysByBook, pickToLeg, priceParlay, recommendParlays } from "./parlays";

const pick = (o: Partial<Pick> = {}): Pick => ({
  player_id: "p1", name: "Test Back", pos: "RB", team: "AAA", opp: "BBB", home: true, kind: "rush", mu: 60, sd: 20, status: "",
  game_id: "g1", gameday: "2026-10-11", gametime: "13:00", side: "Under", line: 70.5, odds: -110, book: "DraftKings",
  p_model: 0.7, p_mkt: 0.6, prob: 0.65, ev: 0.1, kelly: 0.02, books: 4, edge_yds: 10, flagged: false, last5: [], ...o,
});

/** n picks, each in its own game, probabilities falling from 0.8 */
const slate = (n: number, o: (i: number) => Partial<Pick> = () => ({})) =>
  Array.from({ length: n }, (_, i) => pick({ player_id: `p${i}`, game_id: `g${i}`, prob: 0.8 - i * 0.01, ev: 0.3 - i * 0.01, ...o(i) }));

describe("candidates", () => {
  it("keeps only likely, unflagged, non-TD plays at sane prices", () => {
    const keep = pick();
    const rows = [keep, pick({ prob: 0.55 }), pick({ flagged: true }), pick({ kind: "td" }), pick({ odds: -450 })];
    expect(candidates(rows)).toEqual([keep]);
  });
});

describe("priceParlay", () => {
  it("multiplies leg prices and probabilities", () => {
    const p = priceParlay([pick({ odds: 100, prob: 0.6 }), pick({ odds: 100, prob: 0.6 }), pick({ odds: -200, prob: 0.8 })]);
    expect(p.decimal).toBeCloseTo(6);
    expect(p.american).toBe(500);
    expect(p.prob).toBeCloseTo(0.288);
    expect(p.ev).toBeCloseTo(0.288 * 6 - 1);
    expect(p.book).toBe("DraftKings");
  });

  it("refuses legs from different books", () => {
    expect(() => priceParlay([pick(), pick({ book: "FanDuel" })])).toThrow();
  });
});

describe("recommendParlays", () => {
  it("builds the safest 3-leg from the likeliest plays", () => {
    const [safest] = recommendParlays(slate(8));
    expect(safest.key).toBe("safest");
    expect(safest.legs.map((l) => l.player_id)).toEqual(["p0", "p1", "p2"]);
  });

  it("never puts two legs from one game (or one player) in a parlay", () => {
    const rows = [...slate(6), pick({ player_id: "dup", game_id: "g0", prob: 0.9 }), pick({ player_id: "p1", game_id: "g1", kind: "rec", prob: 0.85 })];
    for (const parlay of recommendParlays(rows)) {
      const games = parlay.legs.map((l) => l.game_id);
      expect(new Set(games).size).toBe(games.length);
    }
  });

  it("ranks the value parlay by expected return, not probability", () => {
    const rows = slate(8, (i) => (i === 7 ? { ev: 0.9, prob: 0.62 } : {}));
    const value = recommendParlays(rows).find((p) => p.key === "value")!;
    expect(value.legs[0].player_id).toBe("p7");
  });

  it("drops tiles without enough eligible legs and tiles that repeat another", () => {
    expect(recommendParlays(slate(2))).toEqual([]);
    const keys = recommendParlays(slate(3)).map((p) => p.key);
    expect(keys).toEqual(["safest"]); // value is the same three legs; overs and the 5-leg don't have enough
  });

  it("only offers an overs parlay when there are three overs", () => {
    const rows = slate(6, (i) => ({ side: i % 2 ? "Over" : "Under" }));
    expect(recommendParlays(rows).some((p) => p.key === "overs")).toBe(true);
    expect(recommendParlays(slate(6)).some((p) => p.key === "overs")).toBe(false);
  });
});

describe("per-book parlays", () => {
  const at = (book: string, odds: number) => slate(4, () => ({ book, odds }));
  it("builds each book's parlays only from that book's quotes, and skips books without enough legs", () => {
    const by = parlaysByBook({ DraftKings: at("DraftKings", -110), FanDuel: [...at("FanDuel", 100), ...at("DraftKings", 500)], Thin: at("Thin", 100).slice(0, 2) });
    expect(Object.keys(by).sort()).toEqual(["DraftKings", "FanDuel"]);
    for (const [book, ps] of Object.entries(by)) for (const p of ps) expect(p.legs.every((l) => l.book === book)).toBe(true);
  });
  it("picks the book whose lead parlay returns the most", () => {
    const by = parlaysByBook({ DraftKings: at("DraftKings", -110), FanDuel: at("FanDuel", 100) });
    expect(bestBook(by)).toBe("FanDuel");
    expect(bestBook({})).toBeNull();
  });
});

describe("pickToLeg", () => {
  it("carries the pick's bet onto a betslip leg", () => {
    const p = pick({ side: "Over", line: 54.5, odds: -120 });
    const leg = pickToLeg(p);
    expect(leg.id).toBe("p1|rush|Over|54.5|DraftKings");
    expect(leg).toMatchObject({ playerId: "p1", side: "Over", line: 54.5, odds: -120, book: "DraftKings", gameId: "g1", link: null });
  });
});
