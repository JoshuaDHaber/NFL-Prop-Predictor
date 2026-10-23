import type { Kind } from "../api";
import { isYesNo, playLabel } from "../format";
import { SideArrow } from "./icons";

/** A pick's side and line ("↗ Over 4.5", "Anytime TD"). Neutral on purpose: red and green on this site mean EV, and an
 *  Under is no worse a bet than an Over. */
export default function SidePill({ kind, side, line }: { kind: Kind; side: "Over" | "Under"; line: number }) {
  return <span className="side-pill">{!isYesNo(kind) && <SideArrow side={side} />}{playLabel(kind, side, line)}</span>;
}
