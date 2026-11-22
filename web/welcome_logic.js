// Willkommensseite: reine Funktionen ohne Seite (mit Node pruefbar). Das Zeichnen steht in welcome.js, welcome_panels.js, welcome_dialogs.js.
(function (root) {
  "use strict";

  // Alle Fenster, die es gibt oder geben koennte. Reihenfolge = Reihenfolge auf der Seite (erst links, dann rechts).
  //   built   = Fenster ist gebaut, kann an/aus geschaltet werden
  //   ability = Jarvis kann es schon (Fenster dafuer fehlt noch)
  //   none    = Jarvis kann es noch nicht
  const WINDOWS = [
    { id: "goals", title: "Tagesziele", desc: "Haken, Serie, Woche", state: "built" },
    { id: "focus", title: "Fokus & Timer", desc: "laufende Sitzung und Timer", state: "built" },
    { id: "lists", title: "Listen", desc: "Einkauf & Co. abhaken", state: "built" },
    { id: "calendar", title: "Kalender", desc: "Termine heute und morgen, Monat", state: "built" },
    { id: "weather", title: "Wetter", desc: "Heimatort, heute", state: "built" },
    { id: "notes", title: "Notizen", desc: "gemeinsame Notiz", state: "built" },
    { id: "news", title: "News", desc: "Schlagzeilen", state: "built" },
    { id: "briefing", title: "Briefing", desc: "Tagesbriefing", state: "built" },
    { id: "worldtime", title: "Weltuhr", desc: "Zeit in Städten", state: "built" },
    { id: "music", title: "Musik", desc: "Play/Pause, Lautstärke", state: "built" },
    { id: "system", title: "PC-Status", desc: "CPU, RAM, Akku", state: "built" },
    { id: "reminders", title: "Erinnerungen", desc: "die nächsten drei", state: "built" },
    { id: "history", title: "Befehls-Verlauf", desc: "letzte Befehle", state: "none" },
    { id: "cost", title: "Kosten heute", desc: "API-Verbrauch", state: "none" },
    { id: "custom", title: "Eigenes Fenster", desc: "Inhalt selbst wählen", state: "none" },
  ];

  const STORAGE_KEY = "jarvis.welcome.windows";
  const CITIES_KEY = "jarvis.welcome.cities";
  // Beim ersten Mal sind nur diese Fenster an; die anderen schaltet man in der Fenster-Verwaltung ein.
  const DEFAULT_ENABLED = ["goals", "focus", "lists", "calendar", "weather"];
  const COMPACT_FROM = 4;     // ab so vielen Fenstern in einer Spalte werden sie kleiner

  const builtIds = () => WINDOWS.filter((w) => w.state === "built").map((w) => w.id);

  // Gespeicherte Auswahl -> gueltige Liste: nur gebaute Fenster, ohne Doppelte, in Seiten-Reihenfolge.
  // Fehlt die Auswahl oder ist sie kaputt, gilt die Voreinstellung.
  function normalizeEnabled(value) {
    const built = builtIds();
    if (!Array.isArray(value)) return DEFAULT_ENABLED.slice();
    return built.filter((id) => value.includes(id));
  }

  function toggleWindow(enabled, id) {
    const built = builtIds();
    if (!built.includes(id)) return normalizeEnabled(enabled);
    const current = normalizeEnabled(enabled);
    return normalizeEnabled(current.includes(id) ? current.filter((x) => x !== id) : current.concat(id));
  }

  // Links bekommt bei ungerader Zahl eins mehr
  function splitColumns(enabled) {
    const list = normalizeEnabled(enabled);
    const left = Math.ceil(list.length / 2);
    return { left: list.slice(0, left), right: list.slice(left) };
  }

  const isCompact = (columnCount) => columnCount >= COMPACT_FROM;

  // Zustand einer Karte in der Fenster-Verwaltung: g = an, r = aus, y = Fenster fehlt, yd = keine Faehigkeit
  function cardState(def, enabled) {
    if (def.state === "built") return normalizeEnabled(enabled).includes(def.id) ? "g" : "r";
    return def.state === "ability" ? "y" : "yd";
  }

  const CARD_TEXT = {
    g: "Aktiv · wird angezeigt",
    r: "Aus · kein Fenster sichtbar",
    y: "Jarvis kann es · Fenster fehlt",
    yd: "Noch keine Jarvis-Fähigkeit",
  };

  function greetingWord(hour) {
    if (hour >= 5 && hour < 11) return "Guten Morgen";
    if (hour >= 11 && hour < 18) return "Guten Tag";
    return "Guten Abend";
  }

  const pad = (n) => String(n).padStart(2, "0");

  // 75 -> "01:15", 3725 -> "1:02:05"
  function formatRemaining(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h > 0 ? h + ":" + pad(m) + ":" + pad(s) : pad(m) + ":" + pad(s);
  }

  const dayKey = (date) => date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());

  function addDays(date, days) {
    const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
    return copy;
  }

  // Termine eines Tages, nach Uhrzeit (ohne Uhrzeit zuerst)
  function eventsOn(events, key) {
    return (Array.isArray(events) ? events : [])
      .filter((e) => e && e.date === key)
      .sort((a, b) => String(a.time || "").localeCompare(String(b.time || "")) || String(a.title).localeCompare(String(b.title)));
  }

  // Ziele: wie viele sind erledigt
  function goalProgress(goals) {
    const list = Array.isArray(goals) ? goals : [];
    const done = list.filter((g) => g && g.done).length;
    return { done, total: list.length, percent: list.length ? Math.round((done / list.length) * 100) : 0 };
  }

  // Serie: laengste aktuelle Serie der taeglichen Ziele (0, wenn keine)
  function bestStreak(goals) {
    return (Array.isArray(goals) ? goals : []).reduce((max, g) => Math.max(max, g && g.daily && g.streak > 0 ? g.streak : 0), 0);
  }

  // Nur diese Orte gelten als "am PC": dort darf man Termine eintragen (ueber Remote ist das gesperrt)
  const isLocalHost = (hostname) => hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";

  // ---- Weltuhr: Staedte zur Auswahl (Zeitzonen kennt der Browser selbst)
  const CITIES = [
    { id: "stockholm", name: "Stockholm", tz: "Europe/Stockholm" }, { id: "berlin", name: "Berlin", tz: "Europe/Berlin" },
    { id: "london", name: "London", tz: "Europe/London" }, { id: "reykjavik", name: "Reykjavik", tz: "Atlantic/Reykjavik" },
    { id: "athen", name: "Athen", tz: "Europe/Athens" }, { id: "moskau", name: "Moskau", tz: "Europe/Moscow" },
    { id: "kairo", name: "Kairo", tz: "Africa/Cairo" }, { id: "dubai", name: "Dubai", tz: "Asia/Dubai" },
    { id: "mumbai", name: "Mumbai", tz: "Asia/Kolkata" }, { id: "bangkok", name: "Bangkok", tz: "Asia/Bangkok" },
    { id: "peking", name: "Peking", tz: "Asia/Shanghai" }, { id: "tokio", name: "Tokio", tz: "Asia/Tokyo" },
    { id: "sydney", name: "Sydney", tz: "Australia/Sydney" }, { id: "auckland", name: "Auckland", tz: "Pacific/Auckland" },
    { id: "new-york", name: "New York", tz: "America/New_York" }, { id: "chicago", name: "Chicago", tz: "America/Chicago" },
    { id: "denver", name: "Denver", tz: "America/Denver" }, { id: "los-angeles", name: "Los Angeles", tz: "America/Los_Angeles" },
    { id: "mexiko-stadt", name: "Mexiko-Stadt", tz: "America/Mexico_City" }, { id: "sao-paulo", name: "São Paulo", tz: "America/Sao_Paulo" },
  ];
  const DEFAULT_CITIES = ["stockholm", "new-york", "tokio", "sydney"];
  const MAX_CITIES = 8;

  function normalizeCities(value) {
    if (!Array.isArray(value)) return DEFAULT_CITIES.slice();
    const known = new Set(CITIES.map((c) => c.id));
    const result = [];
    value.forEach((id) => { if (known.has(id) && !result.includes(id)) result.push(id); });
    return result.slice(0, MAX_CITIES);
  }

  function toggleCity(list, id) {
    const current = normalizeCities(list);
    if (!CITIES.some((c) => c.id === id)) return current;
    if (current.includes(id)) return current.filter((x) => x !== id);
    return current.length >= MAX_CITIES ? current : current.concat(id);
  }

  const cityOf = (id) => CITIES.find((c) => c.id === id) || null;

  // "14:05" in der Zeitzone; "heute" / "morgen" / "gestern" im Vergleich zum Datum hier
  function cityTime(date, tz) {
    return new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(date);
  }
  function cityDayLabel(date, tz) {
    const key = (zone) => new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: zone }).format(date);
    const there = key(tz);
    const here = key(undefined);
    if (there === here) return "heute";
    return there > here ? "morgen" : "gestern";
  }

  // ---- Erinnerungen: "2026-11-25T09:00" -> "heute 09:00", "morgen 09:00", "Mi 09:00" (bis 6 Tage), sonst "25.11. 09:00"
  function describeDue(due, now) {
    const text = String(due || "");
    const day = text.slice(0, 10);
    const time = text.slice(11, 16);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return text;
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10)));
    const diff = Math.round((target - start) / 86400000);
    let label;
    if (diff === 0) label = "heute";
    else if (diff === 1) label = "morgen";
    else if (diff === -1) label = "gestern";
    else if (diff > 1 && diff <= 6) label = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"][target.getDay()];
    else label = day.slice(8, 10) + "." + day.slice(5, 7) + ".";
    return time ? label + " " + time : label;
  }

  const api = { WINDOWS, STORAGE_KEY, CITIES_KEY, DEFAULT_ENABLED, CITIES, DEFAULT_CITIES, MAX_CITIES, normalizeCities, toggleCity, cityOf, cityTime, cityDayLabel, describeDue, COMPACT_FROM, CARD_TEXT, builtIds, normalizeEnabled, toggleWindow, splitColumns, isCompact, cardState,
                greetingWord, formatRemaining, dayKey, addDays, eventsOn, goalProgress, bestStreak, isLocalHost };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WelcomeLogic = api;
})(typeof window !== "undefined" ? window : this);