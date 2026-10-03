import { describe, expect, it } from "vitest";
import { limitOdds, type LadderRow } from "./api";

const row = (line: number, over: number | null, under: number | null): LadderRow => ({
  line, book: "A", alt: false, event_link: null,
  over: over === null ? null : { odds: over, prob: 0.5, ev: 0, link: null },
  under: under === null ? null : { odds: under, prob: 0.5, ev: 0, link: null },
});

describe("limitOdds (demo mode mirrors the server's -300..+300 rule)", () => {
  it("hides sides priced outside the range and drops rows left with neither", () => {
    const out = limitOdds([row(40.5, -450, 330), row(60.5, -110, -110), row(90.5, 900, null), row(50.5, -300, 300)], 300);
    expect(out.map((r) => r.line)).toEqual([60.5, 50.5]);
    expect(out[1].over?.odds).toBe(-300); // bounds are inclusive
  });
  it("shows everything when the range is 0", () => {
    expect(limitOdds([row(40.5, -450, 330)], 0)).toHaveLength(1);
  });
  it("keeps the side that is in range when only one is", () => {
    const [r] = limitOdds([row(40.5, -450, 120)], 300);
    expect(r.over).toBeNull();
    expect(r.under?.odds).toBe(120);
  });
});
