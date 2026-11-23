"use strict";
// app_owner.js: NUR BESITZER: Einstellungs-Dialog, Aktionsprotokoll, Ordner, Remote-Verwaltung, Gedaechtnis, "Alle Erinnerungen loeschen". Gaeste laden diese Datei nie.
const settingsDialog = byId("settings");
const settingsNav = byId("settings-nav");
const settingsTitle = byId("settings-title");
const settingsDesc = byId("settings-desc");
const settingsRows = byId("settings-rows");
const settingsError = byId("settings-error");

// live: true = wirkt wirklich und ist aenderbar. Alles andere ist (wie in der
// bisherigen Oberflaeche) sichtbar, aber ausgegraut, bis es funktioniert.
const PAGES = [
  {
    key: "Appearance", icon: "🎨", desc: "Visual settings for the J.A.R.V.I.S. interface.",
    rows: [
      { label: "Theme", category: "appearance", key: "theme", type: "select", options: ["Dark", "Light", "System"], live: true },
      { label: "Accent color", category: "appearance", key: "accent_color", type: "select", options: ["J.A.R.V.I.S. Blue", "British Racing Green"], live: true },
      { label: "Font size", category: "appearance", key: "font_size", type: "number", min: 11, max: 20, suffix: " px", live: true },
    ],
  },
  {
    key: "J.A.R.V.I.S.", icon: "🤖", desc: "How J.A.R.V.I.S. addresses you.",
    rows: [
      { label: "Address", category: "jarvis", key: "address", type: "text", live: true, maxLength: 30,
        note: "Gilt für Antworten und feste Meldungen, z. B. „Sir“. Ein Wort oder Name, höchstens 30 Zeichen." },
      { label: "Home place", category: "jarvis", key: "home_place", type: "text", live: true, maxLength: 60,
        note: "Für „Wie wird das Wetter?“ ohne Ortsangabe und für den Wetter-Satz beim Start. Der Ortsname geht an open-meteo.com. Leer lassen: kein Wetter beim Start." },
    ],
  },
  {
    key: "Memory", icon: "🧠", desc: "Long-term memory and stored information.",
    rows: [
      { label: "Memory enabled", category: "memory", key: "enabled", type: "toggle", live: true,
        note: "Aus: J.A.R.V.I.S. lernt nichts Neues und nutzt nichts Gespeichertes." },
      { type: "memory-list", live: true },
    ],
  },
  {
    key: "Voice", icon: "🎤", desc: "Antworten vorlesen lassen und per Sprache schreiben. Beides ist standardmäßig aus.",
    rows: [
      { label: "Read answers aloud", category: "voice", key: "output", type: "toggle", live: true,
        note: "J.A.R.V.I.S. liest seine Antworten und Timer-Meldungen vor. Eine neue Nachricht oder das Mikrofon unterbricht das Vorlesen." },
      { label: "Voice engine", category: "voice", key: "engine", type: "select", options: ["OpenAI", "Browser"], live: true,
        note: "OpenAI: natürlichere Stimme, spricht Deutsch und Englisch je nach Text. Der Antworttext geht dafür an OpenAI und kostet ein paar Cent. Browser: kostenlos, klingt einfacher." },
      { label: "Voice", category: "voice", key: "voice", type: "select",
        options: ["Onyx (male)", "Echo (male)", "Ash (male)", "Nova (female)", "Shimmer (female)", "Coral (female)"], live: true,
        note: "Gilt für die OpenAI-Engine." },
      { label: "Speech speed", category: "voice", key: "speed", type: "select", options: ["Slow", "Normal", "Fast"], live: true },
      { type: "voice-test", live: true },
      { label: "Voice input", category: "voice", key: "input", type: "toggle", live: true,
        note: "Zeigt neben „Senden“ einen Mikrofon-Knopf: gedrückt halten, sprechen, loslassen. Der Browser erkennt die Sprache; bei Chrome und Edge geschieht das über einen Online-Dienst des Browser-Herstellers." },
      { label: "Input language", category: "voice", key: "input_language", type: "select", options: ["German", "English"], live: true,
        note: "In dieser Sprache hört das Mikrofon zu." },
      { label: "Wake word “Jarvis”", category: "voice", key: "wake_word", type: "toggle", live: true,
        note: "Sag „Jarvis“, gefolgt von deinem Befehl („Jarvis, stelle einen Timer auf 10 Sekunden“) oder warte auf „Ja, Sir?“. Dafür hört der Browser dauerhaft zu, solange diese Seite offen ist; bei Chrome und Edge geht das Gehörte an einen Online-Dienst des Browser-Herstellers. Ein Hinweis oben zeigt, wann er zuhört. Die Aufnahme wird nicht gespeichert." },
    ],
  },
  {
    key: "Widgets", icon: "🧩", desc: "Die Seitenleiste rechts: fünf Felder, jedes einzeln wählbar. Bei „Off“ verschwindet das Feld. Die Leiste erscheint erst bei Fenstern ab etwa 1200 Pixel Breite.",
    rows: [
      { label: "Top widget", category: "widgets", key: "top", type: "select", options: ["Off", "Clock", "Date", "Calendar"], live: true },
      { label: "Middle widget", category: "widgets", key: "middle", type: "select", options: ["Off", "Notes", "Goals", "Lists"], live: true,
        note: "Notizen, Ziele, Listen und Kalender-Termine liegen in der Datei widgets.json auf deinem Rechner. Ziele gelten nur für den heutigen Tag, außer du markierst sie mit ↻ als täglich. Lists zeigt deine Einkaufs- und Packlisten (Jarvis setzt auf Zuruf Einträge darauf)." },
      { label: "Bottom widget", category: "widgets", key: "bottom", type: "select", options: ["Off", "Edmonton Oilers", "Adler Mannheim"], live: true,
        note: "Das laufende oder letzte Spiel und die nächsten (Oilers: vier, Mannheim: drei). Oilers: öffentliche NHL-Schnittstelle, mit Ergebnissen. Mannheim: offizielle Kalenderdatei der Adler, nur Paarungen und Termine, keine Ergebnisse. Nur der Server ruft sie auf, höchstens alle 5 Minuten." },
      { label: "Fourth widget", category: "widgets", key: "fourth", type: "select", options: ["Off", "PC Facts", "Performance", "Lists"], live: true,
        note: "PC Facts: System, Prozessor, Kerne, Arbeitsspeicher und Laufwerke. Performance: CPU, RAM, Laufwerk, Akku (falls vorhanden) und Netzwerk, alle 2 Sekunden. Beides liest nur dein Rechner, es geht nichts ins Internet." },
      { label: "Fifth widget", category: "widgets", key: "fifth", type: "select", options: ["Off", "PC Facts", "Performance", "Lists"], live: true },
    ],
  },
  {
    key: "Abilities", icon: "🛠", desc: "Was J.A.R.V.I.S. tun darf. Ausgeschaltete Fähigkeiten bietet er nicht an, führt sie nicht aus und sagt ehrlich, dass sie aus sind. Zeit, Datum, Rechnen und Systeminfo bleiben immer an.",
    rows: [
      { type: "abilities-list", live: true },
    ],
  },
  {
    key: "News", icon: "📰", desc: "Aus welchen Seiten J.A.R.V.I.S. Schlagzeilen holt, wenn du nach den News fragst. Es werden nur diese festen Seiten abgerufen; eigene Adressen kann man bewusst nicht eintragen. Die Fähigkeit selbst schaltest du unter Abilities.",
    rows: [
      { label: "Tagesschau", category: "news", key: "tagesschau", type: "toggle", live: true },
      { label: "heise online", category: "news", key: "heise", type: "toggle", live: true },
      { label: "Spiegel", category: "news", key: "spiegel", type: "toggle", live: true },
      { label: "Sportschau", category: "news", key: "sportschau", type: "toggle", live: true,
        note: "Sport allgemein, auch Eishockey (DEL). Mit „News zu Eishockey“ filtert J.A.R.V.I.S. danach." },
      { label: "ESPN NHL", category: "news", key: "espn_nhl", type: "toggle", live: true,
        note: "NHL-Meldungen auf Englisch, z. B. zu den Oilers." },
      { label: "Oilers Nation", category: "news", key: "oilersnation", type: "toggle", live: true,
        note: "Fan-Portal nur über die Edmonton Oilers, englisch." },
      { label: "Google News (Suche)", category: "news", key: "gnews", type: "toggle", live: true,
        note: "Sucht zu einem Thema in Google News („News zu Eishockey“). Nur mit Thema; das Stichwort geht dafür an Google. Findet fast alles. Die Links führen über Google; diese Artikel kann J.A.R.V.I.S. nicht selbst lesen, nur du im Browser." },
      { label: "Bing News (Suche)", category: "news", key: "bingnews", type: "toggle", live: true,
        note: "Wie die Google-Suche (nur mit Thema, das Stichwort geht an Bing), liefert aber direkte Links zu den Artikeln. Damit kann J.A.R.V.I.S. die Artikel auch selbst lesen und zusammenfassen." },
      { label: "BBC News", category: "news", key: "bbc", type: "toggle", live: true,
        note: "Englischsprachig. J.A.R.V.I.S. kann die Schlagzeilen auf Deutsch zusammenfassen." },
    ],
  },
  {
    key: "Alarm", icon: "⏰", desc: "Wecker und Timer läuten, bis du sie ausschaltest: mit „Jarvis, Wecker aus“ (Text oder Sprache), mit dem Knopf „Aus“ oder mit „Schlummern“. Läuft Jarvis nicht, wenn ein Wecker klingeln soll, meldet er das nur nachträglich.",
    rows: [
      { label: "Sound", category: "alarm", key: "sound", type: "select", options: ["Computer", "Browser", "Aus"], live: true,
        note: "Computer: der Ton kommt aus den Lautsprechern des Rechners, auf dem Jarvis läuft (nur Windows, auch bei geschlossenem Tab). Browser: der Ton kommt aus dem Tab, funktioniert nur bei offener Seite und erst nach einem Klick auf die Seite. Aus: nur Anzeige." },
      { label: "Ring for timers", category: "alarm", key: "ring_timers", type: "toggle", live: true,
        note: "Ein abgelaufener Timer läutet auch, bis du ihn ausschaltest. Aus: nur die Meldung wie bisher." },
      { label: "Ring at most (minutes)", category: "alarm", key: "max_minutes", type: "number", min: 1, max: 60, live: true,
        note: "Nach dieser Zeit geht das Läuten von selbst aus und Jarvis sagt es dir." },
      { label: "Snooze (minutes)", category: "alarm", key: "snooze_minutes", type: "number", min: 1, max: 60, live: true,
        note: "So lange schlummert ein Wecker oder Timer, bevor er wieder läutet." },
      { label: "Briefing when switched off", category: "alarm", key: "briefing", type: "toggle", live: true,
        note: "Neue Wecker lesen beim Ausschalten kurz Datum, Termine, Erinnerungen und (wenn die Wetter-Fähigkeit an ist) das Wetter vor. Beim Stellen kannst du es pro Wecker mit „ohne Briefing“ abwählen." },
    ],
  },
  {
    key: "Folders", icon: "📁", desc: "Ordner, aus denen J.A.R.V.I.S. Dateien lesen darf (Suchen, Lesen und Zusammenfassen folgen in den nächsten Schritten). Nur du trägst hier Ordner ein: Per Chat kann J.A.R.V.I.S. keinen freigeben, auch nicht auf Anweisung aus einem Dokument. Nicht erlaubt sind ganze Laufwerke, dein kompletter Benutzerordner, Systemordner und der Ordner von J.A.R.V.I.S. selbst. Schlüssel- und Zugangsdateien (.env, .ssh, *.pem, …) bleiben auch in freigegebenen Ordnern gesperrt.",
    rows: [
      { type: "folder-list", live: true },
    ],
  },
  {
    key: "Remote", icon: "📱", desc: "Zugriff vom Handy über Tailscale (privates Netz, nie öffentlich). Standardmäßig aus. Das Handy bekommt nur die Stufen, die du hier einschaltest, nie Programme, Dateien, Notizen oder Mail, und nie Rückfragen. Gekoppelte Geräte kannst du hier jederzeit sperren.",
    rows: [
      { label: "Remote enabled", category: "remote", key: "enabled", type: "toggle", live: true,
        note: "Aus: Der Remote-Name wird abgelehnt, auch von schon gekoppelten Geräten. Braucht JARVIS_REMOTE_HOST in der .env." },
      { label: "Auskunft", category: "remote", key: "info", type: "toggle", live: true,
        note: "Websuche, Wetter, News, Übersetzen, Wikipedia, Weltuhr, Umrechnen, Uhrzeit, Rechnen." },
      { label: "Alltag", category: "remote", key: "daily", type: "toggle", live: true,
        note: "Timer, Erinnerungen, Wecker, Briefing, Fokus, Kalender, Listen, Ziele, „Wecker aus“." },
      { label: "PC-Steuerung (harmlos)", category: "remote", key: "pc", type: "toggle", live: true,
        note: "Lautstärke, Musik steuern, PC-Status. Programme starten und Dateien öffnen gibt es nie über Remote." },
      { label: "Messages per 10 minutes", category: "remote", key: "max_messages", type: "number", min: 0, max: 1000, live: true,
        note: "Je Gerät. 0 = unbegrenzt." },
      { label: "AI calls per day", category: "remote", key: "max_ai_per_day", type: "number", min: 0, max: 100000, live: true,
        note: "Für alle Handys zusammen. 0 = unbegrenzt." },
      { type: "remote-panel", live: true },
    ],
  },
  {
    key: "Focus", icon: "🍅", desc: "Fokus-Sitzungen (Pomodoro): Fokusphasen und Pausen im Wechsel. Starte sie mit „Starte einen Pomodoro“ oder „Fokus für 50 Minuten mit 10 Minuten Pause“. Hier stehen die Werte, die gelten, wenn du keine Zahlen nennst. Bei jedem Wechsel kommt eine Meldung (und ein kurzer Ton, wenn unter Alarm der Sound „Computer“ eingestellt ist). Eine Sitzung ist nach einem Neustart von Jarvis weg.",
    rows: [
      { label: "Focus phase (minutes)", category: "focus", key: "work_minutes", type: "number", min: 1, max: 120, live: true },
      { label: "Break (minutes)", category: "focus", key: "break_minutes", type: "number", min: 1, max: 60, live: true },
      { label: "Long break (minutes)", category: "focus", key: "long_break_minutes", type: "number", min: 1, max: 60, live: true,
        note: "Nach jeder 4. Fokusphase, wenn noch weitere folgen." },
      { label: "Rounds", category: "focus", key: "rounds", type: "number", min: 1, max: 12, live: true },
    ],
  },
  {
    key: "Briefing", icon: "🗞️", desc: "Das Tagesbriefing nennt Datum, Termine, Erinnerungen, Wetter, deine Ziele, offene Timer und Schlagzeilen. Du bekommst es mit „Briefing“ oder „Was steht heute an?“. Wetter, Termine, Erinnerungen, Timer und News kommen nur dazu, wenn die jeweilige Fähigkeit unter Abilities an ist. Der Text wird ohne KI zusammengesetzt.",
    rows: [
      { label: "At first start of the day", category: "briefing", key: "auto", type: "toggle", live: true,
        note: "Das Briefing erscheint von selbst, wenn du Jarvis am Tag das erste Mal öffnest (nur einmal pro Tag, auch bei mehreren Tabs) und wird vorgelesen, sobald der Browser Ton erlaubt." },
      { label: "Include headlines", category: "briefing", key: "news", type: "toggle", live: true,
        note: "Hängt die drei neuesten Schlagzeilen aus deinen News-Quellen an. Dafür ruft Jarvis die News-Seiten ab; ohne Netz fehlt nur dieser Satz." },
    ],
  },
  {
    key: "Goals", icon: "🎯", desc: "Tagesziele mit Serie (🔥 = Tage in Folge erledigt) und Wochenleiste findest du im Ziele-Widget (Seitenleiste, Einstellung Widgets). Die Serie zählt nur tägliche Ziele (↻); ein ausgelassener Tag unterbricht sie. Du fragst Jarvis mit „Wie laufen meine Ziele?“.",
    rows: [
      { label: "Evening reminder", category: "goals", key: "evening", type: "toggle", live: true,
        note: "Ab der eingestellten Uhrzeit meldet sich Jarvis einmal am Tag im Chat, wenn noch Ziele offen sind, und nennt Serien, die sonst reißen. Das ist nur ein Hinweis: Jarvis hakt nichts ab und tut nichts von selbst. Die Seite muss dafür offen sein." },
      { label: "From (hour)", category: "goals", key: "evening_hour", type: "number", min: 17, max: 23, live: true,
        note: "Die Stunde, ab der die Abendfrage kommen darf (17 bis 23 Uhr)." },
    ],
  },
  {
    key: "Hints", icon: "💡", desc: "Jarvis meldet sich von selbst mit kurzen Hinweisen im Chat. Alles ist aus, bis du es einschaltest. Es ist immer nur eine Anzeige: Jarvis führt dabei nichts aus, öffnet nichts und ändert nichts. Die Seite muss offen sein. Abgelaufene Timer meldet schon der Ringer, Erinnerungen und Wecker melden sich selbst.",
    rows: [
      { label: "Appointment soon", category: "hints", key: "appointments", type: "toggle", live: true,
        note: "„In 30 Minuten: Zahnarzt um 14:30 Uhr.“ Aus deinem Kalender (auch Apple); nur Termine mit Uhrzeit, jeder einmal. Braucht die Fähigkeit Kalender-Termine." },
      { label: "Minutes before", category: "hints", key: "appointment_minutes", type: "number", min: 5, max: 120, live: true,
        note: "So viele Minuten vor dem Termin kommt der Hinweis." },
      { label: "Tomorrow's weather", category: "hints", key: "weather", type: "toggle", live: true,
        note: "Abends einmal das Wetter von morgen am Heimatort (Open-Meteo). Braucht die Fähigkeit Wetter und einen Heimatort." },
      { label: "Weather from (hour)", category: "hints", key: "weather_hour", type: "number", min: 15, max: 23, live: true,
        note: "Die Stunde, ab der der Wetterhinweis kommen darf (15 bis 23 Uhr)." },
      { label: "Serious PC problems", category: "hints", key: "pc", type: "toggle", live: true,
        note: "Jarvis meldet sich nur bei echten Problemen: ein Laufwerk meldet Fehler oder ist fast voll (unter 5 %, Windows-Laufwerk unter 10 %), der Arbeitsspeicher liegt 5 Minuten über 95 %, der Prozessor 10 Minuten über 95 % oder der Akku ist unter 10 % und nicht am Strom. Jede Art höchstens einmal pro Tag. Alles bleibt auf dem PC." },
    ],
  },
  {
    key: "Limits", icon: "💶", desc: "Tageslimits für kostenpflichtige Aufrufe an OpenAI. Ist ein Limit erreicht, geht nichts mehr raus, bis um Mitternacht der Zähler wieder bei 0 beginnt. 0 bedeutet kein Limit.",
    rows: [
      { label: "AI calls today", type: "readonly", live: true, text: () => usageText("ai") },
      { label: "Speech calls today", type: "readonly", live: true, text: () => usageText("speech") },
      { label: "AI calls per day", category: "limits", key: "ai_calls_per_day", type: "number", min: 0, max: 100000, live: true,
        note: "Jede Antwort braucht meist 2 bis 4 Aufrufe (Router, Antwort, Gedächtnis). Der Gastmodus hat einen eigenen Zähler." },
      { label: "Speech calls per day", category: "limits", key: "speech_calls_per_day", type: "number", min: 0, max: 100000, live: true,
        note: "Jedes vorgelesene Stück Text mit der OpenAI-Stimme. Die Browser-Stimme kostet nichts und zählt nicht." },
    ],
  },
  {
    key: "Activity", icon: "📋", desc: "Was J.A.R.V.I.S. getan hat: Aktionen, Rückfragen und Absagen. Nur zum Ansehen.",
    rows: [
      { type: "action-list", live: true },
    ],
  },
  {
    key: "About", icon: "ℹ", desc: "Information about this J.A.R.V.I.S. build.",
    rows: [
      { label: "Version", type: "readonly", live: true, text: () => about.version },
      { label: "System information", type: "readonly", live: true, text: () => about.system },
    ],
  },
];

