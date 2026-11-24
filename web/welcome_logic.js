// Willkommensseite: reine Funktionen ohne Seite (mit Node pruefbar). Das Zeichnen steht in welcome.js, welcome_panels.js, welcome_dialogs.js.
(function (root) {
  "use strict";

  // Alle Fenster, die es gibt oder geben koennte. Reihenfolge = Reihenfolge auf der Seite (erst links, dann rechts).
  //   built   = Fenster ist gebaut, kann an/aus geschaltet werden
  //   ability = Jarvis kann es schon (Fenster dafuer fehlt noch)
  //   none    = Jarvis kann es noch nicht
  const WINDOWS = [
    { id: "goals", title: "Tagesziele", desc: "Haken, Serie, Woche", state: "built" },
    { id: "gym", title: "Gym", desc: "Training heute, Ziele, Ergebnis eintragen", state: "built" },
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
    { id: "pclage", title: "PC-Lage", desc: "Ampel, Hinweise, größte Verbraucher", state: "built" },
    { id: "drives", title: "Laufwerke", desc: "SSD und HDD: Platz, Gesundheit, Last", state: "built" },
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

  // Auch ueber die Server-Adresse (Tailscale) ist der Besitzer "am PC": Der Server sagt es mit /api/settings.
  // Eingeschraenkte Geraete (Handy) bekommen dort "remote: true". Ohne gueltige Antwort gilt der Rechnername.
  const isOwnerSettings = (data) => Boolean(data) && typeof data === "object" && !Array.isArray(data) && data.remote !== true;

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

  // ---- Wetter: Symbole (Linien-Zeichnungen auf 24x24, die Seite baut daraus ein SVG), Tage, Temperaturbalken
  const CLOUD = "M7 15a3.6 3.6 0 0 1-.4-7.18A5 5 0 0 1 16.3 6.9 3.8 3.8 0 0 1 16.5 15H7z";
  const WEATHER_ICONS = {
    clear: [["circle", { cx: 12, cy: 12, r: 4 }], ["path", { d: "M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" }]],
    partly: [["circle", { cx: 8, cy: 8, r: 2.8 }], ["path", { d: "M8 2.5v1.2M2.5 8h1.2M4.1 4.1l.9.9M11.9 4.1l-.9.9M4.1 11.9l.9-.9" }],
             ["path", { d: "M9 19.5a3.4 3.4 0 0 1-.3-6.8 4.6 4.6 0 0 1 8.9 1A3.4 3.4 0 0 1 17.5 19.5H9z" }]],
    cloudy: [["path", { d: "M7 18a4 4 0 0 1-.5-7.97A5.5 5.5 0 0 1 17.2 9.6 4.2 4.2 0 0 1 17 18H7z" }]],
    fog: [["path", { d: "M4 8h16M6 12h12M4 16h16M8 20h8" }]],
    rain: [["path", { d: CLOUD }], ["path", { d: "M8 18l-1 3M12 18l-1 3M16 18l-1 3" }]],
    snow: [["path", { d: CLOUD }], ["path", { d: "M8 18v3M6.5 19.5h3M16 18v3M14.5 19.5h3M12 20.2h.01" }]],
    thunder: [["path", { d: CLOUD }], ["path", { d: "M12.5 15.5l-2.5 3.5h3.5l-2 3" }]],
  };
  const isWeatherIcon = (key) => typeof key === "string" && Object.prototype.hasOwnProperty.call(WEATHER_ICONS, key);

  const num = (value) => (typeof value === "number" && isFinite(value) ? value : null);
  const degrees = (value) => (num(value) === null ? "–" : Math.round(value) + "°");
  const celsius = (value) => (num(value) === null ? "–" : Math.round(value) + " °C");
  // "2° bis 6°", mit nur einem Wert der eine, ohne beide ein Strich
  function tempRange(day) {
    const d = day || {};
    if (num(d.low) === null && num(d.high) === null) return "–";
    if (num(d.low) === null || num(d.high) === null) return degrees(num(d.high) === null ? d.low : d.high);
    return degrees(d.low) + " bis " + degrees(d.high);
  }
  // "Växjö, Kronoberg, Schweden" -> "Växjö"
  const shortPlace = (label) => String(label || "").split(",")[0].trim();
  const rainText = (percent) => (num(percent) === null ? "" : Math.round(percent) + " %");

  // "2026-11-22" -> { label: "Heute" | "Morgen" | "Mo", date: "22.11." } im Vergleich zum Datum hier
  function forecastDay(dateText, now) {
    const text = String(dateText || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return { label: text, date: "" };
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(Number(text.slice(0, 4)), Number(text.slice(5, 7)) - 1, Number(text.slice(8, 10)));
    const diff = Math.round((target - start) / 86400000);
    const names = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
    return { label: diff === 0 ? "Heute" : diff === 1 ? "Morgen" : names[target.getDay()], date: text.slice(8, 10) + "." + text.slice(5, 7) + "." };
  }

  // Lage des Temperaturbalkens eines Tages in der Woche: { left, width } in Prozent (mindestens 8 % breit)
  function barSpan(days, day) {
    const list = Array.isArray(days) ? days : [];
    const lows = list.map((d) => num(d && d.low)).filter((v) => v !== null);
    const highs = list.map((d) => num(d && d.high)).filter((v) => v !== null);
    const low = num(day && day.low);
    const high = num(day && day.high);
    if (!lows.length || !highs.length || low === null || high === null) return { left: 0, width: 0 };
    const min = Math.min.apply(null, lows);
    const max = Math.max.apply(null, highs);
    if (max <= min) return { left: 0, width: 100 };
    const width = Math.max(8, ((high - low) / (max - min)) * 100);
    const left = Math.min(100 - width, ((low - min) / (max - min)) * 100);
    return { left: Math.round(left * 10) / 10, width: Math.round(width * 10) / 10 };
  }

  // ---- PC-Lage: Ampel, Gesundheit, Programme (die Bewertung selbst rechnet der Server)
  // Farbstufe aus dem Wort des Servers; Unbekanntes gilt vorsichtshalber als "warn"
  const lightLevel = (level) => (["ok", "warn", "bad", "tip"].includes(level) ? level : "warn");
  const HEALTH_TEXT = { ok: "Gesund", warning: "Warnung", bad: "Defekt gemeldet", unknown: "Zustand unbekannt" };
  const healthText = (state) => (Object.prototype.hasOwnProperty.call(HEALTH_TEXT, state) ? HEALTH_TEXT[state] : HEALTH_TEXT.unknown);
  const healthLevel = (state) => (state === "ok" ? "ok" : state === "warning" ? "warn" : state === "bad" ? "bad" : "tip");
  const mediaLabel = (media) => (media === "SSD" || media === "HDD" ? media : "Laufwerk");
  // fmt = Zahl mit Dezimalkomma (widgets.js formatNumber)
  function programText(kind, p, fmt) {
    if (!p || typeof p.name !== "string") return "";
    const many = p.count > 1 ? " (" + p.count + "×)" : "";
    if (kind === "ram") return p.name + many + " · " + (p.mb >= 1024 ? fmt(p.mb / 1024, 1) + " GB" : Math.round(p.mb) + " MB");
    if (kind === "cpu") return p.name + many + " · " + Math.round(p.percent) + " %";
    if (kind === "disk") return p.name + many + " · " + fmt(p.mb_s, 1) + " MB/s";
    return "";
  }

  // ---- Gym: Zahlen aus Eingabefeldern und Texte (die Regeln "besser = neues Ziel" rechnet der Server)
  // Gewicht: "62,5" oder "62.5"; leer = 0 (Koerpergewicht); sonst null
  function parseWeight(text) {
    const t = String(text === undefined || text === null ? "" : text).trim().replace(",", ".");
    if (t === "") return 0;
    if (!/^\d{1,4}(\.\d{1,2})?$/.test(t)) return null;
    const n = Number(t);
    return n >= 0 && n <= 1000 ? n : null;
  }
  // Wiederholungen je Satz: "8 8 7", "8,8,7", "8/8/7" oder "3x8" (= 8 8 8); ungueltig = null
  function parseReps(text) {
    const t = String(text === undefined || text === null ? "" : text).trim().toLowerCase();
    const times = /^(\d{1,2})\s*[x×]\s*(\d{1,3})$/.exec(t);
    let reps;
    if (times) reps = new Array(Number(times[1])).fill(Number(times[2]));
    else if (/^\d{1,3}([\s,;/]+\d{1,3})*$/.test(t)) reps = t.split(/[\s,;/]+/).map(Number);
    else return null;
    return reps.length >= 1 && reps.length <= 20 && reps.every((r) => r >= 0 && r <= 100) ? reps : null;
  }
  const repsText = (reps) => (Array.isArray(reps) ? reps.join(" ") : "");
  const kgText = (weight) => (Number(weight) > 0 ? String(Number(weight)).replace(".", ",") + " kg" : "Körpergewicht");
  // Ziel einer Uebung: "60 kg · 3 × 8"
  const goalText = (e) => kgText(e.weight) + " · " + e.sets + " × " + e.reps;
  // Ein Ergebnis (Liste von Saetzen): gleiches Gewicht "62,5 kg · 8 8 7", sonst "100 kg × 6 · 96 kg × 8"
  function resultText(r) {
    const sets = r && Array.isArray(r.sets) ? r.sets : [];
    if (!sets.length) return "";
    if (sets.every((s) => s.weight === sets[0].weight)) return kgText(sets[0].weight) + " · " + sets.map((s) => s.reps).join(" ");
    return sets.map((s) => kgText(s.weight) + " × " + s.reps).join(" · ");
  }
  // Das ganze Ziel als Ergebnis (der Knopf "Wie Ziel"): so viele Saetze wie im Ziel
  const goalAsResult = (e) => ({ sets: Array.from({ length: e.sets }, () => ({ weight: e.weight, reps: e.reps })) });
  // Felder -> Saetze: rows = [{ weight: "100", reps: "6" }, ...]; { sets } oder { error }
  function parseSets(rows) {
    if (!Array.isArray(rows) || !rows.length) return { error: "Trage mindestens einen Satz ein." };
    if (rows.length > 20) return { error: "Höchstens 20 Sätze." };
    const sets = [];
    for (let i = 0; i < rows.length; i += 1) {
      const weight = parseWeight(rows[i].weight);
      const t = String(rows[i].reps === undefined || rows[i].reps === null ? "" : rows[i].reps).trim();
      if (weight === null) return { error: "Satz " + (i + 1) + ": Gewicht bitte als Zahl (z. B. 62,5), leer = Körpergewicht." };
      if (!/^\d{1,3}$/.test(t) || Number(t) > 100) return { error: "Satz " + (i + 1) + ": Wiederholungen bitte als ganze Zahl von 0 bis 100." };
      sets.push({ weight, reps: Number(t) });
    }
    return { sets };
  }

  const api = { parseWeight, parseReps, parseSets, repsText, kgText, goalText, resultText, goalAsResult, lightLevel, healthText, healthLevel, mediaLabel, programText, WEATHER_ICONS, isWeatherIcon, degrees, celsius, tempRange, shortPlace, rainText, forecastDay, barSpan, WINDOWS, STORAGE_KEY, CITIES_KEY, DEFAULT_ENABLED, CITIES, DEFAULT_CITIES, MAX_CITIES, normalizeCities, toggleCity, cityOf, cityTime, cityDayLabel, describeDue, COMPACT_FROM, CARD_TEXT, builtIds, normalizeEnabled, toggleWindow, splitColumns, isCompact, cardState,
                greetingWord, formatRemaining, dayKey, addDays, eventsOn, goalProgress, bestStreak, isLocalHost, isOwnerSettings };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WelcomeLogic = api;
})(typeof window !== "undefined" ? window : this);
