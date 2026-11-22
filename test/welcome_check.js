// Prueft welcome_logic.js und die Anzeige der kleinen Fenster (welcome_panels.js) ohne Browser.
"use strict";
const assert = require("assert");
const path = require("path");
const web = path.join(__dirname, "..", "web");
const L = require(path.join(web, "welcome_logic.js"));
const Panels = require(path.join(web, "welcome_panels.js"));

// ---- Auswahl der Fenster
const built = ["goals", "focus", "lists", "calendar", "weather"];                    // beim ersten Mal an
const all = built.concat(["notes", "news", "briefing", "worldtime", "music", "system", "reminders"]);
assert.deepStrictEqual(L.builtIds(), all);
assert.deepStrictEqual(L.DEFAULT_ENABLED, built);
assert.deepStrictEqual(L.normalizeEnabled(undefined), built);          // nichts gespeichert: die ersten fuenf
assert.deepStrictEqual(L.normalizeEnabled("kaputt"), built);
assert.deepStrictEqual(L.normalizeEnabled(null), built);
assert.deepStrictEqual(L.normalizeEnabled(all), all);
assert.deepStrictEqual(L.normalizeEnabled([]), []);                   // bewusst alles aus
assert.deepStrictEqual(L.normalizeEnabled(["weather", "goals", "goals", "news", "x", 5]), ["goals", "weather", "news"]);   // Reihenfolge der Seite, ohne Doppelte und Ungebautes
assert.deepStrictEqual(L.toggleWindow(built, "lists"), ["goals", "focus", "calendar", "weather"]);
assert.deepStrictEqual(L.toggleWindow(["goals"], "calendar"), ["goals", "calendar"]);
assert.deepStrictEqual(L.toggleWindow(built, "news"), built.concat("news"));
assert.deepStrictEqual(L.toggleWindow(built, "custom"), built);        // nicht gebaute lassen sich nicht einschalten
assert.deepStrictEqual(L.toggleWindow(built, "gibtsnicht"), built);

// ---- Verteilung: links bekommt bei ungerader Zahl eins mehr
const split = (n) => L.splitColumns(built.slice(0, n));
assert.deepStrictEqual(split(0), { left: [], right: [] });
assert.deepStrictEqual(split(1), { left: ["goals"], right: [] });
assert.deepStrictEqual(split(2), { left: ["goals"], right: ["focus"] });
assert.deepStrictEqual(split(3), { left: ["goals", "focus"], right: ["lists"] });
assert.deepStrictEqual(split(5), { left: ["goals", "focus", "lists"], right: ["calendar", "weather"] });
assert.strictEqual(L.isCompact(3), false);
assert.strictEqual(L.isCompact(4), true);

// ---- Karten der Fenster-Verwaltung: gruen, rot, gelb, gelb gestrichelt
const def = (id) => L.WINDOWS.find((w) => w.id === id);
assert.strictEqual(L.cardState(def("goals"), built), "g");
assert.strictEqual(L.cardState(def("goals"), ["focus"]), "r");
assert.strictEqual(L.cardState(def("news"), built), "r");
assert.strictEqual(L.cardState({ id: "x", state: "ability" }, built), "y");   // gibt es derzeit keins mehr, die Karte bleibt aber moeglich
assert.strictEqual(L.cardState(def("history"), built), "yd");
assert.strictEqual(L.cardState(def("custom"), built), "yd");
assert.strictEqual(L.WINDOWS.length, new Set(L.WINDOWS.map((w) => w.id)).size, "Fenster-Namen muessen eindeutig sein");
L.WINDOWS.forEach((w) => assert.ok(["built", "ability", "none"].includes(w.state) && w.title && w.desc));
["g", "r", "y", "yd"].forEach((s) => assert.ok(L.CARD_TEXT[s]));

// ---- Gruss nach Tageszeit
[[0, "Guten Abend"], [4, "Guten Abend"], [5, "Guten Morgen"], [10, "Guten Morgen"], [11, "Guten Tag"], [17, "Guten Tag"], [18, "Guten Abend"], [23, "Guten Abend"]]
  .forEach(([hour, word]) => assert.strictEqual(L.greetingWord(hour), word, "Stunde " + hour));

// ---- Zeiten
assert.strictEqual(L.formatRemaining(0), "00:00");
assert.strictEqual(L.formatRemaining(75), "01:15");
assert.strictEqual(L.formatRemaining(3725), "1:02:05");
assert.strictEqual(L.formatRemaining(-5), "00:00");
assert.strictEqual(L.formatRemaining("abc"), "00:00");
assert.strictEqual(L.dayKey(new Date(2026, 10, 22)), "2026-11-22");
assert.strictEqual(L.dayKey(L.addDays(new Date(2026, 11, 31), 1)), "2027-01-01");

