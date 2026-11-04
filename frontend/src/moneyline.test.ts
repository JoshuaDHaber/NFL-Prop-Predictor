import { describe, expect, it } from "vitest";
import type { MoneylineGame } from "./api";
import { mlLeague, mlPlayerId, moneylinePicks, parseMlId, sidePick, started } from "./moneyline";
import { buildBalancedLadders, buildLadderParlays, moneylineRungs, pickToLeg, recommendParlays, type ParlayLeg } from "./parlays";
import { setLeague } from "./league";
import { clashesWith, conflicts, legText } from "./slip";

const side = (team: string, home: boolean, o: Partial<MoneylineGame["sides"][0]> = {}) => ({
  team, name: team === "KC" ? "Kansas City Chiefs" : "Denver Broncos", home, p_model: 0.6, p_mkt: 0.62, prob: 0.62, books: 5,
  odds: -170, book: "FanDuel", ev: -0.02, kelly: 0, link: `https://sportsbook.fanduel.com/addToBetslip?marketId=1&selectionId=${team}`,
  event_link: null, ...o,
});
const game = (o: Partial<MoneylineGame> = {}): MoneylineGame => ({
  game_id: "2099_09_DEN_KC", label: "DEN @ KC", gameday: "2099-11-08", gametime: "13:00", margin: 3, spread: -3,
  sides: [side("DEN", false, { prob: 0.38, p_model: 0.4, odds: 145, ev: -0.07 }), side("KC", true)], ...o,
});

describe("moneyline ids", () => {
  it("carry the team and its game, so one abbreviation in both leagues never collides", () => {
    expect(mlPlayerId("2099_09_DEN_KC", "KC")).toBe("KC@2099_09_DEN_KC");
    expect(parseMlId("KC@2099_09_DEN_KC")).toEqual({ team: "KC", gameId: "2099_09_DEN_KC" });
    expect(parseMlId("00-0033873")).toBeNull();
    expect(mlPlayerId("2099_20991104_LAC_DEN", "LAC")).not.toBe(mlPlayerId("2099_09_LAC_DEN", "LAC"));
    expect([mlLeague("2099_20991104_LAC_DEN"), mlLeague("2099_09_LAC_DEN")]).toEqual(["nba", "nfl"]);
  });
});

describe("sidePick", () => {
  it("is the team's price as a pick (the team wins: an over at 0) with its betslip link", () => {
    const p = sidePick(game(), game().sides[1])!;
    expect([p.kind, p.side, p.line, p.team, p.opp, p.home, p.odds, p.book, p.prob]).toEqual(["ml", "Over", 0, "KC", "DEN", true, -170, "FanDuel", 0.62]);
    expect(p.link).toContain("selectionId=KC");
    const leg = pickToLeg(p);
    expect(leg.gameId).toBe("2099_09_DEN_KC");
    expect(legText(leg)).toBe("Kansas City Chiefs Moneyline (vs DEN) -170 @ FanDuel");
  });
  it("is nothing without a price", () => {
    expect(sidePick(game(), side("KC", true, { odds: null, book: null, ev: null }))).toBeNull();
  });
  it("leaves out games that have started", () => {
    expect(moneylinePicks([game()], Date.UTC(2099, 0, 1))).toHaveLength(2);
    expect(moneylinePicks([game()], Date.UTC(2099, 10, 9))).toHaveLength(0);
    expect(started(game(), Date.UTC(2099, 10, 9))).toBe(true);
  });
});

describe("moneylines on the slip", () => {
  it("clash when both teams of one game are at one book, as a book won't take both", () => {
    const [den, kc] = moneylinePicks([game()], 0).map(pickToLeg);
    expect(conflicts([den, kc])).toHaveLength(1);
    expect(clashesWith([kc], den)).toBe(true);
    expect(clashesWith([kc], { ...den, book: "DraftKings", id: "x" })).toBe(false);
  });
});

