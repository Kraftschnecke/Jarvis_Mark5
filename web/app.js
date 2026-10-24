"use strict";

const layout = document.getElementById("layout");
const sidebar = document.getElementById("sidebar");
const tree = document.getElementById("tree");
const newConversationButton = document.getElementById("new-conversation");
const newProjectButton = document.getElementById("new-project");
const menuButton = document.getElementById("menu-button");
const menuEl = document.getElementById("menu");
const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendButton = document.getElementById("send");
const composer = document.getElementById("composer");
const statusEl = document.getElementById("status");

// Begruessung mit der eingestellten Anrede (Settings > J.A.R.V.I.S.)
function greeting() {
  const address = (settings.jarvis && settings.jarvis.address) || "Sir";
  return "Guten Tag, " + address + ". Wie kann ich helfen?";
}

let busy = false;
let ended = false;
function readyLabel() {
  return guestMode ? "GAST" : "READY";
}

let guestMode = false;      // Server laeuft mit --guest: nur plaudern, siehe guest.py
let projects = [];
let active = { project_id: null, conversation_id: null };
const expanded = loadExpanded();

// ======================================================================
// Hilfen
// ======================================================================

function loadExpanded() {
  try {
    return new Set(JSON.parse(localStorage.getItem("jarvis.expanded") || "[]"));
  } catch (error) {
    return new Set();
  }
}

function saveExpanded() {
  try {
    localStorage.setItem("jarvis.expanded", JSON.stringify([...expanded]));
  } catch (error) {
    /* ohne Speicher funktioniert die Seite trotzdem */
  }
}

// Spricht mit dem Server. Wirft einen Error mit dem Text des Servers.
async function api(method, path, body) {
  const options = { method, headers: {}, cache: "no-store" };

  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new Error("Keine Verbindung zu J.A.R.V.I.S.");
  }

  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    /* Antwort ohne JSON */
  }

  if (!response.ok) {
    throw new Error(data.error || "Fehler " + response.status);
  }

  return data;
}

function setStatus(state, text) {
  statusEl.dataset.state = state;
  statusEl.textContent = "● " + text;
}

// ======================================================================
// Chat
// ======================================================================

// Text sicher anzeigen: erst alles als Text einsetzen, dann nur **fett**
// und `code` in Elemente umwandeln. Nie innerHTML mit fremdem Text.
function renderText(target, text) {
  // Links [Text](https://...) zuerst herausnehmen (links.js), der Rest wird wie bisher gesetzt
  JarvisLinks.splitLinks(text).forEach((piece) => {
    if (piece.url === undefined) {
      renderPlain(target, piece.text);
      return;
    }

    const anchor = document.createElement("a");
    anchor.href = piece.url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = piece.label;
    target.appendChild(anchor);

    const host = document.createElement("span");
    host.className = "link-host";
    host.textContent = " (" + piece.host + ")";
    target.appendChild(host);
  });
}

function renderPlain(target, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;

  text.split(pattern).forEach((part) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      target.appendChild(strong);
    } else if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      const code = document.createElement("code");
      code.textContent = part.slice(1, -1);
      target.appendChild(code);
    } else {
      target.appendChild(document.createTextNode(part));
    }
  });
}

function addMessage(kind, text, label) {
  const bubble = document.createElement("div");
  bubble.className = "message " + kind;

  if (label) {
    const labelEl = document.createElement("span");
    labelEl.className = "label";
    labelEl.textContent = label;
    bubble.appendChild(labelEl);
  }

  renderText(bubble, text);
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

// Rueckfrage vor einer Aktion (Step 4.2): Ja/Nein-Knoepfe unter der Frage
function addConfirmButtons(bubble, id) {
  const row = document.createElement("div");
  row.className = "confirm-row";

  const yes = document.createElement("button");
  yes.type = "button";
  yes.textContent = "Ausführen";

  const no = document.createElement("button");
  no.type = "button";
  no.className = "secondary";
  no.textContent = "Abbrechen";

  async function answer(approve) {
    yes.disabled = true;
    no.disabled = true;
    setBusy(true);
    setStatus("busy", "THINKING...");

    try {
      const data = await api("POST", "/api/confirm", { id, approve });
      row.remove();
      addMessage("jarvis", data.content);
      setStatus("ready", readyLabel());
    } catch (error) {
      row.remove();
      addMessage("error", error.message);
      setStatus("error", "OFFLINE");
    } finally {
      setBusy(false);
      if (!ended) input.focus();
    }
  }

  yes.addEventListener("click", () => answer(true));
  no.addEventListener("click", () => answer(false));
  row.append(yes, no);
  bubble.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

// Plan zur Freigabe (Step 5.3): Ausfuehren / Abbrechen unter dem angezeigten Plan.
// Waehrend der Plan laeuft, gibt es einen Stopp-Knopf (haelt vor dem naechsten Schritt an).
function addPlanButtons(bubble, id) {
  const row = el("div", "confirm-row");
  const run = el("button", "", "Plan ausführen");
  const cancel = el("button", "secondary", "Abbrechen");
  run.type = "button";
  cancel.type = "button";

  async function answer(approve) {
    run.disabled = true;
    cancel.disabled = true;
    setBusy(true);
    planRunning = approve;
    updateStopButton();
    setStatus("busy", approve ? "PLAN LÄUFT..." : "THINKING...");

    if (approve) {
      const stop = el("button", "secondary", "Stopp");
      stop.type = "button";
      stop.addEventListener("click", async () => {
        stop.disabled = true;
        stop.textContent = "Stoppe …";
        try {
          await api("POST", "/api/plan/abort", {});
        } catch (error) {
          stop.textContent = "Stopp fehlgeschlagen";
        }
      });
      row.replaceChildren(el("span", "plan-running", "Plan läuft …"), stop);
    }

    try {
      const data = await api("POST", "/api/plan/confirm", { id, approve });
      row.remove();
      addMessage("jarvis", data.content);
      setStatus("ready", readyLabel());
    } catch (error) {
      row.remove();
      addMessage("error", error.message);
      setStatus("error", "OFFLINE");
    } finally {
      planRunning = false;
      updateStopButton();
      setBusy(false);
      if (!ended) input.focus();
    }
  }

  run.addEventListener("click", () => answer(true));
  cancel.addEventListener("click", () => answer(false));
  row.append(run, cancel);
  bubble.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function showHistory(messages) {
  chat.replaceChildren();

  if (messages.length === 0) {
    addMessage("jarvis", greeting());
    return;
  }

  messages.forEach((message) => {
    addMessage(message.role === "user" ? "user" : "jarvis", message.content);
  });
}

async function sendMessage(text) {
  setBusy(true);
  setStatus("busy", "THINKING...");
  // Eine neue Nachricht beantwortet keine alte Rueckfrage mehr
  document.querySelectorAll(".confirm-row").forEach((row) => row.remove());
  awaitingAck = false;
  voice.stopSpeaking();
  addMessage("user", text);

  try {
    const data = await api("POST", "/api/message", { message: text });

    // Ein Chat-Befehl hat die Konversation gewechselt oder geleert:
    // neuen Verlauf zeigen, danach Befehl und Antwort
    if (data.messages) {
      showHistory(data.messages);
      addMessage("user", text);
    }

    const bubble = addMessage("jarvis", data.content);
    speakReply(data.content);

    if (data.status === "confirmation" && data.confirmation) {
      addConfirmButtons(bubble, data.confirmation.id);
    }

    if (data.status === "plan" && data.plan) {
      addPlanButtons(bubble, data.plan.id);
    }

    if (data.status === "exit" && !guestMode) {
      ended = true;
      input.disabled = true;
      setStatus("ready", "BEENDET");
      return;
    }

    setStatus("ready", readyLabel());
  } catch (error) {
    addMessage("error", error.message);
    setStatus("error", "OFFLINE");
  } finally {
    setBusy(false);
    if (!ended) input.focus();
    // Befehle wie "Oeffne Projekt X" aendern den Stand der Seitenleiste
    refreshTree();
    // Jarvis kann Termine eintragen: Kalender und Ziele nachladen
    refreshWidgets();
  }
}

function setBusy(value) {
  busy = value;
  refreshWake();
  sendButton.disabled = value || ended;
  // Waehrend Jarvis antwortet, darf niemand die Konversation wechseln.
  sidebar.classList.toggle("locked", value);
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();

  const text = input.value.trim();
  if (!text || busy || ended) return;

  input.value = "";
  resizeInput();
  sendMessage(text);
});

// ======================================================================
// Sprache (Step 6): Vorlesen und Push-to-talk, siehe voice.js
// ======================================================================

let speakingNow = false;
let planRunning = false;

// Stopp-Knopf: sichtbar, solange Jarvis spricht oder ein Plan laeuft
function updateStopButton() {
  stopButton.hidden = !(speakingNow || planRunning);
}

const voice = window.JarvisVoice.createVoice({
  onSpeaking: (value) => {
    speakingNow = value;
    updateStopButton();
    if (!value && awaitingAck) { awaitingAck = false; listenOnce(true); }
    refreshWake();
  },
  synth: window.speechSynthesis,
  Utterance: window.SpeechSynthesisUtterance,
  Recognition: window.SpeechRecognition || window.webkitSpeechRecognition,
  Audio: window.Audio,
  createObjectURL: (blob) => URL.createObjectURL(blob),
  revokeObjectURL: (url) => URL.revokeObjectURL(url),
  // Stimme vom Server (OpenAI): Text hin, MP3 zurueck. Welche Stimme, bestimmt der Server.
  fetchAudio: async (text, signal) => {
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal,
    });
    if (!response.ok) throw new Error("speak " + response.status);
    return response.blob();
  },
  onFallback: () => {
    if (fallbackShown) return;
    fallbackShown = true;
    addMessage("error", "Die Stimme von OpenAI ist gerade nicht erreichbar. Ich nutze vorübergehend die Browser-Stimme.");
  },
});
let fallbackShown = false;
let awaitingAck = false;      // "Ja, Sir?" wird gesprochen, danach hoert Jarvis den Befehl
const micButton = document.getElementById("mic");
const stopButton = document.getElementById("stop");