// ---- Termine eines Tages, sortiert; kaputte Eintraege stoeren nicht
const events = [{ date: "2026-11-22", time: "14:30", title: "B" }, { date: "2026-11-22", time: "", title: "Z" }, { date: "2026-11-22", time: "10:00", title: "A" },
  { date: "2026-11-23", time: "08:00", title: "morgen" }, null, { title: "ohne Datum" }];
assert.deepStrictEqual(L.eventsOn(events, "2026-11-22").map((e) => e.title), ["Z", "A", "B"]);
assert.deepStrictEqual(L.eventsOn(undefined, "2026-11-22"), []);

// ---- Ziele
assert.deepStrictEqual(L.goalProgress([{ done: true }, { done: false }, { done: true }, { done: true }]), { done: 3, total: 4, percent: 75 });
assert.deepStrictEqual(L.goalProgress([]), { done: 0, total: 0, percent: 0 });
assert.deepStrictEqual(L.goalProgress(null), { done: 0, total: 0, percent: 0 });
assert.strictEqual(L.bestStreak([{ daily: true, streak: 6 }, { daily: true, streak: 2 }, { daily: false, streak: 9 }]), 6);
assert.strictEqual(L.bestStreak([]), 0);

// ---- Termine eintragen nur am PC
assert.ok(L.isLocalHost("127.0.0.1") && L.isLocalHost("localhost"));
assert.ok(!L.isLocalHost("gott-desktop.taild3a628.ts.net") && !L.isLocalHost("127.0.0.1.evil.example"));

// ---- kleine Fenster mit einem Papier-DOM: alles kommt als Text an, nie als HTML
class Node {
  constructor(tag, className, text) { this.tag = tag; this.className = className || ""; this.textContent = text === undefined ? "" : String(text); this.children = []; this.style = {}; }
  setAttribute() {}
  addEventListener(type, fn) { (this.listeners = this.listeners || []).push(fn); }
  append(...nodes) { nodes.forEach((n) => this.children.push(n)); }
  all() { return [this].concat(...this.children.map((c) => c.all())); }
  text() { return [this.textContent].concat(this.children.map((c) => c.text())).join(" ").replace(/\s+/g, " ").trim(); }
  set innerHTML(value) { throw new Error("innerHTML darf nicht benutzt werden"); }
}
const el = (tag, className, text) => new Node(tag, className, text);
const today = new Date();
const key = L.dayKey(today);
const tomorrowKey = L.dayKey(L.addDays(today, 1));
function makeApp(over) {
  return Object.assign({
    el, L, data: { goals: [], events: [], lists: [] }, weather: null,
    focusNow: () => ({ active: false }), timersNow: () => [],
  }, over);
}
const draw = (panel) => { const body = el("div"); panel.draw(body); return body.text(); };

let app = makeApp();
let p = Panels.create(app);
assert.strictEqual(draw(p.goals), "Noch keine Ziele für heute.");
assert.strictEqual(draw(p.lists), "Noch keine Listen.");
assert.strictEqual(draw(p.weather), "Kein Wetter verfügbar.");
assert.strictEqual(draw(p.focus), "Kein Timer, keine Fokus-Sitzung.");
assert.strictEqual(draw(p.calendar), "Heute keine Termine. Morgen keine Termine");
assert.strictEqual(p.goals.extra(), "");