function usageText(kind) {
  if (!usageInfo) return "–";
  const limit = usageInfo.limits && usageInfo.limits[kind];
  return usageInfo[kind] + " von " + (limit ? limit : "unbegrenzt");
}

async function saveSetting(row, value) {
  settingsError.hidden = true;

  try {
    applySettingsState(
      await api("POST", "/api/settings", { category: row.category, key: row.key, value })
    );
  } catch (error) {
    settingsError.textContent = error.message;
    settingsError.hidden = false;
    renderSettings();   // zeigt wieder den gespeicherten Wert
  }

  renderSettings();
}

function buildControl(row) {
  const stored = row.category ? (settings[row.category] || {})[row.key] : undefined;
  let control;

  if (row.type === "select") {
    control = document.createElement("select");
    row.options.forEach((option) => {
      const el = document.createElement("option");
      el.value = el.textContent = option;
      control.appendChild(el);
    });
    // Ein alter, nicht mehr gueltiger Wert (z.B. "Custom") zeigt die erste Option
    control.value = row.options.includes(stored) ? stored : row.options[0];
    control.addEventListener("change", () => saveSetting(row, control.value));
  } else if (row.type === "number") {
    control = document.createElement("input");
    control.type = "number";
    control.min = row.min;
    control.max = row.max;
    control.value = stored;
    control.title = row.suffix ? "in" + row.suffix : "";
    control.addEventListener("change", () => saveSetting(row, parseInt(control.value, 10)));
  } else if (row.type === "toggle") {
    control = document.createElement("input");
    control.type = "checkbox";
    control.checked = Boolean(stored);
    control.addEventListener("change", () => saveSetting(row, control.checked));
  } else {
    control = document.createElement("input");
    control.type = "text";
    control.readOnly = !(row.type === "text" && row.live);
    if (row.maxLength) control.maxLength = row.maxLength;
    if (row.type === "text" && row.live) {
      control.addEventListener("change", () => saveSetting(row, control.value.trim()));
    }
    control.value = row.type === "readonly"
      ? (typeof row.text === "function" ? row.text() : row.text)
      : (stored === undefined ? "" : stored);
  }

  control.className = "setting-control";
  control.disabled = !row.live;

  // Nur-Lese-Felder mit Inhalt (About) sollen lesbar bleiben
  if (row.type === "readonly" && row.live) {
    control.disabled = false;
  }

  return control;
}

