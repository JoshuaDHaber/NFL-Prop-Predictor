import { describe, expect, it } from "vitest";
import type { Leg } from "./slip";
import { mergeSlips, sameSlip } from "./slipSync";

const leg = (id: string) => ({ id } as Leg);

describe("slip sync", () => {
  it("merges two copies without losing a leg, keeping the first copy's order and stakes", () => {
    const m = mergeSlips({ legs: [leg("a"), leg("b")], stakes: { FanDuel: 20 } }, { legs: [leg("b"), leg("c")], stakes: { FanDuel: 5, DraftKings: 10 } });
    expect(m.legs.map((l) => l.id)).toEqual(["a", "b", "c"]);
    expect(m.stakes).toEqual({ FanDuel: 20, DraftKings: 10 });
  });

  it("tells the same slip from a changed one by its legs and stakes", () => {
    expect(sameSlip({ legs: [leg("a")], stakes: { X: 1 } }, { legs: [leg("a")], stakes: { X: 1 } })).toBe(true);
    expect(sameSlip({ legs: [leg("a")], stakes: {} }, { legs: [leg("a"), leg("b")], stakes: {} })).toBe(false);
    expect(sameSlip({ legs: [leg("a")], stakes: { X: 1 } }, { legs: [leg("a")], stakes: { X: 2 } })).toBe(false);
  });
});
