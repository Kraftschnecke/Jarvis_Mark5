// Gemeinsamer Kern der Willkommensseite (PC) und der Handy-Version: Daten holen, Zustand halten, grosse Fenster oeffnen.
// Was auf der Seite gezeichnet wird (Spalten, Uhr, Status), steht in welcome.js bzw. mobile.js und kommt ueber options herein:
//   layer          Element, in das die grossen Fenster kommen
//   draw()         alle kleinen Fenster neu zeichnen (Daten haben sich geaendert)
//   drawPanel(id)  ein kleines Fenster neu zeichnen
//   render()       Auswahl der Fenster hat sich geaendert: Seite neu aufbauen
//   onOnline(ok)   Verbindung zu Jarvis ja/nein
//   onAddress()    Anrede (Name) ist da oder hat sich geaendert
// Reihenfolge der Skripte: widgets.js, welcome_logic.js, welcome_panels.js, welcome_dialogs.js, welcome_app.js, dann die Seite.
(function () {
  "use strict";

  const L = window.WelcomeLogic;
  const W = window.JarvisWidgets;

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

  function create(options) {
    // ---- gemeinsamer Zustand, den die Fenster benutzen
    const app = {
      L, W, el, api,
      local: L.isLocalHost(location.hostname),     // am PC: Termine eintragen erlaubt, ueber Remote nicht
      data: null,                                  // Antwort von /api/widgets (Termine, Ziele, Listen, ...)
      focus: { active: false },
      timers: [],
      fetchedAt: 0,                                // wann Fokus/Timer geholt wurden (damit sie lokal weiterzaehlen)
      enabled: [],
      extra: {},                                   // News, Briefing, Erinnerungen, PC-Werte, Wettervorhersage: name -> { status: loading|ok|disabled|error, data, error }
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
      options.draw();
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
      options.render();
      loadNeeded(false);
    };

    // ---- Weltuhr: gewaehlte Staedte (pro Browser gespeichert)
    function loadCities() {
      try { return L.normalizeCities(JSON.parse(localStorage.getItem(L.CITIES_KEY))); } catch (error) { return L.normalizeCities(null); }
    }
    app.setCities = (list) => {
      app.cities = L.normalizeCities(list);
      try { localStorage.setItem(L.CITIES_KEY, JSON.stringify(app.cities)); } catch (error) { /* gilt bis zum Neuladen */ }
      options.drawPanel("worldtime");
    };

    // ---- Daten vom Server fuer die Fenster News, Briefing, Erinnerungen, PC (nur wenn das Fenster an ist oder offen)
    const SOURCES = {
      news: { path: "/api/news", pick: (d) => d.items || [] },
      briefing: { path: "/api/briefing", pick: (d) => d.text || "" },
      reminders: { path: "/api/reminders", pick: (d) => d.reminders || [] },
      perf: { path: "/api/performance", pick: (d) => d },
      forecast: { path: "/api/forecast", pick: (d) => d.forecast || null },      // Wochenvorhersage fuer den Heimatort
      pclage: { path: "/api/pc_lage", pick: (d) => d.pc_lage || null },          // PC-Lage und Laufwerke (nur am PC)
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
    const NEEDS = { news: "news", briefing: "briefing", reminders: "reminders", system: "perf", weather: "forecast", pclage: "pclage", drives: "pclage" };
    const LOCAL_ONLY = ["system", "pclage", "drives"];                   // gibt es nur am PC
    const LIVE = ["perf", "pclage"];                                     // jede Runde neu holen (alle paar Sekunden)
    const ALWAYS_FRESH = ["perf", "forecast", "pclage"];                 // und bei der grossen Runde auch erneuern
    function loadNeeded(onlyLive) {
      app.enabled.forEach((id) => {
        const name = NEEDS[id];
        if (!name || (LOCAL_ONLY.includes(id) && !app.local)) return;
        if (onlyLive && !LIVE.includes(name)) return;
        app.loadExtra(name, ALWAYS_FRESH.includes(name));
      });
    }

    // ---- Wetter: Vorhersage fuer einen gesuchten Ort (der Heimatort steht in app.extra.forecast)
    app.searchForecast = async (place) => {
      const data = await api("GET", "/api/forecast?place=" + encodeURIComponent(place));
      if (data.disabled) throw new Error("Wetter ist in den Einstellungen ausgeschaltet.");
      if (!data.forecast) throw new Error("Keine Vorhersage erhalten.");
      return data.forecast;
    };

    // ---- Wetter-Symbol als kleines SVG (Linien, Farbe vom Text); unbekannter Name = Wolke
    const SVG = "http://www.w3.org/2000/svg";
    app.icon = (key, size) => {
      const shapes = L.WEATHER_ICONS[L.isWeatherIcon(key) ? key : "cloudy"];
      const svg = document.createElementNS(SVG, "svg");
      const set = (node, name, value) => node.setAttribute(name, String(value));
      set(svg, "viewBox", "0 0 24 24");
      set(svg, "width", size || 20);
      set(svg, "height", size || 20);
      set(svg, "fill", "none");
      set(svg, "stroke", "currentColor");
      set(svg, "stroke-width", 1.7);
      set(svg, "stroke-linecap", "round");
      set(svg, "stroke-linejoin", "round");
      set(svg, "aria-hidden", "true");
      svg.setAttribute("class", "wicon");
      shapes.forEach(([tag, attrs]) => {
        const shape = document.createElementNS(SVG, tag);
        Object.keys(attrs).forEach((name) => set(shape, name, attrs[name]));
        svg.append(shape);
      });
      return svg;
    };

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
      options.onOnline(ok);
    }

    app.loadWidgets = async function loadWidgets() {
      try { app.data = await api("GET", "/api/widgets"); setOnline(true); emit(); } catch (error) { setOnline(false); }
    };
    app.loadTimers = async () => {
      try {
        const [timers, focus] = await Promise.all([api("GET", "/api/timers"), api("GET", "/api/focus")]);
        app.timers = Array.isArray(timers.timers) ? timers.timers : [];
        app.focus = focus && focus.active ? focus : { active: false };
        app.fetchedAt = Date.now();
        emit();
      } catch (error) { /* naechste Runde */ }
    };
    app.loadSettings = async function loadSettings() {
      try {
        const data = await api("GET", "/api/settings");
        const name = data && data.jarvis && typeof data.jarvis.address === "string" ? data.jarvis.address.trim() : "";
        if (name) app.address = name;
        const local = L.isLocalHost(location.hostname) || L.isOwnerSettings(data);       // Besitzer ueber die Server-Adresse ist auch "am PC"
        if (local !== app.local) {
          app.local = local;
          loadNeeded(false);                                                            // PC-Fenster holen jetzt ihre Daten
          emit();
        }
        setOnline(true);
        options.onAddress();
      } catch (error) { setOnline(false); }
    };

    // ---- grosse Fenster
    let openLayer = null;
    function closeWindow() { if (openLayer) openLayer.close(); }

    app.openWindow = (spec, build) => {
      closeWindow();
      const layer = options.layer;
      const previous = document.activeElement;
      const dim = el("div", "wl-dim");
      const box = el("section", "wl-box" + (spec.wide ? " wide" : ""));
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      box.setAttribute("aria-label", spec.title);
      const head = el("div", "wl-head");
      const closeButton = el("button", "btn", "✕");
      closeButton.type = "button";
      closeButton.setAttribute("aria-label", "Schließen");
      head.append(el("b", "", spec.title), closeButton);
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

    app.init = () => { app.enabled = loadEnabled(); app.cities = loadCities(); };
    app.loadNeeded = loadNeeded;

    return app;
  }

  window.WelcomeApp = { create };
})();
