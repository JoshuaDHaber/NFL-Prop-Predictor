import { describe, expect, it } from "vitest";
import { hitRate, seasonStarts, withGaps } from "./gameLog";
import { hashFor, selectedFromHash } from "./playerHash";

const g = (label: string, yards: number, opp = "LA") => ({ label, opp, yards, volume: 0 });

describe("withGaps", () => {
  it("marks skipped weeks inside a season, one placeholder per stretch", () => {
    const bars = withGaps([g("2025 W12", 3), g("2025 W13", 4), g("2025 W15", 4), g("2025 W17", 2), g("2025 W18", 6), g("2026 W1", 8)]);
    expect(bars.map((b) => b.tick)).toEqual(["W12", "W13", "W14", "W15", "W16", "W17", "W18", "W1"]);
    expect(bars.filter((b) => b.missed).map((b) => b.yards)).toEqual([null, null]);
    expect(withGaps([g("2025 W3", 1), g("2025 W7", 2)])[1].tick).toBe("W4–6");
  });
  it("doesn't bridge seasons, and leaves other labels alone", () => {
    expect(withGaps([g("2025 W18", 1), g("2026 W1", 2)]).length).toBe(2);
    expect(withGaps([g("Oct 22", 20), g("Oct 25", 18)]).map((b) => b.tick)).toEqual(["Oct 22", "Oct 25"]);
  });
  it("finds where a new season starts", () => {
    expect(seasonStarts(withGaps([g("2025 W17", 1), g("2025 W18", 1), g("2026 W1", 2)])).map((b) => b.label)).toEqual(["2026 W1"]);
  });
});

describe("hitRate", () => {
  it("counts games past the line on the play's side, skipping missed weeks", () => {
    const bars = withGaps([g("2025 W1", 4), g("2025 W2", 3), g("2025 W4", 6), g("2025 W5", 5), g("2025 W6", 2), g("2025 W7", 1)]);
    expect(hitRate(bars, "Over", 4.5)).toEqual({ n: 6, hit: 2, n5: 5, hit5: 2 });
    expect(hitRate(bars, "Under", 4.5)).toEqual({ n: 6, hit: 4, n5: 5, hit5: 3 });
  });
});

describe("player hash", () => {
  it("round-trips a drawer and its play next to #game", () => {
    const hash = hashFor({ id: "00-1", kind: "recs", pick: { side: "Under", line: 4.5, book: "FanDuel" } }, "#game=2026_08_CAR_GB");
    expect(hash).toContain("game=2026_08_CAR_GB");
    expect(selectedFromHash(hash)).toEqual({ id: "00-1", kind: "recs", pick: { side: "Under", line: 4.5, book: "FanDuel" } });
    expect(hashFor(null, hash)).toBe("#game=2026_08_CAR_GB");
  });
  it("ignores a broken link", () => {
    expect(selectedFromHash("#player=00-1&kind=nope")).toBeNull();
    expect(selectedFromHash("#player=00-1&kind=rec&side=Over")).toEqual({ id: "00-1", kind: "rec", pick: undefined });
  });
});
