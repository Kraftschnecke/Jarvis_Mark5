// Prueft mobile_logic.js ohne Browser.
"use strict";
const assert = require("assert");
const path = require("path");
const M = require(path.join(__dirname, "..", "web", "mobile_logic.js"));

assert.deepStrictEqual(M.PAGES.map((p) => p.id), ["start", "jarvis", "fenster"]);
assert.strictEqual(new Set(M.PAGES.map((p) => p.id)).size, M.PAGES.length);

// Seite aus der Scroll-Position: erst bei mehr als der halben Seite zaehlt die naechste
assert.strictEqual(M.pageFromScroll(0, 390, 3), 0);
assert.strictEqual(M.pageFromScroll(150, 390, 3), 0);
assert.strictEqual(M.pageFromScroll(200, 390, 3), 1);
assert.strictEqual(M.pageFromScroll(390, 390, 3), 1);
assert.strictEqual(M.pageFromScroll(780, 390, 3), 2);
assert.strictEqual(M.pageFromScroll(5000, 390, 3), 2);          // nie ueber die letzte Seite hinaus
assert.strictEqual(M.pageFromScroll(-40, 390, 3), 0);           // Gummiband am Rand
assert.strictEqual(M.pageFromScroll(100, 0, 3), 0);             // Breite 0 (Seite noch nicht gezeichnet)
assert.strictEqual(M.pageFromScroll(NaN, 390, 3), 0);

assert.strictEqual(M.clampPage(-1, 3), 0);
assert.strictEqual(M.clampPage(3, 3), 2);
assert.strictEqual(M.clampPage(1.4, 3), 1);
assert.strictEqual(M.clampPage(undefined, 3), 0);
assert.strictEqual(M.clampPage(7), 2);                           // ohne Anzahl gilt die Seitenzahl

// Adresse (#jarvis)
assert.strictEqual(M.pageFromHash("#jarvis"), 1);
assert.strictEqual(M.pageFromHash("#FENSTER"), 2);
assert.strictEqual(M.pageFromHash("#start"), 0);
assert.strictEqual(M.pageFromHash(""), 0);
assert.strictEqual(M.pageFromHash("#gibtsnicht"), 0);
assert.strictEqual(M.pageFromHash(undefined), 0);
assert.deepStrictEqual([0, 1, 2].map(M.hashFor), ["#start", "#jarvis", "#fenster"]);
assert.strictEqual(M.hashFor(9), "#fenster");
M.PAGES.forEach((p, i) => assert.strictEqual(M.pageFromHash(M.hashFor(i)), i));

// Schimmer am rechten Rand nur, wenn rechts noch etwas kommt
assert.deepStrictEqual([0, 1, 2].map(M.hasNext), [true, true, false]);

// Verteilung: Tagesziele und Kalender auf die Startseite, der Rest auf die Fenster-Seite (Reihenfolge bleibt)
assert.deepStrictEqual(M.splitWindows(["goals", "focus", "lists", "calendar", "weather"]), { start: ["goals", "calendar"], list: ["focus", "lists", "weather"] });
assert.deepStrictEqual(M.splitWindows(["weather", "news"]), { start: [], list: ["weather", "news"] });
assert.deepStrictEqual(M.splitWindows(["calendar"]), { start: ["calendar"], list: [] });
assert.deepStrictEqual(M.splitWindows([]), { start: [], list: [] });
assert.deepStrictEqual(M.splitWindows(null), { start: [], list: [] });
assert.deepStrictEqual(M.START_WINDOWS, ["goals", "calendar"]);

// ---- Wisch vom Rand (embed.js)
const E = require(path.join(__dirname, "..", "web", "embed.js"));
const d = (sx, sy, ex, ey, open) => E.decide({ x: sx, y: sy }, { x: ex, y: ey }, open);
assert.strictEqual(d(10, 300, 80, 305, false), "open");          // vom Rand nach rechts
assert.strictEqual(d(E.EDGE, 300, E.EDGE + E.OPEN_DX, 300, false), "open");     // genau auf den Grenzen
assert.strictEqual(d(E.EDGE + 1, 300, 200, 300, false), null);   // zu weit vom Rand entfernt
assert.strictEqual(d(10, 300, E.OPEN_DX - 1, 300, false), null); // zu kurz
assert.strictEqual(d(10, 300, 80, 400, false), null);            // eher senkrecht: Scrollen, kein Wisch
assert.strictEqual(d(10, 300, 80, 300 + 70 / E.STRAIGHT + 1, false), null);
assert.strictEqual(d(10, 300, 80, 300, true), null);             // Liste ist schon offen: nichts
assert.strictEqual(d(250, 300, 190, 300, true), "close");        // offen, nach links
assert.strictEqual(d(250, 300, 250 - E.CLOSE_DX + 1, 300, true), null);
assert.strictEqual(d(250, 300, 190, 300, false), null);          // zu: nach links tut nichts
assert.strictEqual(d(250, 300, 190, 380, true), null);           // schraeg

console.log("mobile OK");