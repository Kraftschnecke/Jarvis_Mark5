// Prueft web/links.js ohne Browser (wird von test_links.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const { splitLinks, safeLink } = require(path.join(__dirname, "..", "web", "links.js"));

// normaler Link, Text davor und danach
let parts = splitLinks("Neu: [Selber Wölfe in der Krise](https://www.example.de/a/b?x=1) und mehr.");
assert.deepStrictEqual(parts, [
  { text: "Neu: " },
  { label: "Selber Wölfe in der Krise", url: "https://www.example.de/a/b?x=1", host: "www.example.de" },
  { text: " und mehr." },
]);

// mehrere Links, Aufzaehlung
parts = splitLinks("- [A](https://a.de/1)\n- [B](https://b.de/2)");
assert.strictEqual(parts.filter((p) => p.url).length, 2);
assert.strictEqual(parts.map((p) => p.text || p.label).join("|"), "- |A|\n- |B");

// ohne Link: unveraendert ein Textstueck; leer: nichts
assert.deepStrictEqual(splitLinks("Nur Text mit [Klammern] und (Klammern)"), [{ text: "Nur Text mit [Klammern] und (Klammern)" }]);
assert.deepStrictEqual(splitLinks(""), []);

// abgelehnt: kein https, andere Schemata, Zugangsdaten, fremder Port, kaputt -> bleibt Text
for (const bad of [
  "[x](http://a.de/)", "[x](javascript:alert(1))", "[x](data:text/html,hi)", "[x](ftp://a.de/f)",
  "[x](https://user:pw@a.de/)", "[x](https://a.de:8443/)", "[x](https://)", "[x](https:// a.de)",
  "[x](/relativ)", "[](https://a.de/)",
]) {
  assert.ok(splitLinks(bad).every((p) => p.url === undefined), "darf kein Link werden: " + bad);
  assert.strictEqual(splitLinks(bad).map((p) => p.text).join(""), bad, "Text bleibt vollstaendig: " + bad);
}

// Der angezeigte Rechnername ist der der ECHTEN Adresse, nicht der im Link-Text
parts = splitLinks("[https://www.tagesschau.de](https://boese.example/phishing)");
assert.strictEqual(parts[0].host, "boese.example");
assert.strictEqual(parts[0].label, "https://www.tagesschau.de");

// Lange Adressen (Google-Weiterleitungen, ca. 450 Zeichen) werden noch zum Link
const long = "https://news.google.com/rss/articles/" + "A".repeat(450) + "?oc=5";
assert.strictEqual(splitLinks("[Titel](" + long + ")")[0].url, long);

// Port 443 ausdruecklich ist ok; Gross/Klein im Host wird vereinheitlicht
assert.strictEqual(safeLink("https://A.DE:443/x").host, "a.de");
assert.strictEqual(safeLink("nonsense"), null);

console.log("links.js OK");
