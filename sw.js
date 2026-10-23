// המזווה: offline support. App shell = cache first (updated in the background); price data = network first, cache fallback.
const VER = "v5";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png",
  "https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js"];
self.addEventListener("install", e => { e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request; if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Firebase traffic (auth, Firestore streaming) must never be cached
  if (/googleapis\.com|firebaseio|identitytoolkit|securetoken/.test(url.host)) return;
  // the page itself: network first, so an update shows up on the next open; cached copy when offline
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(r => { const c = r.clone(); caches.open(VER).then(x => x.put("index.html", c)); return r; })
      .catch(() => caches.match("index.html")));
    return;
  }
  const isData = url.origin === location.origin && url.pathname.endsWith(".json");
  if (isData) {
    e.respondWith(fetch(req).then(r => { const c = r.clone(); caches.open(VER).then(x => x.put(req, c)); return r; })
      .catch(() => caches.match(req)));
    return;
  }
  // shell + CDN scripts (html5-qrcode, firebase from gstatic): serve cached, refresh in background
  e.respondWith(caches.match(req, {ignoreSearch: url.origin === location.origin}).then(hit => {
    const net = fetch(req).then(r => { if (r.ok || r.type === "opaque") { const c = r.clone(); caches.open(VER).then(x => x.put(req, c)); } return r; });
    return hit || net;
  }));
});