stopButton.addEventListener("click", async () => {
  awaitingAck = false;
  voice.stopSpeaking();
  if (planRunning) {
    try { await api("POST", "/api/plan/abort", {}); } catch (error) { /* Plan endet ohnehin */ }
  }
});

function voiceSetting(key) {
  return (settings.voice || {})[key];
}

// Nur wenn du es eingeschaltet hast (Standard: aus) und nur Antworten von J.A.R.V.I.S.
function speakReply(text) {
  if (voiceSetting("output") === true) voice.speak(text, voiceSetting("speed"), voiceSetting("engine"));
}

function applyVoice() {
  if (voiceSetting("output") !== true) voice.stopSpeaking();
  const show = voiceSetting("input") === true && voice.canListen();
  micButton.hidden = !show;
  if (!show && voice.isListening()) voice.stopListening();
  refreshWake();
}

// Einen Satz hoeren und wie getippten Text senden. fromWake: nach dem Weckwort
// (dann zeigt die Anzeige "Ich höre zu", auch wenn der Mikrofon-Knopf aus ist).
function listenOnce(fromWake) {
  if (busy || ended || voice.isListening()) return;
  commandListening = fromWake === true;
  const started = voice.startListening({
    onState: (state) => {
      micButton.classList.toggle("listening", state === "listening");
      if (state !== "listening") {
        commandListening = false;
        // Kurz warten: kommt gleich Text, ist Jarvis gleich beschaeftigt und hoert nicht auf das Weckwort
        setTimeout(refreshWake, 60);
      }
      updateWakeBadge();
    },
    onText: (text) => {
      // Gesprochener Text wird wie getippter behandelt, mit denselben Pruefungen
      if (busy || ended) return;
      sendMessage(text);
    },
    onError: (code) => addMessage("error", "Spracheingabe nicht möglich (" + code + ")."),
  }, voiceSetting("input_language"));
  if (!started) { commandListening = false; refreshWake(); }
  updateWakeBadge();
}

function micDown(event) {
  if (event.repeat) return;
  listenOnce(false);
}

// ---- Weckwort "Jarvis" (siehe wake.js): nur wenn eingeschaltet, nie im Gastmodus
const wakeBadge = document.getElementById("wake");
let commandListening = false;
let wakeListening = false;

const wake = window.JarvisWake.createWakeListener({
  Recognition: window.SpeechRecognition || window.webkitSpeechRecognition,
  onState: (state) => { wakeListening = state === "listening"; updateWakeBadge(); },
  onWake: handleWake,
  onError: (code) => {
    addMessage("error", "Das Weckwort funktioniert gerade nicht (" + code + "). Du kannst es in den Einstellungen unter Voice aus- und wieder einschalten.");
  },
});

function updateWakeBadge() {
  if (commandListening) {
    wakeBadge.hidden = false;
    wakeBadge.dataset.mode = "command";
    wakeBadge.textContent = "🎤 Ich höre zu …";
  } else if (wakeListening) {
    wakeBadge.hidden = false;
    wakeBadge.dataset.mode = "wake";
    wakeBadge.textContent = "👂 Sag „Jarvis“";
  } else {
    wakeBadge.hidden = true;
  }
}

// Zuhoeren nur, wenn alles ruhig ist: nicht waehrend Jarvis spricht oder antwortet
// (er soll sich nicht selbst hoeren) und nicht, waehrend das Mikrofon schon laeuft.
function refreshWake() {
  const wanted = voiceSetting("wake_word") === true && !guestMode && !ended && wake.canListen() &&
    !busy && !speakingNow && !awaitingAck && !voice.isListening();
  wake.setActive(wanted, wanted ? INPUT_LOCALES[voiceSetting("input_language")] : undefined);
}
const INPUT_LOCALES = window.JarvisVoice.INPUT_LANGUAGES;

