import type { Meta } from "../api";
import { KIND_LABEL, signed, timeAgo } from "../format";
import type { Kind } from "../api";

export default function ModelCheck({ meta }: { meta: Meta }) {
  const kinds = Object.keys(meta.backtest) as Kind[];
  return (
    <div className="stack">
      <div className="grid">
        {kinds.map((k) => {
          const b = meta.backtest[k];
          const better = ((b.mae_naive - b.mae_model) / b.mae_naive) * 100;
          return (
            <div className="card stat" key={k}>
              <div className="mut">{KIND_LABEL[k]} · {b.n.toLocaleString()} backtested games</div>
              <div className="big">{b.mae_model.toFixed(1)} <small>yds MAE</small></div>
              <div className="mut">
                vs {b.mae_naive.toFixed(1)} for a last-5 average ({better.toFixed(1)}% better) · bias {signed(b.bias)}
              </div>
            </div>
          );
        })}
      </div>
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
