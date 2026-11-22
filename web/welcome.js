// Willkommensseite: Begruessung, Uhr, Verbindungsanzeige, Fenster (Anordnung, Daten, Auswahl) und der weiche Uebergang zur App.
// Das Logo ist ein Link auf index.html, also kommt man auch ohne dieses Skript in die App.
// Reihenfolge der Skripte (siehe welcome.html): widgets.js, welcome_logic.js, welcome_panels.js, welcome_dialogs.js, dann diese Datei.
(function () {
  "use strict";

  const L = window.WelcomeLogic;
  const W = window.JarvisWidgets;
  const $ = (id) => document.getElementById(id);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

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
    try { data = await response.json(); } catch (error) { /* Antwort ohne JSON */ }
    if (!response.ok) throw new Error(data.error || "Fehler " + response.status);
    return data;
  }

  // ---- gemeinsamer Zustand, den die Fenster benutzen
  const app = {
    L, W, el, api,
    local: L.isLocalHost(location.hostname),     // am PC: Termine eintragen erlaubt, ueber Remote nicht
    data: null,                                  // Antwort von /api/widgets (Termine, Ziele, Listen, ...)
    weather: null,                               // Wettersatz vom Server
    focus: { active: false },
    timers: [],
    fetchedAt: 0,                                // wann Fokus/Timer geholt wurden (damit sie lokal weiterzaehlen)
    enabled: [],
    extra: {},                                   // News, Briefing, Erinnerungen, PC-Werte: name -> { status: loading|ok|disabled|error, data, error }
    cities: [],                                  // gewaehlte Staedte der Weltuhr
    online: null,
    address: "Sir",
    dataListeners: [],
    tickListeners: [],
  };

  const elapsed = () => Math.floor((Date.now() - app.fetchedAt) / 1000);
  app.focusNow = () => (app.focus.active ? Object.assign({}, app.focus, { remaining: Math.max(0, app.focus.remaining - elapsed()) }) : { active: false });
  app.timersNow = () => app.timers.map((t) => Object.assign({}, t, { remaining: Math.max(0, t.remaining - elapsed()) }));

  function emit() {
    drawPanels();
    app.dataListeners.slice().forEach((fn) => fn());
  }
  app.setData = (data) => { app.data = data; emit(); };

  // ---- Auswahl der Fenster (pro Browser gespeichert)
  function loadEnabled() {
    try { return L.normalizeEnabled(JSON.parse(localStorage.getItem(L.STORAGE_KEY))); } catch (error) { return L.normalizeEnabled(null); }
  }
  app.setEnabled = (list) => {
    app.enabled = L.normalizeEnabled(list);
    try { localStorage.setItem(L.STORAGE_KEY, JSON.stringify(app.enabled)); } catch (error) { /* ohne Speicher gilt die Auswahl bis zum Neuladen */ }
    renderColumns();
    loadNeeded(false);
  };

  // ---- Weltuhr: gewaehlte Staedte (pro Browser gespeichert)
  function loadCities() {
    try { return L.normalizeCities(JSON.parse(localStorage.getItem(L.CITIES_KEY))); } catch (error) { return L.normalizeCities(null); }
  }
  app.setCities = (list) => {
    app.cities = L.normalizeCities(list);
    try { localStorage.setItem(L.CITIES_KEY, JSON.stringify(app.cities)); } catch (error) { /* gilt bis zum Neuladen */ }
    drawPanel("worldtime");
  };

  // ---- Daten vom Server fuer die Fenster News, Briefing, Erinnerungen, PC (nur wenn das Fenster an ist oder offen)
  const SOURCES = {
    news: { path: "/api/news", pick: (d) => d.items || [] },
    briefing: { path: "/api/briefing", pick: (d) => d.text || "" },
    reminders: { path: "/api/reminders", pick: (d) => d.reminders || [] },
    perf: { path: "/api/performance", pick: (d) => d },
  };
  const pending = {};
  app.loadExtra = async (name, force) => {
    const source = SOURCES[name];
    if (!source || pending[name]) return;
    if (!force && app.extra[name] && app.extra[name].status === "ok") return;
    pending[name] = true;
    if (!app.extra[name]) app.extra[name] = { status: "loading" };
    try {
      const data = await api("GET", source.path);
      app.extra[name] = data.disabled ? { status: "disabled" } : { status: "ok", data: source.pick(data) };
    } catch (error) {
      app.extra[name] = { status: "error", error: error.message };
    }
    pending[name] = false;
    emit();
  };
  // welche Quellen ein eingeschaltetes Fenster braucht
  const NEEDS = { news: "news", briefing: "briefing", reminders: "reminders", system: "perf" };
  function loadNeeded(onlyLive) {
    app.enabled.forEach((id) => {
      const name = NEEDS[id];
      if (!name || (id === "system" && !app.local)) return;
      if (onlyLive && name !== "perf") return;
      app.loadExtra(name, name === "perf");
    });
  }

  // ---- Musiktasten und Lautstaerke (nur am PC); gibt einen Hinweistext zurueck, wenn es nicht klappt
  app.media = async (action) => {
    try { await api("POST", "/api/media", { action }); return ""; } catch (error) { return error.message; }
  };
  app.setVolume = async (percent) => {
    try { await api("POST", "/api/volume", { percent }); return "Lautstärke " + percent + " %."; } catch (error) { return error.message; }
  };

  // ---- Daten holen
  function setOnline(ok) {
    if (app.online === ok) return;
    app.online = ok;
    const status = $("status");
    status.classList.toggle("ok", ok);
    status.classList.toggle("bad", !ok);
    $("status-text").textContent = ok ? "Systeme bereit" : "Jarvis-Server nicht erreichbar";
  }

  async function loadWidgets() {
    try { app.data = await api("GET", "/api/widgets"); setOnline(true); emit(); } catch (error) { setOnline(false); }
  }
  app.loadTimers = async () => {
    try {
      const [timers, focus] = await Promise.all([api("GET", "/api/timers"), api("GET", "/api/focus")]);
      app.timers = Array.isArray(timers.timers) ? timers.timers : [];
      app.focus = focus && focus.active ? focus : { active: false };
      app.fetchedAt = Date.now();
      emit();
    } catch (error) { /* naechste Runde */ }
  };
  app.loadWeather = async () => {
    try { app.weather = (await api("GET", "/api/weather")).summary || null; } catch (error) { app.weather = null; }
    emit();
  };
  async function loadSettings() {
    try {
      const data = await api("GET", "/api/settings");
      const name = data && data.jarvis && typeof data.jarvis.address === "string" ? data.jarvis.address.trim() : "";
      if (name) app.address = name;
      setOnline(true);
      showGreeting();
    } catch (error) { setOnline(false); }
  }

  // ---- grosse Fenster
  let openLayer = null;
  function closeWindow() { if (openLayer) openLayer.close(); }

  app.openWindow = (options, build) => {
    closeWindow();
    const layer = $("layer");
    const previous = document.activeElement;
    const dim = el("div", "wl-dim");
    const box = el("section", "wl-box" + (options.wide ? " wide" : ""));
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", options.title);
    const head = el("div", "wl-head");
    const closeButton = el("button", "btn", "✕");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Schließen");
    head.append(el("b", "", options.title), closeButton);
    const body = el("div", "wl-body");
    box.append(head, body);
    layer.append(dim, box);

    const mine = { data: [], tick: [] };
    const win = {
      close() {
        document.removeEventListener("keydown", onKey);
        mine.data.forEach((fn) => { app.dataListeners = app.dataListeners.filter((x) => x !== fn); });
        mine.tick.forEach((fn) => { app.tickListeners = app.tickListeners.filter((x) => x !== fn); });
        dim.remove();
        box.remove();
        openLayer = null;
        if (previous && previous.focus) previous.focus();
      },
      onData(fn) { mine.data.push(fn); app.dataListeners.push(fn); },
      onTick(fn) { mine.tick.push(fn); app.tickListeners.push(fn); },
    };
    function onKey(event) {
      if (event.key === "Escape") return win.close();
      if (event.key !== "Tab") return;
      // Tab bleibt im Fenster
      const focusable = Array.from(box.querySelectorAll("button, input, select, textarea, [tabindex]:not([tabindex='-1'])")).filter((n) => !n.disabled && !n.hidden && n.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey);
    dim.addEventListener("click", win.close);
    closeButton.addEventListener("click", win.close);
    openLayer = win;
    build(body, win);
    closeButton.focus();
    return win;
  };

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
  app.enabled = loadEnabled();
  app.cities = loadCities();
  renderColumns();
  loadNeeded(false);
  showClock();
  $("start").addEventListener("click", leave);
  $("date").addEventListener("click", () => dialogs.calendar());
  $("status").addEventListener("click", () => dialogs.manage());

  loadSettings();
  loadWidgets();
  app.loadTimers();
  app.loadWeather();

  let ticks = 0;
  setInterval(() => {
    if (document.hidden) return;
    ticks += 1;
    if (ticks % 15 === 0) showClock();
    if (ticks % 5 === 0) { app.loadTimers(); loadNeeded(true); }
    if (ticks % 300 === 0) loadNeeded(false);
    if (ticks % 30 === 0 && app.enabled.includes("worldtime")) drawPanel("worldtime");
    if (ticks % 30 === 0) loadWidgets();
    if (ticks % 600 === 0) { app.loadWeather(); loadSettings(); }
    if (app.focus.active || app.timers.length) drawPanel("focus");
    app.tickListeners.slice().forEach((fn) => fn());
  }, 1000);

  // Zurueck-Taste aus der App: Seite aus dem Zwischenspeicher wieder frisch zeigen
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) { $("stage").classList.remove("leaving"); loadWidgets(); app.loadTimers(); }
  });
})();