// Shared maps always revalidate their capability. Never cache map/API responses or
// fall back to the owner's shell, even if both apps are hosted on the same origin.
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.mode !== "navigate" ||
    url.origin !== self.location.origin ||
    !url.pathname.startsWith("/share/")
  )
    return;
  event.respondWith(
    fetch(event.request).catch(
      () =>
        new Response(
          '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#182a22"><title>Shared map · Curbwatch</title><body><h1>Connect to open your shared map.</h1><p>Your link needs an internet connection to check access and load current street activity.</p><button onclick="location.reload()">Try again</button></body></html>',
          { headers: { "Content-Type": "text/html; charset=utf-8" } },
        ),
    ),
  );
});
