import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const dist = resolve(import.meta.dirname, "../dist");
const paths = ["/index.html", "/favicon.svg", "/manifest.webmanifest"];
for (const folder of ["assets", "icons"]) {
  for (const file of await readdir(join(dist, folder)))
    paths.push(`/${folder}/${file}`);
}
const version = createHash("sha256")
  .update(await readFile(join(dist, "index.html")))
  .digest("hex")
  .slice(0, 16);
const worker = `
const APP_CACHE = 'curbwatch-shell-${version}';
const OCR_CACHE = 'curbwatch-ocr-v1';
const AUTH_MIGRATION = 'curbwatch-auth-boundary-v1';
const PRECACHE = ${JSON.stringify(paths)};
self.addEventListener('install', event => {
  event.waitUntil(caches.open(APP_CACHE).then(cache => cache.addAll(PRECACHE)).then(async () => {
    // One-time security migration: old running shells had no login gate.
    if (!(await caches.has(AUTH_MIGRATION))) {
      await caches.open(AUTH_MIGRATION);
      await self.skipWaiting();
    }
  }));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('curbwatch-shell-') && key !== APP_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  // Verification, saves, and ticket data always use the real server. Never queue writes.
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/share/') || url.pathname === '/sw.js' || url.pathname === '/runtime-config.js') return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/index.html')));
  } else if (url.pathname.startsWith('/ocr/')) {
    event.respondWith(caches.open(OCR_CACHE).then(async cache => {
      const stored = await cache.match(request);
      if (stored) return stored;
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    }));
  } else if (PRECACHE.includes(url.pathname)) {
    event.respondWith(caches.match(url.pathname).then(stored => stored || fetch(request)));
  }
});
`;
await writeFile(join(dist, "sw.js"), worker);
console.log(
  `Built PWA shell ${version}; ${paths.length} local assets. Ticket APIs remain network-only.`,
);
