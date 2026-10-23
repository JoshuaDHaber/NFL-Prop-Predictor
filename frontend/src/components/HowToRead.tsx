import { IconX } from "@tabler/icons-react";
import { useState } from "react";
import Info from "./Info";

const KEY = "how-to-read-dismissed";
const dismissed = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };

/** A one-time primer on the Best props board, until the reader closes it. */
export default function HowToRead() {
  const [hidden, setHidden] = useState(dismissed);
  if (hidden) return null;
  const close = () => { setHidden(true); try { localStorage.setItem(KEY, "1"); } catch { /* private mode: shows again next visit */ } };
  return (
    <aside className="card how-to">
      <button className="how-to-x" onClick={close} aria-label="Dismiss"><IconX size={16} stroke={1.75} aria-hidden /></button>
      <b>How to read this board</b>
      <ol>
        <li>Each row is one bet: a player, a market and a side, at the book with the best price.</li>
        <li><b>Win prob</b> <Info term="winProb" /> is the model's chance it hits; <b>EV</b> <Info term="ev" /> is what $1 returns on average if that chance is right. Rows are sorted by EV.</li>
        <li><b>¼ Kelly</b> <Info term="kelly" /> suggests a stake as a share of your bankroll. Most of these bets still lose; the edge shows up over many.</li>
      </ol>
    </aside>
  );
}
