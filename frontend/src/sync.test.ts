import { describe, expect, it } from "vitest";
import type { SyncPlan } from "./api";
import { elapsedSeconds, mmss, planSummary, progressLine, slowHint } from "./sync";

const plan = (over: Partial<SyncPlan> = {}): SyncPlan => ({
  season: 2026, week: 5, total_games: 14,
  games: [{ game_id: "g1", label: "AAA @ BBB", gameday: "2026-10-11", need_main: ["rush", "td"], need_alt: true, credits: 6 },
          { game_id: "g2", label: "CCC @ DDD", gameday: "2026-10-12", need_main: ["rush"], need_alt: false, credits: 1 }],
  credits: 7, will_run_projections: true, has_odds_key: true, will_recalibrate: false,
  calibration: { at: "2026-10-06T21:00:00", season: 2026, week: 4 }, ...over,
});

describe("planSummary", () => {
  it("describes a normal weekly sync and its cost", () => {
    const s = planSummary(plan(), "missing");
    expect(s.title).toBe("Sync 2026 week 5");
    expect(s.credits).toBe(7);
    expect(s.lines[0]).toContain("using the saved calibration (week 4)");
    expect(s.lines[0]).toContain("about a minute");
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

describe("planSummary: recalibration and thin games", () => {
  it("says a refit is slow and warns when the saved calibration can't be reused", () => {
    expect(planSummary(plan(), "missing", true).lines[0]).toContain("refit its calibration");
    const stale = planSummary(plan({ will_recalibrate: true }), "missing");
    expect(stale.lines[0]).toContain("refit its calibration");
    expect(stale.lines[1]).toContain("missing or too old");
  });
  it("describes topping up thin games and what it costs", () => {
    const games = [
      { game_id: "g1", label: "AAA @ BBB", gameday: "d", need_main: ["rush"], need_alt: true, credits: 9, reason: "thin", stored_quotes: 6 },
      { game_id: "g2", label: "CCC @ DDD", gameday: "d", need_main: ["rush"], need_alt: true, credits: 9, reason: "missing", stored_quotes: 0 },
    ];
    const s = planSummary(plan({ games, credits: 18 }), "thin");
    expect(s.credits).toBe(18);
    expect(s.lines.join(" ")).toContain("1 thin and 1 missing games");
  });
  it("explains when no game needs topping up", () => {
    const s = planSummary(plan({ games: [], credits: 0 }), "thin");
    expect(s.lines[1]).toContain("No game needs topping up");
    expect(s.credits).toBe(0);
  });
});

describe("progress helpers", () => {
  it("formats minutes and seconds", () => {
    expect(mmss(83)).toBe("1:23");
    expect(mmss(5)).toBe("0:05");
    expect(mmss(-3)).toBe("0:00");
  });
  it("measures elapsed time from the server's zone-less UTC timestamp", () => {
    const now = Date.parse("2026-10-06T21:41:00Z");
    expect(elapsedSeconds("2026-10-06T21:38:27.828332", now)).toBeCloseTo(152.17, 1);
    expect(elapsedSeconds("2026-10-06T21:38:27Z", now)).toBe(153);
    expect(elapsedSeconds(null, now)).toBe(0);
    expect(elapsedSeconds("garbage", now)).toBe(0);
  });
  it("builds the status line", () => {
    expect(progressLine({ stage: "Running the model", step: 1, steps: 2 }, 192)).toBe("Step 1 of 2 · Running the model · 3:12");
    expect(progressLine({ stage: "Running the model", step: 1, steps: 1 }, 4)).toBe("Running the model · 0:04");
    expect(progressLine({ stage: null, step: 0, steps: 0 }, 0)).toBe("Working · 0:00");
  });
  it("only hints at slowness for the model step, and only once it has dragged on", () => {
    const m = { stage: "Running the model", detail: null };
    expect(slowHint(m, 30)).toBeNull();
    expect(slowHint(m, 60)).toContain("small server");
    expect(slowHint({ stage: "Running the model (full recalibration)", detail: null }, 60)).toContain("8 minutes");
    expect(slowHint({ stage: "Fetching odds", detail: null }, 600)).toBeNull();
  });
});

