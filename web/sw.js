// Service-Worker (Step 4B.2): nur damit der Browser Jarvis als App installieren laesst.
// Er speichert NICHTS zwischen und aendert keine Antwort: jede Anfrage geht unveraendert an den Server.
// So kann nie eine alte Seite haengen bleiben, und Gespraeche oder Daten landen nirgends im Browser-Zwischenspeicher.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});