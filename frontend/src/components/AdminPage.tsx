import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { Fragment, useEffect, useState } from "react";
import { api, type ScheduleSlot, type SyncRun } from "../api";
import { setToken, useToken } from "../auth";
import { BASE } from "../env";
import { timeAgo } from "../format";
import { elapsedSeconds, localWhen, progressLine, untilText } from "../sync";
import ThemeToggle from "./ThemeToggle";

const ODDS_TEXT: Record<string, string> = { none: "Model only", missing: "Model + missing odds", thin: "Model + thin top-up", all: "Model + all odds" };

function Status({ s }: { s: SyncRun["status"] }) {
  const text = { ok: "OK", partial: "Partial", error: "Error", skipped: "Skipped", running: "Running" }[s];
  return <span className={`st st-${s}`}>{text}</span>;
}

function credits(r: SyncRun): string {
  if (r.credits_before == null || r.credits_after == null) return r.odds_mode === "none" ? "—" : "0";
  return `${r.credits_before - r.credits_after} (${r.credits_after} left)`;
}

function RunLog({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["admin-run", id], queryFn: () => api.adminRun(id) });
  if (q.isLoading) return <p className="mut">Loading log…</p>;
  if (q.error || !q.data) return <p className="err">{(q.error as Error)?.message ?? "No log"}</p>;
  return <pre className="runlog">{q.data.log.join("\n") || "(no output)"}{q.data.error ? `\n\n${q.data.error}` : ""}</pre>;
}

function SignIn({ wrong }: { wrong: boolean }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const save = () => { setToken(draft.trim()); setDraft(""); qc.invalidateQueries({ queryKey: ["admin"] }); };
  return (
    <div className="card admin-signin">
      <b>Admin password</b>
      <p className="mut">{wrong ? "That password didn't work." : "The sync schedule, run log and credit balance are for the site owner."}</p>
      <input type="password" value={draft} placeholder="Admin password" autoComplete="current-password" autoFocus
        onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && draft && save()} />
      <button className="primary" disabled={!draft} onClick={save}>Unlock</button>
    </div>
  );
}

/** Owner-only page: what the schedule will run and when, what each run did, and the Odds API key's balance.
 *  Standalone at /admin, or `embedded` as a tab of the main app (no page header of its own). */
