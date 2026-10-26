import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { detectState } from "./geoState";
import { slipFromHash, type Leg } from "./slip";

interface SlipCtx {
  legs: Leg[];
  has: (id: string) => boolean;
  toggle: (leg: Leg) => void;
  remove: (id: string) => void;
  replace: (oldId: string, leg: Leg) => void;
  clear: () => void;
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

function load(): { legs: Leg[]; state: string; allBooks?: boolean; shared?: boolean } {
  // a slip shared from another device arrives in the URL hash; it replaces the saved slip, then the hash is removed
  const shared = slipFromHash(window.location.hash);
  if (shared) {
    try { window.history.replaceState(null, "", window.location.pathname + window.location.search); } catch { /* ignore */ }
    let allBooks = false;
    try { allBooks = !!JSON.parse(localStorage.getItem(KEY) ?? "{}").allBooks; } catch { /* storage blocked */ }
    return { ...shared, allBooks, shared: true };
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

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify({ legs, state, allBooks })); } catch { /* ignore */ }
  }, [legs, state, allBooks]);

  // the bettor may have moved since the state was saved: re-check on load, but only if location is already allowed
  // (asking happens from the header or the slip, never unprompted)
  useEffect(() => {
    navigator.permissions?.query({ name: "geolocation" }).then((p) => {
      if (p.state === "granted") detectState().then((r) => { if ("state" in r) setState(r.state); });
    }).catch(() => { /* no Permissions API */ });
  }, []);

  const toggle = useCallback((leg: Leg) =>
    setLegs((ls) => (ls.some((l) => l.id === leg.id) ? ls.filter((l) => l.id !== leg.id) : [...ls, leg])), []);
  const remove = useCallback((id: string) => setLegs((ls) => ls.filter((l) => l.id !== id)), []);
  // swap a leg for the same bet at another book; if that exact bet is already on the slip, just drop the old one
  const replace = useCallback((oldId: string, leg: Leg) => setLegs((ls) =>
    ls.some((l) => l.id === leg.id && l.id !== oldId) ? ls.filter((l) => l.id !== oldId) : ls.map((l) => (l.id === oldId ? leg : l))), []);
  const clear = useCallback(() => setLegs([]), []);
  const has = useCallback((id: string) => legs.some((l) => l.id === id), [legs]);

  const value = useMemo(() => ({ legs, has, toggle, remove, replace, clear, state, setState, allBooks, setAllBooks, open, setOpen, staleSince, setStaleSince }),
    [legs, has, toggle, remove, replace, clear, state, allBooks, open, staleSince]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBetSlip() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useBetSlip must be used inside BetSlipProvider");
  return c;
}
