// Prueft web/remote_admin.js ohne Browser (wird von test_remote_ui.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const admin = require(path.join(__dirname, "..", "web", "remote_admin.js"));

const NOW = 1_000_000;

// Zeitangaben
assert.strictEqual(admin.agoText(0, NOW), "nie");
assert.strictEqual(admin.agoText(null, NOW), "nie");
assert.strictEqual(admin.agoText("x", NOW), "nie");
assert.strictEqual(admin.agoText(NaN, NOW), "nie");
assert.strictEqual(admin.agoText(NOW - 5, NOW), "gerade eben");
assert.strictEqual(admin.agoText(NOW + 500, NOW), "gerade eben");          // Uhr geht vor: nie "vor -3 Min."
assert.strictEqual(admin.agoText(NOW - 59, NOW), "gerade eben");
assert.strictEqual(admin.agoText(NOW - 60, NOW), "vor 1 Min.");
assert.strictEqual(admin.agoText(NOW - 3599, NOW), "vor 59 Min.");
assert.strictEqual(admin.agoText(NOW - 3600, NOW), "vor 1 Std.");
assert.strictEqual(admin.agoText(NOW - 86399, NOW), "vor 23 Std.");
assert.strictEqual(admin.agoText(NOW - 86400, NOW), "vor 1 Tag");
assert.strictEqual(admin.agoText(NOW - 86400 * 3, NOW), "vor 3 Tagen");

// Geraete: gesperrt vor abgelaufen vor aktiv, nur aktive lassen sich sperren
const base = { id: "a1", name: "iPhone", created: NOW - 100, last_seen: NOW - 120, revoked: false, expired: false };
assert.deepStrictEqual(admin.deviceView(base, NOW), { state: "active", label: "aktiv", name: "iPhone", seen: "zuletzt vor 2 Min.", canRevoke: true, canRestore: false });
assert.deepStrictEqual(admin.deviceView({ ...base, expired: true }, NOW), { state: "expired", label: "abgelaufen", name: "iPhone", seen: "zuletzt vor 2 Min.", canRevoke: false, canRestore: false });
assert.deepStrictEqual(admin.deviceView({ ...base, revoked: true, expired: true }, NOW), { state: "revoked", label: "gesperrt", name: "iPhone", seen: "zuletzt vor 2 Min.", canRevoke: false, canRestore: true });
assert.strictEqual(admin.deviceView({ ...base, last_seen: 0 }, NOW).seen, "zuletzt nie");
assert.strictEqual(admin.deviceView({ ...base, name: 5 }, NOW).name, "5");

// Kopfzeile
const none = admin.statusView({ available: false, active: false, host: "" });
assert.strictEqual(none.tone, "off");
assert.ok(none.text.includes("JARVIS_REMOTE_HOST") && none.text.includes(".env"));
assert.strictEqual(admin.statusView(null).tone, "off");
assert.strictEqual(admin.statusView(undefined).tone, "off");
const off = admin.statusView({ available: true, active: false, host: "pc.ts.net" });
assert.deepStrictEqual(off, { tone: "off", text: "Remote ist aus. https://pc.ts.net ist nicht erreichbar." });
assert.deepStrictEqual(admin.statusView({ available: true, active: true, host: "pc.ts.net" }), { tone: "on", text: "Remote ist an: https://pc.ts.net" });

// Koppeln nur, wenn Name da und Remote an
assert.strictEqual(admin.canPair({ available: true, active: true }), true);
assert.strictEqual(admin.canPair({ available: true, active: false }), false);
assert.strictEqual(admin.canPair({ available: false, active: true }), false);
assert.strictEqual(admin.canPair(null), false);

// Link: Restzeit, danach weg
const entry = { link: "https://pc.ts.net/pair#abc", name: "iPhone", until: NOW + 125 };
assert.deepStrictEqual(admin.linkView(entry, NOW), { link: "https://pc.ts.net/pair#abc", name: "iPhone", left: "2:05", note: admin.LINK_NOTE });
assert.strictEqual(admin.linkView(entry, NOW + 120).left, "0:05");
assert.strictEqual(admin.linkView(entry, NOW + 125), null);
assert.strictEqual(admin.linkView(entry, NOW + 999), null);
assert.strictEqual(admin.linkView(null, NOW), null);
assert.ok(admin.LINK_NOTE.includes("5 Minuten") && admin.LINK_NOTE.includes("nur einmal"));

console.log("remote_admin.js OK");