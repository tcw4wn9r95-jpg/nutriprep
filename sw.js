const CACHE = "nutriprep-standalone-v23";
const ASSETS = ["./dashboard.html"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  const sameOrigin = url.origin === self.location.origin;
  // Force a fresh copy of same-origin app files (HTML, version.json, sw) so the PWA
  // can never get stuck on a stale build; cache them for offline fallback. Leave
  // cross-origin requests (images, GitHub/Anthropic APIs) to default behaviour.
  e.respondWith(
    fetch(e.request, sameOrigin ? { cache: "no-store" } : undefined)
      .then(r => {
        if (sameOrigin) { const clone = r.clone(); caches.open(CACHE).then(c => c.put(e.request, clone)); }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── Push notifications ─────────────────────────────────────────────────────
self.addEventListener("push", e => {
  let data = { title: "NutriPrep", body: "Time for your next meal action!" };
  try { data = e.data.json(); } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "./apple-touch-icon.png",
      badge: "./apple-touch-icon.png",
      tag: data.type || "nutriprep",
      data: { url: "./dashboard.html" },
      requireInteraction: false,
    })
  );
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: "window" }).then(cs => {
      const target = (e.notification.data || {}).url || "./dashboard.html";
      const open = cs.find(c => c.url.includes("dashboard.html") && "focus" in c);
      return open ? open.focus() : clients.openWindow(target);
    })
  );
});
