// Jarvis-Kern (Mark 5, Step 4B.5): vier Ringe um einen leuchtenden Kern, gezeichnet als SVG.
// Der Zustand (idle, listening, thinking, speaking, error) steht als data-state am Element, die Bewegung kommt aus core.css.
(function (root) {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const STATES = ["idle", "listening", "thinking", "speaking", "error"];
  let counter = 0;

  // Welcher Zustand gilt, wenn mehrere zugleich zutreffen? Fehler vor Sprechen vor Zuhoeren vor Denken.
  function resolveState(flags) {
    const f = flags || {};
    if (f.error) return "error";
    if (f.speaking) return "speaking";
    if (f.listening) return "listening";
    if (f.thinking) return "thinking";
    return "idle";
  }

  // Bewegung an oder aus: eine gespeicherte Wahl gilt, sonst folgt es der Systemeinstellung "Animationen reduzieren".
  function motionOn(saved, prefersReduced) {
    if (saved === "on") return true;
    if (saved === "off") return false;
    return !prefersReduced;
  }

  function node(doc, name, attrs, parent) {
    const el = doc.createElementNS(NS, name);
    Object.keys(attrs || {}).forEach((key) => el.setAttribute(key, attrs[key]));
    if (parent) parent.appendChild(el);
    return el;
  }

  function circle(doc, parent, cls, radius, attrs) {
    return node(doc, "circle", Object.assign({ class: cls, cx: 100, cy: 100, r: radius }, attrs), parent);
  }

  // Baut den Kern. Jede Instanz bekommt eigene Verlaufs-ID, damit mehrere auf einer Seite sich nicht stoeren.
  function create(doc, state) {
    counter += 1;
    const gradient = "jarvis-core-glow-" + counter;
    const svg = node(doc, "svg", {
      class: "jarvis-core", viewBox: "0 0 200 200", role: "img", "aria-label": "Jarvis-Status",
      "data-state": STATES.indexOf(state) >= 0 ? state : "idle",
    });
    const defs = node(doc, "defs", {}, svg);
    const radial = node(doc, "radialGradient", { id: gradient }, defs);
    node(doc, "stop", { offset: "0%", "stop-color": "currentColor", "stop-opacity": "0.95" }, radial);
    node(doc, "stop", { offset: "55%", "stop-color": "currentColor", "stop-opacity": "0.35" }, radial);
    node(doc, "stop", { offset: "100%", "stop-color": "currentColor", "stop-opacity": "0" }, radial);
    circle(doc, svg, "core-glow", 46, { fill: "url(#" + gradient + ")" });
    circle(doc, svg, "ring ring-ticks", 92);
    circle(doc, svg, "ring ring-arcs", 80);
    circle(doc, svg, "ring ring-thin", 66);
    circle(doc, svg, "ring ring-bold", 52);
    circle(doc, svg, "core-dot", 9);
    return svg;
  }

  function setState(svg, state) {
    svg.setAttribute("data-state", STATES.indexOf(state) >= 0 ? state : "idle");
  }

  const api = { STATES, resolveState, motionOn, create, setState };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisCore = api;
})(typeof window !== "undefined" ? window : this);