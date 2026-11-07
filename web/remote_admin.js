// Remote-Verwaltung am PC (Mark 5, Step R4): reine Anzeige-Logik fuer die Einstellungsseite "Remote".
// Alles Text, nichts HTML: Die Seite setzt es mit textContent ein.
(function (root) {
  "use strict";

  const LINK_NOTE = "Der Link gilt 5 Minuten und nur einmal. Öffne ihn auf dem Handy (z. B. per AirDrop oder Nachricht an dich selbst).";

  // "gerade eben", "vor 5 Min.", "vor 3 Std.", "vor 2 Tagen", "nie"
  function agoText(seconds, now) {
    if (typeof seconds !== "number" || !isFinite(seconds) || seconds <= 0) return "nie";
    const diff = Math.floor(now - seconds);    // geht die Uhr vor, ist es negativ und zaehlt als "gerade eben"
    if (diff < 60) return "gerade eben";
    if (diff < 3600) return "vor " + Math.floor(diff / 60) + " Min.";
    if (diff < 86400) return "vor " + Math.floor(diff / 3600) + " Std.";
    const days = Math.floor(diff / 86400);
    return "vor " + days + (days === 1 ? " Tag" : " Tagen");
  }

  // Ein Geraet fuer die Liste: gesperrt vor abgelaufen vor aktiv
  function deviceView(device, now) {
    let state = "active";
    let label = "aktiv";
    if (device.revoked) {
      state = "revoked";
      label = "gesperrt";
    } else if (device.expired) {
      state = "expired";
      label = "abgelaufen";
    }
    return { state, label, name: String(device.name), seen: "zuletzt " + agoText(device.last_seen, now), canRevoke: state === "active", canRestore: state === "revoked" };
  }

  // Kopfzeile der Seite: was ist los mit Remote?
  function statusView(info) {
    if (!info || !info.available) {
      return {
        tone: "off",
        text: "Es ist kein Remote-Name eingetragen. Trage JARVIS_REMOTE_HOST (z. B. mein-pc.tailabc.ts.net) in die .env ein und starte J.A.R.V.I.S. neu.",
      };
    }
    if (!info.active) {
      return { tone: "off", text: "Remote ist aus. https://" + info.host + " ist nicht erreichbar." };
    }
    return { tone: "on", text: "Remote ist an: https://" + info.host };
  }

  function canPair(info) {
    return Boolean(info && info.available && info.active);
  }

  // Der zuletzt erzeugte Link: wie lange noch gueltig? null, wenn abgelaufen
  function linkView(entry, now) {
    if (!entry) return null;
    const left = Math.floor(entry.until - now);
    if (left <= 0) return null;
    const minutes = Math.floor(left / 60);
    const seconds = left % 60;
    return { link: entry.link, name: entry.name, left: minutes + ":" + (seconds < 10 ? "0" : "") + seconds, note: LINK_NOTE };
  }

  const api = { agoText, deviceView, statusView, canPair, linkView, LINK_NOTE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisRemoteAdmin = api;
})(typeof window !== "undefined" ? window : this);