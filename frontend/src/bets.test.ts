import { describe, expect, it } from "vitest";
import { costOf, legLeague, parseOdds, signedMoney, winReturn } from "./bets";

describe("bets helpers", () => {
  it("reads American odds typed by hand and refuses anything else", () => {
    expect(parseOdds("+264")).toBe(264);
    expect(parseOdds(" -110 ")).toBe(-110);
    expect(parseOdds("250")).toBe(250);
    for (const bad of ["", "50", "-99", "1.91", "abc", "+"]) expect(parseOdds(bad)).toBeNull();
  });

  it("knows a leg's league from its market, as the server does", () => {
    expect(legLeague("pts")).toBe("nba");
    expect(legLeague("rush")).toBe("nfl");
  });

  it("signs money", () => {
    expect(signedMoney(24)).toBe("+$24.00");
    expect(signedMoney(-5.5)).toBe("−$5.50");
    expect(signedMoney(0)).toBe("$0.00");
  });
});

describe("bonus bets", () => {
  it("pay back only the winnings and cost nothing", () => {
    expect(winReturn(10, 15, false)).toBe(25);
    expect(winReturn(10, 15, true)).toBe(15);
    expect(costOf({ stake: 10, bonus: true })).toBe(0);
    expect(costOf({ stake: 10, bonus: false })).toBe(10);
  });
});
