// Handy-Version: drei Seiten nebeneinander (Start, Jarvis, Fenster). Das Wischen macht der Browser selbst (scroll-snap),
// diese Datei haelt nur die Punkte unten, den Schimmer am Rand und die Adresse (#jarvis) auf dem Laufenden.
(function () {
  "use strict";

  const M = window.MobileLogic;
  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const pages = $("mpages");
  const dots = Array.from(document.querySelectorAll("#mdots button"));
  const calm = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let current = 0;

  function loadChat() {
    const frame = $("mchat");
    if (!frame.getAttribute("src")) frame.setAttribute("src", frame.dataset.src);
  }

  function show(index) {
    current = index;
    if (index === 1) loadChat();
    dots.forEach((dot, i) => {
      dot.classList.toggle("on", i === index);
      if (i === index) dot.setAttribute("aria-current", "page"); else dot.removeAttribute("aria-current");
    });
    document.body.classList.toggle("last", !M.hasNext(index));
  }

  function go(index, instant) {
    const target = M.clampPage(index, M.PAGES.length);
    pages.scrollTo({ left: target * pages.clientWidth, behavior: instant || calm() ? "auto" : "smooth" });
    show(target);
  }

  let frame = 0;
  pages.addEventListener("scroll", () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const index = M.pageFromScroll(pages.scrollLeft, pages.clientWidth, M.PAGES.length);
      if (index !== current) show(index);
    });
  }, { passive: true });

  // Adresse merken, wenn das Wischen zur Ruhe kommt (kein Eintrag im Verlauf)
  let settle = 0;
  pages.addEventListener("scroll", () => {
    clearTimeout(settle);
    settle = setTimeout(() => {
      try { history.replaceState(null, "", location.pathname + location.search + M.hashFor(current)); } catch (error) { /* ohne Adresse geht es trotzdem */ }
    }, 180);
  }, { passive: true });

  dots.forEach((dot, i) => dot.addEventListener("click", () => go(i)));

  // Zum Ausprobieren am PC: Pfeiltasten
  document.addEventListener("keydown", (event) => {
    if (event.target && /^(input|textarea|select)$/i.test(event.target.tagName)) return;
    if (event.key === "ArrowRight") go(current + 1);
    if (event.key === "ArrowLeft") go(current - 1);
  });

  // Adresse von Hand geaendert (#fenster): dorthin springen
  window.addEventListener("hashchange", () => go(M.pageFromHash(location.hash)));

  // Drehen oder Groesse aendern: bei der aktuellen Seite bleiben
  window.addEventListener("resize", () => go(current, true));

  // ---- Inhalt: Startseite und Fenster-Seite benutzen dieselben kleinen Fenster wie am PC (welcome_panels.js)
  const panelBodies = {};     // id -> { extra, body }

  const app = window.WelcomeApp.create({
    layer: $("layer"),
    draw: () => Object.keys(panelBodies).forEach(drawPanel),
    drawPanel: (id) => drawPanel(id),
    render: () => renderLists(),
    onOnline(ok) {
      ["status", "status2"].forEach((id) => {
        $(id).classList.toggle("ok", ok);
        $(id).classList.toggle("bad", !ok);
      });
      $("status-text").textContent = ok ? "Systeme bereit" : "Jarvis-Server nicht erreichbar";
      $("status-text2").textContent = ok ? "Fenster auswählen" : "Nicht erreichbar";
    },
    onAddress() {},
  });
  const dialogs = window.WelcomeDialogs.create(app);
  const panels = window.WelcomePanels.create(app);

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
    const open = () => dialogs[id]();
    section.addEventListener("click", open);
    section.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
    panelBodies[id] = { extra, body };
    return section;
  }

  function drawPanel(id) {
    const part = panelBodies[id];
    if (!part) return;
    part.extra.textContent = panels[id].extra();
    part.body.replaceChildren();
    panels[id].draw(part.body);
  }

  function renderLists() {
    Object.keys(panelBodies).forEach((id) => delete panelBodies[id]);
    const split = M.splitWindows(app.enabled);
    $("mstart").replaceChildren(...split.start.map(makePanel));
    const list = $("mwindows");
    list.replaceChildren(...split.list.map(makePanel));
    if (!split.list.length) list.append(el("div", "wempty big", "Keine weiteren Fenster eingeschaltet. Tippe oben rechts auf „Fenster auswählen“."));
    Object.keys(panelBodies).forEach(drawPanel);
  }

  function showClock() {
    const now = new Date();
    $("clock").textContent = now.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    $("date").textContent = now.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });
  }

  $("date").addEventListener("click", () => dialogs.calendar());
  $("status").addEventListener("click", () => dialogs.manage());
  $("status2").addEventListener("click", () => dialogs.manage());
  const core = $("mcore");
  core.addEventListener("click", () => go(1));
  core.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); go(1); } });

  app.init();
  renderLists();
  app.loadNeeded(false);
  showClock();
  app.loadSettings();
  app.loadWidgets();
  app.loadTimers();

  let ticks = 0;
  setInterval(() => {
    if (document.hidden) return;
    ticks += 1;
    if (ticks % 15 === 0) showClock();
    if (ticks % 5 === 0) { app.loadTimers(); app.loadNeeded(true); }
    if (ticks % 300 === 0) app.loadNeeded(false);
    if (ticks % 30 === 0) { app.loadWidgets(); if (app.enabled.includes("worldtime")) drawPanel("worldtime"); }
    if (ticks % 600 === 0) app.loadSettings();
    if (app.focus.active || app.timers.length) drawPanel("focus");
    app.tickListeners.slice().forEach((fn) => fn());
  }, 1000);

  // Zurueck aus dem Zwischenspeicher: frisch laden
  window.addEventListener("pageshow", (event) => { if (event.persisted) { app.loadWidgets(); app.loadTimers(); } });

  go(M.pageFromHash(location.hash), true);
})();