// Liste der gespeicherten Erinnerungen (Settings > Memory).
// Alles wird mit textContent eingesetzt: Die Werte stammen aus Nachrichten und
// duerfen nie als HTML gelten.

// Aktionsprotokoll (Settings > Activity), nur lesen. Wieder nur textContent.
const DECISION_LABELS = {
  auto: "automatisch",
  confirmed: "von dir bestätigt",
  declined: "von dir abgelehnt",
  refused: "verboten",
  blocked: "blockiert",
};

const STATUS_LABELS = {
  COMPLETED: "ausgeführt",
  FAILED: "Fehler",
  BLOCKED: "nicht ausgeführt",
  DECLINED: "nicht ausgeführt",
};

function formatActionTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

// Probehoeren mit den aktuellen Einstellungen (auch wenn "Read answers aloud" aus ist)
function buildVoiceTest() {
  const box = el("div", "setting-row voice-test");
  box.append(
    el("span", "", "Try voice"),
    smallButton("Deutsch", "secondary", () =>
      voice.speak("Guten Tag, Sir. Alle Systeme laufen einwandfrei.", voiceSetting("speed"), voiceSetting("engine"))),
    smallButton("English", "secondary", () =>
      voice.speak("Good evening, sir. All systems are running smoothly.", voiceSetting("speed"), voiceSetting("engine"))),
    smallButton("Stop", "secondary", () => voice.stopSpeaking())
  );
  return box;
}

