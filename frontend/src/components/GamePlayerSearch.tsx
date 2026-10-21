import { useEffect, useMemo, useRef, useState } from "react";
import type { Kind, Projection } from "../api";
import { isYesNo, KIND_SHORT } from "../format";
import Avatar from "./Avatar";

/** The market a player's drawer opens on: their headline one by NFL position, else the first they're projected in (Points for the NBA). */
const PRIMARY: Record<string, Kind> = { QB: "pass", RB: "rush", WR: "rec", TE: "rec" };
const MARKET_ORDER: Kind[] = ["pass", "rush", "rec", "rr", "recs", "lng", "rlng", "ptd", "td", "ftd", "pts", "reb", "ast", "threes", "pra", "pr", "pa", "stl", "blk"];

interface GamePlayer { player_id: string; name: string; pos: string; team: string; status: string; kinds: Kind[] }

/** Find a player in this game and open their drawer; filters the game's projections, so it's instant and only lists these two rosters. */
export default function GamePlayerSearch({ rows, onSelect }: { rows: Projection[]; onSelect: (id: string, kind: Kind) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  const players = useMemo(() => {
    const m = new Map<string, GamePlayer>();
    for (const r of rows) {
      const p = m.get(r.player_id) ?? m.set(r.player_id, { player_id: r.player_id, name: r.name, pos: r.pos, team: r.team, status: r.status, kinds: [] }).get(r.player_id)!;
      if (!p.kinds.includes(r.kind)) p.kinds.push(r.kind);
    }
    for (const p of m.values()) p.kinds.sort((a, b) => MARKET_ORDER.indexOf(a) - MARKET_ORDER.indexOf(b));
    return [...m.values()];
  }, [rows]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const needle = q.trim().toLowerCase();
  // a first or last name starting with the search ranks ahead of a match mid-name
  const rank = (p: GamePlayer) => (p.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(needle)) ? 0 : 1);
  const options = !needle ? [] : players
    .filter((p) => p.name.toLowerCase().includes(needle))
    .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
    .slice(0, 12);
  const pick = (p: GamePlayer, kind?: Kind) => {
    const k = kind ?? (p.kinds.includes(PRIMARY[p.pos]) ? PRIMARY[p.pos] : p.kinds[0]);
    onSelect(p.player_id, k); setQ(""); setOpen(false); setActive(0);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && options[active]) { e.preventDefault(); pick(options[active]); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div className="cmp-search go-search" ref={box}>
      <input type="search" placeholder={players.length ? `Search ${players.length} players in this game` : "Search players in this game"}
        value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)} onKeyDown={onKey}
        aria-label="Search players in this game" role="combobox" aria-expanded={open && options.length > 0} aria-controls="go-hits" autoComplete="off" />
      {open && needle && (
        <ul id="go-hits" className="cmp-hits card" role="listbox">
          {!options.length ? <li className="mut cmp-none">No player in this game matches “{q.trim()}”.</li>
            : options.map((p, i) => (
              <li key={p.player_id} role="option" aria-selected={i === active} className={i === active ? "on" : ""}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(p); }}>
                <Avatar name={p.name} size={30} />
                <span><b>{p.name}</b> <span className="pos-pill">{p.pos}</span> <span className="mut">{p.team}</span>{p.status && <small className="q"> {p.status}</small>}</span>
                <span className="go-hit-kinds">
                  {p.kinds.filter((k) => !isYesNo(k)).slice(0, 3).map((k) => (
                    <button key={k} tabIndex={-1} onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); pick(p, k); }} title={`Open ${p.name}'s ${KIND_SHORT[k].toLowerCase()}`}>{KIND_SHORT[k]}</button>
                  ))}
                </span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
