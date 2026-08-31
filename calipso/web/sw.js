const CACHE = "calipso-shell-v3";
const SHELL = [
  "/",
  "/fabrica",
  "/fabrica/manifest.json",
  "/manifest.json",
  "/static/icon.svg",
  "/static/fabrica/estilo.css",
  "/static/fabrica/app.js",
  "/static/fabrica/paleta.js",
  "/static/fabrica/sprites.js",
  "/static/fabrica/camara.js",
  "/static/fabrica/ciudad.js",
  "/static/fabrica/mapa.js",
  "/static/fabrica/paneles.js",
  "/static/fabrica/socket.js",
  "/static/fabrica/chat.js",
  "/static/fabrica/pulso.js",
  "/static/fabrica/interior.js",
  "/static/fabrica/mesa.js",
  "/static/fabrica/plantel.js",
  "/static/fabrica/perillas.js",
  "/static/fabrica/freno.js",
  "/static/fabrica/svg.js",
  "/static/fabrica/permisos.js",
  "/static/fabrica/inbox.js"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;
  event.respondWith(fetch(req).catch(() => caches.match(req)));
});
