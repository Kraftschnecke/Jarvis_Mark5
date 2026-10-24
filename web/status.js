// Statusbericht beim Start und Anzeige der Timer (Step 6b).
// Reine Textfunktionen ohne Zugriff auf die Seite, damit sie ohne Browser testbar sind.
(function (root) {
  "use strict";

  const WEEKDAYS = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
  const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
                  "September", "Oktober", "November", "Dezember"];

  function greetingFor(hour) {
    if (hour >= 4 && hour < 10) return "Guten Morgen";
    if (hour >= 10 && hour < 18) return "Guten Tag";
    return "Guten Abend";
  }

  // 200 -> "3:20", 3725 -> "1:02:05"
  function formatRemaining(seconds) {
    seconds = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const two = (n) => String(n).padStart(2, "0");
    return h > 0 ? h + ":" + two(m) + ":" + two(s) : m + ":" + two(s);
  }

  // timers: [{name, remaining}] wie von /api/timers
  function buildStartupReport(info) {
    const now = info.now;
    const address = info.address || "Sir";
    const parts = [
      greetingFor(now.getHours()) + ", " + address + ". Heute ist " +
        WEEKDAYS[now.getDay()] + ", der " + now.getDate() + ". " + MONTHS[now.getMonth()] +
        ", " + String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0") + " Uhr.",
    ];

    // Wetter-Satz vom Server (Heimatort); fehlt er, steht einfach nichts da
    if (typeof info.weather === "string" && info.weather.trim() && info.weather.length <= 200) {
      parts.push(info.weather.trim());
    }

    const timers = Array.isArray(info.timers) ? info.timers : [];
    if (timers.length === 1) {
      parts.push("Ein Timer läuft: " + timers[0].name + " (noch " + formatRemaining(timers[0].remaining) + ").");
    } else if (timers.length > 1) {
      parts.push(timers.length + " Timer laufen: " +
        timers.map((t) => t.name + " (noch " + formatRemaining(t.remaining) + ")").join(", ") + ".");
    }

    if (info.memoryEnabled === false) parts.push("Mein Gedächtnis ist ausgeschaltet.");

    parts.push("Wie kann ich helfen?");
    return parts.join(" ");
  }

  const api = { greetingFor, formatRemaining, buildStartupReport };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisStatus = api;
})(typeof window !== "undefined" ? window : this);
