import { describe, expect, it } from "vitest";
import { americanOdds, kickoff, pct, signed, signedPct, timeAgo } from "./format";

describe("format", () => {
  it("formats percentages and signs", () => {
    expect(pct(0.1234)).toBe("12.3%");
    expect(signedPct(0.05)).toBe("+5.0%");
    expect(signedPct(-0.021)).toBe("-2.1%");
    expect(signed(3.14159)).toBe("+3.1");
  });
  it("formats American odds", () => {
    expect(americanOdds(120)).toBe("+120");
    expect(americanOdds(-110)).toBe("-110");
  });
  it("labels kickoff by weekday", () => {
    expect(kickoff("2026-10-04", "13:00")).toBe("Sun 13:00");
  });
  it("renders relative times", () => {
    const now = Date.parse("2026-10-04T12:00:00Z");
    expect(timeAgo("2026-10-04T11:30:00", now)).toBe("30 min ago");
    expect(timeAgo("2026-10-04T08:00:00", now)).toBe("4 h ago");
  });
});
