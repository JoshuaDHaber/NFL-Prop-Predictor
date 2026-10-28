import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { detectState } from "./geoState";
import { cleanStakes, clashesWith, conflicts, removedFrom, restoreLegs, slipFromHash, type Leg, type Removed } from "./slip";

interface SlipCtx {
  legs: Leg[];
  has: (id: string) => boolean;
  /** How many same-player, same-market clashes the slip holds (books won't parlay them). */
  clashCount: number;
  /** Whether adding this leg would put a clash on the slip. */
  wouldClash: (leg: Leg) => boolean;
  toggle: (leg: Leg) => void;
  /** Takes legs off the slip; the slip offers to undo it for a few seconds. */
  remove: (ids: string | string[]) => void;
  replace: (oldId: string, leg: Leg) => void;
  clear: () => void;
  /** The last removal (or clear), while it can still be undone. */
  lastRemoved: Removed | null;
  undoRemove: () => void;
  dismissUndo: () => void;
  /** Stake per book, saved with the slip. */
  stakes: Record<string, number>;
  setStake: (book: string, stake: number) => void;
  state: string;
  setState: (s: string) => void;
  /** Show every sportsbook, not just the ones legal in `state`. */
  allBooks: boolean;
  setAllBooks: (b: boolean) => void;
  open: boolean;
  setOpen: (o: boolean) => void;
  /** When the page's odds were fetched, while they're over six hours old (null when current): the slip asks the bettor to
   *  check prices before it hands legs to a book. */
  staleSince: string | null;
  setStaleSince: (at: string | null) => void;
}

const Ctx = createContext<SlipCtx | null>(null);
const KEY = "nfl-props-slip-v1";

/** How long "Removed … · Undo" stays up. */
export const UNDO_MS = 6000;

function load(): { legs: Leg[]; state: string; allBooks?: boolean; stakes?: unknown; shared?: boolean } {
  // a slip shared from another device arrives in the URL hash; it replaces the saved slip, then the hash is removed
  const shared = slipFromHash(window.location.hash);
  if (shared) {
    try { window.history.replaceState(null, "", window.location.pathname + window.location.search); } catch { /* ignore */ }
    let saved: { allBooks?: boolean; stakes?: unknown } = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { /* storage blocked */ }
    return { ...shared, allBooks: !!saved.allBooks, stakes: saved.stakes, shared: true };
  }
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* storage blocked: start empty */ }
  return { legs: [], state: "" };
}

export function BetSlipProvider({ children }: { children: ReactNode }) {
  const [init] = useState(load);
  const [legs, setLegs] = useState<Leg[]>(init.legs);
  const [state, setState] = useState(init.state ?? "");
  const [allBooks, setAllBooks] = useState(!!init.allBooks);
  const [open, setOpen] = useState(!!init.shared);
  const [staleSince, setStaleSince] = useState<string | null>(null);
  const [stakes, setStakes] = useState(() => cleanStakes(init.stakes));
  const [lastRemoved, setLastRemoved] = useState<Removed | null>(null);

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify({ legs, state, allBooks, stakes })); } catch { /* ignore */ }
  }, [legs, state, allBooks, stakes]);

  useEffect(() => {
    if (!lastRemoved) return;
    const t = setTimeout(() => setLastRemoved(null), UNDO_MS);
    return () => clearTimeout(t);
  }, [lastRemoved]);

  // the bettor may have moved since the state was saved: re-check on load, but only if location is already allowed
  // (asking happens from the header or the slip, never unprompted)
  useEffect(() => {
    navigator.permissions?.query({ name: "geolocation" }).then((p) => {
      if (p.state === "granted") detectState().then((r) => { if ("state" in r) setState(r.state); });
    }).catch(() => { /* no Permissions API */ });
  }, []);

  const toggle = useCallback((leg: Leg) =>
    setLegs((ls) => (ls.some((l) => l.id === leg.id) ? ls.filter((l) => l.id !== leg.id) : [...ls, leg])), []);
  const remove = useCallback((ids: string | string[]) => {
    const gone = removedFrom(legs, typeof ids === "string" ? [ids] : ids);
    if (!gone.length) return;
    setLegs((ls) => ls.filter((l) => !gone.some((g) => g.leg.id === l.id)));
    setLastRemoved(gone);
  }, [legs]);
  // swap a leg for the same bet at another book; if that exact bet is already on the slip, just drop the old one
  const replace = useCallback((oldId: string, leg: Leg) => setLegs((ls) =>
    ls.some((l) => l.id === leg.id && l.id !== oldId) ? ls.filter((l) => l.id !== oldId) : ls.map((l) => (l.id === oldId ? leg : l))), []);
  const clear = useCallback(() => remove(legs.map((l) => l.id)), [remove, legs]);
  const undoRemove = useCallback(() => {
    if (lastRemoved) setLegs((ls) => restoreLegs(ls, lastRemoved));
    setLastRemoved(null);
  }, [lastRemoved]);
  const dismissUndo = useCallback(() => setLastRemoved(null), []);
  const setStake = useCallback((book: string, stake: number) => setStakes((s) => ({ ...s, [book]: stake })), []);
  const has = useCallback((id: string) => legs.some((l) => l.id === id), [legs]);
  const clashCount = useMemo(() => conflicts(legs).length, [legs]);
  const wouldClash = useCallback((leg: Leg) => clashesWith(legs, leg), [legs]);

  const value = useMemo(() => ({ legs, has, clashCount, wouldClash, toggle, remove, replace, clear, lastRemoved, undoRemove, dismissUndo, stakes, setStake,
    state, setState, allBooks, setAllBooks, open, setOpen, staleSince, setStaleSince }),
    [legs, has, clashCount, wouldClash, toggle, remove, replace, clear, lastRemoved, undoRemove, dismissUndo, stakes, setStake, state, allBooks, open, staleSince]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBetSlip() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useBetSlip must be used inside BetSlipProvider");
  return c;
}