function buildActionList() {
  const box = el("div", "action-list");

  async function load() {
    try {
      render(await api("GET", "/api/actions"));
    } catch (error) {
      box.replaceChildren(el("p", "memory-empty", error.message), smallButton("Aktualisieren", "secondary", load));
    }
  }

  function render(data) {
    box.replaceChildren();

    const head = el("div", "memory-head");
    head.append(
      el("span", "memory-summary", data.actions.length === 0 ? "Noch keine Einträge" : "Letzte " + data.actions.length + " Einträge, neueste zuerst"),
      smallButton("Aktualisieren", "secondary", load)
    );
    box.appendChild(head);

    data.actions.forEach((entry) => {
      const item = el("div", "action-item action-" + entry.status.toLowerCase());
      const top = el("div", "memory-top");
      top.append(el("span", "memory-key", entry.goal), el("span", "memory-type", formatActionTime(entry.time)));
      item.appendChild(top);

      entry.details.forEach((detail) => item.appendChild(el("code", "action-detail", detail)));

      const decision = DECISION_LABELS[entry.decision] || entry.decision;
      const status = STATUS_LABELS[entry.status] || entry.status;
      item.appendChild(el("div", "action-state", decision + " · " + status));

      if (entry.summary) item.appendChild(el("div", "memory-value", entry.summary));
      box.appendChild(item);
    });
  }

  load();
  return box;
}

