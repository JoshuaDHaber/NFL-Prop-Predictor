import type { JobStatus, SyncPlan } from "./api";

export type SyncMode = "none" | "missing" | "thin" | "all";

export interface PlanSummary {
  title: string;
  lines: string[];       // what will happen, in order
  credits: number;       // Odds API credits it will spend
  blocked: string | null; // why the odds part can't run, if it can't
  nothingToDo: boolean;
}

/** Plain-English description of a sync, built from the server's plan, for the confirm step. */
export function planSummary(plan: SyncPlan, mode: SyncMode, full = false): PlanSummary {
  const lines: string[] = [];
  const week = plan.week ? `${plan.season} week ${plan.week}` : "the next week";
  if (plan.will_run_projections) {
    const refit = full || plan.will_recalibrate;
    lines.push(refit
      ? `Run the model for ${week}'s games and refit its calibration: a few minutes on a small server (about 8 on the free one).`
      : `Run the model for ${week}'s games using the saved calibration${plan.calibration ? ` (week ${plan.calibration.week})` : ""}: about a minute.`);
    if (!full && plan.will_recalibrate) lines.push("The saved calibration is missing or too old, so it has to be refit.");
  } else {
    lines.push("The model run is not done on this host: only odds are fetched.");
  }
  let credits = 0;
  let blocked: string | null = null;
  if (mode !== "none") {
    credits = plan.credits;
    const n = plan.games.length;
    const thin = plan.games.filter((g) => g.reason === "thin").length;
    if (n === 0) {
      lines.push(mode === "thin"
        ? `No game needs topping up: every game has enough lines, or they were fetched less than 3 hours ago. No API credits spent.`
        : `Odds are already stored for all ${plan.total_games} games: no API credits spent.`);
    } else {
      const what = mode === "thin" && thin > 0 ? `${thin} thin and ${n - thin} missing` : `${n} of ${plan.total_games}`;
      lines.push(`Fetch odds for ${what} games (main lines, anytime TD and alternate lines): about ${credits} Odds API credits.`);
      if (!plan.has_odds_key) blocked = "No Odds API key is configured on the server, so odds can't be fetched.";
    }
  } else {
    lines.push("No odds are fetched: no API credits spent.");
  }
  const nothingToDo = mode !== "none" && !plan.will_run_projections && plan.games.length === 0;
  return { title: `Sync ${week}`, lines, credits, blocked, nothingToDo };
}

/** 83 -> "1:23" */
export function mmss(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Seconds since the job started (the server's timestamps are UTC without a zone suffix). */
export function elapsedSeconds(startedAt: string | null | undefined, now = Date.now()): number {
  if (!startedAt) return 0;
  const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(startedAt) ? startedAt : startedAt + "Z");
  return Number.isNaN(t) ? 0 : Math.max(0, (now - t) / 1000);
}

/** One line describing where a running sync is: "Step 1 of 2 · Running the model · 3:12". */
export function progressLine(job: Pick<JobStatus, "stage" | "step" | "steps">, elapsed: number): string {
  const parts: string[] = [];
  if (job.steps && job.steps > 1 && job.step) parts.push(`Step ${job.step} of ${job.steps}`);
  parts.push(job.stage ?? "Working");
  parts.push(mmss(elapsed));
  return parts.join(" · ");
}

/** A hint for the slow step, shown once it has been running a while. */
export function slowHint(job: Pick<JobStatus, "stage" | "detail">, elapsed: number): string | null {
  const model = job.stage?.startsWith("Running the model");
  if (!model || elapsed < 45) return null;
  return job.stage?.includes("recalibration") || /Walk-forward/.test(job.detail ?? "")
    ? "Refitting the calibration is the slow part on a small server (about 8 minutes on the free one). The page keeps updating."
    : "Still working: the model is running on a small server.";
}
