"use strict";

// Element nach id. Fehlt es auf dieser Seite (z. B. gibt es in guest.html keine Projekte und kein Gedaechtnis),
// bekommt der Code ein loses Ersatz-Element, das nie angezeigt wird. So braucht jede Rollen-Seite nur, was sie wirklich zeigt.
const STUB_TAGS = { dialog: "dialog", settings: "dialog", "memory-danger": "dialog", "phone-prefs": "dialog",
  "dialog-input": "input", "danger-input": "input", "danger-check": "input", "danger-form": "form", "dialog-form": "form" };
function byId(id) {
  return document.getElementById(id) || document.createElement(STUB_TAGS[id] || "div");
}

const layout = byId("layout");
const sidebar = byId("sidebar");
const tree = byId("tree");
const newConversationButton = byId("new-conversation");
const newProjectButton = byId("new-project");
const menuButton = byId("menu-button");
const menuEl = byId("menu");
const chat = byId("chat");
const input = byId("input");
const sendButton = byId("send");
const composer = byId("composer");
const statusEl = byId("status");

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
let testerMode = false;     // Testbereich eines Gastes (nur ueber Remote): eigene Daten, keine Projekte
let remoteMode = false;     // Seite wird ueber Remote (Handy) benutzt: eingeschraenkt, siehe remote_mode.js
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

// Aktionen, die die offene Konversation aendern: danach merkt sich der Live-Abgleich den neuen Stand nur
const OWN_CHANGE_PATHS = ["/api/message", "/api/confirm", "/api/plan/", "/api/conversation/", "/api/project/"];
let syncControl = null;

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

  if (method === "POST" && syncControl && OWN_CHANGE_PATHS.some((prefix) => path.startsWith(prefix))) {
    syncControl.markOwnChange();
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
    refreshCore();
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
const micButton = byId("mic");
const stopButton = byId("stop");

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
  // Der Browser erlaubt nur eine Spracherkennung zugleich: der Weckwort-Zuhoerer macht Platz
  wake.setActive(false);
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
    onError: (code) => addMessage("error", window.JarvisVoice.describeSpeechError(code)),
  }, voiceSetting("input_language"));
  if (!started) { commandListening = false; refreshWake(); }
  updateWakeBadge();
}

function micDown(event) {
  if (event.repeat) return;
  listenOnce(false);
}

// ---- Weckwort "Jarvis" (siehe wake.js): nur wenn eingeschaltet, nie im Gastmodus
const wakeBadge = byId("wake");
let commandListening = false;
let wakeListening = false;