// Freigegebene Ordner (Step 2.14): Liste mit Entfernen und ein Feld zum Hinzufuegen (Pfad aus dem Explorer einfuegen)
function buildFolderList() {
  const box = el("div", "folder-list");
  const error = el("p", "dialog-error");
  error.hidden = true;

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
  }

  async function send(path, body) {
    try {
      render(await api("POST", path, body));
      return true;
    } catch (err) {
      showError(err.message);
      return false;
    }
  }

  function render(data) {
    showError("");
    box.replaceChildren();
    if (data.folders.length === 0) {
      box.appendChild(el("p", "memory-empty", "Noch kein Ordner freigegeben: J.A.R.V.I.S. liest keine Dateien."));
    }
    data.folders.forEach((folder) => {
      const item = el("div", "folder-item");
      const name = el("span", "folder-path", folder.path);
      name.title = folder.path;
      const remove = smallButton("Entfernen", "secondary danger-text", () => send("/api/folders/remove", { path: folder.path }));
      item.append(name, remove);
      if (!folder.exists) item.appendChild(el("span", "folder-missing", "gibt es nicht mehr"));
      box.appendChild(item);
    });
    const input = el("input", "folder-input");
    input.type = "text";
    input.placeholder = "Ordnerpfad, z. B. C:\\Users\\du\\Documents";
    input.maxLength = 400;
    input.setAttribute("aria-label", "Ordnerpfad");
    const add = smallButton("Hinzufügen", "", async () => {
      if (await send("/api/folders/add", { path: input.value })) return;
      input.focus();
    });
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); add.click(); } });
    const form = el("div", "folder-form");
    form.append(input, add);
    box.append(form, error, el("p", "setting-note", "Tipp: Im Explorer den Ordner öffnen, in die Adressleiste klicken und den Pfad kopieren. Höchstens " + data.max + " Ordner."));
  }

  api("GET", "/api/folders").then(render).catch((err) => box.replaceChildren(el("p", "memory-empty", err.message)));
  return box;
}

// Remote (R4): Status, Geraeteliste, Koppel-Link. Der Link steht nur hier und nur 5 Minuten, nie in der Liste.
let lastPairLink = null;    // { link, name, until } in Sekunden wie Date.now() / 1000

