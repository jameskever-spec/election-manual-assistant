/* Election Manual Assistant — offline service worker.
   Precaches the app AND all page images at install, so the app is fully
   functional offline from the very first launch. Image caching is
   best-effort: a missing image can never break the install. */
importScripts("js/imglist.js");

const CACHE = "ema-v2.4";
const ASSETS = [
  "./",
  "./index.html",
  "./css/app.css",
  "./js/app.js",
  "./js/data.js",
  "./js/imglist.js",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then(async (c) => {
      await c.addAll(ASSETS);
      // Page images: best-effort, jpg first then png, never fail the install
      await Promise.all(
        IMG_PAGES.map((pg) =>
          c.add(`img/p${pg}.jpg`).catch(() =>
            c.add(`img/p${pg}.png`).catch(() => {})
          )
        )
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      return fetch(e.request).then((resp) => {
        if (resp.ok && e.request.url.includes("/img/")) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return resp;
      });
    })
  );
});
