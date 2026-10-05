import { describe, expect, it } from "vitest";
import type { Ladder, LadderRow, Pick } from "./api";
import { bestBook, buildLadderParlays, candidates, defaultBook, ladderRungs, ladderTargets, parlaysByBook, pickToLeg, priceParlay, recommendParlays } from "./parlays";
import { toAmerican, toDecimal } from "./slip";

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

const rung = (line: number, odds: number, prob: number, o: Partial<LadderRow> = {}): LadderRow =>
  ({ line, book: "DraftKings", alt: true, event_link: null, over: { odds, prob, ev: 0, link: `https://sportsbook.draftkings.com/?outcomes=${line}` }, under: null, ...o });
const ladder = (...quotes: LadderRow[]): Ladder => ({ kind: "rush", mu: 60, sd: 20, game_id: "g1", alt_fetched_at: null, quotes });
const over = (o: Partial<Pick> = {}) => pick({ side: "Over", p_model: 0.8, ...o });

describe("ladder rungs", () => {
  it("keeps this book's likely overs at sane prices, with the rung's own link", () => {
    const l = ladder(rung(30.5, -250, 0.75), rung(30.5, -300, 0.75), rung(20.5, -900, 0.9), rung(60.5, 120, 0.4), rung(40.5, -200, 0.7, { book: "FanDuel" }));
    const rungs = ladderRungs(over(), l, "DraftKings");
    expect(rungs.map((r) => [r.line, r.odds])).toEqual([[30.5, -250]]); // best price per line; -900 too short, +120 too unlikely, FanDuel skipped
    expect(rungs[0]).toMatchObject({ side: "Over", alt: true, link: "https://sportsbook.draftkings.com/?outcomes=30.5" });
  });
  it("drops rungs without a usable betslip link", () => {
    const noLink = rung(25.5, -200, 0.75, { over: { odds: -200, prob: 0.75, ev: 0, link: null } });
    const template = rung(35.5, -200, 0.75, { over: { odds: -200, prob: 0.75, ev: 0, link: "https://{state}.betrivers.com/?coupon={pickType}|1|{wagerAmount}" } });
    const needsState = rung(45.5, -200, 0.75, { over: { odds: -200, prob: 0.75, ev: 0, link: "https://sports.{state}.betmgm.com/en/sports?options=6:1-2-3&type=Single" } });
    expect(ladderRungs(over(), ladder(noLink, template, needsState, rung(55.5, -200, 0.75)), "DraftKings").map((r) => r.line)).toEqual([45.5, 55.5]);
  });
  it("blends the model's probability with the book's price", () => {
    const [r] = ladderRungs(over(), ladder(rung(30.5, -200, 0.9)), "DraftKings");
    expect(r.prob).toBeCloseTo(0.65 * 0.9 + 0.35 * (1 / 1.5));
  });
});

describe("ladder targets", () => {
  it("takes one likely, unflagged rush/receiving over per player", () => {
    const rows = [over({ player_id: "a", p_model: 0.6 }), over({ player_id: "a", kind: "rec", p_model: 0.9 }), over({ player_id: "b", p_model: 0.7 }),
      over({ player_id: "c", flagged: true }), pick({ player_id: "d", side: "Under" }), over({ player_id: "e", kind: "pass" }), over({ player_id: "f", kind: "td" })];
    expect(ladderTargets(rows).map((p) => p.player_id)).toEqual(["a", "b"]);
    expect(ladderTargets(rows, 1)).toHaveLength(1);
  });
});

describe("ladder parlays", () => {
  const entry = (id: string, ...quotes: LadderRow[]) => ({ base: over({ player_id: id, name: id, game_id: "g1" }), ladder: ladder(...quotes) });

  it("lands each parlay in its price band using different players, even from one game", () => {
    const entries = [entry("a", rung(30.5, -200, 0.72)), entry("b", rung(40.5, -150, 0.66)), entry("c", rung(50.5, -180, 0.7)), entry("d", rung(20.5, -300, 0.78))];
    const parlays = buildLadderParlays(entries, "DraftKings");
    expect(parlays.length).toBeGreaterThan(0);
    for (const p of parlays) {
      expect(p.american).toBeGreaterThanOrEqual(100);
      expect(p.american).toBeLessThanOrEqual(300);
      expect(new Set(p.legs.map((l) => l.player_id)).size).toBe(p.legs.length);
      expect(p.legs.length).toBeGreaterThanOrEqual(2);
      expect(p.sameGame).toBe(true);
      expect(p.book).toBe("DraftKings");
    }
    expect(parlays[0].key).toBe("ladder-1");
  });

  it("picks the likeliest combination in a band", () => {
    // a+b and a+c both land in +100..+150; b is likelier than c
    const entries = [entry("a", rung(30.5, -200, 0.7)), entry("b", rung(30.5, -180, 0.75)), entry("c", rung(30.5, -180, 0.6))];
    const [first] = buildLadderParlays(entries, "DraftKings");
    expect(first.legs.map((l) => l.player_id).sort()).toEqual(["a", "b"]);
  });

  it("can choose between several rungs of one player but never uses two", () => {
    const entries = [entry("a", rung(20.5, -400, 0.8), rung(30.5, -250, 0.7), rung(40.5, -150, 0.62)), entry("b", rung(30.5, -200, 0.7))];
    for (const p of buildLadderParlays(entries, "DraftKings")) expect(p.legs.filter((l) => l.player_id === "a").length).toBeLessThanOrEqual(1);
  });

  it("returns nothing when no combination reaches +100, and only reads the chosen book", () => {
    expect(buildLadderParlays([entry("a", rung(10.5, -400, 0.85)), entry("b", rung(10.5, -400, 0.85))], "DraftKings")).toEqual([]);
    expect(buildLadderParlays([entry("a", rung(30.5, -150, 0.7)), entry("b", rung(30.5, -150, 0.7))], "FanDuel")).toEqual([]);
  });

  it("prices the combined odds from the rung prices", () => {
    const [p] = buildLadderParlays([entry("a", rung(30.5, -200, 0.72)), entry("b", rung(40.5, -150, 0.66))], "DraftKings");
    expect(p.decimal).toBeCloseTo(toDecimal(-200) * toDecimal(-150));
    expect(p.american).toBe(toAmerican(p.decimal));
  });

  it("gives every leg of every ladder parlay a betslip link", () => {
    const entries = [entry("a", rung(30.5, -200, 0.72), rung(35.5, -200, 0.72, { over: { odds: -100, prob: 0.9, ev: 0, link: null } })),
      entry("b", rung(40.5, -150, 0.66)), entry("c", rung(20.5, -300, 0.78))];
    const parlays = buildLadderParlays(entries, "DraftKings");
    expect(parlays.length).toBeGreaterThan(0);
    for (const p of parlays) for (const l of p.legs) expect(pickToLeg(l).link).toBeTruthy();
  });

  it("carries rung links onto the betslip leg", () => {
    const [p] = buildLadderParlays([entry("a", rung(30.5, -200, 0.72)), entry("b", rung(40.5, -150, 0.66))], "DraftKings");
    expect(pickToLeg(p.legs[0])).toMatchObject({ alt: true, link: expect.stringContaining("draftkings.com") });
  });
});

describe("defaultBook", () => {
  it("falls back to the book with the most overs when no standard parlay exists", () => {
    const picksByBook = { A: [over()], B: [over({ player_id: "x" }), over({ player_id: "y" })], C: [] };
    expect(defaultBook({}, picksByBook)).toBe("B");
    expect(defaultBook({}, {})).toBeNull();
  });
});
