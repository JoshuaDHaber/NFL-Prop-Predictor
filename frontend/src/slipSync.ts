import type { Leg } from "./slip";

// The betslip saved to a signed-in account (backend app/slip_sync.py), so it follows the bettor between devices. Legs and
// stakes sync; the betting state and "all books" stay per device (each device knows where it is).

export interface ServerSlip { legs: Leg[]; stakes: Record<string, number>; updated_at: string | null }
/** What this browser knows about its last sync: the account, the server copy it last saw, and whether it has edits since. */
export interface SyncMeta { email: string | null; syncedAt: string | null; dirty: boolean }

const META_KEY = "nfl-props-slip-sync";
export function loadMeta(): SyncMeta {
  try { return { email: null, syncedAt: null, dirty: true, ...JSON.parse(localStorage.getItem(META_KEY) ?? "{}") }; }
  catch { return { email: null, syncedAt: null, dirty: true }; }
}
export function saveMeta(m: SyncMeta) {
  try { localStorage.setItem(META_KEY, JSON.stringify(m)); } catch { /* private mode: synced from scratch next visit */ }
}

/** One slip from two: every leg of `first`, then `second`'s legs it lacks, in order. Stakes: `first`'s win where both set
 *  one. Used when two copies diverged (the first sign-in on a device, or two devices saving at once), so no added leg is
 *  lost; a leg removed on only one side comes back, the safer mistake for a bettor. */
export function mergeSlips(first: Pick<ServerSlip, "legs" | "stakes">, second: Pick<ServerSlip, "legs" | "stakes">) {
  const ids = new Set(first.legs.map((l) => l.id));
  return { legs: [...first.legs, ...second.legs.filter((l) => !ids.has(l.id))], stakes: { ...second.stakes, ...first.stakes } };
}

export const sameSlip = (a: Pick<ServerSlip, "legs" | "stakes">, b: Pick<ServerSlip, "legs" | "stakes">) =>
  JSON.stringify(a.legs.map((l) => l.id)) === JSON.stringify(b.legs.map((l) => l.id)) && JSON.stringify(a.stakes) === JSON.stringify(b.stakes);

async function call(init: RequestInit = {}): Promise<{ status: number; slip: ServerSlip }> {
  const res = await fetch("/api/me/slip", {
    ...init, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", ...(init.headers as Record<string, string>) },
  });
  if (!res.ok && res.status !== 409) throw new Error(`slip sync ${res.status}`);
  return { status: res.status, slip: await res.json() };
}
export const fetchSlip = async () => (await call()).slip;
/** Save; a 409 means another device saved since `base`, and carries that newer copy to merge. */
export const pushSlip = (legs: Leg[], stakes: Record<string, number>, base: string | null) =>
  call({ method: "PUT", body: JSON.stringify({ legs, stakes, base }) });
