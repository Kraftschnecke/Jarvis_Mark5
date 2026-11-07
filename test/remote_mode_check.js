// Prueft web/remote_mode.js ohne Browser (wird von test_remote_mode.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const mode = require(path.join(__dirname, "..", "web", "remote_mode.js"));

// Widgets: PC-Daten und Eishockey weg, alles andere bleibt
for (const name of ["PC Facts", "Performance", "Edmonton Oilers", "Adler Mannheim"]) assert.strictEqual(mode.widgetAllowed(name), false, name);
for (const name of ["Clock", "Date", "Calendar", "Notes", "Goals", "Lists", "Off"]) assert.strictEqual(mode.widgetAllowed(name), true, name);

// Streifen
assert.deepStrictEqual(mode.bannerView(null), { show: false, title: "", detail: "" });
assert.deepStrictEqual(mode.bannerView(undefined), { show: false, title: "", detail: "" });
assert.deepStrictEqual(mode.bannerView({}), { show: false, title: "", detail: "" });
assert.deepStrictEqual(mode.bannerView({ remote: false, device: "x" }), { show: false, title: "", detail: "" });
assert.deepStrictEqual(mode.bannerView({ remote: "true" }), { show: false, title: "", detail: "" });
assert.deepStrictEqual(
  mode.bannerView({ remote: true, device: "iPhone Moritz", levels: { info: true, daily: true, pc: false } }),
  { show: true, title: "Remote (eingeschränkt)", detail: "Auskunft, Alltag · iPhone Moritz" });
assert.strictEqual(mode.bannerView({ remote: true, device: "iPad", levels: { info: true, daily: false, pc: true } }).detail, "Auskunft, PC-Steuerung · iPad");
assert.strictEqual(mode.bannerView({ remote: true, device: "iPad", levels: { info: false, daily: false, pc: false } }).detail, "nur Unterhaltung · iPad");
assert.strictEqual(mode.bannerView({ remote: true, levels: { info: true } }).detail, "Auskunft");
assert.strictEqual(mode.bannerView({ remote: true }).detail, "nur Unterhaltung");
assert.strictEqual(mode.bannerView({ remote: true, device: 5, levels: { info: 1 } }).detail, "nur Unterhaltung");   // nur echte Wahrheitswerte zaehlen

console.log("remote_mode.js OK");