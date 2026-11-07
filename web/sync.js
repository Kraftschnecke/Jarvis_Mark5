// Live-Abgleich (Mark 5, Step R2b): PC und Handy sehen dieselbe Konversation.
// Die Seite fragt alle paar Sekunden /api/sync. Ist der Fingerabdruck neu, kommt der Verlauf mit.
(function (root) {
  "use strict";

  const INTERVAL_MS = 2000;

  // options: api(method, path), canApply() -> darf der Verlauf jetzt ersetzt werden?, apply(data), isHidden()
  function createSync(options) {
    let version = null;     // null = noch nichts bekannt, naechste Antwort wird nur uebernommen
    let adopt = true;       // true = die naechste Antwort nur merken (eigene Aktion oder Start)
    let running = false;

    async function poll() {
      if (running || options.isHidden()) return false;
      if (!options.canApply()) return false;
      running = true;
      try {
        const known = version !== null && !adopt ? "?known=" + encodeURIComponent(version) : "";
        const data = await options.api("GET", "/api/sync" + known);

        // Waehrend der Anfrage hat der Nutzer etwas getan: Antwort verwerfen, spaeter neu fragen
        if (!options.canApply()) return false;

        const fresh = version !== null && !adopt && data.version !== version && Array.isArray(data.messages);
        version = data.version;
        adopt = false;

        if (fresh) {
          options.apply(data);
          return true;
        }
        return false;
      } catch (error) {
        return false;     // offline: der Status kommt aus pollBackground
      } finally {
        running = false;
      }
    }

    // Nach einer eigenen Aktion (Nachricht, Konversation wechseln): den neuen Stand nur merken, nicht neu zeichnen
    function markOwnChange() {
      adopt = true;
    }

    function start(timers) {
      const id = timers.setInterval(poll, INTERVAL_MS);
      return () => timers.clearInterval(id);
    }

    return { poll, markOwnChange, start, version: () => version };
  }

  const api = { INTERVAL_MS, createSync };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisSync = api;
})(typeof window !== "undefined" ? window : this);