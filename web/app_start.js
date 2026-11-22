"use strict";
// app_start.js: Handy-Einstellungen, Meldungen im Hintergrund (Timer, Klingeln), Start. Gemeinsam fuer Besitzer und Gast.
// Handy-Einstellungen: nur Anzeige und Browser-Speicher, es geht nichts an den Server
const phonePrefsDialog = byId("phone-prefs");
const phonePrefsRows = byId("phone-prefs-rows");
const phonePrefsError = byId("phone-prefs-error");
const PHONE_LABELS = {
  Dark: "Dunkel", Light: "Hell", System: "Wie das Handy", "J.A.R.V.I.S. Blue": "Blau", "British Racing Green": "Grün",
  Off: "Aus", Clock: "Uhr", Date: "Datum", Calendar: "Kalender", Notes: "Notizen", Goals: "Ziele", Lists: "Listen",
};
const PHONE_SLOT_LABELS = { top: "Seitenleiste: Feld 1", middle: "Seitenleiste: Feld 2", fourth: "Seitenleiste: Feld 3", fifth: "Seitenleiste: Feld 4" };

function changePhonePref(change) {
  const prefs = window.JarvisRemotePrefs;
  phonePrefs = prefs.normalize(Object.assign({}, phonePrefs, change));
  phonePrefsError.hidden = prefs.save(localStorage, phonePrefs);
  phonePrefsError.textContent = "Der Speicher des Browsers ist gesperrt: Die Auswahl gilt nur, bis die Seite neu geladen wird.";
  mergePhonePrefs();
  applyAppearance();
  applyVoice();
  applyWidgets();
}

function phoneSelectRow(label, key, options, current, onChange) {
  const row = el("div", "phone-prefs-row");
  const id = "phone-pref-" + key;
  const lab = el("label", "", label);
  lab.htmlFor = id;
  const select = el("select");
  select.id = id;
  options.forEach((option) => {
    const item = el("option", "", PHONE_LABELS[option] || option);
    item.value = String(option);
    item.selected = String(option) === String(current);
    select.appendChild(item);
  });
  select.addEventListener("change", () => (onChange || ((value) => changePhonePref({ [key]: value })))(select.value));
  row.append(lab, select);
  return row;
}

function renderPhonePrefs() {
  const prefs = window.JarvisRemotePrefs;
  mergePhonePrefs();
  const shown = prefs.view(serverSettings, phonePrefs);
  phonePrefsRows.replaceChildren();
  phonePrefsRows.appendChild(phoneSelectRow("Design", "theme", prefs.THEMES, shown.theme));
  phonePrefsRows.appendChild(phoneSelectRow("Akzentfarbe", "accent_color", prefs.ACCENTS, shown.accent_color));

  const row = el("div", "phone-prefs-row phone-prefs-switch");
  const lab = el("label", "", "Antworten vorlesen");
  lab.htmlFor = "phone-pref-speech";
  const box = el("input");
  box.type = "checkbox";
  box.id = "phone-pref-speech";
  box.checked = shown.speech;
  box.addEventListener("change", () => changePhonePref({ speech: box.checked }));
  row.append(lab, box);
  phonePrefsRows.appendChild(row);

  phonePrefsRows.appendChild(phoneSelectRow("Schriftgröße (px)", "font_size", prefs.FONT_SIZES, shown.font_size,
    (value) => changePhonePref({ font_size: Number(value) })));
  Object.keys(prefs.SLOTS).forEach((slot) => {
    phonePrefsRows.appendChild(phoneSelectRow(PHONE_SLOT_LABELS[slot], "widget-" + slot, prefs.SLOTS[slot], shown.widgets[slot],
      (value) => changePhonePref({ widgets: Object.assign({}, phonePrefs.widgets || shown.widgets, { [slot]: value }) })));
  });

  const reset = smallButton("Alles wie am PC", "secondary", () => {
    phonePrefs = {};
    prefs.save(localStorage, phonePrefs);
    mergePhonePrefs();
    applyAppearance();
    applyVoice();
    applyWidgets();
    renderPhonePrefs();
  });
  phonePrefsRows.appendChild(reset);
  phonePrefsError.hidden = true;
}

byId("open-phone-prefs").addEventListener("click", () => {
  layout.classList.remove("sidebar-open");
  renderPhonePrefs();
  phonePrefsDialog.showModal();
});
byId("phone-prefs-close").addEventListener("click", () => phonePrefsDialog.close());