function buildRemotePanel() {
  const admin = window.JarvisRemoteAdmin;
  const box = el("div", "remote-panel");
  const error = el("p", "dialog-error");
  error.hidden = true;
  let linkTimer = null;

  function showError(message) {
    error.textContent = message;
    error.hidden = !message;
  }

  async function send(path, body) {
    try {
      const data = await api("POST", path, body);
      showError("");
      return data;
    } catch (err) {
      showError(err.message);
      return null;
    }
  }

  function stopTimer() {
    if (linkTimer !== null) window.clearInterval(linkTimer);
    linkTimer = null;
  }

  function renderLink(holder) {
    holder.replaceChildren();
    const view = admin.linkView(lastPairLink, Date.now() / 1000);
    if (!view) {
      lastPairLink = null;
      stopTimer();
      return;
    }
    const codeBox = el("p", "remote-code", view.code);        // gross und gut abtippbar
    const input = el("input", "folder-input");
    input.type = "text";
    input.readOnly = true;
    input.value = view.link;
    input.setAttribute("aria-label", "Koppel-Link für " + view.name);
    input.addEventListener("focus", () => input.select());
    const copy = smallButton("Kopieren", "", async () => {
      try {
        await navigator.clipboard.writeText(view.link);
        copy.textContent = "Kopiert";
      } catch (err) {
        input.select();
        copy.textContent = "Markiert: Strg+C";
      }
    });
    const form = el("div", "folder-form");
    form.append(input, copy);
    holder.append(
      el("p", "setting-label", "Code für „" + view.name + "“ (noch " + view.left + ")"),
      codeBox,
      form,
      el("p", "setting-note", view.note)
    );
  }

  // Gast-Bereiche (C1): eigener Bereich pro Gast mit Limits. Loeschen braucht zwei Klicks.
  function buildProfileSection(info) {
    const section = el("div", "remote-profiles");
    section.appendChild(el("p", "setting-label", "Gast-Bereiche"));
    section.appendChild(el("p", "setting-note", "Jeder Gast hat einen eigenen Bereich mit eigenen Erinnerungen, Listen, Zielen, Notizen und Unterhaltungen. 0 bedeutet unbegrenzt."));

    if ((info.profiles || []).length === 0) section.appendChild(el("p", "memory-empty", "Noch kein Gast-Bereich."));

    (info.profiles || []).forEach((profile) => {
      const view = admin.profileView(profile);
      const item = el("div", "remote-profile");
      item.appendChild(el("span", "remote-device-name", view.name));
      item.appendChild(el("span", "remote-device-state", view.devices + " · " + view.summary));

      const ai = el("input", "folder-input remote-limit");
      ai.type = "text";
      ai.inputMode = "numeric";
      ai.value = String(view.aiPerDay);
      ai.setAttribute("aria-label", "KI-Anfragen pro Tag für " + view.name);
      const rate = el("input", "folder-input remote-limit");
      rate.type = "text";
      rate.inputMode = "numeric";
      rate.value = String(view.perTenMin);
      rate.setAttribute("aria-label", "Nachrichten pro 10 Minuten für " + view.name);
      const save = smallButton("Limits speichern", "secondary", async () => {
        const aiValue = admin.parseLimit(ai.value);
        const rateValue = admin.parseLimit(rate.value);
        if (aiValue === null || rateValue === null) {
          showError("Limits sind ganze Zahlen von 0 bis 100000.");
          return;
        }
        const data = await send("/api/remote/profile_limits", { id: view.id, ai_per_day: aiValue, messages_per_10min: rateValue });
        if (data) render(data.state);
      });

      const resetUsage = smallButton("Zähler zurücksetzen", "secondary", async () => {
        const data = await send("/api/remote/profile_reset_usage", { id: view.id });
        if (data) render(data.state);
      });

      const makeTwoClick = (label, armedLabel, path) => {
        let armed = false;
        let timer = null;
        const button = smallButton(label, "secondary danger-text", async () => {
          if (!armed) {
            armed = true;
            button.textContent = armedLabel;
            timer = window.setTimeout(() => { armed = false; button.textContent = label; }, 4000);
            return;
          }
          window.clearTimeout(timer);
          const data = await send(path, { id: view.id });
          if (data) render(data.state);
        });
        return button;
      };

      const row = el("div", "folder-form");
      row.append(
        el("span", "setting-note", "KI/Tag"), ai, el("span", "setting-note", "Nachr./10 Min."), rate, save, resetUsage,
        makeTwoClick("Daten zurücksetzen", "Wirklich alles leeren?", "/api/remote/profile_reset"),
        makeTwoClick("Bereich löschen", "Wirklich löschen?", "/api/remote/profile_delete")
      );
      item.appendChild(row);
      section.appendChild(item);
    });

    const name = el("input", "folder-input");
    name.type = "text";
    name.placeholder = "Name des Gasts, z. B. Bruder";
    name.maxLength = 30;
    name.setAttribute("aria-label", "Name des neuen Gast-Bereichs");
    const add = smallButton("Gast-Bereich anlegen", "", async () => {
      const data = await send("/api/remote/profile_add", { name: name.value });
      if (data) render(data.state);
    });
    name.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); add.click(); } });
    const form = el("div", "folder-form");
    form.append(name, add);
    section.appendChild(form);
    return section;
  }

  function render(info) {
    stopTimer();
    box.replaceChildren();
    const now = Date.now() / 1000;

    const status = admin.statusView(info);
    box.appendChild(el("p", "remote-status " + status.tone, status.text));

    if (info.devices.length === 0) {
      box.appendChild(el("p", "memory-empty", "Noch kein Gerät gekoppelt."));
    }

    info.devices.forEach((device) => {
      const view = admin.deviceView(device, now);
      const item = el("div", "folder-item remote-device " + view.state);
      item.appendChild(el("span", "remote-device-name", view.area ? view.name + " (Gast: " + view.area + ")" : view.name));
      item.appendChild(el("span", "remote-device-state", view.label + " · " + view.seen));
      if (view.canRevoke) {
        item.appendChild(smallButton("Sperren", "secondary danger-text", async () => {
          const data = await send("/api/remote/revoke", { id: device.id });
          if (data) render(data.state);
        }));
      } else {
        if (view.canRestore) {
          item.appendChild(smallButton("Entsperren", "secondary", async () => {
            const data = await send("/api/remote/restore", { id: device.id });
            if (data) render(data.state);
          }));
        }
        item.appendChild(smallButton("Entfernen", "secondary", async () => {
          const data = await send("/api/remote/forget", { id: device.id });
          if (data) render(data.state);
        }));
      }
      box.appendChild(item);
    });

    if (admin.canPair(info)) {
      const holder = el("div", "remote-link");
      const name = el("input", "folder-input");
      name.type = "text";
      name.placeholder = "Name des Geräts, z. B. iPhone Moritz";
      name.maxLength = 40;
      name.setAttribute("aria-label", "Name des Geräts");
      const target = el("select", "folder-input");
      target.setAttribute("aria-label", "Für wen ist das Gerät");
      const mine = el("option", "", "Mein Gerät (voller Zugriff nach deinen Stufen)");
      mine.value = "owner";
      target.appendChild(mine);
      (info.profiles || []).forEach((profile) => {
        const option = el("option", "", "Gast: " + profile.name);
        option.value = profile.id;
        target.appendChild(option);
      });
      const make = smallButton("Koppel-Code erzeugen", "", async () => {
        const data = await send("/api/remote/pair_link", { name: name.value, profile: target.value });
        if (!data) {
          name.focus();
          return;
        }
        lastPairLink = { link: data.link, code: data.code, name: data.name, until: Date.now() / 1000 + data.expires_in };
        render(data.state);
      });
      name.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); make.click(); } });
      const form = el("div", "folder-form");
      form.append(name, make);
      box.append(form);
      if ((info.profiles || []).length > 0) box.appendChild(target);
      box.appendChild(holder);

      renderLink(holder);
      if (lastPairLink) linkTimer = window.setInterval(() => (holder.isConnected ? renderLink(holder) : stopTimer()), 1000);
    }

    if (info.available) box.appendChild(buildProfileSection(info));

    if (info.devices.some((device) => !device.revoked)) {
      let armed = false;
      let timer = null;
      const all = smallButton("Alle Geräte sperren", "secondary danger-text", async () => {
        if (!armed) {
          armed = true;
          all.textContent = "Wirklich alle sperren?";
          timer = window.setTimeout(() => { armed = false; all.textContent = "Alle Geräte sperren"; }, 4000);
          return;
        }
        window.clearTimeout(timer);
        const data = await send("/api/remote/revoke_all", {});
        if (data) {
          lastPairLink = null;
          render(data.state);
        }
      });
      box.appendChild(all);
    }

    box.appendChild(error);
  }

  api("GET", "/api/remote/state").then(render).catch((err) => box.replaceChildren(el("p", "memory-empty", err.message)));
  return box;
}

