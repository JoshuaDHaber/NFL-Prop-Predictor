import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type JobStatus, type Meta, type SyncPlan } from "../api";
import { elapsedSeconds, planSummary, progressLine, slowHint, type SyncMode } from "../sync";

/** A ticking clock while a sync runs, so a long step never looks like a hang. */
function useElapsed(startedAt: string | null | undefined, running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return elapsedSeconds(startedAt, now);
}

function SyncProgress({ job }: { job: JobStatus }) {
  const elapsed = useElapsed(job.started_at, job.state === "running");
  const hint = slowHint({ stage: job.stage, detail: job.detail }, elapsed);
  return (
    <div className="job progress" aria-live="polite">
      <div><b>{progressLine({ stage: job.stage, step: job.step, steps: job.steps }, elapsed)}</b></div>
      {job.progress != null && (
        <div className="bar" role="progressbar" aria-valuenow={Math.round(job.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          <i style={{ width: `${Math.round(job.progress * 100)}%` }} />
        </div>
      )}
      {job.detail && <div className="mut">{job.detail}</div>}
      {hint && <div className="mut">{hint}</div>}
    </div>
  );
}

/** Admin: sync the next week's data (projections + odds) into the database, with a confirm step that shows the cost. */
export default function RefreshButton({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<{ mode: SyncMode; plan: SyncPlan; full: boolean } | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const wasRunning = useRef(false);
  const status = useQuery({
    queryKey: ["status"], queryFn: api.status, initialData: meta.job,
    refetchInterval: (q) => (q.state.data?.state === "running" ? 1500 : false),
  });
  const start = useMutation({
    mutationFn: api.refresh,
    onSuccess: (job) => { qc.setQueryData(["status"], job); qc.invalidateQueries({ queryKey: ["status"] }); },
  });
  const job = status.data;
  const running = job.state === "running";

  useEffect(() => {
    if (wasRunning.current && !running) qc.invalidateQueries(); // refetch everything once a sync finishes
    wasRunning.current = running;
  }, [running, qc]);

  // look up what the sync would do first, so the confirm step can show games, credits and how long the model will take
  const review = async (mode: SyncMode, full = false) => {
    setOpen(false); setPlanError(null); setLoadingPlan(true);
    try { setPending({ mode, full, plan: await api.refreshPlan(mode, full) }); }
    catch (e) { setPlanError((e as Error).message); }
    finally { setLoadingPlan(false); }
  };
  // ticking "recalibrate" re-asks the server, since it changes the time estimate
  const toggleFull = async (full: boolean) => {
    if (!pending) return;
    try { setPending({ ...pending, full, plan: await api.refreshPlan(pending.mode, full) }); }
    catch (e) { setPlanError((e as Error).message); }
  };
  const confirm = () => {
    if (pending) { start.mutate({ odds: pending.mode, full: pending.full }); setDismissed(null); setPending(null); }
  };

  const summary = pending ? planSummary(pending.plan, pending.mode, pending.full) : null;
  const canRun = meta.can_run_projections;
  const showDone = job.state === "done" && job.finished_at !== dismissed;
  const cal = meta.calibration;

  return (
    <div className="refresh">
      <div className="split">
        <button className="primary" disabled={running || loadingPlan} onClick={() => review("missing")}
          title="Run the model for the next week's games and fetch any odds that aren't stored yet. Shows what it will do and cost first.">
          {running ? "Syncing…" : loadingPlan ? "Checking…" : canRun ? "Sync next week" : "Fetch odds"}
        </button>
        <button className="primary caret" disabled={running || loadingPlan} onClick={() => setOpen(!open)} aria-label="Sync options">▾</button>
      </div>
      {open && (
        <div className="menu" role="menu">
          <button role="menuitem" onClick={() => review("missing")}>
            {canRun ? "Sync next week" : "Fetch missing odds"} <small>default · only what's missing</small>
          </button>
          <button role="menuitem" disabled={!meta.has_odds_key} onClick={() => review("thin")}>
            Top up thin games <small>re-fetch games with few lines</small>
          </button>
          {canRun && <button role="menuitem" onClick={() => review("none")}>Model only <small>no API credits</small></button>}
          {canRun && <button role="menuitem" onClick={() => review("none", true)}>Recalibrate model <small>slow · no credits</small></button>}
          <button role="menuitem" disabled={!meta.has_odds_key} onClick={() => review("all")}>
            Re-fetch all odds for the week <small>{meta.has_odds_key ? "spends credits" : "needs ODDS_API_KEY"}</small>
          </button>
          {cal && <div className="menu-note mut">Calibrated through week {cal.week} · {new Date(cal.at + "Z").toLocaleDateString()}</div>}
        </div>
      )}

      {summary && pending && (
        <div className="sync-panel" role="dialog" aria-label="Confirm sync">
          <b>{summary.title}</b>
          <ul>{summary.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
          {pending.plan.games.length > 0 && pending.mode !== "none" && (
            <details>
              <summary>Games to fetch ({pending.plan.games.length})</summary>
              <ul className="mut">
                {pending.plan.games.map((g) => (
                  <li key={g.game_id}>
                    {g.label}: {g.reason === "thin" ? `only ${g.stored_quotes} lines stored, ` : ""}{g.need_main.length} main {g.need_main.length === 1 ? "market" : "markets"}{g.need_alt ? " + alternates" : ""} ({g.credits} credits)
                  </li>
                ))}
              </ul>
            </details>
          )}
          {canRun && pending.mode !== "all" && (
            <label className="check" title="Refit the model's error tables and redistribution shares on the latest results instead of reusing the saved ones">
              <input type="checkbox" checked={pending.full} onChange={(e) => toggleFull(e.target.checked)} /> Recalibrate the model (slower)
            </label>
          )}
          {summary.blocked && <p className="err">{summary.blocked}</p>}
          <div className="sync-actions">
            <button className="primary" disabled={summary.nothingToDo || !!summary.blocked} onClick={confirm}>
              {summary.credits > 0 ? `Run · ${summary.credits} credits` : "Run"}
            </button>
            <button className="link" onClick={() => setPending(null)}>Cancel</button>
          </div>
          {summary.nothingToDo && <p className="mut">Nothing to do: all games already have odds.</p>}
        </div>
      )}
      {planError && <div className="job"><div className="err">{planError}</div></div>}
      {start.error && <div className="job"><div className="err">{(start.error as Error).message}</div></div>}
      {running && <SyncProgress job={job} />}
      {job.state === "error" && (
        <div className="job" aria-live="polite">
          {job.log.slice(-3).map((l, i) => <div key={i}>{l}</div>)}
          {job.error && <div className="err">{job.error}</div>}
        </div>
      )}
      {showDone && (
        <div className="job done" aria-live="polite">
          <div><b>✓ Sync finished.</b> {job.log.filter((l) => /^Stored|^Redistribution|^Using the saved|Odds already/.test(l)).slice(-2).join(" · ")}</div>
          <button className="link" onClick={() => setDismissed(job.finished_at)}>Dismiss</button>
        </div>
      )}
    </div>
  );
}
