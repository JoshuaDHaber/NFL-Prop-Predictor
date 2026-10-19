import { useQuery } from "@tanstack/react-query";
import { api, type GradeLine } from "../api";
import { marketLabel, signedPct } from "../format";

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

/** How the board did once graded (app/grading.py): logged before each kickoff, scored from nflverse's box scores. */
export default function GradesCard() {
  const q = useQuery({ queryKey: ["grades"], queryFn: api.grades, retry: false });
  if (q.isError || !q.data) return null;   // the static demo has no log
  const g = q.data;
  const head = <thead><tr><th>Picks</th><th>W-L</th><th>Expected W</th><th>Units</th><th>ROI</th></tr></thead>;
  return (
    <div className="card prose">
      <h3>Graded picks</h3>
      {g.graded === 0 ? (
        <p className="mut">
          Every sync logs the board for games still to kick off, and each model run grades the finished ones once nflverse's box scores
          are in (usually the Tuesday after). Nothing graded yet{g.pending ? `: ${g.pending.toLocaleString()} picks are waiting on their games` : ""}.
        </p>
      ) : (
        <>
          <p>
            The board as it stood before each kickoff ({g.season} week{g.weeks.length > 1 ? "s" : ""} {g.weeks.join(", ")}), one unit a pick at the logged price.
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
          {g.model_vs_line.length > 0 && (
            <>
              <h3>Model vs the line</h3>
              <p>
                Average miss of the projection and of the posted line against the result, every logged player and market. Where the line is closer,
                the model should lean on the market more (the "trust the market" slider).
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
    </div>
  );
}
