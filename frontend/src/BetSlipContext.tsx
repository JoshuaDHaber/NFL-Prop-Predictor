import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Leg } from "./slip";

interface SlipCtx {
  legs: Leg[];
  has: (id: string) => boolean;
  toggle: (leg: Leg) => void;
  remove: (id: string) => void;
  clear: () => void;
  state: string;
  setState: (s: string) => void;
  open: boolean;
  setOpen: (o: boolean) => void;
}

const Ctx = createContext<SlipCtx | null>(null);
const KEY = "nfl-props-slip-v1";

function load(): { legs: Leg[]; state: string } {
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
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify({ legs, state })); } catch { /* ignore */ }
  }, [legs, state]);

  const toggle = useCallback((leg: Leg) =>
    setLegs((ls) => (ls.some((l) => l.id === leg.id) ? ls.filter((l) => l.id !== leg.id) : [...ls, leg])), []);
  const remove = useCallback((id: string) => setLegs((ls) => ls.filter((l) => l.id !== id)), []);
  const clear = useCallback(() => setLegs([]), []);
  const has = useCallback((id: string) => legs.some((l) => l.id === id), [legs]);

  const value = useMemo(() => ({ legs, has, toggle, remove, clear, state, setState, open, setOpen }),
    [legs, has, toggle, remove, clear, state, open]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBetSlip() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useBetSlip must be used inside BetSlipProvider");
  return c;
}