function buildMemoryList() {
  const box = el("div", "memory-list");

  function showError(message) {
    box.replaceChildren(el("p", "memory-empty", message), smallButton("Aktualisieren", "secondary", load));
  }

  async function load() {
    try {
      render(await api("GET", "/api/memories"));
    } catch (error) {
      showError(error.message);
    }
  }

  function render(data) {
    box.replaceChildren();

    const count = data.memories.length;
    const head = el("div", "memory-head");
    head.append(
      el("span", "memory-summary", count === 1 ? "1 gespeicherte Information" : count + " gespeicherte Informationen"),
      smallButton("Aktualisieren", "secondary", load)
    );
    box.appendChild(head);

    if (!data.enabled) {
      box.appendChild(el("p", "memory-empty", "Memory ist ausgeschaltet: Diese Einträge werden gerade nicht benutzt."));
    }

    if (count === 0) {
      box.appendChild(el("p", "memory-empty", "Noch nichts gespeichert."));
    }

    data.memories.forEach((memory) => box.appendChild(buildMemoryItem(memory, data)));

    box.appendChild(buildDangerZone(data));
  }

  function buildMemoryItem(memory, data) {
    const item = el("div", "memory-item");

    const top = el("div", "memory-top");
    top.append(el("span", "memory-key", memory.key), el("span", "memory-type", memory.type));

    const actions = el("div", "memory-actions");
    actions.append(
      smallButton("Bearbeiten", "secondary", () => startEdit(item, memory, data)),
      smallButton("Löschen", "secondary danger-text", () => askDelete(memory))
    );

    item.append(top, el("div", "memory-value", memory.value), actions);
    return item;
  }

  function startEdit(item, memory, data) {
    const area = el("textarea", "memory-edit");
    area.value = memory.value;
    area.maxLength = data.max_value_length;
    area.rows = 3;

    const type = el("select", "memory-edit-type");
    ["fact", "preference"].forEach((name) => {
      const option = el("option", "", name);
      option.value = name;
      type.appendChild(option);
    });
    type.value = memory.type;

    const error = el("p", "dialog-error");
    error.hidden = true;

    const save = smallButton("Speichern", "", async () => {
      save.disabled = true;
      error.hidden = true;
      try {
        render(await api("POST", "/api/memory/update", {
          key: memory.key, value: area.value.trim(), type: type.value,
        }));
      } catch (problem) {
        error.textContent = problem.message;
        error.hidden = false;
        save.disabled = false;
      }
    });

    const actions = el("div", "memory-actions");
    actions.append(type, smallButton("Abbrechen", "secondary", () => render(data)), save);

    const top = el("div", "memory-top");
    top.appendChild(el("span", "memory-key", memory.key));

    item.replaceChildren(top, area, error, actions);
    area.focus();
  }

  function askDelete(memory) {
    openDialog({
      title: "Erinnerung löschen?",
      text: "„" + memory.key + "“ = „" + memory.value + "“ wird dauerhaft gelöscht. "
        + "J.A.R.V.I.S. kennt diese Information danach nicht mehr.",
      okLabel: "Löschen",
      danger: true,
      onSubmit: async () => {
        render(await api("POST", "/api/memory/delete", { key: memory.key, confirm: true }));
      },
    });
  }

  function buildDangerZone(data) {
    const zone = el("div", "danger-zone");
    const text = el("div");
    text.append(
      el("span", "setting-label", "Alle Erinnerungen löschen"),
      el("span", "setting-note", "Nicht rückgängig zu machen. Dafür gibt es mehrere Sicherungen.")
    );
    const button = smallButton("Alle löschen …", "secondary danger-text", () => askDeleteAll(data));
    button.disabled = data.memories.length === 0;
    zone.append(text, button);
    return zone;
  }

  // Mehrere Huerden, mit Absicht: Haken setzen, den Satz selbst eintippen
  // (Einfuegen ist gesperrt) und 5 Sekunden warten.
  function askDeleteAll(data) {
    const count = data.memories.length;
    const phrase = data.delete_all_phrase;
    const WAIT_MS = 5000;

    dangerText.textContent = "Das löscht alle " + count + " gespeicherten Informationen dauerhaft. "
      + "Es gibt keine Sicherung und kein Zurück. J.A.R.V.I.S. kennt dich danach nicht mehr.";
    dangerPhrase.textContent = phrase;
    dangerCheck.checked = false;
    dangerInput.value = "";
    dangerError.hidden = true;
    dangerOk.disabled = true;

    const readyAt = Date.now() + WAIT_MS;

    function update() {
      const left = Math.ceil((readyAt - Date.now()) / 1000);
      const ready = dangerCheck.checked && dangerInput.value === phrase && left <= 0;
      dangerOk.disabled = !ready;
      dangerOk.textContent = left > 0 ? "Alles löschen (" + left + ")" : "Alles löschen";
    }

    update();
    dangerTimer = setInterval(update, 250);
    dangerSubmit = async () => {
      render(await api("POST", "/api/memory/delete_all", { confirm_text: dangerInput.value, count }));
    };
    dangerUpdate = update;
    dangerDialog.showModal();
    dangerInput.value = "";
  }

  load();
  return box;
}

