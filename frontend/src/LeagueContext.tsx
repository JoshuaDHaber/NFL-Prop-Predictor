import { createContext, useContext } from "react";
import type { League } from "./league";

/** The league on screen and the switch to the other one (provided in main.tsx). */
export const LeagueContext = createContext<{ league: League; setLeague: (l: League) => void }>({ league: "nfl", setLeague: () => {} });
export const useLeague = () => useContext(LeagueContext);
