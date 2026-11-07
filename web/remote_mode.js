// Remote-Modus der Seite (Mark 5, Step R5): was am Handy anders ist als am PC. Nur Anzeige-Logik, kein HTML.
(function (root) {
  "use strict";

  // Diese Widgets fragen Adressen, die es ueber Remote nicht gibt (PC-Daten, Eishockey): sie bleiben am Handy aus
  const HIDDEN_WIDGETS = ["PC Facts", "Performance", "Edmonton Oilers", "Adler Mannheim"];
  const LEVEL_NAMES = { info: "Auskunft", daily: "Alltag", pc: "PC-Steuerung" };

  function widgetAllowed(name) {
    return HIDDEN_WIDGETS.indexOf(name) < 0;
  }

  // Der Streifen unter der Kopfzeile. info = Antwort von /api/remote/whoami
  function bannerView(info) {
    if (!info || info.remote !== true) return { show: false, title: "", detail: "" };
    const levels = info.levels || {};
    const names = Object.keys(LEVEL_NAMES).filter((key) => levels[key] === true).map((key) => LEVEL_NAMES[key]);
    const device = typeof info.device === "string" && info.device ? info.device : "";
    return {
      show: true,
      title: "Remote (eingeschränkt)",
      detail: [names.length ? names.join(", ") : "nur Unterhaltung", device].filter(Boolean).join(" · "),
    };
  }

  const api = { HIDDEN_WIDGETS, LEVEL_NAMES, widgetAllowed, bannerView };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisRemoteMode = api;
})(typeof window !== "undefined" ? window : this);