// ======================================================================
// Meldungen im Hintergrund (z.B. Timer)
// ======================================================================

// Jede Meldung hat eine Nummer. Jeder Tab merkt sich die letzte, die er kennt,
// und fragt nur nach neueren. So sehen alle offenen Tabs jede Meldung.
let lastBackgroundId = null;

async function pollBackground() {
  try {
    const query = lastBackgroundId === null ? "" : "?after=" + lastBackgroundId;
    const data = await api("GET", "/api/background" + query);
    lastBackgroundId = data.last;
    data.messages.forEach((item) => {
      addMessage("background", item.text, "HINTERGRUND");
      speakReply(item.text);
    });
    if (data.messages.length) refreshWidgets();      // z.B. eine Erinnerung verschwindet aus dem Kalender
    if (!busy && !ended) setStatus("ready", readyLabel());
  } catch (error) {
    if (!busy && !ended) setStatus("error", "OFFLINE");
  }
}

setInterval(pollBackground, 1000);

// ----------------------------------------------------------------------
// Live-Abgleich (R2b): was auf dem anderen Geraet (PC oder Handy) in dieser
// Konversation passiert, erscheint hier ohne Neuladen
// ----------------------------------------------------------------------

syncControl = window.JarvisSync.createSync({
  api: api,
  isHidden: () => document.hidden,
  // Nicht mitten in einer Antwort, bei offener Rueckfrage oder in der Gast-Version
  canApply: () => !guestMode && !busy && !ended && !document.querySelector(".confirm-row"),
  apply: (data) => {
    showHistory(data.messages);
    if (data.projects && data.active) applyState({ projects: data.projects, active: data.active });
    chat.scrollTop = chat.scrollHeight;
  },
});
syncControl.start({
  setInterval: (fn, ms) => window.setInterval(fn, ms),
  clearInterval: (id) => window.clearInterval(id),
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) syncControl.poll();
});

// ----------------------------------------------------------------------
// Laufende Timer (Step 6b): kleine Leiste ueber dem Eingabefeld
// ----------------------------------------------------------------------

const timersBar = byId("timers");
let shownTimerIds = "";

function renderTimers(timers) {
  timersBar.hidden = timers.length === 0;
  const ids = timers.map((t) => t.id).join(",");

  if (ids === shownTimerIds) {
    // gleiche Timer: nur die Zeit aktualisieren, damit Klicks nicht verloren gehen
    timers.forEach((t) => {
      const time = timersBar.querySelector('[data-time="' + t.id + '"]');
      if (time) time.textContent = window.JarvisStatus.formatRemaining(t.remaining);
    });
    return;
  }

  shownTimerIds = ids;
  timersBar.replaceChildren(...timers.map((t) => {
    const chip = el("span", "timer-chip");
    const time = el("span", "timer-time", window.JarvisStatus.formatRemaining(t.remaining));
    time.dataset.time = t.id;
    const cancel = el("button", "timer-cancel", "✕");
    cancel.type = "button";
    cancel.title = "Timer „" + t.name + "“ abbrechen";
    cancel.setAttribute("aria-label", cancel.title);
    cancel.addEventListener("click", async () => {
      cancel.disabled = true;
      try { await api("POST", "/api/timer/cancel", { id: t.id }); } catch (error) { /* naechste Runde zeigt den Stand */ }
      refreshTimers();
    });
    chip.append(el("span", "timer-name", t.name), time, cancel);
    return chip;
  }));
}

async function refreshTimers() {
  if (guestMode) return;
  try {
    renderTimers((await api("GET", "/api/timers")).timers);
  } catch (error) {
    /* Server nicht erreichbar: pollBackground zeigt OFFLINE */
  }
}

setInterval(refreshTimers, 1000);

// ----------------------------------------------------------------------
// Fokus-Sitzung (Step 2.13): eine Anzeige mit Phase, Runde, Restzeit und Abbrechen
// ----------------------------------------------------------------------

const focusBar = byId("focus");
let shownFocusKey = "";