describe("moneylines in parlays and ladders", () => {
  const prop = (o: Partial<ParlayLeg>): ParlayLeg => ({
    player_id: "p", name: "Back", pos: "RB", team: "KC", opp: "DEN", home: true, kind: "rush", mu: 70, sd: 20, status: "",
    game_id: "2099_09_DEN_KC", gameday: "2099-11-08", gametime: "13:00", side: "Over", line: 60.5, odds: -150, book: "FanDuel",
    p_model: 0.7, p_mkt: 0.6, prob: 0.66, ev: 0.05, kelly: 0, books: 4, edge_yds: 5, flagged: false, last5: [],
    link: "https://sportsbook.fanduel.com/addToBetslip?marketId=2&selectionId=9", alt: true, ...o,
  });
  it("count as a likely leg, but not as an over", () => {
    const ml = sidePick(game(), side("KC", true, { prob: 0.9, odds: -250 }))!;
    const overs = [1, 2, 3, 4, 5, 6, 7].map((i) => prop({ player_id: `p${i}`, game_id: `g${i}`, prob: 0.7 - i * 0.01, ev: 0.2 - i * 0.03 }));
    const ml2 = { ...ml, player_id: "BUF@2099_09_BUF_MIA", team: "BUF", game_id: "2099_09_BUF_MIA", prob: 0.85 };
    const ml3 = { ...ml, player_id: "DET@2099_09_DET_GB", team: "DET", game_id: "2099_09_DET_GB", prob: 0.8 };
    const tiles = recommendParlays([ml, ml2, ml3, ...overs]);
    // one moneyline at most in a props tile, so favorites can't crowd the props out; they get a tile of their own
    expect(tiles[0].legs.map((l) => l.kind)).toEqual(["ml", "rush", "rush"]);
    expect(tiles.find((t) => t.key === "favorites")?.legs.map((l) => l.team)).toEqual(["KC", "BUF", "DET"]);
    const overTile = tiles.find((t) => t.key === "overs");
    expect(overTile).toBeDefined();
    expect(overTile!.legs.every((l) => l.kind !== "ml")).toBe(true);
  });
  it("become one-rung ladder players when likely, linked and not too short", () => {
    const picks = [sidePick(game(), side("KC", true, { prob: 0.7, odds: -200 }))!, sidePick(game(), side("DEN", false, { prob: 0.3, odds: 200 }))!,
      sidePick(game(), side("KC", true, { prob: 0.9, odds: -900 }))!, { ...sidePick(game(), side("KC", true, { prob: 0.7 }))!, link: null }];
    expect(moneylineRungs(picks, "FanDuel").map((r) => r.map((l) => l.odds))).toEqual([[-200]]);
    expect(moneylineRungs(picks, "DraftKings")).toEqual([]);
  });
  it("can fill a ladder beside player rungs, and a both-teams ladder for their game", () => {
    setLeague("nfl");
    const ml = moneylineRungs([sidePick(game(), side("KC", true, { prob: 0.72, odds: -150 }))!], "FanDuel");
    const den = prop({ player_id: "d1", team: "DEN", opp: "KC", home: false });
    const ladder = { kind: "rush" as const, mu: 70, sd: 20, game_id: den.game_id, alt_fetched_at: null,
      quotes: [{ line: 50.5, book: "FanDuel", alt: true, event_link: null, over: { odds: -150, prob: 0.75, ev: 0.1, link: den.link! }, under: null }] };
    const tiles = buildLadderParlays([{ base: den, ladder }], "FanDuel", undefined, ml);
    expect(tiles[0].legs.map((l) => l.kind).sort()).toEqual(["ml", "rush"]);
    expect(tiles[0].blurb).toContain("moneylines");
    const both = buildBalancedLadders([{ base: den, ladder }], "FanDuel", [den.game_id], [], undefined, ml);
    expect(both).toHaveLength(1);
    expect(new Set(both[0].legs.map((l) => l.team))).toEqual(new Set(["KC", "DEN"]));
  });
});
