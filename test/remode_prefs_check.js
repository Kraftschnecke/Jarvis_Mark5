// Prueft web/remote_prefs.js ohne Browser (wird von test_remote_prefs.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const prefs = require(path.join(__dirname, "..", "web", "remote_prefs.js"));

function memory(initial) {
  const data = Object.assign({}, initial);
  return { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, data };
}

assert.strictEqual(prefs.KEY, "jarvis.remote.prefs");
assert.deepStrictEqual(prefs.THEMES, ["Dark", "Light", "System"]);
assert.deepStrictEqual(prefs.ACCENTS, ["J.A.R.V.I.S. Blue", "British Racing Green"]);

// normalize: nur gueltige Werte
assert.deepStrictEqual(prefs.normalize({ theme: "Light", accent_color: "British Racing Green", speech: true }), { theme: "Light", accent_color: "British Racing Green", speech: true });
assert.deepStrictEqual(prefs.normalize({ theme: "Light", speech: false }), { theme: "Light", speech: false });
assert.deepStrictEqual(prefs.normalize({ theme: "Pink", accent_color: "Rot", speech: "ja", extra: 1 }), {});
assert.deepStrictEqual(prefs.normalize({ speech: 1 }), {});
for (const bad of [null, undefined, 5, "text", [], [1, 2], true]) assert.deepStrictEqual(prefs.normalize(bad), {});

// load / save
const store = memory({});
assert.deepStrictEqual(prefs.load(store), {});
assert.strictEqual(prefs.save(store, { theme: "Light", speech: true, evil: "x" }), true);
assert.strictEqual(store.data[prefs.KEY], JSON.stringify({ theme: "Light", speech: true }));      // Fremdes wird nicht gespeichert
assert.deepStrictEqual(prefs.load(store), { theme: "Light", speech: true });
assert.deepStrictEqual(prefs.load(memory({ [prefs.KEY]: "{kaputt" })), {});
assert.deepStrictEqual(prefs.load(memory({ [prefs.KEY]: JSON.stringify({ theme: "Pink" }) })), {});
assert.deepStrictEqual(prefs.load({ getItem() { throw new Error("gesperrt"); } }), {});
assert.strictEqual(prefs.save({ setItem() { throw new Error("voll"); } }, { theme: "Dark" }), false);
assert.deepStrictEqual(prefs.load(null), {});

// apply: ueberdeckt nur, was gewaehlt ist; das Original bleibt unveraendert
const pc = { appearance: { theme: "Dark", accent_color: "J.A.R.V.I.S. Blue", font_size: 14 }, voice: { output: false, speed: 1.2, engine: "browser" }, address: "Sir" };
const frozen = JSON.stringify(pc);
const merged = prefs.apply(pc, { theme: "Light", accent_color: "British Racing Green", speech: true });
assert.deepStrictEqual(merged.appearance, { theme: "Light", accent_color: "British Racing Green", font_size: 14 });
assert.deepStrictEqual(merged.voice, { output: true, speed: 1.2, engine: "browser" });
assert.strictEqual(merged.address, "Sir");
assert.strictEqual(JSON.stringify(pc), frozen);
assert.deepStrictEqual(prefs.apply(pc, {}).appearance, pc.appearance);                 // nichts gewaehlt: Werte des PC
assert.deepStrictEqual(prefs.apply(pc, {}).voice, pc.voice);
assert.strictEqual(prefs.apply(pc, { speech: false }).voice.output, false);
assert.strictEqual(prefs.apply({ voice: { output: true } }, { speech: false }).voice.output, false);   // Handy darf auch ausschalten
assert.strictEqual(prefs.apply({ voice: { output: true } }, {}).voice.output, true);
assert.strictEqual(prefs.apply(pc, { theme: "Pink", speech: "ja" }).appearance.theme, "Dark");       // Ungueltiges wird nicht uebernommen
assert.strictEqual(prefs.apply(pc, { theme: "Pink", speech: "ja" }).voice.output, false);
assert.deepStrictEqual(prefs.apply(undefined, { speech: true }), { appearance: {}, voice: { output: true }, widgets: {} });
assert.deepStrictEqual(prefs.apply(null, null), { appearance: {}, voice: {}, widgets: {} });

