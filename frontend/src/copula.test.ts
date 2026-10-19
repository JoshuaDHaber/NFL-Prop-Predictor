import { describe, expect, it } from "vitest";
import { jointProb, legRho, normCdf, normInv, pairKey, parlayProb, type CopulaLeg } from "./copula";

const leg = (o: Partial<CopulaLeg>): CopulaLeg =>
  ({ player_id: "qb", team: "AAA", game_id: "g1", kind: "pass", pos: "QB", side: "Over", prob: 0.5, ...o });

describe("normal distribution helpers", () => {
  it("match known values", () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 12);
    expect(normCdf(1.959963985)).toBeCloseTo(0.975, 9);
    expect(normCdf(-3)).toBeCloseTo(0.0013498980316301, 12);
    for (const p of [1e-6, 0.01, 0.3, 0.5, 0.77, 0.999]) expect(normCdf(normInv(p))).toBeCloseTo(p, 10);
  });
});

describe("joint chance (Mendell-Elston, mirrored from backend engine/correlation.py)", () => {
  it("multiplies independent legs", () => {
    expect(jointProb([0.6, 0.5, 0.3], [1, -1, 1], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])).toBeCloseTo(0.09, 12);
  });
  it("gives the exact orthant chance for two correlated coin flips, and an Under flips it", () => {
    const both = jointProb([0.5, 0.5], [1, 1], [[1, 0.4], [0.4, 1]]);
    expect(both).toBeCloseTo(0.25 + Math.asin(0.4) / (2 * Math.PI), 2);
    expect(jointProb([0.5, 0.5], [1, -1], [[1, 0.4], [0.4, 1]])).toBeCloseTo(0.5 - both, 2);
  });
  it("matches the Python twin on a four-leg case", () => {
    // backend: joint_prob([0.62, 0.55, 0.7, 0.58], [1, 1, -1, 1], rho) (simulation: within 0.005)
    const rho = [[1, 0.36, 0.35, -0.19], [0.36, 1, 0.04, 0], [0.35, 0.04, 1, 0], [-0.19, 0, 0, 1]];
    expect(jointProb([0.62, 0.55, 0.7, 0.58], [1, 1, -1, 1], rho)).toBeCloseTo(0.13482681934099494, 6);
  });
});

describe("parlay chance", () => {
  const corr = { [pairKey("team", "pass:QB", "rec:WR")]: 0.36, [pairKey("opp", "rush:RB", "rush:RB")]: -0.19 };
  const qb = leg({ prob: 0.55 });
  const wr = leg({ player_id: "wr", kind: "rec", pos: "WR", prob: 0.6 });
  it("looks pairs up by relation, market and position, in either order", () => {
    expect(legRho(qb, wr, corr)).toBe(0.36);
    expect(legRho(wr, qb, corr)).toBe(0.36);
    expect(legRho(qb, { ...wr, game_id: "g2" }, corr)).toBe(0);                 // another game: independent
    expect(legRho(leg({ player_id: "a", kind: "rush", pos: "RB" }), leg({ player_id: "b", team: "BBB", kind: "rush", pos: "FB" }), corr)).toBe(-0.19);
  });
  it("lifts a stack, lowers a hedge, and leaves other games alone", () => {
    expect(parlayProb([qb, wr], corr)).toBeGreaterThan(0.55 * 0.6 + 0.04);
    expect(parlayProb([qb, { ...wr, side: "Under", prob: 0.4 }], corr)).toBeLessThan(0.55 * 0.4 - 0.03);
    expect(parlayProb([qb, { ...wr, game_id: "g2" }], corr)).toBeCloseTo(0.33, 12);
    expect(parlayProb([qb, wr])).toBeCloseTo(0.33, 12);                              // no table: independent
  });
});