const wake = window.JarvisWake.createWakeListener({
  Recognition: window.SpeechRecognition || window.webkitSpeechRecognition,
  onState: (state) => { wakeListening = state === "listening"; updateWakeBadge(); },
  onWake: handleWake,
  onError: (code) => {
    addMessage("error", "Das Weckwort funktioniert gerade nicht. " + window.JarvisVoice.describeSpeechError(code) + " Du kannst es in den Einstellungen unter Voice aus- und wieder einschalten.");
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
  const wanted = voiceSetting("wake_word") === true && !guestMode && !remoteMode && !ended && wake.canListen() &&
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

micButton.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  // Der Knopf behaelt den Zeiger, auch wenn er beim Halten leicht wegrutscht (sonst endet die Aufnahme sofort)
  try { micButton.setPointerCapture(event.pointerId); } catch (error) { /* ohne Capture gilt pointerleave */ }
  micDown(event);
});
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

const widgetsEl = byId("widgets");
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
  const choice = (settings.widgets || {})[slot] || "Off";
  return remoteMode && !window.JarvisRemoteMode.widgetAllowed(choice) ? "Off" : choice;
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
  let alarmsByDay = {};
  let alarmLoading = false;

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
  // Wecker direkt im Kalender stellen (Step 2.11b): klappt unter dem Termin-Formular auf, gilt fuer den gewaehlten Tag
  const alarmToggle = wEl("button", "w-alarm-toggle", "⏰ Wecker stellen");
  const alarmForm = wEl("form", "w-alarm-form w-alarm-new");
  const aTime = wEl("input", "w-event-time");
  const aName = wEl("input", "w-event-title");
  const aRepeat = wEl("select", "w-alarm-repeat");
  const aUntil = wEl("input", "w-event-time w-alarm-until");
  const aBriefLabel = wEl("label", "w-alarm-brieflabel");
  const aBrief = wEl("input", "w-alarm-brief");
  const aSave = wEl("button", "w-goal-add", "＋");
  alarmToggle.type = "button"; alarmToggle.setAttribute("aria-expanded", "false");
  alarmForm.hidden = true;
  aTime.type = "time"; aTime.required = true; aTime.setAttribute("aria-label", "Uhrzeit des Weckers");
  aName.type = "text"; aName.maxLength = 40; aName.placeholder = "Name (optional)"; aName.setAttribute("aria-label", "Name des Weckers");
  [["", "Einmalig"], ["daily", "Täglich"], ["weekdays", "Werktags (Mo–Fr)"], ["weekly", "Jede Woche"]].forEach(([value, text]) => {
    const option = wEl("option", "", text); option.value = value; aRepeat.append(option);
  });
  aRepeat.setAttribute("aria-label", "Wiederholung");
  aUntil.type = "date"; aUntil.hidden = true; aUntil.setAttribute("aria-label", "Wiederholen bis (optional)"); aUntil.title = "Letzter Tag (leer = ohne Ende)";
  aBrief.type = "checkbox"; aBrief.checked = true;
  aBriefLabel.append(aBrief, " Briefing");
  aSave.type = "submit"; aSave.setAttribute("aria-label", "Wecker anlegen");
  alarmForm.append(aTime, aRepeat, aUntil, aName, aBriefLabel, aSave);
  section.append(head, grid, dayHead, list, form, alarmToggle, alarmForm, status);
  alarmToggle.addEventListener("click", () => {
    alarmForm.hidden = !alarmForm.hidden;
    alarmToggle.setAttribute("aria-expanded", String(!alarmForm.hidden));
    if (!alarmForm.hidden) aTime.focus();
  });
  aRepeat.addEventListener("change", () => { aUntil.hidden = aRepeat.value === ""; if (aUntil.hidden) aUntil.value = ""; });
  alarmForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const body = { time: aTime.value, label: aName.value, date: selected, repeat: aRepeat.value, until: aUntil.value, briefing: aBrief.checked };
      setAlarms((await api("POST", "/api/alarms/add", body)).alarms);
      aTime.value = ""; aName.value = ""; aRepeat.value = ""; aUntil.value = ""; aUntil.hidden = true; status.textContent = "";
    } catch (error) { status.textContent = error.message; }
  });

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
      if (alarmsByDay[key]) {
        cell.classList.add("has-alarm");
        const wakeups = alarmsByDay[key].map((a) => "⏰ " + a.time + " " + a.label).join("\n");
        cell.title = (cell.title ? cell.title + "\n" : "") + wakeups;
      }
      cell.addEventListener("click", () => { selected = key; drawGrid(); drawDay(); });
      grid.append(cell);
    });
  }

  function drawDay() {
    dayHead.textContent = W.formatDayLong(selected);
    list.replaceChildren();
    const events = byDate[selected] || [];
    const alarms = alarmsByDay[selected] || [];
    if (!events.length && !alarms.length) list.append(wEl("li", "w-muted", "Keine Termine."));
    events.forEach((event) => {
      const item = wEl("li", event.source === "apple" ? "w-event w-event-apple" : "w-event");
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
      if (event.source === "apple") {
        const badge = wEl("span", "w-event-cal", event.calendar || "Apple");
        badge.title = event.readonly ? "Aus dem Apple-Kalender – am Handy ändern" : "Apple-Kalender (auch am Handy)";
        item.append(badge);
      }
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
      if (!event.readonly) item.append(remove);
      list.append(item);
    });
    alarms.forEach((alarm) => list.append(alarmItem(alarm)));
  }

  // Wecker (Step 2.11b): neben den Terminen sichtbar, mit Bearbeiten (✎) und Loeschen (×)
  function alarmItem(alarm) {
    const item = wEl("li", "w-event w-alarm");
    const when = wEl("span", "w-event-when", "⏰ " + alarm.time);
    const text = wEl("span", "w-event-text", (alarm.repeat ? "↻ " : "") + alarm.label);
    if (alarm.repeat) text.title = alarm.repeat;
    const edit = wEl("button", "w-goal-remove w-alarm-edit", "✎");
    const remove = wEl("button", "w-goal-remove", "×");
    edit.type = "button"; remove.type = "button";
    edit.title = "Wecker bearbeiten"; edit.setAttribute("aria-label", "Wecker bearbeiten: " + alarm.label);
    remove.title = alarm.repeat ? "Ganzen Wecker löschen (" + alarm.repeat + ")" : "Wecker löschen";
    remove.setAttribute("aria-label", "Wecker löschen: " + alarm.label);

    // Ein Wecker mit Wiederholung verschwindet ganz: erst nach einem zweiten Klick
    let armed = null;
    remove.addEventListener("click", async () => {
      if (alarm.repeat && !armed) {
        remove.textContent = "✓?";
        remove.classList.add("armed");
        status.textContent = "Noch einmal klicken: der ganze Wecker (" + alarm.repeat + ") wird gelöscht.";
        armed = setTimeout(() => { armed = null; remove.textContent = "×"; remove.classList.remove("armed"); status.textContent = ""; }, 4000);
        return;
      }
      clearTimeout(armed);
      try {
        setAlarms((await api("POST", "/api/alarms/delete", { id: alarm.id })).alarms);
        status.textContent = "";
      } catch (error) {
        status.textContent = error.message; armed = null; remove.textContent = "×"; remove.classList.remove("armed");
      }
    });

    edit.addEventListener("click", () => {
      const form = wEl("form", "w-alarm-form");
      const time = wEl("input", "w-event-time");
      const name = wEl("input", "w-event-title");
      const brief = wEl("input", "w-alarm-brief");
      const briefLabel = wEl("label", "w-alarm-brieflabel");
      const save = wEl("button", "w-goal-add", "✓");
      const cancel = wEl("button", "w-goal-remove", "✕");
      time.type = "time"; time.required = true; time.value = alarm.time; time.setAttribute("aria-label", "Uhrzeit");
      name.type = "text"; name.maxLength = 40; name.value = alarm.label; name.setAttribute("aria-label", "Name");
      brief.type = "checkbox"; brief.checked = alarm.briefing;
      briefLabel.append(brief, " Briefing");
      save.type = "submit"; save.setAttribute("aria-label", "Speichern");
      cancel.type = "button"; cancel.setAttribute("aria-label", "Abbrechen");
      form.append(time, name, briefLabel, save, cancel);
      item.replaceChildren(form);
      time.focus();
      cancel.addEventListener("click", () => { status.textContent = ""; drawDay(); });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          setAlarms((await api("POST", "/api/alarms/update", { id: alarm.id, time: time.value, label: name.value, briefing: brief.checked })).alarms);
          status.textContent = "";
        } catch (error) { status.textContent = error.message; }
      });
    });

    item.append(when, text, edit, remove);
    return item;
  }

  function setAlarms(alarms) {
    alarmsByDay = W.alarmsByDate(alarms);
    drawGrid();
    drawDay();
  }

  async function refreshAlarms() {
    if (alarmLoading) return;
    alarmLoading = true;
    try { setAlarms((await api("GET", "/api/alarms")).alarms); } catch (error) { /* naechste Runde */ } finally { alarmLoading = false; }
  }

  function update(data) {
    byDate = W.eventsByDate(data.events);
    // Apple-Kalender (Step 2.19): wohin neue Termine gehen, und ein Hinweis, wenn die Verbindung gerade nicht klappt
    const sync = data.sync;
    field.placeholder = sync && sync.can_write ? "Termin → " + sync.write_calendar + " …" : "Termin …";
    if (sync && sync.enabled && !sync.ok && sync.error) status.textContent = "Apple-Kalender: " + sync.error;
    drawGrid();
    drawDay();
    refreshAlarms();
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
  const modes = wEl("div", "w-note-modes");
  const others = wEl("div", "w-note-others");
  area.rows = 7;
  area.maxLength = 5000;
  section.append(wEl("h3", "w-title", "Notizen"));

  // Am Handy: "Allgemein" (fuer alle Geraete) oder "Nur dieses Gerät" (nur hier bearbeitet, der PC zeigt sie an)
  let mode = "shared";
  const buttons = {};
  if (remoteMode) {
    try { if (localStorage.getItem("jarvis.remote.notemode") === "device") mode = "device"; } catch (error) { /* ohne Speicher: allgemein */ }
    [["shared", "Allgemein"], ["device", "Nur dieses Gerät"]].forEach(([key, label]) => {
      const button = wEl("button", "w-note-mode", label);
      button.type = "button";
      button.addEventListener("click", () => switchMode(key));
      buttons[key] = button;
      modes.append(button);
    });
    section.append(modes);
  }
  section.append(area, status, others);

  let loaded = false;
  let timer = null;

  function label() {
    return mode === "device" ? "Notiz nur für dieses Gerät …" : "Notizen …";
  }

  function currentText(data) {
    return mode === "device" ? (data.device_note || "") : data.notes;
  }

  function showModes() {
    Object.keys(buttons).forEach((key) => {
      buttons[key].classList.toggle("on", key === mode);
      buttons[key].setAttribute("aria-pressed", String(key === mode));
    });
    area.placeholder = label();
    area.setAttribute("aria-label", mode === "device" ? "Notiz nur für dieses Gerät" : "Notizen");
  }

  // Am PC: die Notizen der Handys, nur lesen (bearbeitet werden sie nur auf dem jeweiligen Handy)
  function showOthers(data) {
    others.replaceChildren();
    (Array.isArray(data.device_notes) ? data.device_notes : []).forEach((note) => {
      others.append(wEl("h4", "w-note-from", "Notiz von " + note.name), wEl("div", "w-note-text", note.text));
    });
  }

  async function save() {
    clearTimeout(timer);
    timer = null;
    const saving = mode;
    try {
      const data = await api("POST", saving === "device" ? "/api/widgets/device_note" : "/api/widgets/notes", { text: area.value });
      widgetData = data;
      status.textContent = "Gespeichert";
    } catch (error) {
      status.textContent = "Nicht gespeichert: " + error.message;
    }
  }

  async function switchMode(key) {
    if (key === mode) return;
    if (timer) await save();                 // erst die offene Eingabe in die richtige Notiz schreiben
    mode = key;
    try { localStorage.setItem("jarvis.remote.notemode", key); } catch (error) { /* ohne Speicher gilt es nur bis zum Neuladen */ }
    showModes();
    area.value = widgetData ? currentText(widgetData) : "";
    status.textContent = "";
  }

  area.addEventListener("input", () => {
    if (!loaded) return;
    status.textContent = "…";
    clearTimeout(timer);
    timer = setTimeout(save, 700);
  });
  area.addEventListener("blur", () => { if (timer) save(); });

  // Aenderungen von aussen (anderes Geraet) uebernehmen, aber nie mitten in einer Eingabe
  registerRefresher(section, (data) => {
    if (!loaded || timer || document.activeElement === area) return;
    area.value = currentText(data);
    showOthers(data);
  });

  showModes();
  area.disabled = true;
  loadWidgetData().then((data) => { area.value = currentText(data); showOthers(data); area.disabled = false; loaded = true; })
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
  const weekBar = wEl("div", "w-week");
  section.append(wEl("h3", "w-title", "Ziele heute"), list, form,
    wEl("div", "w-status w-muted", "↻ = täglich wiederkehrend, 🔥 = Tage in Folge"), weekBar, status);

  let goals = [];
  let week = [];

  // Letzte 7 Tage: wie viele der taeglichen Ziele erledigt waren (nur wenn es welche gab)
  function drawWeek() {
    weekBar.replaceChildren();
    if (!week.some((d) => d.total > 0)) return;
    week.forEach((d) => {
      const names = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
      const cell = wEl("div", "w-week-day" + (d.total && d.done === d.total ? " full" : ""));
      cell.append(wEl("span", "w-week-name", names[new Date(d.date + "T12:00:00").getDay()]),
        wEl("span", "w-week-count", d.total ? d.done + "/" + d.total : "–"));
      cell.title = d.date + ": " + (d.total ? d.done + " von " + d.total + " täglichen Zielen erledigt" : "keine täglichen Ziele");
      weekBar.append(cell);
    });
  }

  function apply(data) { goals = data.goals; week = data.week || []; draw(); }

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
      const streak = goal.daily && goal.streak > 0
        ? wEl("span", "w-streak", "🔥 " + goal.streak) : null;
      if (streak) streak.title = goal.streak + (goal.streak === 1 ? " Tag" : " Tage") + " in Folge erledigt";
      item.append(box, wEl("span", "w-goal-text", goal.text), ...(streak ? [streak] : []), repeat, remove);
      list.append(item);
    });
    drawWeek();
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
      if (queued === 0 && data) apply(data);
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

  loadWidgetData(true).then(apply)
    .catch((error) => { status.textContent = error.message; });
  // Neuer Tag oder Aenderung von aussen: Liste neu laden (Eingabefeld bleibt unberuehrt)
  registerRefresher(section, apply);
}

