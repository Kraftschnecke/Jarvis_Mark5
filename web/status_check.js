// Prueft web/status.js ohne Browser (wird von test_status.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const S = require(path.join(__dirname, "..", "web", "status.js"));

// Tageszeit
for (const [h, g] of [[0, "Guten Abend"], [3, "Guten Abend"], [4, "Guten Morgen"], [9, "Guten Morgen"],
                      [10, "Guten Tag"], [17, "Guten Tag"], [18, "Guten Abend"], [23, "Guten Abend"]]) {
  assert.strictEqual(S.greetingFor(h), g, String(h));
}

// Restzeit
assert.strictEqual(S.formatRemaining(0), "0:00");
assert.strictEqual(S.formatRemaining(5), "0:05");
assert.strictEqual(S.formatRemaining(200), "3:20");
assert.strictEqual(S.formatRemaining(3599), "59:59");
assert.strictEqual(S.formatRemaining(3725), "1:02:05");
assert.strictEqual(S.formatRemaining(-4), "0:00");
assert.strictEqual(S.formatRemaining("x"), "0:00");
assert.strictEqual(S.formatRemaining(7.9), "0:07");

// Bericht: Datum ist eine Mittwochmorgen (lokale Zeit, daher mit Konstruktor ohne Zeitzone)
const wed = new Date(2026, 9, 21, 4, 42);
let text = S.buildStartupReport({ address: "Sir", now: wed, timers: [], memoryEnabled: true });
assert.strictEqual(text, "Guten Morgen, Sir. Heute ist Mittwoch, der 21. Oktober, 04:42 Uhr. Wie kann ich helfen?");

// Ein Timer, mehrere Timer, Gedaechtnis aus, andere Anrede, fehlende Angaben
text = S.buildStartupReport({ address: "Chef", now: new Date(2026, 0, 5, 13, 5),
  timers: [{ name: "Nudeln", remaining: 200 }], memoryEnabled: true });
assert(text.startsWith("Guten Tag, Chef. Heute ist Montag, der 5. Januar, 13:05 Uhr."), text);
assert(text.includes("Ein Timer läuft: Nudeln (noch 3:20)."), text);

text = S.buildStartupReport({ address: "Sir", now: wed,
  timers: [{ name: "Nudeln", remaining: 200 }, { name: "Ei", remaining: 45 }], memoryEnabled: false });
assert(text.includes("2 Timer laufen: Nudeln (noch 3:20), Ei (noch 0:45)."), text);
assert(text.includes("Mein Gedächtnis ist ausgeschaltet."), text);
assert(text.endsWith("Wie kann ich helfen?"), text);

text = S.buildStartupReport({ now: wed });                 // nichts angegeben: kein Absturz
assert(text.includes("Sir") && !text.includes("Timer") && !text.includes("Gedächtnis"), text);
text = S.buildStartupReport({ now: wed, timers: "kaputt", memoryEnabled: undefined });
assert(!text.includes("Timer"), text);

// Wetter-Satz: kommt hinter das Datum, fehlt er, steht nichts da; Unsinn wird ignoriert
text = S.buildStartupReport({ address: "Sir", now: wed, timers: [], weather: "In Mannheim sind es 12 °C, bewölkt. Heute bis 15 °C." });
assert.strictEqual(text, "Guten Morgen, Sir. Heute ist Mittwoch, der 21. Oktober, 04:42 Uhr. In Mannheim sind es 12 °C, bewölkt. Heute bis 15 °C. Wie kann ich helfen?");
for (const bad of [null, undefined, "", "   ", 42, {}, "x".repeat(201)]) {
  assert.strictEqual(S.buildStartupReport({ now: wed, weather: bad }), S.buildStartupReport({ now: wed }), String(bad));
}

console.log("status.js OK");
