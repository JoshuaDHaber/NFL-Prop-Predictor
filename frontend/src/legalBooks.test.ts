import { describe, expect, it } from "vitest";
import { allowedBooks, isLegal } from "./legalBooks";

describe("legal books", () => {
  it("knows where each book is licensed", () => {
    expect(isLegal("DraftKings", "nj")).toBe(true);
    expect(isLegal("BetRivers", "NC")).toBe(false);
    expect(isLegal("Bovada", "NJ")).toBe(false);   // offshore: legal nowhere
  });

  it("lists the books for a state, or every book when unknown or asked for", () => {
    expect(allowedBooks("NH", false)).toEqual(["DraftKings"]);
    expect(allowedBooks("CA", false)).toEqual([]);
    expect(allowedBooks("AR", false)).toEqual(["DraftKings", "FanDuel"]);
    expect(allowedBooks("", false)).toBeNull();
    expect(allowedBooks("NJ", true)).toBeNull();
  });
});
