// Makes the app installable and lets it open offline. Pages are fetched from the network first (so a deploy shows up
// on the next launch) with the last copy as the offline fallback; built assets have hashed names, so a cached copy is
// always correct. API calls are never cached: stale odds are worse than an error.
const CACHE = "props-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.includes("/api/")) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put("shell", copy)); }
      return res;
    }).catch(() => caches.match("shell").then((r) => r || Response.error())));
  } else if (url.pathname.includes("/assets/")) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    })));
  }
});