app = makeApp({
  data: {
    goals: [{ text: "Training <img src=x onerror=alert(1)>", done: true }, { text: "Lernen", done: false }, { text: "A", done: false }, { text: "B", done: false }, { text: "C", done: false }, { text: "D", done: false }],
    events: [{ date: key, time: "10:00", title: "Abnahme" }, { date: key, time: "09:00", title: "<b>fett</b>" }, { date: tomorrowKey, time: "08:15", title: "Vorlesung" }, { date: tomorrowKey, time: "19:00", title: "Fußball" }],
    lists: [{ name: "Einkauf", items: [{ text: "Milch", done: false }, { text: "Brot", done: true }, { text: "Eier", done: false }, { text: "Reis", done: false }, { text: "Tee", done: false }] }],
  },
  weather: "In Växjö sind es 4 °C.",
  focusNow: () => ({ active: true, remaining: 1450, label: "Lernen", phase_name: "Arbeit" }),
  timersNow: () => [{ id: 1, name: "Nudeln", remaining: 300 }, { id: 2, name: "Ei", remaining: 60 }, { id: 3, name: "Drittes", remaining: 5 }],
});
p = Panels.create(app);
let text = draw(p.goals);
assert.ok(text.includes("Training <img src=x onerror=alert(1)>"), "Ziele-Text bleibt Text");     // der Text steht als Text da, wird nicht zu einem Element
assert.ok(text.includes("+ 1 weitere"));
assert.strictEqual(p.goals.extra(), "1/6");
text = draw(p.calendar);
assert.ok(text.indexOf("09:00") < text.indexOf("10:00"), "Termine nach Uhrzeit");
assert.ok(text.includes("<b>fett</b>") && text.includes("Morgen 2 Termine · ab 08:15"), text);
text = draw(p.lists);
assert.ok(text.includes("Milch") && text.includes("Eier") && text.includes("Reis") && !text.includes("Brot") && !text.includes("Tee") && text.includes("+ 1 weitere"), text);   // 4 offen: 3 gezeigt
assert.strictEqual(p.lists.extra(), "Einkauf");
text = draw(p.focus);
assert.ok(text.includes("24:10") && text.includes("Lernen · Arbeit") && text.includes("05:00 Nudeln") && text.includes("01:00 Ei") && !text.includes("Drittes"), text);   // mit Fokus nur zwei Timer
assert.strictEqual(draw(p.weather), "In Växjö sind es 4 °C.");

// ein Tag mit vielen Terminen und ein einzelner Termin morgen
app = makeApp({ data: { events: [1, 2, 3, 4, 5].map((n) => ({ date: key, time: "1" + n + ":00", title: "T" + n })).concat([{ date: tomorrowKey, time: "", title: "ganztags" }]) } });
text = draw(Panels.create(app).calendar);
assert.ok(text.includes("+ 2 weitere heute") && text.includes("T3") && !text.includes("T4") && text.includes("Morgen 1 Termin") && !text.includes("ab "), text);

// ---- Weltuhr
assert.deepStrictEqual(L.normalizeCities(null), L.DEFAULT_CITIES);
assert.deepStrictEqual(L.normalizeCities(["tokio", "tokio", "mars", 5, "berlin"]), ["tokio", "berlin"]);
assert.deepStrictEqual(L.normalizeCities([]), []);
assert.strictEqual(L.normalizeCities(L.CITIES.map((c) => c.id)).length, L.MAX_CITIES);
assert.deepStrictEqual(L.toggleCity(["tokio"], "berlin"), ["tokio", "berlin"]);
assert.deepStrictEqual(L.toggleCity(["tokio", "berlin"], "tokio"), ["berlin"]);
assert.deepStrictEqual(L.toggleCity(["tokio"], "mars"), ["tokio"]);
const full = L.CITIES.slice(0, L.MAX_CITIES).map((c) => c.id);
assert.deepStrictEqual(L.toggleCity(full, L.CITIES[L.MAX_CITIES].id), full);        // mehr als das Maximum geht nicht
assert.strictEqual(new Set(L.CITIES.map((c) => c.id)).size, L.CITIES.length);
L.CITIES.forEach((c) => assert.ok(/^\d\d:\d\d$/.test(L.cityTime(new Date(), c.tz)), c.tz));      // jede Zeitzone kennt der Browser
assert.strictEqual(L.cityTime(new Date(Date.UTC(2026, 10, 22, 12, 0)), "Asia/Tokyo"), "21:00");
assert.strictEqual(L.cityDayLabel(new Date(Date.UTC(2026, 10, 22, 12, 0)), undefined), "heute");
assert.strictEqual(L.cityDayLabel(new Date(Date.UTC(2026, 10, 22, 12, 0)), "Pacific/Auckland") === "morgen" || process.env.TZ !== undefined, true);

// ---- Erinnerungen
const now0 = new Date(2026, 10, 22, 10, 0);
assert.strictEqual(L.describeDue("2026-11-22T18:00", now0), "heute 18:00");
assert.strictEqual(L.describeDue("2026-11-23T09:00", now0), "morgen 09:00");
assert.strictEqual(L.describeDue("2026-11-25T09:00", now0), "Mi 09:00");
assert.strictEqual(L.describeDue("2026-11-28T09:00", now0), "Sa 09:00");
assert.strictEqual(L.describeDue("2026-11-29T09:00", now0), "29.11. 09:00");
assert.strictEqual(L.describeDue("2026-11-21T09:00", now0), "gestern 09:00");
assert.strictEqual(L.describeDue("kaputt", now0), "kaputt");
assert.strictEqual(L.describeDue(null, now0), "");

