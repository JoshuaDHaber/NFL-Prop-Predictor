import { describe, expect, it } from "vitest";
import type { SyncPlan } from "./api";
import { planSummary } from "./sync";

const plan = (over: Partial<SyncPlan> = {}): SyncPlan => ({
  season: 2026, week: 5, total_games: 14,
  games: [{ game_id: "g1", label: "AAA @ BBB", gameday: "2026-10-11", need_main: ["rush", "td"], need_alt: true, credits: 6 },
          { game_id: "g2", label: "CCC @ DDD", gameday: "2026-10-12", need_main: ["rush"], need_alt: false, credits: 1 }],
  credits: 7, will_run_projections: true, has_odds_key: true, ...over,
});

describe("planSummary", () => {
  it("describes a normal weekly sync and its cost", () => {
    const s = planSummary(plan(), "missing");
    expect(s.title).toBe("Sync 2026 week 5");
    expect(s.credits).toBe(7);
    expect(s.lines[0]).toContain("Run the model for 2026 week 5");
    expect(s.lines[1]).toContain("2 of 14 games");
    expect(s.lines[1]).toContain("about 7 Odds API credits");
    expect(s.blocked).toBeNull();
  });
  it("spends nothing when every game already has odds", () => {
    const s = planSummary(plan({ games: [], credits: 0 }), "missing");
    expect(s.credits).toBe(0);
    expect(s.lines[1]).toBe("Odds are already stored for all 14 games: no API credits spent.");
    expect(s.nothingToDo).toBe(false); // the model still runs
  });
  it("projections only never spends credits", () => {
    const s = planSummary(plan(), "none");
    expect(s.credits).toBe(0);
    expect(s.lines).toHaveLength(2);
    expect(s.lines[1]).toBe("No odds are fetched: no API credits spent.");
  });
  it("on a host that doesn't run the model it says so, and can have nothing to do", () => {
    const s = planSummary(plan({ will_run_projections: false, games: [], credits: 0 }), "missing");
    expect(s.lines[0]).toContain("only odds are fetched");
    expect(s.nothingToDo).toBe(true);
  });
  it("warns when odds can't be fetched without an API key", () => {
    expect(planSummary(plan({ has_odds_key: false }), "missing").blocked).toContain("No Odds API key");
  });
  it("works before the schedule has a week", () => {
    expect(planSummary(plan({ season: null, week: null }), "missing").title).toBe("Sync the next week");
  });
});
