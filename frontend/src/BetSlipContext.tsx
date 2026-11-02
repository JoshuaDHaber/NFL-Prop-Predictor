import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAuth } from "./auth";
import { detectState } from "./geoState";
import { cleanStakes, clashesWith, conflicts, removedFrom, restoreLegs, slipFromHash, type Leg, type Removed } from "./slip";
import { fetchSlip, loadMeta, mergeSlips, pushSlip, sameSlip, saveMeta, type ServerSlip } from "./slipSync";

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

  useSlipSync(legs, stakes, setLegs, setStakes);

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

/** Keep the slip's legs and stakes in step with the signed-in (21+) account, so they follow the bettor between devices
 *  (slipSync.ts). A change here is saved a moment later; returning to the page reads the account's copy and takes it if
 *  another device saved since. The first sync of an account in this browser, or two devices saving at once, merges the
 *  two copies instead of dropping either. */
function useSlipSync(legs: Leg[], stakes: Record<string, number>, setLegs: (l: Leg[]) => void, setStakes: (s: Record<string, number>) => void) {
  const user = useAuth()?.user;
  const email = user?.age_confirmed ? user.email : null;
  const meta = useRef(loadMeta());
  const local = useRef({ legs, stakes });
  local.current = { legs, stakes };
  const applied = useRef<string | null>(null);   // the slip just taken from the server: not an edit to send back
  const first = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const busy = useRef(false);

  const setMeta = (m: Partial<typeof meta.current>) => { meta.current = { ...meta.current, ...m }; saveMeta(meta.current); };
  const take = (s: Pick<ServerSlip, "legs" | "stakes">) => {
    const next = { legs: s.legs, stakes: cleanStakes(s.stakes) };
    if (sameSlip(next, local.current)) return;
    applied.current = JSON.stringify(next.legs.map((l) => l.id)) + JSON.stringify(next.stakes);
    setLegs(next.legs);
    setStakes(next.stakes);
  };

  const push = useCallback(async (base: string | null) => {
    if (!email || busy.current) return;
    busy.current = true;
    try {
      let r = await pushSlip(local.current.legs, local.current.stakes, base);
      if (r.status === 409) {   // another device saved first: keep both sets of legs, then save that
        const merged = mergeSlips(local.current, r.slip);
        take(merged);
        r = await pushSlip(merged.legs, merged.stakes, r.slip.updated_at);
      }
      if (r.status === 200) setMeta({ email, syncedAt: r.slip.updated_at, dirty: false });
    } catch { /* offline: still dirty, sent next time */ } finally { busy.current = false; }
  }, [email]); // eslint-disable-line react-hooks/exhaustive-deps

  const pull = useCallback(async () => {
    if (!email || busy.current) return;
    let server: ServerSlip;
    try { server = await fetchSlip(); } catch { return; }
    if (meta.current.email !== email) {
      // this account's first sync in this browser: what was built here (signed out, or another account) joins its slip
      const merged = mergeSlips(server, local.current);
      take(merged);
      setMeta({ email, syncedAt: server.updated_at, dirty: !sameSlip(merged, server) });
      if (meta.current.dirty) void push(server.updated_at);
    } else if (meta.current.dirty) {
      void push(meta.current.syncedAt);
    } else if (server.updated_at && server.updated_at !== meta.current.syncedAt) {
      take(server);   // another device saved since: its slip is the latest
      setMeta({ syncedAt: server.updated_at });
    }
  }, [email, push]); // eslint-disable-line react-hooks/exhaustive-deps

  // signing in, and every return to the page (another device may have changed the slip meanwhile)
  useEffect(() => {
    if (!email) return;
    void pull();
    const back = () => { if (document.visibilityState === "visible") void pull(); };
    document.addEventListener("visibilitychange", back);
    window.addEventListener("focus", back);
    return () => { document.removeEventListener("visibilitychange", back); window.removeEventListener("focus", back); };
  }, [email, pull]);

  // an edit here: remember it's unsaved, and save it a moment later
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const now = JSON.stringify(legs.map((l) => l.id)) + JSON.stringify(stakes);
    if (applied.current === now) { applied.current = null; return; }
    setMeta({ dirty: true });
    if (!email || meta.current.email !== email) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void push(meta.current.syncedAt), 800);
    return () => clearTimeout(timer.current);
  }, [legs, stakes]); // eslint-disable-line react-hooks/exhaustive-deps
}
