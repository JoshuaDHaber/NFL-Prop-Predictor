import type { SyncPlan } from "./api";

export type SyncMode = "none" | "missing" | "all";

export interface PlanSummary {
  title: string;
  lines: string[];       // what will happen, in order
  credits: number;       // Odds API credits it will spend
  blocked: string | null; // why the odds part can't run, if it can't
  nothingToDo: boolean;
}

/** Plain-English description of a sync, built from the server's plan, for the confirm step. */
export function planSummary(plan: SyncPlan, mode: SyncMode): PlanSummary {
  const lines: string[] = [];
  const week = plan.week ? `${plan.season} week ${plan.week}` : "the next week";
  if (mode !== "all" || plan.will_run_projections) {
    lines.push(plan.will_run_projections
      ? `Run the model for ${week}'s games (about 15 to 30 seconds).`
      : "The model run is not done on this host: only odds are fetched.");
  }
  let credits = 0;
  let blocked: string | null = null;
  if (mode !== "none") {
    credits = plan.credits;
    const n = plan.games.length;
    if (n === 0) {
      lines.push(`Odds are already stored for all ${plan.total_games} games: no API credits spent.`);
    } else {
      lines.push(`Fetch odds for ${n} of ${plan.total_games} games (main lines, anytime TD and alternate lines): about ${credits} Odds API credits.`);
      if (!plan.has_odds_key) blocked = "No Odds API key is configured on the server, so odds can't be fetched.";
    }
  } else {
    lines.push("No odds are fetched: no API credits spent.");
  }
  const nothingToDo = mode !== "none" && !plan.will_run_projections && plan.games.length === 0;
  return { title: `Sync ${week}`, lines, credits, blocked, nothingToDo };
}
