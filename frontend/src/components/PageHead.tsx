import type { ReactNode } from "react";

/** A tab's title (which can carry an inline picker, like "Parlays at FanDuel"), with optional controls on the right. */
export default function PageHead({ title, aside }: { title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="page-head">
      <h2 className="page-h">{title}</h2>
      {aside && <div className="page-head-aside">{aside}</div>}
    </div>
  );
}
