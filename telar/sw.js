/* Telar se mudó: este service worker solo se retira a sí mismo y a su caché. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil((async () => {
  await caches.delete("telar-v1");
  await self.registration.unregister();
  for (const c of await self.clients.matchAll({type: "window"})) c.navigate(c.url);
})()));