function renderFocus(state) {
  if (!state || !state.active) {
    focusBar.hidden = true;
    focusBar.replaceChildren();
    shownFocusKey = "";
    return;
  }
  focusBar.hidden = false;
  const key = [state.phase, state.round, state.rounds, state.label].join("|");
  if (key === shownFocusKey) {
    const time = focusBar.querySelector("[data-focus-time]");
    if (time) time.textContent = window.JarvisStatus.formatRemaining(state.remaining);
    return;
  }
  shownFocusKey = key;
  const icon = state.phase === "work" ? "🍅 Fokus " : state.phase === "long_break" ? "☕ Lange Pause " : "☕ Pause ";
  const chip = el("span", "timer-chip focus-chip");
  const time = el("span", "timer-time", window.JarvisStatus.formatRemaining(state.remaining));
  time.dataset.focusTime = "1";
  const cancel = el("button", "timer-cancel", "✕");
  cancel.type = "button";
  cancel.title = "Fokus-Sitzung beenden";
  cancel.setAttribute("aria-label", cancel.title);
  cancel.addEventListener("click", async () => {
    cancel.disabled = true;
    try { await api("POST", "/api/focus/stop", {}); } catch (error) { /* naechste Runde zeigt den Stand */ }
    refreshFocus();
  });
  chip.append(el("span", "timer-name", icon + state.round + "/" + state.rounds + (state.label ? " · " + state.label : "")), time, cancel);
  focusBar.replaceChildren(chip);
}

async function refreshFocus() {
  if (guestMode) return;
  try {
    renderFocus(await api("GET", "/api/focus"));
  } catch (error) {
    /* Server nicht erreichbar: pollBackground zeigt OFFLINE */
  }
}

setInterval(refreshFocus, 1000);

// ----------------------------------------------------------------------
// Wecker und Timer laeuten (Step 2.11): Banner "Aus" / "Schlummern", Ton im Browser (web/alarm.js)
// ----------------------------------------------------------------------

const ringingBar = byId("ringing");
const ringingParts = {
  title: byId("ringing-title"),
  detail: byId("ringing-detail"),
  hint: byId("ringing-hint"),
  off: byId("ringing-off"),
  snooze: byId("ringing-snooze"),
};

const ringer = window.JarvisAlarm.createController({
  api: api,
  AudioContext: window.AudioContext || window.webkitAudioContext || null,
  setInterval: (fn, ms) => window.setInterval(fn, ms),
  clearInterval: (id) => window.clearInterval(id),
  getTitle: () => document.title,
  setTitle: (text) => { document.title = text; },
  say: (text) => { addMessage("jarvis", text); speakReply(text); },
  setBanner: (view) => {
    ringingBar.hidden = !view.show;
    ringingParts.title.textContent = view.title;
    ringingParts.detail.textContent = view.detail;
    ringingParts.hint.textContent = view.hint;
    ringingParts.hint.hidden = view.hint === "";
    ringingParts.snooze.textContent = view.snoozeLabel || "Schlummern";
  },
});

ringingParts.off.addEventListener("click", () => ringer.stop());
ringingParts.snooze.addEventListener("click", () => ringer.snooze());
// Der Browser erlaubt Ton erst nach einer Bedienung der Seite
["pointerdown", "keydown"].forEach((name) => document.addEventListener(name, () => ringer.unlock(), { passive: true }));

function pollRinging() {
  if (!guestMode) ringer.poll();
}

setInterval(pollRinging, 1000);

// ======================================================================
// Abendfrage zu offenen Zielen (Step 2.28): nur ein Hinweis im Chat, Jarvis tut nichts
// ======================================================================
async function checkEvening() {
  if (guestMode || remoteMode || !(settings.goals && settings.goals.evening)) return;
  try {
    const data = await api("POST", "/api/goals/evening", {});
    if (data.text) addMessage("jarvis", data.text);
  } catch (error) {
    /* ohne Abendfrage */
  }
}
setInterval(checkEvening, 5 * 60 * 1000);

// Proaktive Hinweise (Step 2.29): Termin bald, Wetter von morgen. Nur Anzeige, nichts wird ausgefuehrt.
async function checkHints() {
  const h = settings.hints;
  if (guestMode || remoteMode || !h || !(h.appointments || h.weather)) return;
  try {
    const data = await api("POST", "/api/hints", {});
    data.hints.forEach((hint) => addMessage("background", hint.text, "HINWEIS"));
  } catch (error) {
    /* ohne Hinweise */
  }
}
setInterval(checkHints, 60 * 1000);
setTimeout(checkEvening, 4000);        // kurz nach dem Start (Einstellungen sind dann geladen), sonst beim naechsten Takt

