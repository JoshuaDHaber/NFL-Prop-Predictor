import { useState } from "react";
import { teamLogo } from "../teams";

/** A team's logo, or nothing if it is unknown or fails to load (the abbreviation beside it still names the team). */
export default function TeamLogo({ team, size = 36 }: { team: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const src = teamLogo(team);
  if (!src || failed) return null;
  return <img className="team-logo" src={src} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />;
}
