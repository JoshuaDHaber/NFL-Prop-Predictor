import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type Kind, type LadderRow, type QuoteSide } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { IS_STATIC } from "../env";
import { americanOdds, playLabel, signedPct, timeAgo } from "../format";
import { legId, type Leg } from "../slip";

export interface PlayerCtx { playerId: string; name: string; team: string; opp: string; home: boolean; gameId: string }

interface Cell { side: "Over" | "Under"; row: LadderRow; q: QuoteSide }

const bestOf = (rows: LadderRow[], side: "over" | "under"): Cell | null => {
  let best: Cell | null = null;
  for (const row of rows) {
    const q = row[side];
    if (q && (!best || q.odds > best.q.odds)) best = { side: side === "over" ? "Over" : "Under", row, q };
  }
  return best;
};

export const ODDS_RANGE = 300; // prices shown by default: -300 to +300

interface LadderProps { ctx: PlayerCtx; kind: Kind; mu: number; book: string; onBookChange: (b: string) => void }

export default function LineLadder({ ctx, kind, mu, book, onBookChange }: LadderProps) {
  const isTd = kind === "td"; // anytime TD: one line (0.5), shown as Yes / No
  const qc = useQueryClient();
  const slip = useBetSlip();
  const meta = qc.getQueryData<{ has_odds_key: boolean; can_write: boolean }>(["meta"]);
  const [allBooks, setAllBooks] = useState(false);
  const [onlyEv, setOnlyEv] = useState(false);
  const [limitOdds, setLimitOdds] = useState(true);
  const oddsRange = limitOdds ? ODDS_RANGE : 0;
  const ladder = useQuery({ queryKey: ["ladder", ctx.playerId, kind, oddsRange], queryFn: () => api.lines(ctx.playerId, kind, oddsRange) });
  const fetchAlt = useMutation({
    mutationFn: () => api.fetchAlt(ctx.playerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ladder", ctx.playerId] }); qc.invalidateQueries({ queryKey: ["picks"] }); },
  });

  const onlyBook = book !== "all";
  const rows = useMemo(() => {
    const quotes = (ladder.data?.quotes ?? []).filter((q) => !onlyBook || q.book === book);
    if (allBooks || onlyBook) return quotes.map((r) => ({ key: `${r.line}-${r.book}-${r.alt}`, line: r.line, alt: r.alt, over: bestOf([r], "over"), under: bestOf([r], "under") }));
    const byLine = new Map<number, LadderRow[]>();
    quotes.forEach((r) => byLine.set(r.line, [...(byLine.get(r.line) ?? []), r]));
    return [...byLine.entries()].sort((a, b) => a[0] - b[0]).map(([line, rs]) => ({
      key: String(line), line, alt: rs.every((r) => r.alt), over: bestOf(rs, "over"), under: bestOf(rs, "under"),
    }));
  }, [ladder.data, allBooks, onlyBook, book]);
  const shown = onlyEv ? rows.filter((r) => (r.over?.q.ev ?? -1) > 0 || (r.under?.q.ev ?? -1) > 0) : rows;
  const hasAlt = (ladder.data?.quotes ?? []).some((q) => q.alt);

  const toLeg = (c: Cell): Leg => {
    const base = { playerId: ctx.playerId, kind, side: c.side, line: c.row.line, book: c.row.book };
    return { id: legId(base), ...base, name: ctx.name, team: ctx.team, opp: ctx.opp, home: ctx.home, odds: c.q.odds,
      link: c.q.link, eventLink: c.row.event_link, alt: c.row.alt, prob: c.q.prob, ev: c.q.ev, gameId: ctx.gameId };
  };

  const cost = 2; // main + alternate market for this stat
  const load = () => {
    if (window.confirm(`Fetch alternate lines and betslip links for this game?\n\nUses about ${cost} Odds API credits per stat this player is projected in.`)) fetchAlt.mutate();
  };

  const cell = (c: Cell | null) => {
    if (!c) return <td className="lcell none">–</td>;
    const id = legId({ playerId: ctx.playerId, kind, side: c.side, line: c.row.line, book: c.row.book });
    const inSlip = slip.has(id);
    return (
      <td className={`lcell ${c.q.ev > 0 ? "plus" : ""}`}>
        <button className={`add ${inSlip ? "on" : ""}`} onClick={() => slip.toggle(toLeg(c))}
          aria-label={`${inSlip ? "Remove" : "Add"} ${playLabel(kind, c.side, c.row.line)} at ${c.row.book}`}>{inSlip ? "✓" : "+"}</button>
        <span className="lc-main"><span className="odds">{americanOdds(c.q.odds)}</span>
          <span className={c.q.ev > 0 ? "pos" : "mut"}> {signedPct(c.q.ev)}</span><br />
          <span className="mut">{c.row.book}</span></span>
      </td>
    );
  };

  return (
    <section>
      <div className="ladder-head">
        <h3>Lines &amp; alternates</h3>
        <div className="ladder-tools">
          {!isTd && <label className="check" title={`Hide prices beyond -${ODDS_RANGE} / +${ODDS_RANGE}`}>
            <input type="checkbox" checked={limitOdds} onChange={(e) => setLimitOdds(e.target.checked)} /> −{ODDS_RANGE} to +{ODDS_RANGE}
          </label>}
          <label className="check"><input type="checkbox" checked={onlyEv} onChange={(e) => setOnlyEv(e.target.checked)} /> +EV only</label>
          {!onlyBook && <label className="check"><input type="checkbox" checked={allBooks} onChange={(e) => setAllBooks(e.target.checked)} /> All books</label>}
        </div>
      </div>
      {ladder.isLoading && <p className="mut">Loading lines…</p>}
      {ladder.error && <p className="err">Couldn't load lines.</p>}
      {ladder.data && (
        <>
          {onlyBook && (
            <div className="book-note">
              Showing <b>{book}</b> lines only (from your sportsbook filter).
              <button className="link" onClick={() => onBookChange("all")}>Show all books</button>
            </div>
          )}
          <div className="mut ladder-note">
            {isTd ? `Model chance of a TD ${(mu * 100).toFixed(0)}%. Win probability and EV lean at least 60% on the market's chance, since the model is a weak signal here.` : `Win probability and EV here use the model alone (no market blend). Projection ${mu.toFixed(0)} yds.`}
            {ladder.data.alt_fetched_at && ` Alternates fetched ${timeAgo(ladder.data.alt_fetched_at)}.`}
          </div>
          <div className="scroll ladder">
            <table>
              <thead><tr><th>{isTd ? "Market" : "Line"}</th><th>{isTd ? "Yes" : "Over"}</th><th>{isTd ? "No" : "Under"}</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.key} className={!isTd && Math.abs(r.line - mu) < 5 ? "near" : ""}>
                    <td><b>{isTd ? "Anytime TD" : r.line}</b>{r.alt && <span className="alt">alt</span>}</td>
                    {cell(r.over)}{cell(r.under)}
                  </tr>
                ))}
                {!shown.length && <tr><td colSpan={3} className="mut">No {onlyBook ? `${book} ` : ""}quotes{onlyEv ? " with positive EV" : ""} for this player.</td></tr>}
              </tbody>
            </table>
          </div>
          {!hasAlt && !IS_STATIC && !isTd && (
            <div className="alt-cta">
              <button className="primary" onClick={load} disabled={!meta?.has_odds_key || !meta?.can_write || fetchAlt.isPending}>
                {fetchAlt.isPending ? "Fetching…" : "Load alternate lines"}
              </button>
              <span className="mut">{!meta?.can_write ? "Admin only" : meta?.has_odds_key ? `Uses ~${cost} API credits · adds betslip links` : "Needs ODDS_API_KEY"}</span>
            </div>
          )}
          {fetchAlt.error && <p className="err">{(fetchAlt.error as Error).message}</p>}
          {fetchAlt.data && <p className="mut">Loaded {fetchAlt.data.alt_quotes} alternate quotes. Credits left: {fetchAlt.data.credits_remaining ?? "?"}.</p>}
        </>
      )}
    </section>
  );
}
