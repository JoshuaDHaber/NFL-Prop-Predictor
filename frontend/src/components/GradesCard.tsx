import { useQuery } from "@tanstack/react-query";
import { api, type ClvLine, type GradeLine, type MarketFit, type WeightCell } from "../api";
import { marketLabel, pct, signedPct, signedPts } from "../format";
import Info from "./Info";

const units = (u: number) => `${u >= 0 ? "+" : "−"}${Math.abs(u).toFixed(2)}`;

function Rows({ lines, label }: { lines: GradeLine[]; label: (l: GradeLine) => string }) {
  return (
    <>
      {lines.filter((l) => l.n > 0).map((l) => (
        <tr key={l.label}>
          <td>{label(l)}</td>
          <td>{l.wins}-{l.losses}{l.pushes ? `-${l.pushes}` : ""}{l.voids ? <span className="mut"> ({l.voids} void)</span> : null}</td>
          <td>{l.expected_wins.toFixed(1)}</td>
          <td>{units(l.units)}</td>
          <td>{l.roi == null ? "–" : signedPct(l.roi)}</td>
        </tr>
      ))}
    </>
  );
}

function ClvRows({ lines, label }: { lines: ClvLine[]; label: (l: ClvLine) => string }) {
  return (
    <>
      {lines.filter((l) => l.n > 0).map((l) => (
        <tr key={l.label}>
          <td>{label(l)}</td><td>{l.n}</td>
          <td className={(l.beat ?? 0) > 0.5 ? "good" : ""}>{l.beat == null ? "–" : pct(l.beat, 0)}</td>
          <td className={(l.ev_close ?? 0) > 0 ? "good" : ""}>{l.ev_close == null ? "–" : signedPct(l.ev_close)}</td>
          <td>{l.move == null ? "–" : signedPts(l.move)}</td>
        </tr>
      ))}
    </>
  );
}

/** The fitted weights the board prices with: how much each market leans on the books (by time to kickoff), and which books
 *  count most in the market's consensus. */
