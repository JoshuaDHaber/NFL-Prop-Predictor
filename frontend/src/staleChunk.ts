/**
 * After a deploy, a tab opened before it still points at the old build, whose lazily loaded files (the player drawer)
 * no longer exist, so opening them fails forever. Reload once to pick up the new build; the guard stops a loop when
 * the file is genuinely missing or the network is down.
 */
const KEY = "stale-chunk-reload-at";
const WINDOW_MS = 30_000;

export function importOrReload<T>(load: () => Promise<T>, reload = () => window.location.reload(), now = Date.now()): Promise<T> {
  return load().catch((err) => {
    let last = 0;
    try { last = Number(sessionStorage.getItem(KEY)) || 0; } catch { /* storage blocked: still reload once */ }
    if (now - last < WINDOW_MS) throw err;           // already reloaded for this: surface the error instead of looping
    try { sessionStorage.setItem(KEY, String(now)); } catch { /* ignore */ }
    reload();
    return new Promise<T>(() => {});                  // keep Suspense waiting while the page reloads
  });
}