// ---- Listen (Step 2.30): Einkauf, Packen, ... Jarvis setzt auf Zuruf Eintraege darauf, hier aenderst du alles von Hand
function renderLists(section) {
  const picker = wEl("select", "w-list-picker");
  const removeList = wEl("button", "w-goal-remove", "🗑");
  const head = wEl("div", "w-list-head");
  const count = wEl("span", "w-list-count w-muted");
  const list = wEl("ul", "w-goals");
  const form = wEl("form", "w-goal-form");
  const field = wEl("input", "w-goal-input");
  const add = wEl("button", "w-goal-add", "＋");
  const newForm = wEl("form", "w-goal-form");
  const newField = wEl("input", "w-goal-input");
  const newAdd = wEl("button", "w-goal-add", "＋ Liste");
  const status = wEl("div", "w-status w-muted", "");
  picker.setAttribute("aria-label", "Liste wählen");
  removeList.type = "button";
  removeList.title = "Diese Liste löschen (zweimal klicken)";
  removeList.setAttribute("aria-label", "Liste löschen");
  head.append(picker, count, removeList);
  field.type = "text"; field.maxLength = 100; field.placeholder = "Neuer Eintrag …"; field.setAttribute("aria-label", "Neuer Eintrag");
  add.type = "submit"; add.setAttribute("aria-label", "Eintrag hinzufügen");
  form.append(field, add);
  newField.type = "text"; newField.maxLength = 40; newField.placeholder = "Neue Liste (z. B. Einkauf) …"; newField.setAttribute("aria-label", "Name der neuen Liste");
  newAdd.type = "submit";
  newForm.append(newField, newAdd);
  section.append(wEl("h3", "w-title", "Listen"), head, list, form, newForm, status);

  let lists = [];
  let selected = 0;
  let armed = false;

  function draw() {
    if (selected >= lists.length) selected = Math.max(0, lists.length - 1);
    picker.replaceChildren();
    lists.forEach((l, index) => {
      const option = wEl("option", "", l.name);       // nur der Name: die Zahl der offenen Eintraege steht daneben und aendert den Namen nicht
      option.value = String(index);
      picker.append(option);
    });
    picker.value = String(selected);
    const openCount = lists.length ? lists[selected].items.filter((i) => !i.done).length : 0;
    count.textContent = openCount ? openCount + " offen" : "";
    head.hidden = form.hidden = !lists.length;
    armed = false;
    removeList.textContent = "🗑";
    list.replaceChildren();
    if (!lists.length) { list.append(wEl("li", "w-muted", "Noch keine Liste. Lege unten eine an oder sag Jarvis: „Setz Milch auf die Einkaufsliste“.")); return; }
    const items = lists[selected].items;
    if (!items.length) list.append(wEl("li", "w-muted", "Diese Liste ist leer."));
    items.forEach((item, index) => {
      const row = wEl("li", "w-goal" + (item.done ? " done" : ""));
      const box = wEl("input");
      box.type = "checkbox";
      box.checked = item.done;
      box.setAttribute("aria-label", item.text);
      box.addEventListener("change", () => { item.done = box.checked; persist(); });
      const remove = wEl("button", "w-goal-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", "Eintrag löschen");
      remove.addEventListener("click", () => { items.splice(index, 1); persist(); });
      row.append(box, wEl("span", "w-goal-text", item.text), remove);
      list.append(row);
    });
  }

  let saving = Promise.resolve();
  let queued = 0;

  function persist() {
    draw();
    queued += 1;
    saving = saving.then(async () => {
      let data = null;
      try {
        data = await api("POST", "/api/widgets/lists", { lists });
        widgetData = data;
        status.textContent = "";
      } catch (error) {
        status.textContent = "Nicht gespeichert: " + error.message;
      }
      queued -= 1;
      if (queued === 0 && data) { lists = data.lists; draw(); }
    });
  }

  picker.addEventListener("change", () => { selected = Number(picker.value); draw(); });
  removeList.addEventListener("click", () => {
    if (!armed) {
      armed = true;
      removeList.textContent = "Sicher?";
      setTimeout(() => { if (armed) { armed = false; removeList.textContent = "🗑"; } }, 3000);
      return;
    }
    lists.splice(selected, 1);
    persist();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = field.value.trim();
    if (!text || !lists.length) return;
    lists[selected].items.push({ text, done: false });
    field.value = "";
    persist();
  });
  newForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = newField.value.trim();
    if (!name) return;
    lists.push({ name, items: [] });
    selected = lists.length - 1;
    newField.value = "";
    persist();
  });

  loadWidgetData(true).then((data) => { lists = data.lists || []; draw(); })
    .catch((error) => { status.textContent = error.message; });
  // Jarvis hat per Chat etwas eingetragen: neu laden (Eingabefelder bleiben unberuehrt)
  registerRefresher(section, (data) => { lists = data.lists || []; draw(); });
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
  Notes: renderNotes, Goals: renderGoals, Lists: renderLists,
  "Edmonton Oilers": (section) => renderHockey(section, "Oilers"),
  "Adler Mannheim": (section) => renderHockey(section, "Adler Mannheim"),
};

