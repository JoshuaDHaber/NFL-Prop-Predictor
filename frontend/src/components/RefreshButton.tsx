import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Meta } from "../api";

export default function RefreshButton({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
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
    if (wasRunning.current && !running) qc.invalidateQueries(); // refetch everything once a run finishes
    wasRunning.current = running;
  }, [running, qc]);

  const go = (odds: "none" | "missing" | "all") => { setOpen(false); start.mutate(odds); };

  return (
    <div className="refresh">
      <div className="split">
        <button className="primary" disabled={running} onClick={() => go("missing")}
          title={meta.can_run_projections ? "Recompute projections; fetch odds (including alternate lines) only for what is not stored yet"
            : "Fetch odds (including alternate lines) only for what is not stored yet"}>
          {running ? "Refreshing…" : meta.can_run_projections ? "Refresh data" : "Fetch odds"}
        </button>
        <button className="primary caret" disabled={running} onClick={() => setOpen(!open)} aria-label="Refresh options">▾</button>
      </div>
      {open && (
        <div className="menu" role="menu">
          {meta.can_run_projections && <button role="menuitem" onClick={() => go("none")}>Projections only <small>no API credits</small></button>}
          <button role="menuitem" onClick={() => go("missing")}>
            {meta.can_run_projections ? "Projections + missing odds" : "Missing odds"} <small>default · incl. alt lines</small>
          </button>
          <button role="menuitem" disabled={!meta.has_odds_key} onClick={() => go("all")}>
            Re-fetch all odds <small>{meta.has_odds_key ? "~100+ API credits" : "needs ODDS_API_KEY"}</small>
          </button>
        </div>
      )}
      {(running || job.state === "error") && (
        <div className="job" aria-live="polite">
          {job.log.slice(-3).map((l, i) => <div key={i}>{l}</div>)}
          {job.error && <div className="err">{job.error}</div>}
        </div>
      )}
    </div>
  );
}
