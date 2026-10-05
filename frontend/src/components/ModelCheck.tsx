import type { Meta } from "../api";
import { KIND_LABEL, signed, timeAgo } from "../format";
import type { Kind } from "../api";

function RedistributionCard({ r }: { r: NonNullable<Meta["redistribution"]> }) {
  const rush = r.by_kind.rush;
  const off = Object.keys(r.rho).filter((k) => !r.active_roles.includes(k));
  const label: Record<string, string> = { rush: "carries", rec: "targets", pass: "pass attempts" };
  return (
    <div className="card prose">
      <h3>Injury redistribution</h3>
      <p>
        When a regular is out, his volume goes to teammates in the same position group. The share handed over is fitted on the
        backtest{r.rho.rush ? ` (carries: ${(r.rho.rush * 100).toFixed(0)}% of the missing volume)` : ""}.
      </p>
      {rush && (
        <p>
          Rushing teammates of an absent regular were projected <b>{rush.bias_before.toFixed(1)} yds too low on average</b> before
          this ({rush.n} backtested games); with it the bias is {rush.bias_after >= 0 ? "+" : ""}{rush.bias_after.toFixed(1)} yds and the
          average miss moves from {rush.mae_before.toFixed(1)} to {rush.mae_after.toFixed(1)} yds.
        </p>
      )}
      {off.length > 0 && (
        <p className="mut">
          Switched off for {off.map((k) => label[k] ?? k).join(" and ")}: on held-out weeks it overshot and made projections less accurate.
        </p>
      )}
    </div>
  );
}

export default function ModelCheck({ meta }: { meta: Meta }) {
  const kinds = Object.keys(meta.backtest) as Kind[];
  return (
    <div className="stack">
      <div className="grid">
        {kinds.map((k) => {
          const b = meta.backtest[k];
          const better = ((b.mae_naive - b.mae_model) / b.mae_naive) * 100;
          const brier = b.metric === "brier";
          return (
            <div className="card stat" key={k}>
              <div className="mut">{KIND_LABEL[k]} · {b.n.toLocaleString()} backtested {brier ? "player-games" : "games"}</div>
              <div className="big">{b.mae_model.toFixed(brier ? 3 : 1)} <small>{brier ? "Brier score" : "yds MAE"}</small></div>
              <div className="mut">
                {brier
                  ? `vs ${b.mae_naive.toFixed(3)} for always predicting the average TD rate (${better.toFixed(1)}% better; lower is better)`
                  : `vs ${b.mae_naive.toFixed(1)} for a last-5 average (${better.toFixed(1)}% better)`} · bias {signed(b.bias, brier ? 3 : 1)}
              </div>
              {brier && b.calibration && b.calibration.length > 0 && (
                <table className="calib" aria-label="Anytime TD calibration">
                  <thead><tr><th>Predicted</th><th>Actual</th><th>Games</th></tr></thead>
                  <tbody>
                    {b.calibration.map((c, i) => (
                      <tr key={i}><td>{(c.predicted * 100).toFixed(0)}%</td><td>{(c.actual * 100).toFixed(0)}%</td><td>{c.n}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
      {meta.redistribution && <RedistributionCard r={meta.redistribution} />}
      <div className="card prose">
        <h3>How to read this</h3>
        <p>
          Every historical game from last season onward was projected using only data available before kickoff
          (a walk-forward backtest). MAE is the average miss in yards; bias is average (actual − projection), so
          near zero means the projections are not systematically high or low. The same residuals are used to fit
          the spread of outcomes behind every win probability.
        </p>
        <p>
          The backtest tests accuracy, not profitability — there is no historical odds data in it. Treat large
          edges against sharp markets with suspicion; they usually mean the model is missing context.
        </p>
      </div>
      <div className="card prose">
        <h3>Data freshness</h3>
        <ul>
          {meta.run && <li>Projections computed {timeAgo(meta.run.created_at)} for {meta.run.season} week {meta.run.week}.</li>}
          {Object.entries(meta.odds).map(([k, o]) => (
            <li key={k}>{KIND_LABEL[k as Kind]} lines: {o.lines.toLocaleString()} quotes, fetched {timeAgo(o.fetched_at)}.</li>
          ))}
        </ul>
        {meta.run && meta.run.excluded.length > 0 && (
          <>
            <h3>Excluded this run</h3>
            <p className="mut">{meta.run.excluded.join(", ")}</p>
          </>
        )}
      </div>
    </div>
  );
}