function chime() {
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    const context = new Context();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 880;
    gain.gain.value = 0.08;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.12);
    oscillator.onended = () => context.close();
  } catch (error) { /* ohne Ton funktioniert es trotzdem, die Anzeige genuegt */ }
}

// Jemand hat "Jarvis ..." gesagt. Mit Befehl dahinter (rest) geht der direkt los,
// sonst antwortet Jarvis "Ja, Sir?" (gesprochen oder als Ton) und hoert dann einen Satz.
function handleWake(rest) {
  if (busy || ended) { refreshWake(); return; }
  if (rest) {
    wake.setActive(false);
    sendMessage(rest);
    return;
  }
  wake.setActive(false);
  if (voiceSetting("output") === true) {
    const english = voiceSetting("input_language") === "English";
    const reply = english ? "Yes, Sir?" : "Ja, Sir?";
    awaitingAck = true;
    if (!voice.speak(reply, voiceSetting("speed"), voiceSetting("engine"))) {
      awaitingAck = false;
      listenOnce(true);
    }
  } else {
    chime();
    listenOnce(true);
  }
}

function micUp() {
  voice.stopListening();
}

micButton.addEventListener("pointerdown", (event) => { event.preventDefault(); micDown(event); });
micButton.addEventListener("pointerup", micUp);
micButton.addEventListener("pointerleave", micUp);
micButton.addEventListener("pointercancel", micUp);
micButton.addEventListener("keydown", (event) => {
  if (event.key === " " || event.key === "Enter") { event.preventDefault(); micDown(event); }
});
micButton.addEventListener("keyup", (event) => {
  if (event.key === " " || event.key === "Enter") micUp();
});


// ======================================================================
// Seitenleiste rechts (Etappe C): drei Widgets, jedes in den Einstellungen waehlbar
// ======================================================================

const widgetsEl = document.getElementById("widgets");
const WIDGET_SLOTS = ["top", "middle", "bottom", "fourth", "fifth"];
const widgetShown = { top: null, middle: null, bottom: null, fourth: null, fifth: null };   // was gerade gezeichnet ist
let widgetClock = null;          // Sekundentakt fuer Uhr und Datum
let hockeyTimer = null;          // Spielplan alle 5 Minuten neu holen
let widgetData = null;           // Notizen und Ziele vom Server

