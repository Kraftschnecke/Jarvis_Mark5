// Hilfen fuer die Seitenleisten-Widgets (Etappe C). Reine Funktionen ohne Seite,
// damit sie sich mit Node pruefen lassen. Das Zeichnen steht in app.js.
(function (root) {
  "use strict";

  const pad = (n) => String(n).padStart(2, "0");

  // "14:05:09" (24 Stunden)
  function formatClock(date) {
    return pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
  }

  // "Mittwoch, 21. Oktober 2026"
  function formatDateLong(date, locale) {
    return new Intl.DateTimeFormat(locale || "de-DE", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    }).format(date);
  }

  // "Oktober 2026"
  function monthTitle(year, month, locale) {
    return new Intl.DateTimeFormat(locale || "de-DE", { month: "long", year: "numeric" })
      .format(new Date(year, month, 1));
  }

  // Wochentage, Montag zuerst: ["Mo", "Di", ...]
  function weekdayNames(locale) {
    const format = new Intl.DateTimeFormat(locale || "de-DE", { weekday: "short" });
    const names = [];
    for (let day = 1; day <= 7; day++) names.push(format.format(new Date(2024, 0, day)).replace(".", ""));  // 1.1.2024 = Montag
    return names;
  }

  // Monatsraster, Montag zuerst: Liste von Wochen, jede mit 7 Eintraegen (Tag oder null)
  function calendarWeeks(year, month) {
    const first = (new Date(year, month, 1).getDay() + 6) % 7;     // 0 = Montag
    const days = new Date(year, month + 1, 0).getDate();
    const cells = Array(first).fill(null);
    for (let day = 1; day <= days; day++) cells.push(day);
    while (cells.length % 7 !== 0) cells.push(null);
    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
    return weeks;
  }

  // Ein Spiel fuer die Anzeige. game kommt vom Server (widgets.py).
  // { teamName, opponent, home, score: "3 : 1" | null, outcome: "win"|"loss"|null, when, live }
  function describeGame(game, options) {
    const opts = options || {};
    const mine = game.team_is_home ? game.home : game.away;
    const other = game.team_is_home ? game.away : game.home;
    const hasScore = Number.isInteger(game.home.score) && Number.isInteger(game.away.score);
    let outcome = null;
    if (game.state === "final" && hasScore && mine.score !== other.score) {
      outcome = mine.score > other.score ? "win" : "loss";
    }
    const start = new Date(game.start);
    const when = Number.isNaN(start.getTime()) ? "" : new Intl.DateTimeFormat(opts.locale || "de-DE", {
      weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit",
      timeZone: opts.timeZone,
    }).format(start);
    return {
      teamName: mine.name,
      opponent: other.name,
      home: game.team_is_home === true,
      // Immer Heimteam zuerst, so wie im Sport ueblich
      score: hasScore ? game.home.score + " : " + game.away.score : null,
      outcome,
      when,
      live: game.state === "live",
    };
  }

  // "2026-10-23" (so speichert der Server Tage)
  function dateKey(year, month, day) {
    return year + "-" + pad(month + 1) + "-" + pad(day);
  }

  // Termine nach Tag: { "2026-10-23": [termin, ...] }
  function eventsByDate(events) {
    const result = {};
    (Array.isArray(events) ? events : []).forEach((event) => {
      if (!event || typeof event.date !== "string") return;
      (result[event.date] = result[event.date] || []).push(event);
    });
    return result;
  }

  // "Freitag, 23. Oktober" fuer einen Tag im Format JJJJ-MM-TT
  function formatDayLong(key, locale) {
    const [year, month, day] = key.split("-").map(Number);
    return new Intl.DateTimeFormat(locale || "de-DE", { weekday: "long", day: "numeric", month: "long" })
      .format(new Date(year, month - 1, day));
  }

  // Zahl mit Dezimalkomma: 13.24 -> "13,2"
  function formatNumber(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "–";
    return number.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  // "13,2 GB"
  function formatGb(value) {
    return Number.isFinite(Number(value)) && value !== null ? formatNumber(value, 1) + " GB" : "–";
  }

  // Netzwerk-Tempo aus KB/s: "0 KB/s", "512 KB/s", "1,5 MB/s"
  function formatRate(kbPerSecond) {
    const kb = Number(kbPerSecond);
    if (!Number.isFinite(kb) || kb < 0) return "–";
    if (kb >= 1024) return formatNumber(kb / 1024, 1) + " MB/s";
    return formatNumber(Math.round(kb), 0) + " KB/s";
  }

  // Laufzeit: "5 Min", "3 Std 12 Min", "2 Tage 4 Std"
  function formatUptime(seconds) {
    const total = Number(seconds);
    if (seconds === null || seconds === undefined || !Number.isFinite(total) || total < 0) return "–";
    const minutes = Math.floor(total / 60);
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor((minutes % 1440) / 60);
    if (days > 0) return days + (days === 1 ? " Tag " : " Tage ") + hours + " Std";
    if (hours > 0) return hours + " Std " + (minutes % 60) + " Min";
    return minutes + " Min";
  }

  // Farbstufe eines Balkens: bis 70 % ok, bis 90 % warn, darueber high; ungueltig -> 0 %
  function loadLevel(percent) {
    const value = Number(percent);
    if (!Number.isFinite(value) || value < 70) return "ok";
    return value < 90 ? "warn" : "high";
  }

  function clampPercent(percent) {
    const value = Number(percent);
    return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
  }

  const api = { formatNumber, formatGb, formatRate, formatUptime, loadLevel, clampPercent, formatClock, formatDateLong, monthTitle, weekdayNames, calendarWeeks, describeGame,
                dateKey, eventsByDate, formatDayLong };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisWidgets = api;
})(typeof window !== "undefined" ? window : this);
