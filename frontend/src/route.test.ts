import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS, filterParams } from "./route";

describe("filterParams", () => {
  it("leaves the visitor's own default book out of the address, so it never pins it", () => {
    expect(filterParams({ ...DEFAULT_FILTERS, book: "DraftKings" }, true, "DraftKings").book).toBeNull();
    expect(filterParams({ ...DEFAULT_FILTERS, book: "BetMGM" }, true, "DraftKings").book).toBe("BetMGM");
    // switching to every book when the default is one book is a real choice, so it's kept
    expect(filterParams({ ...DEFAULT_FILTERS, book: "all" }, true, "DraftKings").book).toBe("all");
    expect(filterParams({ ...DEFAULT_FILTERS, book: "all" }, true).book).toBeNull();
  });
});