function wEl(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function widgetChoice(slot) {
  if (guestMode) return "Off";
  return (settings.widgets || {})[slot] || "Off";
}

function loadWidgetData(force) {
  if (widgetData && !force) return Promise.resolve(widgetData);
  return api("GET", "/api/widgets").then((data) => { widgetData = data; return data; });
}

// Felder, die sich neu zeichnen, wenn sich Daten von aussen aendern (z.B. Jarvis traegt einen Termin ein)
const widgetRefreshers = [];

function registerRefresher(section, redraw) {
  widgetRefreshers.push({ section, redraw });
}

async function refreshWidgets() {
  if (guestMode || !widgetRefreshers.length) return;
  let data;
  try { data = await loadWidgetData(true); } catch (error) { return; }
  for (let i = widgetRefreshers.length - 1; i >= 0; i--) {
    const entry = widgetRefreshers[i];
    if (!entry.section.isConnected) widgetRefreshers.splice(i, 1);
    else entry.redraw(data);
  }
}

// ---- oben: Uhr, Datum, Kalender
function updateTime() {
  const now = new Date();
  document.querySelectorAll(".w-clock-time").forEach((node) => { node.textContent = window.JarvisWidgets.formatClock(now); });
  document.querySelectorAll(".w-clock-date, .w-date-long").forEach((node) => { node.textContent = window.JarvisWidgets.formatDateLong(now); });
}

function renderClock(section) {
  section.append(wEl("div", "w-clock-time"), wEl("div", "w-clock-date w-muted"));
  updateTime();
}

function renderDate(section) {
  const now = new Date();
  section.append(
    wEl("div", "w-date-day", String(now.getDate())),
    wEl("div", "w-date-long w-muted"),
  );
  updateTime();
}

function renderCalendar(section) {
  const W = window.JarvisWidgets;
  const today = new Date();
  let year = today.getFullYear();
  let month = today.getMonth();
  let selected = W.dateKey(year, month, today.getDate());
  let byDate = W.eventsByDate(widgetData && widgetData.events);

  const head = wEl("div", "w-cal-head");
  const prev = wEl("button", "w-cal-nav", "‹");
  const next = wEl("button", "w-cal-nav", "›");
  const title = wEl("span", "w-cal-title");
  [prev, next].forEach((button) => { button.type = "button"; });
  prev.setAttribute("aria-label", "Vorheriger Monat");
  next.setAttribute("aria-label", "Nächster Monat");
  head.append(prev, title, next);
  const grid = wEl("div", "w-cal-grid");

  const dayHead = wEl("div", "w-cal-dayhead");
  const list = wEl("ul", "w-events");
  const form = wEl("form", "w-event-form");
  const field = wEl("input", "w-event-title");
  const clock = wEl("input", "w-event-time");
  const add = wEl("button", "w-goal-add", "＋");
  const status = wEl("div", "w-status w-muted", "");
  field.type = "text"; field.maxLength = 100; field.placeholder = "Termin …";
  field.setAttribute("aria-label", "Neuer Termin");
  clock.type = "time"; clock.setAttribute("aria-label", "Uhrzeit (optional)");
  add.type = "submit"; add.setAttribute("aria-label", "Termin hinzufügen");
  form.append(field, clock, add);
  section.append(head, grid, dayHead, list, form, status);

  function drawGrid() {
    title.textContent = W.monthTitle(year, month);
    grid.replaceChildren();
    W.weekdayNames().forEach((name) => grid.append(wEl("span", "w-cal-dow", name)));
    W.calendarWeeks(year, month).flat().forEach((day) => {
      if (day === null) { grid.append(wEl("span", "w-cal-day empty")); return; }
      const key = W.dateKey(year, month, day);
      const cell = wEl("button", "w-cal-day", String(day));
      cell.type = "button";
      if (key === W.dateKey(today.getFullYear(), today.getMonth(), today.getDate())) cell.classList.add("today");
      if (key === selected) cell.classList.add("selected");
      if (byDate[key]) {
        cell.classList.add("has-events");
        cell.title = byDate[key].map((e) => (e.time ? e.time + " " : "") + e.title).join("\n");
      }
      cell.addEventListener("click", () => { selected = key; drawGrid(); drawDay(); });
      grid.append(cell);
    });
  }

  function drawDay() {
    dayHead.textContent = W.formatDayLong(selected);
    list.replaceChildren();
    const events = byDate[selected] || [];
    if (!events.length) list.append(wEl("li", "w-muted", "Keine Termine."));
    events.forEach((event) => {
      const item = wEl("li", "w-event");
      const remove = wEl("button", "w-goal-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", (event.series ? "Nur diesen Termin löschen: " : "Termin löschen: ") + event.title);
      remove.title = event.series ? "Nur diesen Tag löschen" : "Termin löschen";
      remove.addEventListener("click", async () => {
        try {
          widgetData = await api("POST", "/api/widgets/events/delete", { id: event.id });
          status.textContent = "";
          update(widgetData);
        } catch (error) { status.textContent = error.message; }
      });
      const label = wEl("span", "w-event-text", (event.repeat ? "↻ " : "") + event.title);
      if (event.repeat) label.title = event.repeat;
      item.append(wEl("span", "w-event-when", event.time || "ganztägig"), label);
      if (event.series) {
        // Ganze Serie loeschen: zwei Klicks (der erste fragt nach), damit nichts aus Versehen verschwindet
        const series = wEl("button", "w-goal-remove w-series-remove", "↻×");
        series.type = "button";
        series.title = "Ganze Serie löschen (" + event.repeat + ")";
        series.setAttribute("aria-label", "Ganze Serie löschen: " + event.title);
        let armed = null;
        series.addEventListener("click", async () => {
          if (!armed) {
            series.textContent = "✓?";
            series.classList.add("armed");
            status.textContent = "Noch einmal klicken: die ganze Serie wird gelöscht.";
            armed = setTimeout(() => {
              armed = null; series.textContent = "↻×"; series.classList.remove("armed"); status.textContent = "";
            }, 4000);
            return;
          }
          clearTimeout(armed);
          try {
            widgetData = await api("POST", "/api/widgets/events/delete_series", { series: event.series });
            status.textContent = "";
            update(widgetData);
          } catch (error) {
            status.textContent = error.message; armed = null; series.textContent = "↻×"; series.classList.remove("armed");
          }
        });
        item.append(series);
      }
      item.append(remove);
      list.append(item);
    });
  }

  function update(data) {
    byDate = W.eventsByDate(data.events);
    drawGrid();
    drawDay();
  }

  prev.addEventListener("click", () => { month -= 1; if (month < 0) { month = 11; year -= 1; } drawGrid(); });
  next.addEventListener("click", () => { month += 1; if (month > 11) { month = 0; year += 1; } drawGrid(); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = field.value.trim();
    if (!text) return;
    try {
      widgetData = await api("POST", "/api/widgets/events", { title: text, date: selected, time: clock.value });
      field.value = ""; clock.value = ""; status.textContent = "";
      update(widgetData);
    } catch (error) { status.textContent = error.message; }
  });

  update({ events: [] });
  registerRefresher(section, update);
  loadWidgetData(true).then(update).catch((error) => { status.textContent = error.message; });
}

// ---- Mitte: Notizen, Ziele des Tages
function renderNotes(section) {
  const area = wEl("textarea", "w-notes");
  const status = wEl("div", "w-status w-muted", "");
  area.rows = 7;
  area.maxLength = 5000;
  area.placeholder = "Notizen …";
  area.setAttribute("aria-label", "Notizen");
  section.append(wEl("h3", "w-title", "Notizen"), area, status);

  let loaded = false;
  let timer = null;
  async function save() {
    clearTimeout(timer);
    timer = null;
    try {
      const data = await api("POST", "/api/widgets/notes", { text: area.value });
      widgetData = data;
      status.textContent = "Gespeichert";
    } catch (error) {
      status.textContent = "Nicht gespeichert: " + error.message;
    }
  }
  area.addEventListener("input", () => {
    if (!loaded) return;
    status.textContent = "…";
    clearTimeout(timer);
    timer = setTimeout(save, 700);
  });
  area.addEventListener("blur", () => { if (timer) save(); });

  area.disabled = true;
  loadWidgetData().then((data) => { area.value = data.notes; area.disabled = false; loaded = true; })
    .catch((error) => { status.textContent = error.message; });
}

function renderGoals(section) {
  const list = wEl("ul", "w-goals");
  const form = wEl("form", "w-goal-form");
  const field = wEl("input", "w-goal-input");
  const dailyToggle = wEl("button", "w-daily-toggle", "↻");
  const add = wEl("button", "w-goal-add", "＋");
  const status = wEl("div", "w-status w-muted", "");
  field.type = "text";
  field.maxLength = 200;
  field.placeholder = "Neues Ziel …";
  field.setAttribute("aria-label", "Neues Ziel");
  dailyToggle.type = "button";
  dailyToggle.title = "Tägliches Ziel: kommt jeden Tag wieder, als noch nicht erledigt";
  dailyToggle.setAttribute("aria-label", "Tägliches Ziel");
  dailyToggle.setAttribute("aria-pressed", "false");
  add.type = "submit";
  add.setAttribute("aria-label", "Ziel hinzufügen");
  form.append(field, dailyToggle, add);
  section.append(wEl("h3", "w-title", "Ziele heute"), list, form,
    wEl("div", "w-status w-muted", "↻ = täglich wiederkehrend"), status);

  let goals = [];

  function draw() {
    list.replaceChildren();
    if (!goals.length) list.append(wEl("li", "w-muted", "Noch keine Ziele für heute."));
    goals.forEach((goal, index) => {
      const item = wEl("li", "w-goal" + (goal.done ? " done" : ""));
      const box = wEl("input");
      box.type = "checkbox";
      box.checked = goal.done;
      box.setAttribute("aria-label", goal.text);
      box.addEventListener("change", () => { goals[index].done = box.checked; persist(); });
      const repeat = wEl("button", "w-daily" + (goal.daily ? " on" : ""), "↻");
      repeat.type = "button";
      repeat.title = goal.daily ? "Täglich: klicken, um nur für heute zu behalten" : "Nur heute: klicken, damit es täglich wiederkommt";
      repeat.setAttribute("aria-pressed", String(goal.daily));
      repeat.setAttribute("aria-label", "Täglich wiederholen: " + goal.text);
      repeat.addEventListener("click", () => { goals[index].daily = !goals[index].daily; persist(); });
      const remove = wEl("button", "w-goal-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", "Ziel löschen");
      remove.addEventListener("click", () => { goals.splice(index, 1); persist(); });
      item.append(box, wEl("span", "w-goal-text", goal.text), repeat, remove);
      list.append(item);
    });
  }

  // Mehrere schnelle Aenderungen werden nacheinander gespeichert; erst die Antwort der letzten
  // wird uebernommen (sonst wuerde eine alte Antwort ein gerade hinzugefuegtes Ziel wieder ausblenden).
  let saving = Promise.resolve();
  let queued = 0;

  function persist() {
    draw();
    queued += 1;
    saving = saving.then(async () => {
      let data = null;
      try {
        data = await api("POST", "/api/widgets/goals", { items: goals });
        widgetData = data;
        status.textContent = "";
      } catch (error) {
        status.textContent = "Nicht gespeichert: " + error.message;
      }
      queued -= 1;
      if (queued === 0 && data) { goals = data.goals; draw(); }
    });
  }

  dailyToggle.addEventListener("click", () => {
    const on = dailyToggle.getAttribute("aria-pressed") !== "true";
    dailyToggle.setAttribute("aria-pressed", String(on));
    dailyToggle.classList.toggle("on", on);
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = field.value.trim();
    if (!text) return;
    goals.push({ text, done: false, daily: dailyToggle.getAttribute("aria-pressed") === "true" });
    field.value = "";
    // Der naechste Eintrag ist wieder ein Ziel nur fuer heute
    dailyToggle.setAttribute("aria-pressed", "false");
    dailyToggle.classList.remove("on");
    persist();
  });

  loadWidgetData(true).then((data) => { goals = data.goals; draw(); })
    .catch((error) => { status.textContent = error.message; });
  // Neuer Tag oder Aenderung von aussen: Liste neu laden (Eingabefeld bleibt unberuehrt)
  registerRefresher(section, (data) => { goals = data.goals; draw(); });
}

// ---- unten: Eishockey (Spielplan holt der Server von der NHL)
function gameRow(game) {
  const info = window.JarvisWidgets.describeGame(game);
  const row = wEl("li", "w-game");
  row.append(
    wEl("span", "w-game-when", info.when),
    wEl("span", "w-game-vs", (info.home ? "vs " : "@ ") + info.opponent),
  );
  return row;
}

function renderHockey(section, teamName) {
  const body = wEl("div", "w-hockey");
  section.append(wEl("h3", "w-title", "🏒 " + teamName), body);
  body.append(wEl("div", "w-muted", "Lade Spielplan …"));

  async function load() {
    let data;
    try {
      data = await api("GET", "/api/hockey");
    } catch (error) {
      if (body.isConnected) { body.replaceChildren(wEl("div", "w-muted", error.message)); }
      return;
    }
    if (!body.isConnected) return;
    body.replaceChildren();
    if (!data.current && !(data.next || []).length) {
      body.append(wEl("div", "w-muted", "Keine Spiele gefunden."));
      return;
    }
    if (data.current) {
      const info = window.JarvisWidgets.describeGame(data.current);
      const card = wEl("div", "w-game-current" + (info.live ? " live" : ""));
      const names = data.current.home.name + (info.score ? " " + info.score + " " : " – ") + data.current.away.name;
      card.append(
        wEl("div", "w-muted", info.live ? "Läuft gerade" : "Letztes Spiel"),
        wEl("div", "w-game-score" + (info.outcome ? " " + info.outcome : ""), names),
      );
      if (!info.score) card.append(wEl("div", "w-muted", info.live ? info.when : "Ergebnis nicht verfügbar"));
      body.append(card);
    }
    if ((data.next || []).length) {
      body.append(wEl("div", "w-muted", "Nächste Spiele"));
      const list = wEl("ul", "w-games");
      data.next.forEach((game) => list.append(gameRow(game)));
      body.append(list);
    }
    if (data.stale) body.append(wEl("div", "w-status w-muted", "Stand evtl. veraltet (kein Netz)."));
  }

  load();
  clearInterval(hockeyTimer);
  hockeyTimer = setInterval(load, 5 * 60 * 1000);
}

// ---- PC Facts und Performance (Step 2.8): der Server liest den Rechner, der Browser zeigt nur an
function factRow(label, value) {
  const row = wEl("div", "w-fact");
  row.append(wEl("span", "w-fact-label", label), wEl("span", "w-fact-value", value));
  return row;
}

function renderPcFacts(section) {
  const body = wEl("div", "w-facts");
  section.append(wEl("h3", "w-title", "🖥 PC Facts"), body);
  body.append(wEl("div", "w-muted", "Lade …"));
  api("GET", "/api/system").then((data) => {
    if (!body.isConnected) return;
    const W = window.JarvisWidgets;
    body.replaceChildren(
      factRow("System", data.os || "–"),
      factRow("Prozessor", data.cpu_name || "–"),
      factRow("Kerne", (data.cpu_cores || "–") + " Kerne / " + (data.cpu_threads || "–") + " Threads"),
      factRow("RAM", W.formatGb(data.ram_total_gb)),
    );
    (data.drives || []).forEach((drive) => {
      body.append(factRow(drive.name, W.formatNumber(drive.free_gb, 0) + " von " + W.formatNumber(drive.total_gb, 0) + " GB frei"));
    });
    body.append(factRow("Computer", data.computer_name || "–"));
  }).catch((error) => { if (body.isConnected) body.replaceChildren(wEl("div", "w-muted", error.message)); });
}

function barRow(label) {
  const row = wEl("div", "w-perf-row");
  const head = wEl("div", "w-perf-head");
  const value = wEl("span", "w-perf-value", "–");
  head.append(wEl("span", "w-perf-label", label), value);
  const bar = wEl("div", "w-bar");
  const fill = wEl("div", "w-bar-fill ok");
  bar.append(fill);
  row.append(head, bar);
  return { row, value, fill };
}

function setBar(bar, percent, text) {
  const W = window.JarvisWidgets;
  bar.fill.style.width = W.clampPercent(percent) + "%";
  bar.fill.className = "w-bar-fill " + W.loadLevel(percent);
  bar.value.textContent = text;
}

function renderPerformance(section) {
  const W = window.JarvisWidgets;
  const body = wEl("div", "w-perf");
  const cpu = barRow("CPU"), ram = barRow("RAM"), disk = barRow("Laufwerk"), battery = barRow("Akku");
  battery.row.hidden = true;
  const net = wEl("div", "w-perf-line");
  const uptime = wEl("div", "w-perf-line");
  const status = wEl("div", "w-status w-muted");
  body.append(cpu.row, ram.row, disk.row, battery.row, net, uptime, status);
  section.append(wEl("h3", "w-title", "📊 Performance"), body);

  async function load() {
    let data;
    try {
      data = await api("GET", "/api/performance");
    } catch (error) {
      if (body.isConnected) status.textContent = error.message;
      return;
    }
    if (!body.isConnected) return;
    status.textContent = "";
    setBar(cpu, data.cpu_percent, W.formatNumber(data.cpu_percent, 0) + " %");
    setBar(ram, data.ram_percent, W.formatGb(data.ram_used_gb) + " / " + W.formatGb(data.ram_total_gb));
    setBar(disk, data.disk_percent, W.formatNumber(data.disk_percent, 0) + " %");
    battery.row.hidden = !data.battery;
    if (data.battery) setBar(battery, 100 - data.battery.percent, W.formatNumber(data.battery.percent, 0) + " %" + (data.battery.plugged ? " ⚡" : ""));
    const network = data.network || {};
    net.textContent = "Netz  ↓ " + W.formatRate(network.down_kb_s) + "   ↑ " + W.formatRate(network.up_kb_s);
    uptime.textContent = "Läuft seit " + W.formatUptime(data.uptime_seconds);
  }

  load();
  // Alle 2 Sekunden, solange das Feld sichtbar ist; wird es ausgetauscht, beendet sich der Takt von selbst
  const timer = setInterval(() => {
    if (!body.isConnected) { clearInterval(timer); return; }
    if (!document.hidden) load();
  }, 2000);
}

const WIDGET_RENDERERS = {
  "PC Facts": renderPcFacts, Performance: renderPerformance,
  Clock: renderClock, Date: renderDate, Calendar: renderCalendar,
  Notes: renderNotes, Goals: renderGoals,
  "Edmonton Oilers": (section) => renderHockey(section, "Oilers"),
  "Adler Mannheim": (section) => renderHockey(section, "Adler Mannheim"),
};

// Schmales Fenster: die Leiste ist ausgeblendet und laesst sich ueber den Knopf oben aufklappen
const widgetsButton = document.getElementById("widgets-button");
const narrowForWidgets = window.matchMedia("(max-width: 1180px)");

function setWidgetsOpen(open) {
  layout.classList.toggle("widgets-open", open);
  widgetsButton.setAttribute("aria-expanded", String(open));
}

function updateWidgetsButton() {
  const show = narrowForWidgets.matches && !widgetsEl.hidden && !guestMode;
  widgetsButton.hidden = !show;
  if (!show) setWidgetsOpen(false);
}

widgetsButton.addEventListener("click", () => setWidgetsOpen(!layout.classList.contains("widgets-open")));
narrowForWidgets.addEventListener("change", updateWidgetsButton);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") setWidgetsOpen(false); });
document.addEventListener("pointerdown", (event) => {
  if (!layout.classList.contains("widgets-open")) return;
  if (widgetsEl.contains(event.target) || widgetsButton.contains(event.target)) return;
  setWidgetsOpen(false);
});

// Termine und Ziele regelmaessig abgleichen (Jarvis traegt Termine ein, um Mitternacht beginnt ein neuer Tag)
setInterval(refreshWidgets, 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshWidgets(); });

