import { useSyncExternalStore } from "react";

/** Settings the preferences page shows. Each lives in this browser's storage under the key it always had (so nothing
 *  remembered before accounts is lost), and, while signed in, in the account too: see auth.ts. */
export interface Prefs {
  theme: "auto" | "light" | "dark";
  /** The sportsbook game pages open at ("all": every book). */
  game_book: string;
  one_per_player: boolean;
  detailed_cards: boolean;
  /** The order of the main sections in the top bar and phone tab bar (signed-in accounts reorder them on Preferences). */
  tab_order: MainTab[];
}
export type PrefKey = keyof Prefs;

/** The sections outside the More menu, the same in both leagues, in their usual order. */
export const MAIN_TABS = ["games", "picks", "parlays", "hot", "projections"] as const;
export type MainTab = typeof MAIN_TABS[number];
/** A saved order made whole: unknown sections dropped, any it lacks (added since) after it in their usual place. */
export function fullTabOrder(order: readonly string[]): MainTab[] {
  const known = order.filter((t, i): t is MainTab => (MAIN_TABS as readonly string[]).includes(t) && order.indexOf(t) === i);
  return [...known, ...MAIN_TABS.filter((t) => !known.includes(t))];
}
/** A league's section list in the visitor's order: the main sections reordered in place, the rest (More) where they were. */
export function orderTabs<T extends string>(tabs: [T, string][], order: readonly string[]): [T, string][] {
  const main = tabs.filter(([k]) => order.includes(k)).sort(([a], [b]) => order.indexOf(a) - order.indexOf(b));
  return tabs.map((t) => (order.includes(t[0]) ? main.shift()! : t));
}

export const PREFERRED_GAME_BOOK = "FanDuel";
export const DEFAULTS: Prefs = { theme: "auto", game_book: PREFERRED_GAME_BOOK, one_per_player: true, detailed_cards: false,
  tab_order: [...MAIN_TABS] };

// [storage key, read, write]: the formats the app already used
const STORE: { [K in PrefKey]: [string, (raw: string | null) => Prefs[K], (v: Prefs[K]) => string | null] } = {
  theme: ["theme", (r) => (r === "light" || r === "dark" ? r : "auto"), (v) => (v === "auto" ? null : v)],
  game_book: ["gameBook", (r) => r || PREFERRED_GAME_BOOK, (v) => v],
  one_per_player: ["picks-one-per-player", (r) => r !== "0", (v) => (v ? "1" : "0")],
  detailed_cards: ["picks-detailed-cards", (r) => r === "1", (v) => (v ? "1" : "0")],
  tab_order: ["tab-order", (r) => (r ? fullTabOrder(r.split(",")) : DEFAULTS.tab_order), (v) => (v.join() === MAIN_TABS.join() ? null : v.join())],
};

function read(): Prefs {
  const out = { ...DEFAULTS } as Record<PrefKey, unknown>;
  for (const k of Object.keys(STORE) as PrefKey[]) {
    let raw: string | null = null;
    try { raw = localStorage.getItem(STORE[k][0]); } catch { /* storage blocked: the default */ }
    out[k] = STORE[k][1](raw);
  }
  return out as unknown as Prefs;
}

let current = read();
const listeners = new Set<() => void>();
/** auth.ts sets this: a change made while signed in is saved to the account as well. */
let onChange: ((p: Partial<Prefs>) => void) | null = null;
export const setPrefsSink = (f: typeof onChange) => { onChange = f; };

/** Settings picked since the page opened: still known when storage is blocked (private mode). */
const picked = new Set<PrefKey>();
/** Whether this browser holds a value for a setting: chosen here, on a game page or from the account, not just the default. */
function isStored(k: PrefKey): boolean {
  if (picked.has(k)) return true;
  try { return localStorage.getItem(STORE[k][0]) != null; } catch { return false; }
}

function store<K extends PrefKey>(k: K, v: Prefs[K]) {
  const raw = STORE[k][2](v);
  if (raw != null) picked.add(k); else picked.delete(k);
  try { raw == null ? localStorage.removeItem(STORE[k][0]) : localStorage.setItem(STORE[k][0], raw); } catch { /* private mode: not remembered */ }
}

const same = (a: unknown, b: unknown) => (Array.isArray(a) && Array.isArray(b) ? a.join() === b.join() : a === b);

/** Change settings here (and in the account, when signed in). */
export function setPrefs(p: Partial<Prefs>, { save = true } = {}) {
  // choosing the default value (FanDuel) still counts as choosing it, so it's stored the first time
  const changed = (Object.keys(p) as PrefKey[]).filter((k) => p[k] !== undefined
    && (!same(p[k], current[k]) || (!isStored(k) && STORE[k][2](p[k] as never) != null)));
  if (!changed.length) return;
  current = { ...current, ...p };
  changed.forEach((k) => store(k, current[k] as never));
  listeners.forEach((l) => l());
  if (save) onChange?.(Object.fromEntries(changed.map((k) => [k, current[k]])));
}

export const getPrefs = () => current;
/** The settings this browser has chosen (or that differ from the defaults): what a new account starts with. */
export const changedPrefs = (): Partial<Prefs> =>
  Object.fromEntries((Object.keys(DEFAULTS) as PrefKey[]).filter((k) => !same(current[k], DEFAULTS[k]) || isStored(k)).map((k) => [k, current[k]]));

/** The sportsbook the visitor picked (Preferences, a game page or their account), or null if they never picked one. */
export const chosenGameBook = (): string | null => (isStored("game_book") ? current.game_book : null);

/** The book Best props opens at: the visitor's own sportsbook once they've picked one, else every book (the best price
 *  anywhere). Someone who never picked keeps every book rather than the FanDuel default game pages use. */
export function useBoardBook(): string {
  usePrefs();
  return chosenGameBook() ?? "all";
}

export function usePrefs(): Prefs {
  return useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), getPrefs);
}
/** One setting and its setter, like useState. */
export function usePref<K extends PrefKey>(k: K): [Prefs[K], (v: Prefs[K]) => void] {
  return [usePrefs()[k], (v) => setPrefs({ [k]: v } as Partial<Prefs>)];
}
