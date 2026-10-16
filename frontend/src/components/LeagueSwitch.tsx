import { IS_STATIC } from "../env";
import { useLeague } from "../LeagueContext";
import type { League } from "../league";

const OPTIONS: [League, string, string][] = [["nfl", "🏈", "NFL"], ["nba", "🏀", "NBA"]];

/** The main toggle between the NFL and NBA sides of the app (the static demo is NFL only). */
export default function LeagueSwitch() {
  const { league, setLeague } = useLeague();
  if (IS_STATIC) return null;
  return (
    <div className="seg league-switch" role="group" aria-label="League">
      {OPTIONS.map(([l, icon, label]) => (
        <button key={l} className={league === l ? "on" : ""} aria-pressed={league === l} onClick={() => league !== l && setLeague(l)}>
          <span className="ico" aria-hidden>{icon}</span>{label}
        </button>
      ))}
    </div>
  );
}
