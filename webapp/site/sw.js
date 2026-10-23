/* Mebelix: oddiy service worker — saytni telefonga «ilova» qilib o'rnatish uchun.
   Sahifalar har doim internetdan olinadi (narx va mavjudlik yangi bo'lsin); internet bo'lmasa — oxirgi nusxa. */
const CACHE = "mebelix-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/") || u.pathname.startsWith("/app")
      || /\.(mp4|webm|mov)$/i.test(u.pathname) || r.headers.has("range")) return;
  const isAsset = u.pathname.startsWith("/s/") || u.pathname.startsWith("/uploads/");
  if (isAsset) {
    e.respondWith(caches.match(r).then(hit => hit || fetch(r).then(res => {
      if (res.ok) { const c = res.clone(); caches.open(CACHE).then(ca => ca.put(r, c)); }
      return res;
    })));
  } else if (r.mode === "navigate") {
    e.respondWith(fetch(r).then(res => {
      if (res.ok) { const c = res.clone(); caches.open(CACHE).then(ca => ca.put(r, c)); }
      return res;
    }).catch(() => caches.match(r).then(hit => hit || caches.match("/"))));
  }
});
