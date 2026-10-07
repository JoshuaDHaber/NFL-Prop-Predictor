import { describe, expect, it } from "vitest";
import type { GameWeather } from "./api";
import { americanOdds, fmtEdge, fmtProj, kickoff, notableWeather, pct, playLabel, signed, signedPct, timeAgo, weatherShort, weatherText, wxEffect } from "./format";

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


describe("weather", () => {
  const w = (o: Partial<GameWeather>): GameWeather => ({ stadium: "Lambeau Field", roof: "outdoors", indoor: false, source: "forecast", temp: 38,
    wind: 19.4, gust: 27, precip_prob: 10, precip: 0, snow: 0, fetched_at: null, factors: {}, ...o });
  it("describes the kickoff forecast, and indoor games by their roof", () => {
    expect(weatherText(w({}))).toBe("38°F · wind 19 mph (gusts 27)");
    expect(weatherText(w({ precip_prob: 70, gust: 20 }))).toBe("38°F · wind 19 mph · 70% rain");
    expect(weatherText(w({ indoor: true, roof: "dome", source: "indoor" }))).toBe("Dome");
    expect(weatherText(w({ source: "none", temp: null, wind: null }))).toBeNull();
  });
  it("flags only weather that matters, with the condition that stands out", () => {
    expect(notableWeather(w({ temp: 70, wind: 6 }))).toBe(false);
    expect(weatherShort(w({}))).toBe("💨 19 mph");
    expect(weatherShort(w({ wind: 5, snow: 0.4 }))).toBe("❄️ snow");
    expect(weatherShort(w({ wind: 5 }))).toBe("🥶 38°F");
  });
  it("shows the adjustment as a percentage, and nothing when there is none", () => {
    expect(wxEffect(0.782)).toBe("−22%");
    expect(wxEffect(1.03)).toBe("+3%");
    expect(wxEffect(1)).toBeNull();
    expect(wxEffect(null)).toBeNull();
  });
});