// Schmales Fenster: die Leiste ist ausgeblendet und laesst sich ueber den Knopf oben aufklappen
const widgetsButton = byId("widgets-button");
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
    const section = byId("widget-" + slot);
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

const dialog = byId("dialog");
const dialogForm = byId("dialog-form");
const dialogTitle = byId("dialog-title");
const dialogText = byId("dialog-text");
const dialogInput = byId("dialog-input");
const dialogError = byId("dialog-error");
const dialogOk = byId("dialog-ok");
const dialogCancel = byId("dialog-cancel");

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
  if (remoteMode) return;        // Umbenennen, Loeschen, Zuruecksetzen gibt es nur am PC
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

  if (testerMode) {
    // Im Testbereich gibt es keine Projekte: nur "Neue Unterhaltung" und ein Hinweis
    newConversationButton.disabled = false;
    newConversationButton.title = "Beginnt eine neue, leere Unterhaltung";
    tree.appendChild(el("p", "empty-hint", window.JarvisRemoteMode.testerSidebarView(true).hint));
    return;
  }

  newConversationButton.disabled = active.project_id === null;
  newConversationButton.title =
    active.project_id === null ? "Öffne zuerst eine Konversation in einem Projekt" : "";

  if (projects.length === 0) {
    const hint = document.createElement("p");
    hint.className = "empty-hint";
    hint.textContent = remoteMode
      ? "Noch keine Projekte. Lege sie am PC an."
      : "Noch keine Projekte. Lege mit „New Project“ eins an.";
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
async function newConversation(project) {
  if (testerMode) {
    // Eigene Unterhaltung leeren, ohne Titel und Projekt
    try {
      const data = await api("POST", "/api/conversation/new", {});
      showHistory(data.messages);
      layout.classList.remove("sidebar-open");
      applyState(data);
    } catch (error) {
      addMessage("error", error.message);
    }
    return;
  }
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