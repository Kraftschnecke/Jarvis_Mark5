// Prueft web/core.js ohne Browser (wird von test_core.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const core = require(path.join(__dirname, "..", "web", "core.js"));

// Zustand: Fehler vor Sprechen vor Zuhoeren vor Denken vor Ruhe
assert.strictEqual(core.resolveState({}), "idle");
assert.strictEqual(core.resolveState(), "idle");
assert.strictEqual(core.resolveState({ thinking: true }), "thinking");
assert.strictEqual(core.resolveState({ thinking: true, listening: true }), "listening");
assert.strictEqual(core.resolveState({ thinking: true, listening: true, speaking: true }), "speaking");
assert.strictEqual(core.resolveState({ thinking: true, listening: true, speaking: true, error: true }), "error");
assert.strictEqual(core.resolveState({ listening: true }), "listening");
assert.strictEqual(core.resolveState({ speaking: true }), "speaking");
assert.deepStrictEqual(core.STATES, ["idle", "listening", "thinking", "speaking", "error"]);

// Bewegung: gespeicherte Wahl gewinnt, sonst die Systemeinstellung
assert.strictEqual(core.motionOn("on", true), true);
assert.strictEqual(core.motionOn("off", false), false);
assert.strictEqual(core.motionOn(null, true), false);
assert.strictEqual(core.motionOn(null, false), true);
assert.strictEqual(core.motionOn("quatsch", true), false);
assert.strictEqual(core.motionOn(undefined, false), true);

// Aufbau mit einem kleinen DOM-Ersatz
function fakeDoc() {
  return {
    createElementNS(ns, name) {
      return {
        ns, name, attrs: {}, children: [],
        setAttribute(key, value) { this.attrs[key] = String(value); },
        appendChild(child) { this.children.push(child); return child; },
      };
    },
  };
}
function all(el) { return [el].concat(...el.children.map(all)); }

const doc = fakeDoc();
const svg = core.create(doc, "thinking");
assert.strictEqual(svg.name, "svg");
assert.strictEqual(svg.ns, "http://www.w3.org/2000/svg");
assert.strictEqual(svg.attrs["data-state"], "thinking");
assert.strictEqual(svg.attrs.class, "jarvis-core");
assert.strictEqual(svg.attrs.viewBox, "0 0 200 200");
const circles = all(svg).filter((el) => el.name === "circle");
const classes = circles.map((el) => el.attrs.class);
assert.deepStrictEqual(classes, ["core-glow", "ring ring-ticks", "ring ring-arcs", "ring ring-thin", "ring ring-bold", "core-dot"]);
assert.ok(circles.every((el) => el.attrs.cx === "100" && el.attrs.cy === "100"));
assert.deepStrictEqual(circles.slice(1, 5).map((el) => Number(el.attrs.r)), [92, 80, 66, 52]);   // von aussen nach innen
assert.strictEqual(all(svg).filter((el) => el.name === "stop").length, 3);

// Mehrere Kerne: eigene Verlaufs-ID, Glow verweist auf den eigenen Verlauf
const second = core.create(doc);
const id = (el) => all(el).find((x) => x.name === "radialGradient").attrs.id;
assert.notStrictEqual(id(svg), id(second));
assert.strictEqual(all(svg).find((x) => x.attrs.class === "core-glow").attrs.fill, "url(#" + id(svg) + ")");
assert.strictEqual(second.attrs["data-state"], "idle");
assert.strictEqual(core.create(doc, "unsinn").attrs["data-state"], "idle");

// Zustand setzen: nur bekannte Zustaende
core.setState(svg, "speaking");
assert.strictEqual(svg.attrs["data-state"], "speaking");
core.setState(svg, "kaputt");
assert.strictEqual(svg.attrs["data-state"], "idle");

console.log("core.js OK");