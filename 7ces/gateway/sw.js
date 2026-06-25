// 7CE's service worker — caches the app shell for offline load. Only runs in a secure context
// (localhost or HTTPS, e.g. over Tailscale). API/dynamic endpoints are always network-only so
// chat replies, cost meter, and model list are never stale.
const CACHE = "7ces-shell-v2";
const SHELL = ["/chat", "/manifest.json", "/icons/icon-192.png", "/icons/icon-512.png"];
const NETWORK_ONLY = ["/deepseek", "/anthropic", "/meter", "/models", "/health"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never intercept API calls or dynamic data — let them hit the network directly.
  if (e.request.method !== "GET" || NETWORK_ONLY.some((p) => url.pathname.startsWith(p))) return;
  // Cache-first for shell assets; refresh in the background; fall back to the cached shell offline.
  e.respondWith(
    caches.match(e.request).then(
      (hit) =>
        hit ||
        fetch(e.request)
          .then((res) => {
            if (res && res.status === 200 && res.type !== "error") {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(e.request, copy));
            }
            return res;
          })
          .catch(() => caches.match("/chat"))
    )
  );
});
