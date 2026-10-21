import { useSyncExternalStore } from "react";

/** The admin password, kept in this browser only. Sent as a Bearer token on every request. */
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
