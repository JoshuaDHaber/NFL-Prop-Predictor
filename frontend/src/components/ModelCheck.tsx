import type { Meta } from "../api";
import { KIND_LABEL, signed, timeAgo, weatherText, wxEffect } from "../format";
import type { Kind } from "../api";

function RedistributionCard({ r }: { r: NonNullable<Meta["redistribution"]> }) {
  const rush = r.by_kind.rush;
  const qb = r.by_kind.pass;
  const off = Object.keys(r.rho).filter((k) => !r.active_roles.includes(k) && !(r.replace_roles ?? []).includes(k));
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
      {qb && (r.replace_roles ?? []).includes("pass") && (
        <p>
          When a starting quarterback is out, his replacement takes over his attempts. Replacement quarterbacks were projected{" "}
          <b>{qb.bias_before.toFixed(0)} yds too low</b> before this ({qb.n} backtested games) and {qb.bias_after >= 0 ? "+" : ""}{qb.bias_after.toFixed(0)} after.
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

const pctPer = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1)}%`;

function WeatherCard({ fit, games }: { fit: NonNullable<Meta["weather"]>; games: Meta["games"] }) {
  const c = fit.coef;
  const air = c.pass ?? c.rec;
  const label: Record<string, string> = { pass: "Passing", rec: "Receiving", rush: "Rushing" };
  const outdoor = games.filter((g) => g.weather && !g.weather.indoor);
  const providers = [...new Set(outdoor.map((g) => g.weather!.provider).filter(Boolean))];
  return (
    <div className="card prose">
      <h3>Weather</h3>
      <p>
        At outdoor stadiums, yardage projections are scaled for kickoff wind and cold, using effects fitted on the backtest's own misses.
        {air && <> Passing and receiving: <b>{pctPer(air.wind)} per mph</b> of wind over {fit.wind_from} mph and {pctPer(air.cold)} per degree under {fit.cold_from}°F.</>}
        {c.rush && <> Rushing: {pctPer(c.rush.wind)} per mph of wind.</>}
        {" "}Each effect is shrunk toward zero by how noisy it is. Domes, closed and retractable roofs get no adjustment; rain and snow are shown but not applied (there's no history of them to fit).
      </p>
      {Object.keys(fit.by_kind).length > 0 && (
        <table className="calib" aria-label="Weather adjustment in the backtest">
          <thead><tr><th>Market</th><th>Games moved</th><th>Bias before → after</th><th>MAE before → after</th></tr></thead>
          <tbody>
            {Object.entries(fit.by_kind).map(([k, b]) => (
              <tr key={k}><td>{label[k] ?? k}</td><td>{b.n}</td><td>{signed(b.bias_before)} → {signed(b.bias_after)}</td><td>{b.mae_before.toFixed(1)} → {b.mae_after.toFixed(1)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {outdoor.length > 0 && (
        <>
          <h3>This week's outdoor games</h3>
          <table className="wx-games">
            <thead><tr><th>Game</th><th>Forecast at kickoff</th><th className="num">Pass/rec</th><th className="num">Rush</th></tr></thead>
            <tbody>
              {outdoor.map((g) => (
                <tr key={g.game_id}>
                  <td>{g.label}</td>
                  <td>{weatherText(g.weather) ?? <span className="mut">no forecast yet</span>}</td>
                  <td className="num">{wxEffect(g.weather!.factors.pass) ?? "–"}</td>
                  <td className="num">{wxEffect(g.weather!.factors.rush) ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mut">Forecasts are from {providers.length ? providers.join(" and ") : "Open-Meteo"}, fetched when the model last ran; sync again closer to kickoff for a fresher one.</p>
        </>
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
      {meta.calibration && (
        <p className="mut">
          Calibration (error tables, TD scale, redistribution share, weather effect) was last fitted for week {meta.calibration.week}, {new Date(meta.calibration.at + "Z").toLocaleDateString()}
          {meta.calibration.reused_from_run ? "; later syncs reuse it until it is recalibrated." : "."}
        </p>
      )}
      {meta.redistribution && <RedistributionCard r={meta.redistribution} />}
      {meta.weather && <WeatherCard fit={meta.weather} games={meta.games} />}
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
