// Remote-Verwaltung am PC (Mark 5, Step R4): reine Anzeige-Logik fuer die Einstellungsseite "Remote".
// Alles Text, nichts HTML: Die Seite setzt es mit textContent ein.
(function (root) {
  "use strict";

  const LINK_NOTE = "Der Code gilt 5 Minuten und nur einmal. Tippe ihn auf dem neuen Gerät auf der Kopplungsseite ein, oder schicke den Link (z. B. per Nachricht).";

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
    const area = device.profile && device.profile !== "owner" ? String(device.profile_name || "Gast") : "";
    return { state, label, name: String(device.name), area, seen: "zuletzt " + agoText(device.last_seen, now), canRevoke: state === "active", canRestore: state === "revoked", agent: device.agent === true };
  }

  // Der PC-Agent (S6): verbunden oder nicht, mit Hinweis zum Koppeln
  function agentView(state) {
    if (state && state.online === true) {
      return { state: "active", text: "PC-Agent verbunden" + (state.name ? ": " + String(state.name) : "") };
    }
    return { state: "expired", text: "PC-Agent nicht verbunden. Koppeln im Server-Terminal: server_main.py --pair-agent \"PC Moritz\"" };
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
    const hash = String(entry.link).lastIndexOf("#");
    const code = typeof entry.code === "string" && entry.code ? entry.code : hash >= 0 ? String(entry.link).slice(hash + 1) : "";
    return { link: entry.link, code, name: entry.name, left: minutes + ":" + (seconds < 10 ? "0" : "") + seconds, note: LINK_NOTE };
  }

  // Ein Gast-Bereich fuer die Liste: Name, Limits als Text (0 = unbegrenzt), Anzahl aktiver Geraete
  function limitText(value) {
    return value === 0 ? "unbegrenzt" : String(value);
  }

  function profileView(profile) {
    const count = Number(profile.devices) || 0;
    return {
      id: String(profile.id),
      name: String(profile.name),
      aiPerDay: profile.limits.ai_per_day,
      perTenMin: profile.limits.messages_per_10min,
      summary: "KI-Anfragen/Tag: " + limitText(profile.limits.ai_per_day) + " · Nachrichten/10 Min.: " + limitText(profile.limits.messages_per_10min),
      devices: count === 1 ? "1 Gerät" : count + " Geräte",
    };
  }

  // Limit-Eingabe: ganze Zahl 0..100000, sonst null
  function parseLimit(text) {
    const value = String(text).trim();
    if (!/^\d{1,6}$/.test(value)) return null;
    const number = Number(value);
    return number <= 100000 ? number : null;
  }

  const api = { agoText, deviceView, agentView, statusView, canPair, linkView, profileView, parseLimit, LINK_NOTE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisRemoteAdmin = api;
})(typeof window !== "undefined" ? window : this);