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

// Testbereich (Gast): eigener Streifen, keine Projekte
assert.deepStrictEqual(
  mode.bannerView({ remote: true, tester: true, area: "Bruder", device: "Laptop", levels: { info: true, daily: true, pc: false } }),
  { show: true, title: "Testbereich", detail: "Bruder · eigene Daten, kein Zugriff auf den PC · Laptop" });
assert.strictEqual(mode.bannerView({ remote: true, tester: true }).detail, "eigene Daten, kein Zugriff auf den PC");
assert.strictEqual(mode.bannerView({ remote: true, tester: true, area: 5, device: {} }).detail, "eigene Daten, kein Zugriff auf den PC");
assert.strictEqual(mode.bannerView({ remote: true, tester: "true", device: "x" }).title, "Remote (eingeschränkt)");     // nur echtes true
assert.strictEqual(mode.bannerView({ remote: false, tester: true }).show, false);
assert.deepStrictEqual(mode.testerSidebarView(true), { showProjects: false, newLabel: "Neue Unterhaltung", hint: "Im Testbereich gibt es keine Projekte." });
for (const other of [false, undefined, null, "true", 1]) assert.strictEqual(mode.testerSidebarView(other).showProjects, true, String(other));
assert.strictEqual(mode.testerSidebarView(false).newLabel, "New Conversation");

console.log("remote_mode.js OK");