function applyWidgets() {
  let any = false;
  WIDGET_SLOTS.forEach((slot) => {
    const choice = widgetChoice(slot);
    const section = document.getElementById("widget-" + slot);
    section.hidden = choice === "Off";
    if (choice !== "Off") any = true;
    if (widgetShown[slot] === choice) return;        // unveraendert: nicht neu zeichnen
    widgetShown[slot] = choice;
    section.replaceChildren();
    if (slot === "bottom") { clearInterval(hockeyTimer); hockeyTimer = null; }
    if (choice !== "Off") WIDGET_RENDERERS[choice](section);
  });
  widgetsEl.hidden = !any;
  document.body.classList.toggle("has-widgets", any);
  updateWidgetsButton();

  const needsClock = ["Clock", "Date"].some((name) => WIDGET_SLOTS.some((slot) => widgetShown[slot] === name));
  if (needsClock && !widgetClock) widgetClock = setInterval(updateTime, 1000);
  if (!needsClock && widgetClock) { clearInterval(widgetClock); widgetClock = null; }
}

// Enter sendet, Shift+Enter macht eine neue Zeile
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

function resizeInput() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}
input.addEventListener("input", resizeInput);

// ======================================================================
// Dialog (Texteingabe oder Bestaetigung)
// ======================================================================

