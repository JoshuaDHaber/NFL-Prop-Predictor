import { useSyncExternalStore } from "react";

/** The admin token for a hosted API, kept in this browser only. Sent as a Bearer token on every request. */
const KEY = "nfl-props-admin-token";
const listeners = new Set<() => void>();

export function getToken(): string {
  try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; }
}
export function setToken(t: string) {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* storage blocked */ }
  listeners.forEach((l) => l());
}
export function useToken(): string {
  return useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), getToken);
}

/** True while requests are being retried because the hosted API is asleep (free hosts stop idle services). */
let waking = false;
const wakeListeners = new Set<() => void>();
export function setWaking(v: boolean) {
  if (waking !== v) { waking = v; wakeListeners.forEach((l) => l()); }
}
export function useWaking(): boolean {
  return useSyncExternalStore((cb) => (wakeListeners.add(cb), () => wakeListeners.delete(cb)), () => waking);
}
