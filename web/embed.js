// Chat in der Handy-Version (mobile.html): die App laeuft dort in einem Rahmen (?embed=1).
// Hier: Gespraechsliste per Wisch vom linken Rand oeffnen, per Wisch nach links schliessen.
// Ohne ?embed=1 tut diese Datei nichts. Die Entscheidung steht in einer reinen Funktion (mit Node pruefbar).
(function (root) {
  "use strict";

  const EDGE = 24;        // so nah am linken Rand muss der Finger starten (px)
  const OPEN_DX = 40;     // so weit nach rechts muss er wischen (px)
  const CLOSE_DX = 50;    // so weit nach links, um die Liste zu schliessen (px)
  const STRAIGHT = 1.5;   // waagerecht muss mindestens so viel mehr sein als senkrecht

  // start = { x, y }, end = { x, y }, open = Liste ist offen. Antwort: "open", "close" oder null.
  function decide(start, end, open) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    if (Math.abs(dx) < Math.abs(dy) * STRAIGHT) return null;
    if (!open && start.x <= EDGE && dx >= OPEN_DX) return "open";
    if (open && dx <= -CLOSE_DX) return "close";
    return null;
  }

  const api = { EDGE, OPEN_DX, CLOSE_DX, STRAIGHT, decide };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.EmbedSwipe = api;

  if (!/(^|[?&])embed=1(&|$)/.test(location.search)) return;
  const layout = document.getElementById("layout");
  if (!layout) return;
  document.body.classList.add("embed");

  // Unsichtbarer Streifen am linken Rand: der Rahmen darum soll dort nicht die Seite wechseln
  const strip = document.createElement("div");
  strip.id = "embed-edge";
  document.body.append(strip);

  let start = null;
  const isOpen = () => layout.classList.contains("sidebar-open");
  document.addEventListener("touchstart", (event) => {
    const t = event.touches[0];
    start = event.touches.length === 1 ? { x: t.clientX, y: t.clientY } : null;
  }, { passive: true });
  document.addEventListener("touchmove", (event) => {
    if (!start) return;
    const t = event.touches[0];
    const action = decide(start, { x: t.clientX, y: t.clientY }, isOpen());
    if (!action) return;
    start = null;
    layout.classList.toggle("sidebar-open", action === "open");
  }, { passive: true });
  document.addEventListener("touchend", () => { start = null; }, { passive: true });
})(typeof window !== "undefined" ? window : globalThis);