const dialog = document.getElementById("dialog");
const dialogForm = document.getElementById("dialog-form");
const dialogTitle = document.getElementById("dialog-title");
const dialogText = document.getElementById("dialog-text");
const dialogInput = document.getElementById("dialog-input");
const dialogError = document.getElementById("dialog-error");
const dialogOk = document.getElementById("dialog-ok");
const dialogCancel = document.getElementById("dialog-cancel");

let dialogSubmit = null;

// options: title, text, value (nur bei Texteingabe), okLabel, danger,
//          onSubmit(value): async; wirft einen Error, wenn es nicht klappt.
function openDialog(options) {
  dialogTitle.textContent = options.title;
  dialogText.textContent = options.text || "";
  dialogText.hidden = !options.text;
  dialogError.hidden = true;

  const withInput = options.value !== undefined;
  dialogInput.hidden = !withInput;
  dialogInput.value = withInput ? options.value : "";

  dialogOk.textContent = options.okLabel || "OK";
  dialogOk.className = options.danger ? "danger-fill" : "";
  dialogSubmit = options.onSubmit;

  dialog.showModal();

  if (withInput) {
    dialogInput.focus();
    dialogInput.select();
  }
}

dialogForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  dialogOk.disabled = true;

  try {
    await dialogSubmit(dialogInput.hidden ? undefined : dialogInput.value.trim());
    dialog.close();
  } catch (error) {
    dialogError.textContent = error.message;
    dialogError.hidden = false;
  } finally {
    dialogOk.disabled = false;
  }
});

dialogCancel.addEventListener("click", () => dialog.close());

// ======================================================================
// Kontextmenue
// ======================================================================

function closeMenu() {
  menuEl.hidden = true;
  menuEl.replaceChildren();
}

// items: [{ label, danger, run }]
function openMenu(anchor, items, event) {
  menuEl.replaceChildren();

  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.label;
    if (item.danger) button.className = "danger";
    button.addEventListener("click", () => {
      closeMenu();
      item.run();
    });
    menuEl.appendChild(button);
  });

  menuEl.hidden = false;

  const box = anchor.getBoundingClientRect();
  const x = event && event.clientX ? event.clientX : box.right;
  const y = event && event.clientY ? event.clientY : box.bottom;

  menuEl.style.left = Math.min(x, window.innerWidth - menuEl.offsetWidth - 8) + "px";
  menuEl.style.top = Math.min(y, window.innerHeight - menuEl.offsetHeight - 8) + "px";
}

document.addEventListener("click", (event) => {
  if (!menuEl.contains(event.target)) closeMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMenu();
});
window.addEventListener("resize", closeMenu);
sidebar.addEventListener("scroll", closeMenu);

// ======================================================================
// Seitenleiste
// ======================================================================

function applyState(state) {
  projects = state.projects;
  active = state.active;

  if (active.project_id !== null) {
    expanded.add(active.project_id);
    saveExpanded();
  }

  renderTree();
}

async function refreshTree() {
  if (guestMode) return;
  try {
    applyState(await api("GET", "/api/projects"));
  } catch (error) {
    /* die Seitenleiste bleibt, wie sie ist */
  }
}

function makeRow(className, label) {
  const row = document.createElement("div");
  row.className = "row " + className;
  row.tabIndex = 0;
  row.setAttribute("role", "button");

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = label;
  row.appendChild(name);

  return row;
}

