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
assert.deepStrictEqual(admin.deviceView(base, NOW), { state: "active", label: "aktiv", name: "iPhone", area: "", seen: "zuletzt vor 2 Min.", canRevoke: true, canRestore: false });
assert.deepStrictEqual(admin.deviceView({ ...base, expired: true }, NOW), { state: "expired", label: "abgelaufen", name: "iPhone", area: "", seen: "zuletzt vor 2 Min.", canRevoke: false, canRestore: false });
assert.deepStrictEqual(admin.deviceView({ ...base, revoked: true, expired: true }, NOW), { state: "revoked", label: "gesperrt", name: "iPhone", area: "", seen: "zuletzt vor 2 Min.", canRevoke: false, canRestore: true });
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
assert.deepStrictEqual(admin.linkView(entry, NOW), { link: "https://pc.ts.net/pair#abc", code: "abc", name: "iPhone", left: "2:05", note: admin.LINK_NOTE });
assert.strictEqual(admin.linkView(entry, NOW).code, "abc");                                            // ohne eigenes Feld: der Teil nach dem #
assert.strictEqual(admin.linkView(Object.assign({}, entry, { code: "K7M2-QX9P" }), NOW).code, "K7M2-QX9P");
assert.strictEqual(admin.linkView({ link: "https://pc.ts.net/pair", name: "x", until: NOW + 10 }, NOW).code, "");
assert.strictEqual(admin.linkView(entry, NOW + 120).left, "0:05");
assert.strictEqual(admin.linkView(entry, NOW + 125), null);
assert.strictEqual(admin.linkView(entry, NOW + 999), null);
assert.strictEqual(admin.linkView(null, NOW), null);
assert.ok(admin.LINK_NOTE.includes("5 Minuten") && admin.LINK_NOTE.includes("nur einmal"));
 
// Gast-Bereiche (C1)
assert.strictEqual(admin.deviceView({ ...base, profile: "owner" }, NOW).area, "");
assert.strictEqual(admin.deviceView({ ...base, profile: "ab12cd34", profile_name: "Bruder" }, NOW).area, "Bruder");
assert.strictEqual(admin.deviceView({ ...base, profile: "ab12cd34", profile_name: "" }, NOW).area, "Gast");
const prof = { id: "ab12cd34", name: "Bruder", limits: { ai_per_day: 100, messages_per_10min: 0 }, devices: 1 };
assert.deepStrictEqual(admin.profileView(prof), {
  id: "ab12cd34", name: "Bruder", aiPerDay: 100, perTenMin: 0,
  summary: "KI-Anfragen/Tag: 100 · Nachrichten/10 Min.: unbegrenzt", devices: "1 Gerät",
});
assert.strictEqual(admin.profileView({ ...prof, devices: 0 }).devices, "0 Geräte");
assert.strictEqual(admin.profileView({ ...prof, devices: 3 }).devices, "3 Geräte");
assert.strictEqual(admin.parseLimit("0"), 0);
assert.strictEqual(admin.parseLimit(" 25 "), 25);
assert.strictEqual(admin.parseLimit("100000"), 100000);
for (const bad of ["100001", "-1", "1.5", "", "abc", "1e3", "1234567"]) assert.strictEqual(admin.parseLimit(bad), null, bad);
 
console.log("remote_admin.js OK");