function MarketFitCard({ fit }: { fit: MarketFit }) {
  const ll = (v: number | null) => (v == null ? "–" : v.toFixed(3));
  return (
    <>
      <h3>How much to trust the market <Info term="fitted" /></h3>
      {fit.n === 0 ? (
        <p className="mut">
          No graded picks to fit yet, so every market uses the default blend (35% market, more where the model is weak). Once games are graded,
          each market's weight is the blend of model and market that would have scored best on them, by how long before kickoff the price was posted.
        </p>
      ) : (
        <>
          <p>
            Fitted on {fit.n.toLocaleString()} graded picks: the blend of model and market whose chances scored best (log loss, lower is better),
            pulled toward the overall weight where a market has few picks. Prices posted on game day lean on the market more when it's sharper then.
          </p>
          <div className="scroll"><table className="calib" aria-label="Market weights">
            <thead><tr><th>Market</th><th>Picks</th><th>Market weight</th><th>Game day</th><th>6–48 h</th><th>48 h+</th><th>Log loss: model · market · blend</th></tr></thead>
            <tbody>
              {fit.kinds.map((k) => {
                const b = Object.fromEntries((fit.buckets[k.label] ?? []).map((c) => [c.label, c]));
                const used = (c: WeightCell) => Math.max(c.w, c.floor ?? 0);
                const cell = (label: string) => <td className="mut">{b[label] ? `${pct(used(b[label]), 0)}${b[label].n ? ` (${b[label].n})` : ""}` : "–"}</td>;
                return (
                  <tr key={k.label}>
                    <td>{marketLabel(k.label)}</td><td>{k.n}</td>
                    <td><b>{pct(used(k), 0)}</b>{k.floor != null && k.w < k.floor && <span className="mut" title={`The fit says ${pct(k.w, 0)}, but this market never leans on the books less than ${pct(k.floor, 0)}`}> floor</span>}</td>
                    {cell("game day")}{cell("6–48 h")}{cell("48 h+")}
                    <td>{ll(k.ll_model)} · <span className={(k.ll_market ?? 9) < (k.ll_model ?? 9) ? "good" : ""}>{ll(k.ll_market)}</span> · {ll(k.ll_blend)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
        </>
      )}
      <h3>Book weights</h3>
      <p>
        The market's chance averages every book's no-vig price (margin stripped with the power method, which takes more from longshots), weighted
        by how close each book's prices 6+ hours out came to where the others closed. Books owned by one company share one weight.
      </p>
      <p className="book-weights">
        {fit.books.map((b) => <span key={b.book} className="chip" title={b.n ? `Fitted on ${b.n} early quotes` : "Prior (no history scored yet)"}>{b.book} <b>{b.w.toFixed(2)}</b>{!b.n && <span className="mut">*</span>}</span>)}
      </p>
      {fit.books.some((b) => !b.n) && <p className="mut">* not enough history yet: the starting weight.</p>}
    </>
  );
}

/** "Oct 20" from an Eastern date. */
const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** How the board did once graded (app/grading.py, app/nba/grading.py): logged before each game, scored from the box scores
 * (nflverse's for the NFL, ESPN's for the NBA). */
export default function GradesCard({ nba = false }: { nba?: boolean }) {
  const q = useQuery({ queryKey: [nba ? "nba-grades" : "grades"], queryFn: nba ? api.nbaGrades : api.grades, retry: false });
  if (q.isError || !q.data) return null;   // the static demo has no log
  const g = q.data;
  const span = nba
    ? `${g.season ? `${g.season - 1}-${String(g.season).slice(2)}` : ""}${g.dates?.length ? `, ${day(g.dates[0])}${g.dates[1] !== g.dates[0] ? ` – ${day(g.dates[1])}` : ""}` : ""}`
    : `${g.season} week${g.weeks.length > 1 ? "s" : ""} ${g.weeks.join(", ")}`;
  const head = <thead><tr><th>Picks</th><th>W-L</th><th>Expected W</th><th>Units</th><th>ROI</th></tr></thead>;
  return (
    <div className="card prose">
      <h3>Graded picks</h3>
      {g.graded === 0 ? (
        <p className="mut">
          {nba ? "Every sync logs the board for games still to tip off, and each model run grades the finished ones from ESPN's box scores (the morning after)."
            : "Every sync logs the board for games still to kick off, and each model run grades the finished ones once nflverse's box scores are in (usually the Tuesday after)."}
          {" "}Nothing graded yet{g.pending ? `: ${g.pending.toLocaleString()} picks are waiting on their games` : ""}.
        </p>
      ) : (
        <>
          <p>
            The board as it stood before each {nba ? "tip-off" : "kickoff"} ({span}), one unit a pick at the logged price.
            Expected W adds up the model's win chances: a board that keeps landing under it is overconfident.
            {g.pending > 0 && <span className="mut"> {g.pending.toLocaleString()} more are waiting on their games.</span>}
          </p>
          <table className="calib" aria-label="Graded board">
            {head}
            <tbody>
              <Rows lines={g.board} label={(l) => l.label} />
              <Rows lines={g.by_market} label={(l) => marketLabel(l.label)} />
              <Rows lines={g.by_ev} label={(l) => l.label} />
              {g.by_week.length > 1 && <Rows lines={g.by_week} label={(l) => l.label} />}
            </tbody>
          </table>
          {(g.clv ?? []).some((c) => c.n > 0) && (
            <>
              <h3>Against the closing line <Info term="clv" /></h3>
              <p>
                The books' fair chance of each pick at the last odds fetch before {nba ? "tip-off" : "kickoff"}, at the pick's line. Beat close: the price
                was better than the close says it was worth. Market move: how far the books' own chance moved toward the pick after it was priced.
                Picks as first shown are the honest test; the last price before {nba ? "tip-off" : "kickoff"} is often the close itself.
              </p>
              <div className="scroll"><table className="calib" aria-label="Closing line value">
                <thead><tr><th>Picks</th><th>With a close</th><th>Beat close</th><th>EV at close</th><th>Market move</th></tr></thead>
                <tbody>
                  <ClvRows lines={g.clv ?? []} label={(l) => l.label} />
                  <ClvRows lines={g.clv_by_market ?? []} label={(l) => marketLabel(l.label)} />
                </tbody>
              </table></div>
            </>
          )}
          {g.model_vs_line.length > 0 && (
            <>
              <h3>Model vs the line</h3>
              <p>
                Average miss of the projection and of the posted line against the result, every logged player and market. Where the line is closer,
                the model should lean on the market more (the fitted weights below).
              </p>
              <table className="calib" aria-label="Model vs line">
                <thead><tr><th>Market</th><th>Players</th><th>Model MAE</th><th>Line MAE</th><th>Model closer</th></tr></thead>
                <tbody>
                  {g.model_vs_line.map((c) => (
                    <tr key={c.kind}>
                      <td>{marketLabel(c.kind)}</td><td>{c.n}</td>
                      <td className={c.mae_model <= c.mae_line ? "good" : ""}>{c.mae_model.toFixed(c.mae_model < 5 ? 2 : 1)}</td>
                      <td className={c.mae_line < c.mae_model ? "good" : ""}>{c.mae_line.toFixed(c.mae_line < 5 ? 2 : 1)}</td>
                      <td>{(c.model_closer * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
      {g.market_fit && <MarketFitCard fit={g.market_fit} />}
    </div>
  );
}
