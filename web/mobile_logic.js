// Handy-Version: reine Funktionen ohne Seite (mit Node pruefbar). Das Wischen und Zeichnen steht in mobile.js.
(function (root) {
  "use strict";

  // Die Seiten von links nach rechts. Von rechts hineinwischen (Finger nach links) = naechste Seite.
  const PAGES = [
    { id: "start", title: "Start" },
    { id: "jarvis", title: "Jarvis" },
    { id: "fenster", title: "Fenster" },
  ];

  const clampPage = (index, count) => {
    const n = Number.isFinite(count) && count > 0 ? Math.floor(count) : PAGES.length;
    const i = Number.isFinite(index) ? Math.round(index) : 0;
    return Math.min(n - 1, Math.max(0, i));
  };

  // Welche Seite gerade vorne ist, aus der Scroll-Position (Breite einer Seite = Breite des Fensters)
  const pageFromScroll = (scrollLeft, width, count) => (width > 0 ? clampPage(scrollLeft / width, count) : 0);

  // "#jarvis" -> 1, alles Unbekannte -> 0 (Start)
  const pageFromHash = (hash) => {
    const name = String(hash || "").replace(/^#/, "").toLowerCase();
    const index = PAGES.findIndex((p) => p.id === name);
    return index < 0 ? 0 : index;
  };

  const hashFor = (index) => "#" + PAGES[clampPage(index, PAGES.length)].id;

  // Gibt es rechts noch eine Seite? (dann zeigt der Rand einen Schimmer)
  const hasNext = (index) => clampPage(index, PAGES.length) < PAGES.length - 1;

  // Auf der Startseite stehen Tagesziele und Kalender (wenn eingeschaltet), alle anderen Fenster auf der Fenster-Seite.
  const START_WINDOWS = ["goals", "calendar"];
  function splitWindows(enabled) {
    const list = Array.isArray(enabled) ? enabled : [];
    return {
      start: START_WINDOWS.filter((id) => list.includes(id)),
      list: list.filter((id) => !START_WINDOWS.includes(id)),
    };
  }

  const api = { START_WINDOWS, splitWindows, PAGES, clampPage, pageFromScroll, pageFromHash, hashFor, hasNext };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MobileLogic = api;
})(typeof window !== "undefined" ? window : globalThis);