export default function AdminPage({ embedded = false }: { embedded?: boolean }) {
  const qc = useQueryClient();
  const token = useToken();
  const [open, setOpen] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const state = useQuery({
    queryKey: ["admin", token], queryFn: api.admin, retry: false,
    refetchInterval: (q) => (q.state.data?.job.state === "running" ? 2000 : 30_000),
  });
  const runNow = useMutation({ mutationFn: api.runSlotNow, onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }) });
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  const signOut = token && <button className="link" onClick={() => { setToken(""); qc.removeQueries({ queryKey: ["admin"] }); }}>Sign out</button>;
  const header = embedded ? null : (
    <header>
      <div>
        <h1><span className="logo">🏈</span> Sync <span className="grad">admin</span></h1>
        <div className="sub"><a href={BASE}>← Back to the site</a></div>
      </div>
      {signOut}
    </header>
  );
  const page = (children: React.ReactNode, cls = "") => embedded
    ? <div className={`admin-page ${cls}`}>{children}</div>
    : <div className={`wrap admin-page ${cls}`}><ThemeToggle />{header}{children}</div>;
  const status = (state.error as { status?: number } | null)?.status;
  if (status === 403 || status === 429) return page(<SignIn wrong={!!token} />);
  if (state.isLoading) return page(<p className="mut">Loading…</p>);
  if (state.error || !state.data) return page(<p className="err">{(state.error as Error)?.message}</p>);

  const d = state.data;
  const job = d.job;
  const running = job.state === "running";
  const c = d.credits;
  const confirmRun = (s: ScheduleSlot) => {
    const cost = s.odds_mode === "none" ? "It spends no Odds API credits." : "It fetches odds, which spends credits (never below the floor).";
    if (window.confirm(`Run "${s.label}" now? ${ODDS_TEXT[s.odds_mode]}${s.full ? " with recalibration" : ""}. ${cost}`)) runNow.mutate(s.id);
  };

  return (
    page(<>
      {embedded && signOut && <div className="admin-signout">{signOut}</div>}

      {c.low && (
        <div className="banner">
          <b>Rotate the Odds API key.</b> The key ending {c.key_hint} has {c.remaining} credits left, at or under the floor of {c.floor},
          so scheduled syncs have stopped fetching odds. In Railway, open the service's <b>Variables</b>, replace <code>ODDS_API_KEY</code> with
          another key and deploy. The next sync uses the new key.
        </div>
      )}
      {!d.auto_sync.enabled && (
        <div className="banner">Scheduled syncs are <b>off</b> on this server. Set <code>AUTO_SYNC=1</code> to turn them on (they're on by default on Railway).</div>
      )}

      <div className="admin-cards">
        <div className="card admin-card">
          <span className="mut">Next sync</span>
          {d.auto_sync.enabled && d.auto_sync.next_at ? (
            <><div className="big">{untilText(d.auto_sync.next_at, now)}</div>
              <span className="mut">{d.auto_sync.next_label} · {localWhen(d.auto_sync.next_at)}</span></>
          ) : <div className="big">Off</div>}
        </div>
        <div className="card admin-card">
          <span className="mut">Odds API credits</span>
          <div className={`big${c.low ? " under" : ""}`}>{c.remaining ?? "?"}</div>
          <span className="mut">
            {c.error ?? `Key …${c.key_hint} · stops at ${c.floor}`}{c.checked_at && !c.error ? ` · checked ${timeAgo(c.checked_at, now)}` : ""}
          </span>
        </div>
        <div className="card admin-card">
          <span className="mut">Now</span>
          {running ? (
            <>
              <div className="big"><small>{progressLine(job, elapsedSeconds(job.started_at, now))}</small></div>
              {job.progress != null && <div className="job"><div className="bar"><i style={{ width: `${Math.round(job.progress * 100)}%` }} /></div></div>}
              {job.detail && <span className="mut">{job.detail}</span>}
            </>
          ) : <><div className="big">Idle</div><span className="mut">{job.finished_at ? `Last sync finished ${timeAgo(job.finished_at, now)}` : "No sync since the server started"}</span></>}
        </div>
      </div>
      {runNow.error && <p className="err">{(runNow.error as Error).message}</p>}

      <h2>Schedule <small className="mut">Eastern time</small></h2>
      <div className="card scroll">
        <table className="admin-table">
          <thead><tr><th>When</th><th>Sync</th><th>What it does</th><th>Next</th><th>Last run</th><th /></tr></thead>
          <tbody>
            {d.slots.map((s) => (
              <tr key={s.id}>
                <td>{s.when}</td>
                <td><b>{s.label}</b></td>
                <td className="wrap-cell">{s.why}</td>
                <td title={localWhen(s.next_at)}>{untilText(s.next_at, now)}</td>
                <td>{s.last_run ? <><Status s={s.last_run.status} /> <span className="mut">{timeAgo(s.last_run.started_at, now)}</span></> : <span className="mut">never</span>}</td>
                <td><button className="link" disabled={running || runNow.isPending} onClick={() => confirmRun(s)}>Run now</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Run log</h2>
      <div className="card scroll">
        <table className="admin-table">
          <thead><tr><th>Started</th><th>Sync</th><th>Trigger</th><th>Week</th><th>Status</th><th>Games</th><th>Credits</th><th>Result</th></tr></thead>
          <tbody>
            {d.runs.map((r) => (
              <Fragment key={r.id}>
                <tr className="clickable" tabIndex={0} aria-expanded={open === r.id}
                  onClick={() => setOpen(open === r.id ? null : r.id)} onKeyDown={(e) => e.key === "Enter" && setOpen(open === r.id ? null : r.id)}>
                  <td title={new Date(r.started_at + "Z").toLocaleString()}>{localWhen(r.started_at)}</td>
                  <td>{r.label}</td>
                  <td className="mut">{r.trigger}</td>
                  <td>{r.week ? `${r.season} W${r.week}` : "—"}</td>
                  <td><Status s={r.status} /></td>
                  <td>{r.odds_mode === "none" ? "—" : r.games_fetched}</td>
                  <td>{credits(r)}</td>
                  <td className="wrap-cell">{r.error ?? r.summary}</td>
                </tr>
                {open === r.id && <tr><td colSpan={8}><RunLog id={r.id} /></td></tr>}
              </Fragment>
            ))}
            {!d.runs.length && <tr><td colSpan={8} className="mut">No syncs yet. The first one runs at the next scheduled time.</td></tr>}
          </tbody>
        </table>
      </div>
    </>)
  );
}