// ---- neue kleine Fenster
const loadedApp = (extra, over) => makeApp(Object.assign({ W: { loadLevel: (v) => (v < 70 ? "ok" : v < 90 ? "warn" : "high") }, extra, cities: ["tokio", "berlin", "sydney", "london", "athen"], local: true }, over));
p = Panels.create(loadedApp({}));
assert.strictEqual(draw(p.news), "Lade …");
assert.strictEqual(draw(p.reminders), "Lade …");
p = Panels.create(loadedApp({ news: { status: "disabled" }, briefing: { status: "error", error: "Briefing nicht abrufbar." }, reminders: { status: "ok", data: [] }, perf: { status: "loading" } }));
assert.strictEqual(draw(p.news), "In den Einstellungen ausgeschaltet.");
assert.strictEqual(draw(p.briefing), "Briefing nicht abrufbar.");
assert.strictEqual(draw(p.reminders), "Keine Erinnerungen.");
assert.strictEqual(draw(p.system), "Lade …");
p = Panels.create(loadedApp({
  news: { status: "ok", data: [1, 2, 3, 4].map((n) => ({ title: "Meldung " + n + " <b>x</b>" })) },
  briefing: { status: "ok", data: "Guten Abend, Sir. <i>Heute</i> viel zu tun." },
  reminders: { status: "ok", data: [1, 2, 3, 4].map((n) => ({ due: "2026-11-2" + n + "T09:00", text: "Aufgabe " + n })) },
  perf: { status: "ok", data: { cpu_percent: 12, ram_percent: 75, disk_percent: 95, battery: { percent: 80, plugged: true } } },
}, { data: { notes: "Milch kaufen\nAnruf <u>planen</u>" } }));
text = draw(p.news);
assert.ok(text.includes("Meldung 3 <b>x</b>") && !text.includes("Meldung 4") && text.includes("+ 1 weitere"), text);
const compactNews = Panels.create(Object.assign({}, loadedApp({ news: { status: "ok", data: [1, 2, 3, 4].map((n) => ({ title: "Meldung " + n })) } }), { compact: true }));
text = draw(compactNews.news);
assert.ok(text.includes("Meldung 2") && !text.includes("Meldung 3") && text.includes("+ 2 weitere"), text);   // volle Spalte: zwei Zeilen
assert.ok(draw(p.briefing).includes("<i>Heute</i>"));
text = draw(p.reminders);
assert.ok(text.includes("Aufgabe 3") && !text.includes("Aufgabe 4") && text.includes("+ 1 weitere"), text);
assert.ok(draw(p.notes).includes("Anruf <u>planen</u>"));
text = draw(p.system);
assert.ok(text.includes("CPU") && text.includes("12 %") && text.includes("95 %") && text.includes("Akku 80 % · lädt"), text);
const meters = [];
p.system.draw({ append: (...n) => n.forEach((x) => x.all().forEach((y) => y.className.startsWith("bar ") && meters.push(y.className))) });
assert.deepStrictEqual(meters, ["bar ok", "bar warn", "bar high"]);
text = draw(p.worldtime);
assert.ok(text.includes("Tokio") && text.includes("Berlin") && text.includes("London") && !text.includes("Athen"), text);     // vier Staedte gezeigt
assert.strictEqual(draw(Panels.create(loadedApp({}, { cities: [] })).worldtime), "Keine Stadt gewählt.");
assert.strictEqual(draw(Panels.create(loadedApp({}, { data: { notes: "  " } })).notes), "Noch keine Notiz.");
// nicht am PC: Musik und PC-Status bleiben leer
p = Panels.create(loadedApp({ perf: { status: "ok", data: { cpu_percent: 1 } } }, { local: false }));
assert.strictEqual(draw(p.music), "Nur am PC.");
assert.strictEqual(draw(p.system), "Nur am PC.");
// am PC: drei Tasten; ein Klick ruft media auf
const calls = [];
p = Panels.create(loadedApp({}, { media: (a) => calls.push(a) }));
const bar = el("div");
p.music.draw(bar);
const keys = bar.all().filter((n) => n.tag === "button");
assert.strictEqual(keys.length, 3);
keys.forEach((k) => (k.listeners || []).forEach((f) => f({ stopPropagation() {} })));
assert.deepStrictEqual(calls, ["previous", "play_pause", "next"]);

console.log("welcome OK");