import { useSyncExternalStore } from "react";
import { changedPrefs, setPrefs, setPrefsSink, type Prefs } from "./prefs";

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

// ---------- accounts: Google or an emailed link/code; the session is an httpOnly cookie the page never sees ----------
export interface Account {
  email: string;
  name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  age_confirmed: boolean;
  prefs: { [K in keyof Prefs]: Prefs[K] | null };
}
export interface AuthState { user: Account | null; google: boolean; next?: string | null }

/** null until /api/auth/me answers (the site works the same meanwhile: signing in is optional). */
let auth: AuthState | null = null;
const authListeners = new Set<() => void>();
let loading: Promise<void> | null = null;

async function call(path: string, init: RequestInit = {}): Promise<AuthState> {
  const res = await fetch(`/api/auth/${path}`, {
    ...init, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", ...(init.headers as Record<string, string>) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Try again.");
  return body as AuthState;
}

/** Take a fresh answer from the server: the account's saved settings win over this browser's. */
function apply(next: AuthState, { fromSignIn = false } = {}) {
  const was = auth?.user?.email;
  auth = next;
  const user = next.user;
  if (user) {
    const saved = Object.fromEntries(Object.entries(user.prefs).filter(([, v]) => v != null)) as Partial<Prefs>;
    if (Object.keys(saved).length) setPrefs(saved, { save: false });
    // a new account starts from what this browser had already chosen
    else if (fromSignIn && user.age_confirmed && Object.keys(changedPrefs()).length) void savePrefs(changedPrefs());
  }
  authListeners.forEach((l) => l());
  return was !== user?.email;
}

export function loadAuth(): Promise<void> {
  loading ??= call("me").then((s) => { apply(s); }, () => { auth = { user: null, google: false }; authListeners.forEach((l) => l()); });
  return loading;
}

export function useAuth(): AuthState | null {
  const s = useSyncExternalStore((cb) => (authListeners.add(cb), () => authListeners.delete(cb)), () => auth);
  if (!s && !loading) void loadAuth();
  return s;
}

/** Saving a change made while signed in (and 21+ confirmed); a failure leaves this browser's copy as it is. */
async function savePrefs(p: Partial<Prefs>) {
  if (!auth?.user?.age_confirmed) return;
  try { apply(await call("prefs", { method: "PUT", body: JSON.stringify(p) })); } catch { /* kept in this browser */ }
}
setPrefsSink((p) => { void savePrefs(p); });

/** Each returns whether who's signed in changed, so callers can refetch what depends on it (the admin page, can_write). */
export const emailSignIn = (email: string, next: string) => call("email", { method: "POST", body: JSON.stringify({ email, next }) });
export const verifyLink = async (token: string) => { const s = await call("email/verify", { method: "POST", body: JSON.stringify({ token }) }); apply(s, { fromSignIn: true }); return s; };
export const verifyCode = async (email: string, code: string) => { const s = await call("email/verify", { method: "POST", body: JSON.stringify({ email, code }) }); apply(s, { fromSignIn: true }); return s; };
export const confirmAge = async () => { apply(await call("age", { method: "POST" }), { fromSignIn: true }); };
/** Signing out signs this browser out of everything: the account and the admin password, if one was saved here, which
 *  otherwise kept the owner's pages open after "Sign out". Forgotten even if the server can't be reached. */
export const signOut = async () => { try { return apply(await call("logout", { method: "POST" })); } finally { setToken(""); } };
export const deleteAccount = async () => { const changed = apply(await call("me", { method: "DELETE" })); setToken(""); return changed; };
export const googleHref = (next: string) => `/api/auth/google/start?next=${encodeURIComponent(next)}`;
/** Where you are now, to come back to after signing in. */
export const herePath = () => window.location.pathname + window.location.search + window.location.hash;