function addMoreButton(row, items) {
  const more = document.createElement("span");
  more.className = "more";
  more.textContent = "⋯";
  more.title = "Mehr";
  more.addEventListener("click", (event) => {
    event.stopPropagation();
    openMenu(more, items, event);
  });
  row.appendChild(more);

  row.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    openMenu(row, items, event);
  });
}

function onActivate(row, handler) {
  row.addEventListener("click", handler);
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler();
    }
  });
}

function renderTree() {
  tree.replaceChildren();

  newConversationButton.disabled = active.project_id === null;
  newConversationButton.title =
    active.project_id === null ? "Öffne zuerst eine Konversation in einem Projekt" : "";

  if (projects.length === 0) {
    const hint = document.createElement("p");
    hint.className = "empty-hint";
    hint.textContent = "Noch keine Projekte. Lege mit „New Project“ eins an.";
    tree.appendChild(hint);
    return;
  }

  projects.forEach((project) => {
    const isOpen = expanded.has(project.id);

    const row = makeRow("project-row", project.name);
    if (project.id === active.project_id) row.classList.add("active");

    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = isOpen ? "▾" : "▸";
    row.prepend(arrow);

    onActivate(row, () => clickProject(project));

    const add = document.createElement("span");
    add.className = "more add";
    add.textContent = "＋";
    add.title = "Neue Konversation in diesem Projekt";
    add.addEventListener("click", (event) => {
      event.stopPropagation();
      newConversation(project);
    });
    row.appendChild(add);

    addMoreButton(row, [
      { label: "Rename Project", run: () => renameProject(project) },
      { label: "Delete Project", danger: true, run: () => deleteProject(project) },
    ]);
    tree.appendChild(row);

    if (!isOpen) return;

    if (project.conversations.length === 0) {
      const create = makeRow("conversation-row create-row", "＋ Neue Konversation");
      onActivate(create, () => newConversation(project));
      tree.appendChild(create);
    }

    project.conversations.forEach((conversation) => {
      const item = makeRow("conversation-row", conversation.title);
      if (conversation.id === active.conversation_id) item.classList.add("active");

      onActivate(item, () => openConversation(project, conversation));
      addMoreButton(item, [
        { label: "Rename", run: () => renameConversation(project, conversation) },
        { label: "Reset", run: () => resetConversation(project, conversation) },
        { label: "Delete", danger: true, run: () => deleteConversation(project, conversation) },
      ]);
      tree.appendChild(item);
    });
  });
}

// ---------- Aktionen ----------

// Klick auf ein Projekt: aktiv setzen und aufklappen. Ist es schon aktiv,
// klappt der Klick es auf oder zu.
async function clickProject(project) {
  if (busy) return;

  if (active.project_id === project.id) {
    if (expanded.has(project.id)) expanded.delete(project.id);
    else expanded.add(project.id);
    saveExpanded();
    renderTree();
    return;
  }

  try {
    const before = active.conversation_id;
    const data = await api("POST", "/api/project/open", { project_id: project.id });
    // Die offene Konversation gehoert zum alten Projekt: Chat leeren
    if (before !== data.active.conversation_id) showHistory([]);
    applyState(data);
  } catch (error) {
    addMessage("error", error.message);
    refreshTree();
  }
}

async function openConversation(project, conversation) {
  if (busy) return;
  layout.classList.remove("sidebar-open");

  try {
    const data = await api("POST", "/api/conversation/open", {
      project_id: project.id,
      conversation_id: conversation.id,
    });
    showHistory(data.messages);
    applyState(data);
    input.focus();
  } catch (error) {
    addMessage("error", error.message);
    refreshTree();
  }
}

function newProject() {
  openDialog({
    title: "New Project",
    text: "Name des Projekts:",
    value: "",
    okLabel: "Erstellen",
    onSubmit: async (name) => {
      const data = await api("POST", "/api/project/new", { name });
      // Das neue Projekt ist aktiv, eine alte Konversation gehoert nicht mehr dazu
      showHistory([]);
      applyState(data);
    },
  });
}

// Ohne Angabe im aktiven Projekt, sonst im angegebenen Projekt.
function newConversation(project) {
  const projectId = project ? project.id : active.project_id;
  if (projectId === null) return;

  openDialog({
    title: "New Conversation",
    text: project ? `Titel der Konversation in „${project.name}“:` : "Titel der Konversation:",
    value: "Neue Unterhaltung",
    okLabel: "Erstellen",
    onSubmit: async (title) => {
      const data = await api("POST", "/api/conversation/new", {
        title,
        project_id: projectId,
      });
      showHistory(data.messages);
      layout.classList.remove("sidebar-open");
      applyState(data);
    },
  });
}

function renameProject(project) {
  openDialog({
    title: "Rename Project",
    text: "Neuer Name:",
    value: project.name,
    okLabel: "Umbenennen",
    onSubmit: async (name) => {
      applyState(await api("POST", "/api/project/rename", { project_id: project.id, name }));
    },
  });
}

function deleteProject(project) {
  openDialog({
    title: "Delete Project",
    text: `Projekt „${project.name}“ löschen? Alle Konversationen darin werden ebenfalls gelöscht.`,
    okLabel: "Löschen",
    danger: true,
    onSubmit: async () => {
      const wasActive = active.project_id === project.id;
      const data = await api("POST", "/api/project/delete", { project_id: project.id });
      if (wasActive) showHistory([]);
      applyState(data);
    },
  });
}

function renameConversation(project, conversation) {
  openDialog({
    title: "Rename Conversation",
    text: "Neuer Titel:",
    value: conversation.title,
    okLabel: "Umbenennen",
    onSubmit: async (title) => {
      applyState(
        await api("POST", "/api/conversation/rename", {
          project_id: project.id,
          conversation_id: conversation.id,
          title,
        })
      );
    },
  });
}

function resetConversation(project, conversation) {
  openDialog({
    title: "Reset Conversation",
    text: `Alle Nachrichten in „${conversation.title}“ löschen? Die Konversation bleibt bestehen.`,
    okLabel: "Zurücksetzen",
    danger: true,
    onSubmit: async () => {
      const wasActive = active.conversation_id === conversation.id;
      const data = await api("POST", "/api/conversation/reset", {
        project_id: project.id,
        conversation_id: conversation.id,
      });
      if (wasActive) showHistory([]);
      applyState(data);
    },
  });
}

function deleteConversation(project, conversation) {
  openDialog({
    title: "Delete Conversation",
    text: `Konversation „${conversation.title}“ löschen?`,
    okLabel: "Löschen",
    danger: true,
    onSubmit: async () => {
      const wasActive = active.conversation_id === conversation.id;
      const data = await api("POST", "/api/conversation/delete", {
        project_id: project.id,
        conversation_id: conversation.id,
      });
      if (wasActive) showHistory([]);
      applyState(data);
    },
  });
}

