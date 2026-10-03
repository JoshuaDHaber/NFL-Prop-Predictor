import { describe, expect, it } from "vitest";
import type { Leg } from "./slip";
import { alternativesAtBook, bookCoverage, bookOptions, groupByBook, legId, rebook, legLink, parlay, sameGame, slipText, toAmerican, toDecimal, toWin } from "./slip";

const leg = (o: Partial<Leg> = {}): Leg => ({
  id: "x", playerId: "p1", name: "Test Back", team: "AAA", opp: "BBB", home: true, kind: "rush", side: "Over", line: 60.5,
  odds: 100, book: "DraftKings", link: null, eventLink: null, alt: false, prob: 0.5, ev: 0, gameId: "g1", ...o,
});

describe("odds math", () => {
  it("converts between American and decimal odds", () => {
    expect(toDecimal(150)).toBeCloseTo(2.5);
    expect(toDecimal(-200)).toBeCloseTo(1.5);
    expect(toAmerican(2.5)).toBe(150);
    expect(toAmerican(1.5)).toBe(-200);
  });
  it("multiplies parlay legs", () => {
    const p = parlay([leg({ odds: 100 }), leg({ odds: 100 }), leg({ odds: -200 })], 10);
    expect(p.decimal).toBeCloseTo(2 * 2 * 1.5);
    expect(p.american).toBe(500);
    expect(p.payout).toBeCloseTo(60);
    expect(p.profit).toBeCloseTo(50);
  });
  it("computes single-bet winnings", () => {
    expect(toWin(-110, 11)).toBeCloseTo(10);
    expect(toWin(250, 10)).toBeCloseTo(25);
  });
});

describe("links", () => {
  it("prefers the direct betslip link", () => {
    expect(legLink(leg({ link: "https://fd/addToBetslip?x=1", eventLink: "https://fd/game", book: "FanDuel" }), "")).toBe("https://fd/addToBetslip?x=1");
  });
  it("fills the state placeholder, or falls back to the game page when state is unknown", () => {
    const l = leg({ link: "https://sports.{state}.betmgm.com/a", eventLink: "https://sports.betmgm.com/e", book: "BetMGM" });
    expect(legLink(l, "NJ")).toBe("https://sports.nj.betmgm.com/a");
    expect(legLink(l, "")).toBe("https://sports.betmgm.com/e");
  });
  it("skips links with unresolved template tokens and falls back to the book page", () => {
    const l = leg({ link: "https://x/?coupon={pickType}|1|{wagerAmount}", book: "DraftKings" });
    expect(legLink(l, "pa")).toContain("draftkings.com");
  });
  it("returns null for books we have no page for", () => {
    expect(legLink(leg({ book: "Mystery Book" }), "pa")).toBeNull();
  });
});

describe("slip helpers", () => {
  it("builds stable ids and groups by book", () => {
    expect(legId({ playerId: "p", kind: "rush", side: "Over", line: 50.5, book: "A" })).toBe("p|rush|Over|50.5|A");
    expect(groupByBook([leg({ book: "A" }), leg({ book: "B" }), leg({ book: "A" })]).map(([b, ls]) => [b, ls.length])).toEqual([["A", 2], ["B", 1]]);
  });
  it("detects same-game legs", () => {
    expect(sameGame([leg({ gameId: "g1" }), leg({ gameId: "g1" })])).toBe(true);
    expect(sameGame([leg({ gameId: "g1" }), leg({ gameId: "g2" })])).toBe(false);
  });
  it("formats a copyable slip", () => {
    expect(slipText([leg()])).toBe("DraftKings\n  - Test Back Over 60.5 Rushing yds (vs BBB) +100 @ DraftKings");
  });
});

const ladder = {
  kind: "rush", mu: 50, sd: 20, game_id: "g1", alt_fetched_at: null,
  quotes: [
    { line: 60.5, book: "DraftKings", alt: false, event_link: "https://dk/e", over: { odds: -110, prob: 0.4, ev: -0.1, link: "https://dk/o" }, under: { odds: -110, prob: 0.6, ev: 0.1, link: null } },
    { line: 60.5, book: "FanDuel", alt: false, event_link: null, over: { odds: -105, prob: 0.4, ev: -0.05, link: "https://fd/o" }, under: null },
    { line: 55.5, book: "BetMGM", alt: true, event_link: null, over: { odds: -150, prob: 0.5, ev: -0.2, link: null }, under: null },
  ],
} as const;

describe("rebooking", () => {
  it("lists only books offering the exact line and side, best price first", () => {
    const opts = bookOptions(ladder as any, { line: 60.5, side: "Over" });
    expect(opts.map((o) => o.book)).toEqual(["FanDuel", "DraftKings"]);
    expect(bookOptions(ladder as any, { line: 60.5, side: "Under" }).map((o) => o.book)).toEqual(["DraftKings"]);
    expect(bookOptions(undefined, { line: 60.5, side: "Over" })).toEqual([]);
  });
  it("moves a leg to another book, updating price, links and id", () => {
    const l = leg({ book: "DraftKings", odds: -110, line: 60.5, side: "Over" });
    const moved = rebook(l, bookOptions(ladder as any, l)[0]);
    expect(moved).toMatchObject({ book: "FanDuel", odds: -105, link: "https://fd/o" });
    expect(moved.id).toBe("p1|rush|Over|60.5|FanDuel");
    expect(moved.name).toBe(l.name);
  });
  it("suggests the nearest lines a book does offer", () => {
    const l = { line: 58.5, side: "Over" as const };
    expect(alternativesAtBook(ladder as any, l, "DraftKings").map((o) => o.line)).toEqual([60.5]);
    expect(alternativesAtBook(ladder as any, l, "BetMGM").map((o) => o.line)).toEqual([55.5]);
    expect(alternativesAtBook(ladder as any, l, "Nowhere")).toEqual([]);
    expect(alternativesAtBook(ladder as any, { line: 60.5, side: "Under" }, "FanDuel")).toEqual([]);
  });
  it("re-lines a leg when swapping to a suggestion", () => {
    const l = leg({ book: "FanDuel", line: 58.5, side: "Over" });
    const o = alternativesAtBook(ladder as any, l, "DraftKings")[0];
    expect(rebook(l, o)).toMatchObject({ book: "DraftKings", line: 60.5, id: "p1|rush|Over|60.5|DraftKings" });
  });
  it("counts how many legs each book can take", () => {
    const cov = bookCoverage({ a: [{ book: "X" }, { book: "Y" }] as any, b: [{ book: "X" }] as any });
    expect(cov).toEqual([{ book: "X", count: 2 }, { book: "Y", count: 1 }]);
  });
});