// Dialog "Alle Erinnerungen löschen"
const dangerDialog = byId("memory-danger");
const dangerText = byId("danger-text");
const dangerPhrase = byId("danger-phrase");
const dangerCheck = byId("danger-check");
const dangerInput = byId("danger-input");
const dangerError = byId("danger-error");
const dangerOk = byId("danger-ok");
let dangerTimer = null;
let dangerSubmit = null;
let dangerUpdate = () => {};

dangerCheck.addEventListener("change", () => dangerUpdate());
dangerInput.addEventListener("input", () => dangerUpdate());
dangerInput.addEventListener("paste", (event) => event.preventDefault());
dangerInput.addEventListener("drop", (event) => event.preventDefault());
byId("danger-cancel").addEventListener("click", () => dangerDialog.close());
dangerDialog.addEventListener("close", () => {
  clearInterval(dangerTimer);
  dangerInput.value = "";
  dangerCheck.checked = false;
  dangerSubmit = null;
  dangerUpdate = () => {};
});
byId("danger-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  if (dangerOk.disabled || !dangerSubmit) return;

  dangerOk.disabled = true;
  try {
    await dangerSubmit();
    dangerDialog.close();
  } catch (error) {
    dangerError.textContent = error.message;
    dangerError.hidden = false;
    dangerUpdate();
  }
});

function renderSettings() {
  settingsNav.replaceChildren();

  PAGES.forEach((page) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = page.icon + "  " + page.key;
    if (page.key === currentPage) button.className = "current";
    button.addEventListener("click", () => {
      currentPage = page.key;
      settingsError.hidden = true;
      renderSettings();
    });
    settingsNav.appendChild(button);
  });

  const page = PAGES.find((p) => p.key === currentPage);
  settingsTitle.textContent = page.key;
  settingsDesc.textContent = page.desc;
  settingsRows.replaceChildren();

  // Die Liste der Faehigkeiten kommt vom Server (abilities.py), nicht fest im Code
  const rows = page.rows.flatMap((row) => row.type !== "abilities-list" ? [row] : abilitiesInfo.map((ability) => ({
    label: ability.label, category: "abilities", key: ability.id, type: "toggle", live: true, note: ability.description,
  })));

  rows.forEach((row) => {
    if (row.type === "action-list") {
      settingsRows.appendChild(buildActionList());
      return;
    }

    if (row.type === "voice-test") {
      settingsRows.appendChild(buildVoiceTest());
      return;
    }

    if (row.type === "memory-list") {
      settingsRows.appendChild(buildMemoryList());
      return;
    }

    if (row.type === "folder-list") {
      settingsRows.appendChild(buildFolderList());
      return;
    }

    if (row.type === "remote-panel") {
      settingsRows.appendChild(buildRemotePanel());
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "setting-row" + (row.live ? "" : " unavailable");

    const text = document.createElement("div");
    const label = document.createElement("span");
    label.className = "setting-label";
    label.textContent = row.label;
    text.appendChild(label);

    if (!row.live) {
      const note = document.createElement("span");
      note.className = "setting-note";
      note.textContent = "Not available yet";
      text.appendChild(note);
    } else if (row.note) {
      const note = document.createElement("span");
      note.className = "setting-note";
      note.textContent = row.note;
      text.appendChild(note);
    }

    wrapper.appendChild(text);
    wrapper.appendChild(buildControl(row));
    settingsRows.appendChild(wrapper);
  });
}

byId("open-settings").addEventListener("click", async () => {
  layout.classList.remove("sidebar-open");
  await loadSettings();
  renderSettings();
  settingsDialog.showModal();
});
byId("settings-close").addEventListener("click", () => settingsDialog.close());