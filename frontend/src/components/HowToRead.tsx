import { IconX } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import Info from "./Info";

const BEST_PROPS = (
  <ol>
    <li>Each row is one bet: a player, a market and a side, at the book with the best price.</li>
    <li><b>Win prob</b> <Info term="winProb" /> is the model's chance it hits; <b>EV</b> <Info term="ev" /> is what $1 returns on average if that chance is right. Rows are sorted by EV.</li>
    <li><b>¼ Kelly</b> <Info term="kelly" /> suggests a stake as a share of your bankroll. Most of these bets still lose; the edge shows up over many.</li>
  </ol>
);

/** A one-time primer on a board (Best props by default), until the reader closes it. Each board remembers its own dismissal. */
export default function HowToRead({ storageKey = "how-to-read-dismissed", children = BEST_PROPS }: { storageKey?: string; children?: ReactNode }) {
  const dismissed = () => { try { return localStorage.getItem(storageKey) === "1"; } catch { return false; } };
  const [hidden, setHidden] = useState(dismissed);
  if (hidden) return null;
  const close = () => { setHidden(true); try { localStorage.setItem(storageKey, "1"); } catch { /* private mode: shows again next visit */ } };
  return (
    <aside className="card how-to">
      <button className="how-to-x" onClick={close} aria-label="Dismiss"><IconX size={16} stroke={1.75} aria-hidden /></button>
      <b>How to read this board</b>
      {children}
    </aside>
  );
}
