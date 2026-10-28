import { useEffect, useRef, useState } from "react";
import type { Kind } from "./api";
import { KIND_LABEL } from "./format";

// The open player drawer lives in the hash next to any #game: #game=<id>&player=<id>&kind=rec, plus the play that was clicked
// (&side=Under&line=4.5&book=FanDuel) so the drawer can lead with it. Opening adds a history entry, so the back button (and a
// phone's back swipe) closes the drawer instead of leaving the page, and a drawer can be linked.

/** The play a drawer was opened from: the row the reader clicked. */
export interface DrawerPick { side: "Over" | "Under"; line: number; book: string }
export interface Selected { id: string; kind: Kind; pick?: DrawerPick }

const KEYS = ["player", "kind", "side", "line", "book"];

export function selectedFromHash(hash = window.location.hash): Selected | null {
  const h = new URLSearchParams(hash.slice(1));
  const id = h.get("player"), kind = h.get("kind");
  if (!id || !kind || !(kind in KIND_LABEL)) return null;
  const side = h.get("side"), line = h.get("line"), book = h.get("book");
  const pick = (side === "Over" || side === "Under") && line && Number.isFinite(Number(line)) && book ? { side, line: Number(line), book } as DrawerPick : undefined;
  return { id, kind: kind as Kind, pick };
}

/** The hash with the drawer's keys swapped for `s` (or dropped), keeping #game and anything else. */
export function hashFor(s: Selected | null, hash = window.location.hash) {
  const h = new URLSearchParams(hash.slice(1));
  KEYS.forEach((k) => h.delete(k));
  if (s) {
    h.set("player", s.id);
    h.set("kind", s.kind);
    if (s.pick) { h.set("side", s.pick.side); h.set("line", String(s.pick.line)); h.set("book", s.pick.book); }
  }
  const str = h.toString();
  return str ? `#${str}` : "";
}

const urlWith = (s: Selected | null) => window.location.pathname + window.location.search + hashFor(s);

/** The player drawer's state, kept in the URL: open() adds a history entry, close() steps back off it. */
export function useSelectedPlayer() {
  const [selected, setSelected] = useState<Selected | null>(() => selectedFromHash());
  // true while the drawer's entry sits on top of the page's in history, so closing goes back instead of stacking another entry
  const pushed = useRef(false);
  useEffect(() => {
    const sync = () => { const s = selectedFromHash(); if (!s) pushed.current = false; setSelected(s); };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  const open = (s: Selected) => {
    if (selected) window.history.replaceState(null, "", urlWith(s));
    else { window.history.pushState(null, "", urlWith(s)); pushed.current = true; }
    setSelected(s);
  };
  const close = () => {
    if (pushed.current) { pushed.current = false; window.history.back(); return; }   // popstate clears the state
    window.history.replaceState(null, "", urlWith(null));
    setSelected(null);
  };
  /** A market picked inside the drawer: kept in the link, without moving the drawer's own state (or its tab order). */
  const remember = (kind: Kind) => {
    if (selected && kind !== selectedFromHash()?.kind) window.history.replaceState(null, "", urlWith({ id: selected.id, kind }));
  };
  return { selected, open, close, remember };
}
