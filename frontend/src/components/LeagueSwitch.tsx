import { useLeague } from "../LeagueContext";
import type { League } from "../league";
import { LeagueIcon } from "./icons";
import Menu, { MenuItem } from "./Menu";

const OPTIONS: [League, string][] = [["nfl", "NFL"], ["nba", "NBA"]];

/** The switch between the NFL and NBA sides of the app: a small menu in the top bar. */
export default function LeagueSwitch() {
  const { league, setLeague } = useLeague();
  const [, label] = OPTIONS.find(([l]) => l === league)!;
  return (
    <Menu label={<><LeagueIcon league={league} />{label}</>} ariaLabel={`League: ${label}`}>
      {(close) => OPTIONS.map(([l, name]) => (
        <MenuItem key={l} on={league === l} onClick={() => { close(); if (league !== l) setLeague(l); }}>
          <span className="with-icon"><LeagueIcon league={l} />{name}</span>
        </MenuItem>
      ))}
    </Menu>
  );
}
