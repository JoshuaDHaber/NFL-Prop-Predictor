import { useSyncExternalStore } from "react";

/** Settings the preferences page shows. Each lives in this browser's storage under the key it always had (so nothing
 *  remembered before accounts is lost), and, while signed in, in the account too: see auth.ts. */
export interface Prefs {
  theme: "auto" | "light" | "dark";
  /** The sportsbook game pages open at ("all": every book). */
  game_book: string;
  one_per_player: boolean;
  detailed_cards: boolean;
}
export type PrefKey = keyof Prefs;

export const PREFERRED_GAME_BOOK = "FanDuel";
export const DEFAULTS: Prefs = { theme: "auto", game_book: PREFERRED_GAME_BOOK, one_per_player: true, detailed_cards: false };

// [storage key, read, write]: the formats the app already used
const STORE: { [K in PrefKey]: [string, (raw: string | null) => Prefs[K], (v: Prefs[K]) => string | null] } = {
  theme: ["theme", (r) => (r === "light" || r === "dark" ? r : "auto"), (v) => (v === "auto" ? null : v)],
  game_book: ["gameBook", (r) => r || PREFERRED_GAME_BOOK, (v) => v],
  one_per_player: ["picks-one-per-player", (r) => r !== "0", (v) => (v ? "1" : "0")],
  detailed_cards: ["picks-detailed-cards", (r) => r === "1", (v) => (v ? "1" : "0")],
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

function store<K extends PrefKey>(k: K, v: Prefs[K]) {
  const raw = STORE[k][2](v);
  try { raw == null ? localStorage.removeItem(STORE[k][0]) : localStorage.setItem(STORE[k][0], raw); } catch { /* private mode: not remembered */ }
}

/** Change settings here (and in the account, when signed in). */
export function setPrefs(p: Partial<Prefs>, { save = true } = {}) {
  const changed = (Object.keys(p) as PrefKey[]).filter((k) => p[k] !== undefined && p[k] !== current[k]);
  if (!changed.length) return;
  current = { ...current, ...p };
  changed.forEach((k) => store(k, current[k] as never));
  listeners.forEach((l) => l());
  if (save) onChange?.(Object.fromEntries(changed.map((k) => [k, current[k]])));
}

export const getPrefs = () => current;
/** The settings that differ from the defaults: what a new account starts with. */
export const changedPrefs = (): Partial<Prefs> =>
  Object.fromEntries((Object.keys(DEFAULTS) as PrefKey[]).filter((k) => current[k] !== DEFAULTS[k]).map((k) => [k, current[k]]));

export function usePrefs(): Prefs {
  return useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), getPrefs);
}
/** One setting and its setter, like useState. */
export function usePref<K extends PrefKey>(k: K): [Prefs[K], (v: Prefs[K]) => void] {
  return [usePrefs()[k], (v) => setPrefs({ [k]: v } as Partial<Prefs>)];
}
