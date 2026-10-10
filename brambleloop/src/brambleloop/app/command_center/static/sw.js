// Brambleloop Command Center service worker (F-883).
//
// What it caches: ONLY the static application shell listed in SHELL (HTML, CSS, JS, icons),
// so the app can open and say "offline" honestly when the network is gone.
// What it never caches: anything under /api/ -- those responses carry money, customer and
// security data and are current truth only at the moment they are served (F-898). API
// requests are not intercepted at all; they go straight to the network. Non-GET requests are
// never intercepted. Cross-origin requests are never intercepted.
const VERSION = "cc-shell-v10";
const SHELL = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "css/app.css",
  "icons/icon.svg",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "js/app.js",
  "js/api.js",
  "js/components.js",
  "js/dom.js",
  "js/format.js",
  "js/routes.js",
  "js/views/_shared.js",
  "js/views/account.js",
  "js/views/approvals.js",
  "js/views/company.js",
  "js/views/completion.js",
  "js/views/ask.js",
  "js/views/drill.js",
  "js/views/emergency.js",
  "js/views/home.js",
  "js/views/laura.js",
  "js/views/insights.js",
  "js/views/learn.js",
  "js/views/money.js",
  "js/views/more.js",
  "js/views/notifications.js",
  "js/views/operations.js",
  "js/views/store.js",
  "js/views/timeline.js",
];
const SCOPE_PATH = new URL(self.registration.scope).pathname; // "/cc/"
const SHELL_PATHS = new Set(SHELL.map((p) => new URL(p, self.registration.scope).pathname));

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

function isApi(url) {
  return url.pathname.startsWith("/api/");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (isApi(url)) return; // network only, never cached
  if (!url.pathname.startsWith(SCOPE_PATH)) return;

  const shellKey = req.mode === "navigate" ? new URL("index.html", self.registration.scope).pathname : url.pathname;
  if (req.mode !== "navigate" && !SHELL_PATHS.has(url.pathname)) return;

  // Network first so a deploy is picked up immediately; the cached shell is the offline fallback.
  event.respondWith((async () => {
    try {
      const res = await fetch(req, { cache: "no-store" });
      if (res.ok && res.type === "basic" && SHELL_PATHS.has(shellKey) && req.mode !== "navigate") {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(shellKey, copy)).catch(() => {});
      }
      return res;
    } catch (err) {
      const cache = await caches.open(VERSION);
      const hit = await cache.match(shellKey);
      if (hit) return hit;
      throw err;
    }
  })());
});
