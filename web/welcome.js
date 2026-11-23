// Willkommensseite: Begruessung, Uhr, Verbindungsanzeige, Fenster (Anordnung, Daten, Auswahl) und der weiche Uebergang zur App.
// Das Logo ist ein Link auf index.html, also kommt man auch ohne dieses Skript in die App.
// Reihenfolge der Skripte (siehe welcome.html): widgets.js, welcome_logic.js, welcome_panels.js, welcome_dialogs.js, welcome_app.js, dann diese Datei.
(function () {
  "use strict";

  const L = window.WelcomeLogic;
  const $ = (id) => document.getElementById(id);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---- gemeinsamer Kern (Daten, Zustand, grosse Fenster), siehe welcome_app.js
  const app = window.WelcomeApp.create({
    layer: $("layer"),
    draw: () => drawPanels(),
    drawPanel: (id) => drawPanel(id),
    render: () => renderColumns(),
    onOnline(ok) {
      const status = $("status");
      status.classList.toggle("ok", ok);
      status.classList.toggle("bad", !ok);
      $("status-text").textContent = ok ? "Systeme bereit" : "Jarvis-Server nicht erreichbar";
    },
    onAddress: () => showGreeting(),
  });
  const loadWidgets = app.loadWidgets;
  const loadSettings = app.loadSettings;

  const dialogs = window.WelcomeDialogs.create(app);
  const panels = window.WelcomePanels.create(app);
  const opener = {};
  Object.keys(panels).forEach((id) => { opener[id] = dialogs[id]; });

  // ---- Fenster auf der Seite
  const panelBodies = {};       // id -> { section, extra, body }

  function makePanel(id) {
    const def = panels[id];
    const section = el("section", "panel");
    section.tabIndex = 0;
    section.setAttribute("role", "button");
    section.setAttribute("aria-label", def.title + " öffnen");
    const h2 = el("h2");
    const extra = el("em");
    h2.append(el("span", "", def.title), extra);
    const body = el("div");
    section.append(h2, body);
    const open = () => opener[id]();
    section.addEventListener("click", open);
    section.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
    panelBodies[id] = { section, extra, body };
    return section;
  }

  function drawPanel(id) {
    const part = panelBodies[id];
    if (!part) return;
    part.extra.textContent = panels[id].extra();
    part.body.replaceChildren();
    panels[id].draw(part.body);
  }

  function drawPanels() { Object.keys(panelBodies).forEach(drawPanel); }

  function renderColumns() {
    Object.keys(panelBodies).forEach((id) => delete panelBodies[id]);
    const cols = L.splitColumns(app.enabled);
    [["col-l", cols.left], ["col-r", cols.right]].forEach(([id, ids]) => {
      const column = $(id);
      column.replaceChildren(...ids.map(makePanel));
      column.classList.toggle("compact", L.isCompact(ids.length));
    });
    app.compact = L.isCompact(Math.max(cols.left.length, cols.right.length));
    drawPanels();
  }

  // ---- Begruessung, Uhr, Datum
  function showGreeting() {
    $("greeting").textContent = L.greetingWord(new Date().getHours()) + ", " + app.address + ".";
  }

  function showClock() {
    const now = new Date();
    $("clock").textContent = now.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    $("date").textContent = now.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    showGreeting();
  }

  // ---- Klick auf den Kern: kurz ausblenden, dann zur App
  function leave(event) {
    const link = $("start");
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.button) return;   // neuer Tab o.ae.: normal verhalten
    event.preventDefault();
    const calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm) { location.href = link.href; return; }
    $("stage").classList.add("leaving");
    setTimeout(() => { location.href = link.href; }, 420);
  }

  // ---- Start
  app.init();
  renderColumns();
  app.loadNeeded(false);
  showClock();
  $("start").addEventListener("click", leave);
  $("date").addEventListener("click", () => dialogs.calendar());
  $("status").addEventListener("click", () => dialogs.manage());

  loadSettings();
  loadWidgets();
  app.loadTimers();

  let ticks = 0;
  setInterval(() => {
    if (document.hidden) return;
    ticks += 1;
    if (ticks % 15 === 0) showClock();
    if (ticks % 5 === 0) { app.loadTimers(); app.loadNeeded(true); }
    if (ticks % 300 === 0) app.loadNeeded(false);
    if (ticks % 30 === 0 && app.enabled.includes("worldtime")) drawPanel("worldtime");
    if (ticks % 30 === 0) loadWidgets();
    if (ticks % 600 === 0) loadSettings();
    if (app.focus.active || app.timers.length) drawPanel("focus");
    app.tickListeners.slice().forEach((fn) => fn());
  }, 1000);

  // Zurueck-Taste aus der App: Seite aus dem Zwischenspeicher wieder frisch zeigen
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) { $("stage").classList.remove("leaving"); loadWidgets(); app.loadTimers(); }
  });
})();