// view: was der Dialog zeigt
const allOff = { top: "Off", middle: "Off", fourth: "Off", fifth: "Off" };
assert.deepStrictEqual(prefs.view(pc, {}), { theme: "Dark", accent_color: "J.A.R.V.I.S. Blue", speech: false, font_size: 14, widgets: allOff });
assert.deepStrictEqual(prefs.view(pc, { theme: "System", speech: true }), { theme: "System", accent_color: "J.A.R.V.I.S. Blue", speech: true, font_size: 14, widgets: allOff });
assert.deepStrictEqual(prefs.view({}, {}), { theme: "Dark", accent_color: "J.A.R.V.I.S. Blue", speech: false, font_size: 13, widgets: allOff });
assert.deepStrictEqual(prefs.view({ appearance: { theme: "Nonsense", accent_color: "x", font_size: 99 }, voice: { output: "yes" }, widgets: { top: "Pizza" } }, {}), { theme: "Dark", accent_color: "J.A.R.V.I.S. Blue", speech: false, font_size: 13, widgets: allOff });
assert.strictEqual(prefs.view({ voice: { output: true } }, {}).speech, true);

// Schriftgroesse: wie am PC 11 bis 20, ganze Zahlen
assert.deepStrictEqual(prefs.FONT_SIZES, [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
assert.deepStrictEqual(prefs.normalize({ font_size: 16 }), { font_size: 16 });
for (const bad of [10, 21, 14.5, "16", null, NaN, [16]]) assert.deepStrictEqual(prefs.normalize({ font_size: bad }), {}, String(bad));
assert.strictEqual(prefs.apply(pc, { font_size: 18 }).appearance.font_size, 18);
assert.strictEqual(pc.appearance.font_size, 14);
assert.strictEqual(prefs.apply(pc, {}).appearance.font_size, 14);

// Seitenleiste: nur Felder und Widgets, die es am Handy gibt (kein PC Facts, keine Eishockey-Felder)
assert.deepStrictEqual(Object.keys(prefs.SLOTS), ["top", "middle", "fourth", "fifth"]);
for (const forbidden of ["PC Facts", "Performance", "Edmonton Oilers", "Adler Mannheim"]) {
  for (const slot of Object.keys(prefs.SLOTS)) assert.ok(!prefs.SLOTS[slot].includes(forbidden), slot + " " + forbidden);
}
assert.ok(!("bottom" in prefs.SLOTS));
for (const slot of Object.keys(prefs.SLOTS)) assert.strictEqual(prefs.SLOTS[slot][0], "Off");
assert.deepStrictEqual(prefs.normalize({ widgets: { top: "Calendar", middle: "Goals", fourth: "Lists" } }), { widgets: { top: "Calendar", middle: "Goals", fourth: "Lists" } });
assert.deepStrictEqual(prefs.normalize({ widgets: { top: "Lists", middle: "Clock", fourth: "PC Facts", bottom: "Adler Mannheim", evil: "Off" } }), {});
assert.deepStrictEqual(prefs.normalize({ widgets: { top: "Date", bottom: "Off", fifth: "Performance" } }), { widgets: { top: "Date" } });
for (const bad of [null, "x", [], 5, {}]) assert.deepStrictEqual(prefs.normalize({ widgets: bad }), {});
const slots = prefs.apply({ widgets: { top: "Clock", middle: "Notes", bottom: "Off", fourth: "Off" } }, { widgets: { middle: "Lists", fifth: "Lists" } });
assert.deepStrictEqual(slots.widgets, { top: "Clock", middle: "Lists", bottom: "Off", fourth: "Off", fifth: "Lists" });     // nur Gewaehltes wird ueberdeckt, der Rest bleibt wie am PC
assert.deepStrictEqual(prefs.view({ widgets: { top: "Calendar", middle: "Goals", fourth: "PC Facts" } }, { widgets: { fifth: "Lists" } }).widgets,
  { top: "Calendar", middle: "Goals", fourth: "Off", fifth: "Lists" });
const orig = { widgets: { top: "Clock" } };
prefs.apply(orig, { widgets: { top: "Date" } });
assert.deepStrictEqual(orig, { widgets: { top: "Clock" } });                                                              // Original unveraendert
assert.deepStrictEqual(prefs.load(memory({ [prefs.KEY]: JSON.stringify({ widgets: { top: "Date" }, font_size: 15 }) })), { font_size: 15, widgets: { top: "Date" } });

console.log("remote_prefs.js OK");