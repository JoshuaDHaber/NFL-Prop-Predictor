import { describe, expect, it } from "vitest";
import { luminance, matchupColors, teamLogo } from "./teams";

describe("team colors", () => {
  it("keeps both primaries when they look different", () => {
    const [a, h] = matchupColors("BAL", "CLE");
    expect([a.light, h.light]).toEqual(["#241773", "#FF3C00"]);
  });
  it("switches the home side to its secondary when the primaries clash", () => {
    const [, h] = matchupColors("SEA", "NE"); // navy vs navy
    expect(h.light).toBe("#C60C30");
  });
  it("never puts a near-black color on the dark theme", () => {
    for (const [away, home] of [["CHI", "ATL"], ["LV", "PIT"], ["HOU", "NE"], ["NYJ", "LV"]]) {
      for (const s of matchupColors(away, home)) expect(luminance(s.dark)).toBeGreaterThanOrEqual(0.03);
    }
  });
  it("picks readable text on light colors", () => {
    expect(matchupColors("PIT", "BAL")[0].ink).toBe("#101820");
  });
  it("maps ESPN's logo names and ignores unknown teams", () => {
    expect(teamLogo("LA")).toContain("/lar.png");
    expect(teamLogo("WAS")).toContain("/wsh.png");
    expect(teamLogo("XYZ")).toBeNull();
  });
});