// ======================================================================
// Start
// ======================================================================

// Erst die Einstellungen laden, damit die Begruessung die richtige Anrede hat.
// Der Statusbericht nennt Tageszeit, Datum und laufende Timer (Step 6b).
async function showStartupReport() {
  if (guestMode) {
    addMessage("jarvis", GUEST_WELCOME);
    return;
  }

  // Briefing beim ersten Start des Tages: ersetzt dann die kurze Begruessung (Step 2.12)
  if (!remoteMode && settings.briefing && settings.briefing.auto) {
    try {
      const data = await api("POST", "/api/briefing/auto", {});
      if (data.text) {
        addMessage("jarvis", data.text);
        speakReply(data.text);
        return;
      }
    } catch (error) {
      /* ohne Briefing: normale Begruessung */
    }
  }

  let timers = [];
  try {
    timers = (await api("GET", "/api/timers")).timers;
  } catch (error) {
    /* ohne Timer-Angabe */
  }

  // Wetter am Heimatort: hoechstens 2,5 Sekunden warten, sonst ohne
  let weather = null;
  try {
    weather = (await Promise.race([
      api("GET", "/api/weather"),
      new Promise((resolve) => setTimeout(() => resolve({}), 2500)),
    ])).summary || null;
  } catch (error) {
    /* ohne Wetter */
  }

  addMessage("jarvis", window.JarvisStatus.buildStartupReport({
    address: (settings.jarvis && settings.jarvis.address) || "Sir",
    now: new Date(),
    timers,
    weather,
    memoryEnabled: settings.memory ? settings.memory.enabled : true,
  }));
}

const GUEST_WELCOME =
  "Willkommen im Gastmodus. Ich kann mich unterhalten, die Uhrzeit und das Datum nennen, " +
  "rechnen und im Web suchen. Auf diesem Rechner kann ich nichts tun.";

// ======================================================================
// Jarvis-Kern (Step 4B.5): Ringe in der Titelleiste, zeigen ruhig / zuhoeren / denken / sprechen / Fehler
// ======================================================================

const core = window.JarvisCore.create(document, "idle");
byId("core-slot").appendChild(core);

function refreshCore() {
  core.setAttribute("data-state", window.JarvisCore.resolveState({
    error: statusEl.dataset.state === "error",
    speaking: speakingNow,
    listening: micButton.classList.contains("listening"),
    thinking: statusEl.dataset.state === "busy",
  }));
}
new MutationObserver(refreshCore).observe(statusEl, { attributes: true, attributeFilter: ["data-state"] });
new MutationObserver(refreshCore).observe(micButton, { attributes: true, attributeFilter: ["class"] });

// Klick auf den Kern oder den Schriftzug: zurueck zur Willkommensseite (nur beim Besitzer; Gast und Gastmodus haben keine).
// Umschalt+Klick auf den Kern (beim Gast: schon ein Klick) schaltet die Bewegung an/aus. Die Wahl bleibt in diesem Browser gespeichert,
// ohne Wahl folgt die Seite der Systemeinstellung "Animationen reduzieren".
function hasStartPage() { return !guestMode && !document.body.classList.contains("tester"); }
function savedMotion() {
  try { return localStorage.getItem("jarvis.motion"); } catch (error) { return null; }
}
if (savedMotion() === "on" || savedMotion() === "off") document.documentElement.dataset.motion = savedMotion();
document.querySelector(".logo").addEventListener("click", () => { if (hasStartPage()) location.href = "/"; });
core.addEventListener("click", (event) => {
  if (hasStartPage() && !event.shiftKey) { location.href = "/"; return; }
  const now = window.JarvisCore.motionOn(savedMotion(), matchMedia("(prefers-reduced-motion: reduce)").matches);
  const next = now ? "off" : "on";
  document.documentElement.dataset.motion = next;
  try { localStorage.setItem("jarvis.motion", next); } catch (error) { /* ohne Speicher gilt es nur bis zum Neuladen */ }
});

// Hotkey der Desktop-App (Step 4B.4): kommt das Fenster nach vorn, steht der Cursor sofort im Eingabefeld.
window.addEventListener("focus", () => {
  const active = document.activeElement;
  if (!active || active === document.body) input.focus();
});

loadSettings().finally(() => { showStartupReport(); refreshTree(); refreshTimers(); refreshFocus(); });