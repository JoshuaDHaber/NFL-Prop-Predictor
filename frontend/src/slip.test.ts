import { describe, expect, it } from "vitest";
import type { Leg } from "./slip";
import { slipLinksText, combinedLink, openProgress, linkStatus, alternativesAtBook, bookCoverage, bookOptions, groupByBook, legId, rebook, legLink, parlay, sameGame, slipText, toAmerican, toDecimal, toWin } from "./slip";

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

describe("link status", () => {
  it("classifies links by whether they can add the leg to the slip", () => {
    expect(linkStatus({ link: "https://fd/addToBetslip?x=1" }, "")).toBe("direct");
    expect(linkStatus({ link: null }, "pa")).toBe("missing");
    expect(linkStatus({ link: "https://sports.{state}.betmgm.com/a" }, "")).toBe("needs-state");
    expect(linkStatus({ link: "https://sports.{state}.betmgm.com/a" }, "NJ")).toBe("direct");
    expect(linkStatus({ link: "https://x/?c={pickType}|1" }, "pa")).toBe("missing");
  });
});

describe("open-all stepping", () => {
  const a = leg({ id: "a", book: "DraftKings", link: "https://dk/a" });
  const b = leg({ id: "b", book: "DraftKings", link: "https://dk/b" });
  const c = leg({ id: "c", book: "DraftKings", link: null });
  const d = leg({ id: "d", book: "FanDuel", link: "https://fd/d" });
  it("tracks which linked legs at a book are still to open", () => {
    expect(openProgress([a, b, c, d], "DraftKings", "", [])).toMatchObject({ done: 0, skipped: 1 });
    const p = openProgress([a, b, c, d], "DraftKings", "", ["a"]);
    expect(p.done).toBe(1);
    expect(p.remaining.map((l) => l.id)).toEqual(["b"]);
  });
  it("is finished once every linked leg was opened", () => {
    expect(openProgress([a, b], "DraftKings", "", ["a", "b"]).remaining).toEqual([]);
  });
});

describe("combined links", () => {
  it("builds one FanDuel URL carrying every selection", () => {
    const c = combinedLink("FanDuel", [
      "https://sportsbook.fanduel.com/addToBetslip?marketId=42.1&selectionId=11",
      "https://sportsbook.fanduel.com/addToBetslip?marketId=42.2&selectionId=22",
    ]);
    expect(c?.url).toBe("https://sportsbook.fanduel.com/addToBetslip?marketId[0]=42.1&selectionId[0]=11&marketId[1]=42.2&selectionId[1]=22");
    expect(c?.count).toBe(2);
  });
  it("joins DraftKings outcome ids into one URL", () => {
    const c = combinedLink("DraftKings", [
      "https://sportsbook.draftkings.com/?outcomes=0QA1%232_13L1Q1Q20",
      "https://sportsbook.draftkings.com/?outcomes=0QA3%234_13L1Q2Q20",
    ]);
    expect(c?.url).toBe("https://sportsbook.draftkings.com/?outcomes=0QA1%232_13L1Q1Q20,0QA3%234_13L1Q2Q20");
  });
  it("declines when it can't combine safely", () => {
    expect(combinedLink("FanDuel", ["https://x/addToBetslip?marketId=1&selectionId=2"])).toBeNull(); // single leg
    expect(combinedLink("BetMGM", ["https://a", "https://b"])).toBeNull(); // format unknown
    expect(combinedLink("FanDuel", ["https://x/y", "https://x/z"])).toBeNull(); // missing ids
  });
});

describe("copy slip links", () => {
  const dk = (id: string, o: string) => leg({ id, book: "DraftKings", link: `https://sportsbook.draftkings.com/?outcomes=${o}` });
  const fd = (id: string, m: string, s: string) => leg({ id, book: "FanDuel", link: `https://sportsbook.fanduel.com/addToBetslip?marketId=${m}&selectionId=${s}` });
  it("copies the bare combined URL for a single book", () => {
    expect(slipLinksText([dk("a", "A1"), dk("b", "B2")], "")).toBe("https://sportsbook.draftkings.com/?outcomes=A1,B2");
  });
  it("copies the single link for a one-leg slip", () => {
    expect(slipLinksText([dk("a", "A1")], "")).toBe("https://sportsbook.draftkings.com/?outcomes=A1");
  });
  it("labels each book when several are on the slip", () => {
    const t = slipLinksText([dk("a", "A1"), dk("b", "B2"), fd("c", "42.1", "9")], "");
    expect(t).toBe("DraftKings:\nhttps://sportsbook.draftkings.com/?outcomes=A1,B2\n\nFanDuel:\nhttps://sportsbook.fanduel.com/addToBetslip?marketId=42.1&selectionId=9");
  });
  it("lists individual links for books without a combined format, and skips unlinked legs", () => {
    const m = (id: string, u: string) => leg({ id, book: "BetMGM", link: u });
    expect(slipLinksText([m("a", "https://mgm/a"), m("b", "https://mgm/b"), leg({ id: "z", book: "BetMGM", link: null })], ""))
      .toBe("BetMGM:\nhttps://mgm/a\nhttps://mgm/b");
  });
  it("is empty when nothing has a link", () => {
    expect(slipLinksText([leg({ link: null })], "")).toBe("");
  });
});
