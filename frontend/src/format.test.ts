import { describe, expect, it } from "vitest";
import { americanOdds, fmtEdge, fmtProj, kickoff, pct, playLabel, signed, signedPct, timeAgo } from "./format";

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

describe("anytime TD formatting", () => {
  it("shows a touchdown projection as a chance, and yardage as yards", () => {
    expect(fmtProj("td", 0.412)).toBe("41%");
    expect(fmtProj("rush", 54.6)).toBe("55");
  });
  it("names the plays: Anytime TD / No TD, but Over 54.5 for yardage", () => {
    expect(playLabel("td", "Over", 0.5)).toBe("Anytime TD");
    expect(playLabel("td", "Under", 0.5)).toBe("No TD");
    expect(playLabel("rec", "Under", 54.5)).toBe("Under 54.5");
  });
  it("gives the edge in yards, or percentage points for touchdowns", () => {
    expect(fmtEdge("pass", 7.74)).toBe("+7.7");
    expect(fmtEdge("td", -3.26)).toBe("-3.3 pts");
  });
});

