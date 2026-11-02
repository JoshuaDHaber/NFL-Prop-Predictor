import { describe, expect, it } from "vitest";
import { favoritesFirst, gameTeams, toggled } from "./favorites";

const g = (game_id: string) => ({ game_id });

describe("favorites", () => {
  it("reads both teams from NFL and NBA game ids", () => {
    expect(gameTeams("2026_07_BUF_KC")).toEqual(["BUF", "KC"]);
    expect(gameTeams("2027_20261020_BOS_DET")).toEqual(["BOS", "DET"]);
  });
  it("puts favorite teams' games first, home or away, keeping kickoff order", () => {
    const games = ["2026_09_BUF_MIA", "2026_09_KC_DEN", "2026_09_DET_GB", "2026_09_SF_LA"].map(g);
    expect(favoritesFirst(games, ["GB", "KC"]).map((x) => x.game_id)).toEqual(["2026_09_KC_DEN", "2026_09_DET_GB", "2026_09_BUF_MIA", "2026_09_SF_LA"]);
    expect(favoritesFirst(games, [])).toBe(games);
  });
  it("toggles an item in or out", () => {
    expect(toggled(["KC"], "DET", (x) => x === "DET")).toEqual(["KC", "DET"]);
    expect(toggled(["KC", "DET"], "KC", (x) => x === "KC")).toEqual(["DET"]);
  });
});