newProjectButton.addEventListener("click", newProject);
newConversationButton.addEventListener("click", () => newConversation());
// Schmales Fenster: Leiste schiebt sich ueber den Chat. Breites Fenster: Leiste klappt ein und
// aus, und der Zustand bleibt beim naechsten Oeffnen erhalten.
const narrowForSidebar = window.matchMedia("(max-width: 720px)");

// Schmal: ein Klick neben die Leiste (oder Esc) schiebt sie wieder weg, sie verdeckt ja den Knopf
document.addEventListener("pointerdown", (event) => {
  if (!layout.classList.contains("sidebar-open")) return;
  if (sidebar.contains(event.target) || menuButton.contains(event.target)) return;
  layout.classList.remove("sidebar-open");
});
document.addEventListener("keydown", (event) => { if (event.key === "Escape") layout.classList.remove("sidebar-open"); });

try {
  if (localStorage.getItem("jarvis.sidebar") === "collapsed") layout.classList.add("sidebar-collapsed");
} catch (error) { /* ohne Speicher bleibt die Leiste offen */ }

menuButton.setAttribute("aria-expanded", String(!layout.classList.contains("sidebar-collapsed")));

menuButton.addEventListener("click", () => {
  if (narrowForSidebar.matches) {
    layout.classList.toggle("sidebar-open");
    return;
  }
  const collapsed = layout.classList.toggle("sidebar-collapsed");
  menuButton.setAttribute("aria-expanded", String(!collapsed));
  try { localStorage.setItem("jarvis.sidebar", collapsed ? "collapsed" : "open"); } catch (error) { /* egal */ }
});

// ======================================================================
// Einstellungen
// ======================================================================

const settingsDialog = document.getElementById("settings");
const settingsNav = document.getElementById("settings-nav");
const settingsTitle = document.getElementById("settings-title");
const settingsDesc = document.getElementById("settings-desc");
const settingsRows = document.getElementById("settings-rows");
const settingsError = document.getElementById("settings-error");

let settings = {};
let about = { version: "", system: "" };
let abilitiesInfo = [];
let usageInfo = null;
let currentPage = "Appearance";

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
      { label: "Middle widget", category: "widgets", key: "middle", type: "select", options: ["Off", "Notes", "Goals"], live: true,
        note: "Notizen, Ziele und Kalender-Termine liegen in der Datei widgets.json auf deinem Rechner. Ziele gelten nur für den heutigen Tag, außer du markierst sie mit ↻ als täglich." },
      { label: "Bottom widget", category: "widgets", key: "bottom", type: "select", options: ["Off", "Edmonton Oilers", "Adler Mannheim"], live: true,
        note: "Das laufende oder letzte Spiel und die nächsten (Oilers: vier, Mannheim: drei). Oilers: öffentliche NHL-Schnittstelle, mit Ergebnissen. Mannheim: offizielle Kalenderdatei der Adler, nur Paarungen und Termine, keine Ergebnisse. Nur der Server ruft sie auf, höchstens alle 5 Minuten." },
      { label: "Fourth widget", category: "widgets", key: "fourth", type: "select", options: ["Off", "PC Facts", "Performance"], live: true,
        note: "PC Facts: System, Prozessor, Kerne, Arbeitsspeicher und Laufwerke. Performance: CPU, RAM, Laufwerk, Akku (falls vorhanden) und Netzwerk, alle 2 Sekunden. Beides liest nur dein Rechner, es geht nichts ins Internet." },
      { label: "Fifth widget", category: "widgets", key: "fifth", type: "select", options: ["Off", "PC Facts", "Performance"], live: true },
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

function applyAppearance() {
  const theme = (settings.appearance && settings.appearance.theme) || "Dark";
  const size = settings.appearance && settings.appearance.font_size;
  const light =
    theme === "Light" || (theme === "System" && matchMedia("(prefers-color-scheme: light)").matches);

  if (light) document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;

  const green = settings.appearance && settings.appearance.accent_color === "British Racing Green";
  if (green) document.documentElement.dataset.accent = "green";
  else delete document.documentElement.dataset.accent;

  if (Number.isInteger(size) && size >= 11 && size <= 20) {
    document.documentElement.style.fontSize = size + "px";
  }

  try {
    localStorage.setItem("jarvis.theme", theme);
    localStorage.setItem("jarvis.accent", green ? "green" : "blue");
    if (Number.isInteger(size)) localStorage.setItem("jarvis.fontsize", String(size));
  } catch (error) {
    /* ohne Speicher funktioniert die Seite trotzdem */
  }
}

matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyAppearance);

function applySettingsState(data) {
  settings = data.settings;
  about = data.about;
  abilitiesInfo = Array.isArray(data.abilities) ? data.abilities : [];
  usageInfo = data.usage || null;
  guestMode = data.guest === true;
  document.body.classList.toggle("guest", guestMode);
  if (guestMode) setStatus("ready", "GAST");
  applyAppearance();
  applyVoice();
  applyWidgets();
}

async function loadSettings() {
  try {
    applySettingsState(await api("GET", "/api/settings"));
  } catch (error) {
    /* Standard-Design bleibt */
  }
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
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function smallButton(label, className, onClick) {
  const button = el("button", className, label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

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
const dangerDialog = document.getElementById("memory-danger");
const dangerText = document.getElementById("danger-text");
const dangerPhrase = document.getElementById("danger-phrase");
const dangerCheck = document.getElementById("danger-check");
const dangerInput = document.getElementById("danger-input");
const dangerError = document.getElementById("danger-error");
const dangerOk = document.getElementById("danger-ok");
let dangerTimer = null;
let dangerSubmit = null;
let dangerUpdate = () => {};

dangerCheck.addEventListener("change", () => dangerUpdate());
dangerInput.addEventListener("input", () => dangerUpdate());
dangerInput.addEventListener("paste", (event) => event.preventDefault());
dangerInput.addEventListener("drop", (event) => event.preventDefault());
document.getElementById("danger-cancel").addEventListener("click", () => dangerDialog.close());
dangerDialog.addEventListener("close", () => {
  clearInterval(dangerTimer);
  dangerInput.value = "";
  dangerCheck.checked = false;
  dangerSubmit = null;
  dangerUpdate = () => {};
});
document.getElementById("danger-form").addEventListener("submit", async (event) => {
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

document.getElementById("open-settings").addEventListener("click", async () => {
  layout.classList.remove("sidebar-open");
  await loadSettings();
  renderSettings();
  settingsDialog.showModal();
});
document.getElementById("settings-close").addEventListener("click", () => settingsDialog.close());

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
// Laufende Timer (Step 6b): kleine Leiste ueber dem Eingabefeld
// ----------------------------------------------------------------------

const timersBar = document.getElementById("timers");
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

loadSettings().finally(() => { showStartupReport(); refreshTree(); refreshTimers(); });
