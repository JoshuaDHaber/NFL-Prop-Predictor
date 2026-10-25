import type { BlowoutChance, MoneylineGame } from "../api";
import { pct } from "../format";
import { matchupColors, shadeVars } from "../teams";

/** The chance a game is decided by `margin`+ points, either way (null when the run has no blowout model). */
export function blowoutAt(g: MoneylineGame | undefined, margin = 20): BlowoutChance | undefined {
  return g?.blowout?.chances.find((c) => c.margin === margin);
}

// each half of a row's track spans 0-50%: the largest chances on a slate sit around 40% at 15+
const HALF = 0.5;
const width = (p: number) => `${Math.min(p / HALF, 1) * 100}%`;

/** One NBA game's blowout chances at 15/20/25/30+: the away team's share to the left, the home team's to the right. */
export function BlowoutCard({ g }: { g: MoneylineGame }) {
  if (!g.blowout) return null;
  const [away, home] = g.sides;
  const [awayColor, homeColor] = matchupColors(away.team, home.team);
  const c20 = blowoutAt(g);
  return (
    <article className="card bo-card">
      <header className="ml-head"><b>Blowout chances</b><span className="mut">from the market spread</span></header>
      <div className="bo-rows" role="table" aria-label="Chance the game is decided by this many points or more">
        <div className="bo-row bo-th" role="row">
          <span role="columnheader">Margin</span><span role="columnheader">{away.team}</span><span aria-hidden />
          <span role="columnheader">{home.team}</span><span role="columnheader">Either</span>
        </div>
        {g.blowout.chances.map((c) => (
          <div className="bo-row" role="row" key={c.margin}>
            <span role="rowheader">{c.margin}+ pts</span>
            <span role="cell" className="mut">{pct(c.p_away, 0)}</span>
            <span className="bo-track ml-bar" aria-hidden>
              <span className="bo-half bo-left"><i className="tbar" style={{ width: width(c.p_away), ...shadeVars(awayColor) }} /></span>
              <span className="bo-half"><i className="tbar" style={{ width: width(c.p_home), ...shadeVars(homeColor) }} /></span>
            </span>
            <span role="cell" className="mut">{pct(c.p_home, 0)}</span>
            <span role="cell"><b>{pct(c.p, 0)}</b></span>
          </div>
        ))}
      </div>
      <p className="mut ml-foot">
        {c20 && <>A 20-point game is {c20.p >= 0.3 ? "a real risk" : c20.p >= 0.2 ? "about as likely as usual" : "less likely than usual"} here
          (NBA average about 22%); starters in a blowout often sit the fourth quarter, which cuts their minutes. </>}
        Fitted on {g.blowout.games.toLocaleString()} games since 2018-19.
      </p>
    </article>
  );
}
