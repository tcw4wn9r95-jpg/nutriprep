const CACHE = "nutriprep-standalone-v8";
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
  e.respondWith(
    fetch(e.request)
      .then(r => {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
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
