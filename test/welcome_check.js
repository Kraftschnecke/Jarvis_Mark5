// Prueft welcome_logic.js und die Anzeige der kleinen Fenster (welcome_panels.js) ohne Browser.
"use strict";
const assert = require("assert");
const path = require("path");
const web = path.join(__dirname, "..", "web");
const L = require(path.join(web, "welcome_logic.js"));
const Panels = require(path.join(web, "welcome_panels.js"));
const Dialogs = require(path.join(web, "welcome_dialogs.js"));
const Widgets = require(path.join(web, "widgets.js"));

// ---- Auswahl der Fenster
const built = ["goals", "focus", "lists", "calendar", "weather"];                    // beim ersten Mal an
const all = built.concat(["notes", "news", "briefing", "worldtime", "music", "system", "pclage", "drives", "reminders"]);
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
  replaceChildren(...nodes) { this.children = nodes; }
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
    el, L, data: { goals: [], events: [], lists: [] }, extra: {}, icon: (key, size) => el("svg", "wicon " + key + " " + size),
    focusNow: () => ({ active: false }), timersNow: () => [],
  }, over);
}
const draw = (panel) => { const body = el("div"); panel.draw(body); return body.text(); };

let app = makeApp();
let p = Panels.create(app);
assert.strictEqual(draw(p.goals), "Noch keine Ziele für heute.");
assert.strictEqual(draw(p.lists), "Noch keine Listen.");
assert.strictEqual(draw(p.weather), "Lade …");
assert.strictEqual(draw(p.focus), "Kein Timer, keine Fokus-Sitzung.");
assert.strictEqual(draw(p.calendar), "Heute keine Termine. Morgen keine Termine");
assert.strictEqual(p.goals.extra(), "");

app = makeApp({
  data: {
    goals: [{ text: "Training <img src=x onerror=alert(1)>", done: true }, { text: "Lernen", done: false }, { text: "A", done: false }, { text: "B", done: false }, { text: "C", done: false }, { text: "D", done: false }],
    events: [{ date: key, time: "10:00", title: "Abnahme" }, { date: key, time: "09:00", title: "<b>fett</b>" }, { date: tomorrowKey, time: "08:15", title: "Vorlesung" }, { date: tomorrowKey, time: "19:00", title: "Fußball" }],
    lists: [{ name: "Einkauf", items: [{ text: "Milch", done: false }, { text: "Brot", done: true }, { text: "Eier", done: false }, { text: "Reis", done: false }, { text: "Tee", done: false }] }],
  },
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
const loadedApp = (extra, over) => makeApp(Object.assign({ W: Widgets, extra, cities: ["tokio", "berlin", "sydney", "london", "athen"], local: true }, over));
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

// ---- Wetter: Logik
assert.strictEqual(L.degrees(3.6), "4°");
assert.strictEqual(L.degrees(-0.4), "0°");
assert.strictEqual(L.degrees(null), "–");
assert.strictEqual(L.degrees("5"), "–");
assert.strictEqual(L.degrees(NaN), "–");
assert.strictEqual(L.celsius(11.6), "12 °C");
assert.strictEqual(L.celsius(undefined), "–");
assert.strictEqual(L.tempRange({ low: 2, high: 6 }), "2° bis 6°");
assert.strictEqual(L.tempRange({ low: null, high: 6 }), "6°");
assert.strictEqual(L.tempRange({ low: 2, high: null }), "2°");
assert.strictEqual(L.tempRange({}), "–");
assert.strictEqual(L.tempRange(null), "–");
assert.strictEqual(L.shortPlace("Växjö, Kronoberg, Schweden"), "Växjö");
assert.strictEqual(L.shortPlace(undefined), "");
assert.strictEqual(L.rainText(60), "60 %");
assert.strictEqual(L.rainText(null), "");
const nowW = new Date(2026, 10, 22, 10, 0);           // Sonntag
assert.deepStrictEqual(L.forecastDay("2026-11-22", nowW), { label: "Heute", date: "22.11." });
assert.deepStrictEqual(L.forecastDay("2026-11-23", nowW), { label: "Morgen", date: "23.11." });
assert.deepStrictEqual(L.forecastDay("2026-11-24", nowW), { label: "Di", date: "24.11." });
assert.deepStrictEqual(L.forecastDay("2026-11-28", nowW), { label: "Sa", date: "28.11." });
assert.deepStrictEqual(L.forecastDay("kaputt", nowW), { label: "kaputt", date: "" });
assert.deepStrictEqual(L.forecastDay(null, nowW), { label: "", date: "" });
// Temperaturbalken: Woche von -1 bis 13 Grad
const weekDays = [{ low: -1, high: 5 }, { low: 3, high: 13 }, { low: 6, high: 6 }, { low: null, high: 8 }];
assert.deepStrictEqual(L.barSpan(weekDays, weekDays[0]), { left: 0, width: 42.9 });
assert.deepStrictEqual(L.barSpan(weekDays, weekDays[1]), { left: 28.6, width: 71.4 });
assert.deepStrictEqual(L.barSpan(weekDays, weekDays[2]), { left: 50, width: 8 });          // mindestens 8 % breit
assert.deepStrictEqual(L.barSpan(weekDays, weekDays[3]), { left: 0, width: 0 });           // ohne Tiefstwert kein Balken
assert.deepStrictEqual(L.barSpan(weekDays, { low: 13, high: 13 }), { left: 92, width: 8 });      // am oberen Rand bleibt der Balken im Feld
assert.deepStrictEqual(L.barSpan([{ low: 4, high: 4 }], { low: 4, high: 4 }), { left: 0, width: 100 });
assert.deepStrictEqual(L.barSpan([], { low: 1, high: 2 }), { left: 0, width: 0 });
assert.deepStrictEqual(L.barSpan(null, null), { left: 0, width: 0 });
for (const day of weekDays.slice(0, 3)) { const b = L.barSpan(weekDays, day); assert.ok(b.left >= 0 && b.left + b.width <= 100.05, JSON.stringify(b)); }
// Symbole: alle sieben, nur Linien-Formen; unbekannter Name zaehlt nicht
assert.deepStrictEqual(Object.keys(L.WEATHER_ICONS).sort(), ["clear", "cloudy", "fog", "partly", "rain", "snow", "thunder"]);
Object.values(L.WEATHER_ICONS).forEach((shapes) => shapes.forEach(([tag, attrs]) => {
  assert.ok(tag === "path" || tag === "circle", tag);
  Object.values(attrs).forEach((v) => assert.ok(/^[-0-9.a-zA-Z ]+$/.test(String(v)), "nur Zeichen fuer Formen: " + v));
}));
["clear", "partly", "rain"].forEach((k) => assert.ok(L.isWeatherIcon(k)));
["toString", "__proto__", "constructor", "", null, 5, "Rain"].forEach((k) => assert.ok(!L.isWeatherIcon(k), String(k)));

// ---- Wetter: kleines Fenster
const wxDays = [0, 1, 2, 3, 4, 5, 6].map((i) => {
  const d = L.addDays(today, i);
  return { date: L.dayKey(d), condition: "Tag " + i, icon: ["rain", "clear", "snow", "fog", "cloudy", "thunder", "partly"][i], high: 6 + i, low: 2 - i, rain_chance_percent: i === 0 ? 60 : 10 };
});
const wxData = { place: "Växjö, Kronoberg, Schweden", now: { temperature: 3.6, icon: "partly", condition: "teilweise <b>bewölkt</b>", feels_like: 1, humidity_percent: 80, wind_kmh: 10 }, days: wxDays };
p = Panels.create(loadedApp({ forecast: { status: "loading" } }));
assert.strictEqual(draw(p.weather), "Lade …");
assert.strictEqual(p.weather.extra(), "");
assert.strictEqual(draw(Panels.create(loadedApp({ forecast: { status: "disabled" } })).weather), "In den Einstellungen ausgeschaltet.");
assert.strictEqual(draw(Panels.create(loadedApp({ forecast: { status: "error", error: "Das Wetter ist gerade nicht abrufbar." } })).weather), "Das Wetter ist gerade nicht abrufbar.");
assert.strictEqual(draw(Panels.create(loadedApp({ forecast: { status: "ok", data: { place: "X", days: [] } } })).weather), "Keine Vorhersage verfügbar.");
assert.strictEqual(draw(Panels.create(loadedApp({ forecast: { status: "ok", data: null } })).weather), "Keine Vorhersage verfügbar.");
p = Panels.create(loadedApp({ forecast: { status: "ok", data: wxData } }));
text = draw(p.weather);
assert.ok(text.includes("4 °C") && text.includes("teilweise <b>bewölkt</b>") && text.includes("heute 2° bis 6° · Regen 60 %"), text);   // Text bleibt Text
assert.ok(text.includes("Morgen") && text.includes("7°") && text.includes("9°") && !text.includes("10°"), text);                           // genau drei weitere Tage
assert.strictEqual(p.weather.extra(), "Växjö");
const wxBody = el("div");
p.weather.draw(wxBody);
assert.deepStrictEqual(wxBody.all().filter((n) => n.className.startsWith("wicon")).map((n) => n.className.split(" ")[1]), ["partly", "clear", "snow", "fog"], "Symbol jetzt + drei Tage");
// ohne Jetzt-Werte gilt der Tageshoechstwert; wenig Regen wird nicht genannt
const dry = Object.assign({}, wxData, { now: null, days: [Object.assign({}, wxDays[0], { rain_chance_percent: 10 })].concat(wxDays.slice(1)) });
text = draw(Panels.create(loadedApp({ forecast: { status: "ok", data: dry } })).weather);
assert.ok(text.includes("6 °C") && !text.includes("Regen"), text);
// volle Spalte: nur eine Zeile (Temperatur und Spanne), keine Leiste
text = draw(Panels.create(Object.assign({}, loadedApp({ forecast: { status: "ok", data: wxData } }), { compact: true })).weather);
assert.ok(text.includes("4 °C") && text.includes("2° bis 6°") && !text.includes("Morgen") && !text.includes("Regen"), text);

// ---- PC-Lage und Laufwerke: Logik
assert.deepStrictEqual(["ok", "warn", "bad", "tip"].map(L.lightLevel), ["ok", "warn", "bad", "tip"]);
["rot", "", null, undefined, "__proto__", 5].forEach((v) => assert.strictEqual(L.lightLevel(v), "warn", String(v)));     // Unbekanntes ist nie "ok"
assert.deepStrictEqual(["ok", "warning", "bad", "unknown"].map(L.healthText), ["Gesund", "Warnung", "Defekt gemeldet", "Zustand unbekannt"]);
["", null, "toString", "__proto__", "Healthy"].forEach((v) => assert.strictEqual(L.healthText(v), "Zustand unbekannt", String(v)));
assert.deepStrictEqual(["ok", "warning", "bad", "unknown", "x"].map(L.healthLevel), ["ok", "warn", "bad", "tip", "tip"]);
assert.deepStrictEqual(["SSD", "HDD", "unbekannt", null, "<b>"].map(L.mediaLabel), ["SSD", "HDD", "Laufwerk", "Laufwerk", "Laufwerk"]);
const nf = Widgets.formatNumber;
assert.strictEqual(L.programText("ram", { name: "chrome.exe", mb: 3300, count: 24 }, nf), "chrome.exe (24×) · 3,2 GB");
assert.strictEqual(L.programText("ram", { name: "a.exe", mb: 512.4, count: 1 }, nf), "a.exe · 512 MB");
assert.strictEqual(L.programText("cpu", { name: "x.exe", percent: 12.4, count: 2 }, nf), "x.exe (2×) · 12 %");
assert.strictEqual(L.programText("disk", { name: "steam.exe", mb_s: 12.34, count: 1 }, nf), "steam.exe · 12,3 MB/s");
assert.strictEqual(L.programText("gpu", { name: "x", count: 1 }, nf), "");
assert.strictEqual(L.programText("ram", null, nf), "");
assert.strictEqual(L.programText("ram", { name: 5 }, nf), "");

// ---- PC-Lage und Laufwerke: kleine Fenster
const lageData = {
  assessment: { level: "warn", headline: "D: (HDD) stark ausgelastet <b>x</b>", findings: [{ level: "tip", tip: "Neustart." }, { level: "warn", text: "t", tip: "Programme auf die SSD <i>schieben</i>." }] },
  drives: [{ letter: "C", media: "SSD", used_percent: 75, free_gb: 60.2, busy_percent: 4, health_state: "ok" },
           { letter: "D", media: "HDD", used_percent: 46, free_gb: 500, busy_percent: 97.3, health_state: "warning" },
           { letter: "E", media: "unbekannt", used_percent: 10, free_gb: 100, busy_percent: null, health_state: "unknown" }],
  programs: { ram: [], cpu: [], disk: [] }, autostart: [],
};
p = Panels.create(loadedApp({}, { local: false }));
assert.strictEqual(draw(p.pclage), "Nur am PC.");
assert.strictEqual(draw(p.drives), "Nur am PC.");
p = Panels.create(loadedApp({}));
assert.strictEqual(draw(p.pclage), "Lade …");
assert.strictEqual(draw(Panels.create(loadedApp({ pclage: { status: "disabled" } })).drives), "In den Einstellungen ausgeschaltet.");
assert.strictEqual(draw(Panels.create(loadedApp({ pclage: { status: "error", error: "Die PC-Lage konnte nicht gelesen werden." } })).pclage), "Die PC-Lage konnte nicht gelesen werden.");
assert.strictEqual(draw(Panels.create(loadedApp({ pclage: { status: "ok", data: null } })).pclage), "Keine Auswertung verfügbar.");
assert.strictEqual(draw(Panels.create(loadedApp({ pclage: { status: "ok", data: { drives: [] } } })).drives), "Keine Laufwerke gefunden.");
p = Panels.create(loadedApp({ pclage: { status: "ok", data: lageData } }));
text = draw(p.pclage);
assert.ok(text.includes("D: (HDD) stark ausgelastet <b>x</b>") && text.includes("Tipp: Programme auf die SSD <i>schieben</i>."), text);   // erster echter Hinweis, Text bleibt Text
assert.ok(!text.includes("Neustart"), text);
const lightBody = el("div");
p.pclage.draw(lightBody);
assert.ok(lightBody.all().some((n) => n.className === "wlight warn"), "Ampel zeigt die Stufe des Servers");
text = draw(Panels.create(Object.assign({}, loadedApp({ pclage: { status: "ok", data: lageData } }), { compact: true })).pclage);
assert.ok(text.includes("stark ausgelastet") && !text.includes("Tipp"), text);                     // volle Spalte: nur die Zeile
const calmData = { assessment: { level: "ok", headline: "Alles ruhig.", findings: [{ level: "tip", tip: "Neustart." }] }, drives: [], programs: {}, autostart: [] };
text = draw(Panels.create(loadedApp({ pclage: { status: "ok", data: calmData } })).pclage);
assert.ok(text.includes("Alles ruhig.") && text.includes("Tipp: Neustart."), text);                 // ohne Problem zeigt der erste Tipp
text = draw(Panels.create(loadedApp({ pclage: { status: "ok", data: lageData } })).drives);
assert.ok(text.includes("C: SSD") && text.includes("60 GB frei") && !text.includes("60 GB frei · aktiv"), text);       // wenig Last: nicht erwaehnt
assert.ok(text.includes("D: HDD") && text.includes("500 GB frei · aktiv 97 % · Warnung"), text);
assert.ok(text.includes("E: Laufwerk") && !text.includes("weitere"), text);
text = draw(Panels.create(Object.assign({}, loadedApp({ pclage: { status: "ok", data: lageData } }), { compact: true })).drives);
assert.ok(text.includes("C: SSD") && text.includes("D: HDD") && text.includes("+ 1 weitere") && !text.includes("E: Laufwerk"), text);      // volle Spalte: zwei Zeilen
const bars = [];
Panels.create(loadedApp({ pclage: { status: "ok", data: lageData } })).drives.draw({ append: (...n) => n.forEach((x) => x.all().forEach((y) => y.className.startsWith("bar ") && bars.push(y.className))) });
assert.deepStrictEqual(bars, ["bar warn", "bar ok", "bar ok"]);                                  // Belegung 75 / 46 / 10 %

// ---- PC-Lage und Laufwerke: grosse Fenster
function openDialog(name, extra, over) {
  let opened = null;
  const fns = [];
  const reloads = [];
  const dapp = loadedApp(extra, Object.assign({
    loadExtra: (n, force) => reloads.push([n, force]),
    openWindow: (spec, build) => { const body = el("div"); build(body, { onData: (fn) => fns.push(fn), onTick() {}, close() {} }); opened = { spec, body }; },
  }, over));
  Dialogs.create(dapp)[name]();
  return { dapp, fns, reloads, spec: opened.spec, view: () => opened.body.text(), nodes: () => opened.body.all() };
}
let d = openDialog("pclage", { pclage: { status: "ok", data: Object.assign({}, lageData, { programs: { ram: [{ name: "chrome.exe", mb: 3300, count: 24 }], cpu: [], disk: [{ name: "steam.exe", mb_s: 12.34, count: 2 }] }, autostart: ["Steam", "<b>Discord</b>"] }) } });
assert.strictEqual(d.spec.title, "PC-Lage");
assert.ok(d.view().includes("D: (HDD) stark ausgelastet <b>x</b>") && d.view().includes("Tipp: Neustart.") && d.view().includes("Tipp: Programme auf die SSD <i>schieben</i>."), d.view());
assert.ok(d.view().includes("chrome.exe (24×) · 3,2 GB") && d.view().includes("steam.exe (2×) · 12,3 MB/s") && d.view().includes("nichts Auffälliges"), d.view());
assert.ok(d.view().includes("2 Einträge: Steam, <b>Discord</b>"), d.view());
assert.strictEqual(d.nodes().filter((n) => n.className === "wfinding").length, 2);
const refresh = d.nodes().find((n) => n.tag === "button" && n.textContent === "Aktualisieren");
refresh.listeners[0]();
assert.deepStrictEqual(d.reloads[d.reloads.length - 1], ["pclage", true]);
d.dapp.extra.pclage = { status: "ok", data: calmData };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("Alles ruhig.") && !d.view().includes("stark ausgelastet") && !d.view().includes("Keine Hinweise"), d.view());
d.dapp.extra.pclage = { status: "ok", data: { assessment: { level: "ok", headline: "Alles ruhig.", findings: [] }, drives: [], programs: {}, autostart: [] } };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("Keine Hinweise, alles ruhig.") && d.view().includes("Keine Einträge gefunden."), d.view());
d.dapp.extra.pclage = { status: "error", error: "Die PC-Lage konnte nicht gelesen werden." };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("Die PC-Lage konnte nicht gelesen werden.") && !d.view().includes("Hinweise"), d.view());
d.dapp.extra.pclage = { status: "loading" };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("Lade …"));
d = openDialog("pclage", {}, { local: false });
assert.ok(d.view().includes("nur am PC") && d.nodes().filter((n) => n.tag === "button").length === 0 && d.reloads.length === 0, d.view());      // nichts holen, keine Knoepfe

d = openDialog("drives", { pclage: { status: "ok", data: lageData } });
assert.strictEqual(d.spec.title, "Laufwerke");
assert.strictEqual(d.spec.wide, true);
assert.ok(d.view().includes("C: SSD") && d.view().includes("Gesund") && d.view().includes("60,2 GB frei von"), d.view());
assert.ok(d.view().includes("D: HDD") && d.view().includes("Warnung") && d.view().includes("Auslastung 97 %"), d.view());
assert.ok(d.view().includes("E: Laufwerk") && d.view().includes("Zustand unbekannt") && d.view().includes("Auslastung –"), d.view());
assert.ok(d.view().includes("Lesen –"), "fehlende Werte als Strich");
assert.strictEqual(d.nodes().filter((n) => n.className === "wdrivecard").length, 3);
const badges = d.nodes().filter((n) => n.className.startsWith("wbadge")).map((n) => n.className);
assert.deepStrictEqual(badges, ["wbadge ok", "wbadge warn", "wbadge tip"]);
d.dapp.extra.pclage = { status: "ok", data: { drives: [{ letter: "F", media: "SSD", used_percent: 5, free_gb: 10, total_gb: 20 }] } };      // Werte ganz ohne Eintrag (nicht nur null)
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("Auslastung –") && !d.view().includes("NaN"), d.view());
d.dapp.extra.pclage = { status: "ok", data: { drives: [Object.assign({}, lageData.drives[0], { system: true, model: "INTEL <i>SSD</i>", read_mb_s: 3.2, write_mb_s: 0.4 })] } };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("C: SSD · Windows") && d.view().includes("INTEL <i>SSD</i>") && d.view().includes("Lesen 3,2 MB/s · Schreiben 0,4 MB/s"), d.view());
d.dapp.extra.pclage = { status: "disabled" };
d.fns.forEach((fn) => fn());
assert.ok(d.view().includes("In den Einstellungen ausgeschaltet."));
d = openDialog("drives", {}, { local: false });
assert.ok(d.view().includes("nur am PC"));

// ---- Wetter: grosses Fenster mit Ortssuche (Papier-Fenster; die Antworten kommen aus einer Liste)
async function wxDialogTest() {
  const searches = [];
  const reloads = [];
  const pending = {};                                          // Ort -> { resolve, reject }
  let opened = null;
  const dataFns = [];
  const dapp = makeApp({
    extra: { forecast: { status: "ok", data: wxData } },
    loadExtra: (name, force) => reloads.push([name, force]),
    searchForecast: (name) => { searches.push(name); return new Promise((resolve, reject) => { pending[name] = { resolve, reject }; }); },
    openWindow: (spec, build) => { const body = el("div"); build(body, { onData: (fn) => dataFns.push(fn), onTick() {}, close() {} }); opened = { spec, body }; },
  });
  Dialogs.create(dapp).weather();
  const view = () => opened.body.text();
  const nodes = () => opened.body.all();
  const input = nodes().find((n) => n.tag === "input");
  const button = (label) => nodes().find((n) => n.tag === "button" && n.textContent === label);
  const tick = () => new Promise((resolve) => setImmediate(resolve));

  assert.strictEqual(opened.spec.title, "Wetter");
  assert.ok(reloads.some(([name, force]) => name === "forecast" && !force), "Vorhersage wird bei Bedarf geholt");
  assert.ok(view().includes("Växjö, Kronoberg, Schweden") && view().includes("gefühlt 1 °C") && view().includes("Luftfeuchte 80 %") && view().includes("Wind 10 km/h"), view());
  assert.ok(view().includes("teilweise <b>bewölkt</b>"), "Text bleibt Text");
  assert.strictEqual(nodes().filter((n) => n.className.startsWith("wxrow")).length, 7, "sieben Tage");
  assert.ok(view().includes("Heute") && view().includes("Morgen") && view().includes("2° / 6°") && view().includes("60 %"), view());
  assert.ok(!view().includes("nicht dein Heimatort") && button("Zurück zum Heimatort").hidden === true);
  const fills = nodes().filter((n) => n.tag === "i");
  assert.strictEqual(fills.length, 7);
  fills.forEach((f) => assert.ok(/^[0-9.]+%$/.test(f.style.left) && /^[0-9.]+%$/.test(f.style.width), JSON.stringify(f.style)));

  // leere Suche tut nichts
  input.value = "   ";
  input.listeners.forEach((fn) => fn({ key: "Enter" }));
  await tick();
  assert.deepStrictEqual(searches, []);

  // Suche mit Enter: erst "Lade", dann der andere Ort mit Hinweis
  input.value = " Lissabon ";
  input.listeners.forEach((fn) => fn({ key: "x" }));            // andere Taste: nichts
  assert.deepStrictEqual(searches, []);
  input.listeners.forEach((fn) => fn({ key: "Enter" }));
  assert.deepStrictEqual(searches, ["Lissabon"], "Leerzeichen am Rand weg");
  assert.strictEqual(view().includes("Lade …"), true);
  pending.Lissabon.resolve(Object.assign({}, wxData, { place: "Lissabon, Portugal" }));
  await tick();
  assert.ok(view().includes("Lissabon, Portugal") && view().includes("nicht dein Heimatort") && !view().includes("Växjö"), view());
  assert.strictEqual(button("Zurück zum Heimatort").hidden, false);

  // Fehler: Meldung, Zurueck bleibt moeglich
  input.value = "Nirgendwo";
  button("Suchen").listeners[0]();
  pending.Nirgendwo.reject(new Error("Den Ort „Nirgendwo“ habe ich nicht gefunden."));
  await tick();
  assert.ok(view().includes("Den Ort „Nirgendwo“ habe ich nicht gefunden.") && !view().includes("Lissabon"), view());
  assert.strictEqual(button("Zurück zum Heimatort").hidden, false);

  // zwei Suchen kurz hintereinander: die alte Antwort darf die neue nicht ueberschreiben
  input.value = "Rom";
  button("Suchen").listeners[0]();
  input.value = "Oslo";
  button("Suchen").listeners[0]();
  pending.Oslo.resolve(Object.assign({}, wxData, { place: "Oslo, Norwegen" }));
  await tick();
  pending.Rom.resolve(Object.assign({}, wxData, { place: "Rom, Italien" }));
  await tick();
  assert.ok(view().includes("Oslo, Norwegen") && !view().includes("Rom, Italien"), view());

  // eine alte Suche, die erst spaeter scheitert, darf die neue Anzeige ebenfalls nicht ueberschreiben
  input.value = "Bern";
  button("Suchen").listeners[0]();
  input.value = "Genf";
  button("Suchen").listeners[0]();
  pending.Genf.resolve(Object.assign({}, wxData, { place: "Genf, Schweiz" }));
  await tick();
  pending.Bern.reject(new Error("Bern kaputt"));
  await tick();
  assert.ok(view().includes("Genf, Schweiz") && !view().includes("Bern kaputt"), view());
  input.value = "Oslo";
  button("Suchen").listeners[0]();
  pending.Oslo.resolve(Object.assign({}, wxData, { place: "Oslo, Norwegen" }));
  await tick();

  // Aktualisieren mit gesuchtem Ort holt diesen Ort neu, nicht den Heimatort
  const before = searches.length;
  button("Aktualisieren").listeners[0]();
  assert.strictEqual(searches.length, before + 1);
  assert.strictEqual(searches[searches.length - 1], "Oslo");
  pending.Oslo.resolve(Object.assign({}, wxData, { place: "Oslo, Norwegen" }));
  await tick();

  // neue Daten fuer den Heimatort stoeren die Suchansicht nicht
  dataFns.forEach((fn) => fn());
  assert.ok(view().includes("Oslo, Norwegen"));

  // Zurueck: Heimatort, Feld leer
  button("Zurück zum Heimatort").listeners[0]();
  assert.ok(view().includes("Växjö, Kronoberg, Schweden") && !view().includes("nicht dein Heimatort"));
  assert.strictEqual(input.value, "");
  // Aktualisieren am Heimatort: Server neu fragen
  button("Aktualisieren").listeners[0]();
  assert.deepStrictEqual(reloads[reloads.length - 1], ["forecast", true]);
  // Heimatort-Daten kommen spaeter: die Ansicht folgt
  dapp.extra.forecast = { status: "ok", data: Object.assign({}, wxData, { place: "Berlin, Deutschland" }) };
  dataFns.forEach((fn) => fn());
  assert.ok(view().includes("Berlin, Deutschland"));
  dapp.extra.forecast = { status: "error", error: "Das Wetter ist gerade nicht abrufbar." };
  dataFns.forEach((fn) => fn());
  assert.ok(view().includes("Das Wetter ist gerade nicht abrufbar."));
  dapp.extra.forecast = { status: "disabled" };
  dataFns.forEach((fn) => fn());
  assert.ok(view().includes("In den Einstellungen ausgeschaltet."));
}

// ---- Kern der Seite (welcome_app.js): welche Daten wann geholt werden, Wetter-Suche, Symbole
async function appCoreTest() {
  const urls = [];
  const answers = {
    "/api/pc_lage": { pc_lage: { assessment: { level: "ok" }, drives: [] } }, "/api/performance": { cpu_percent: 1 },
    "/api/forecast": { forecast: { place: "Växjö", days: [] } }, "/api/news": { items: [{ title: "x" }] },
  };
  class SvgNode { constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; } setAttribute(k, v) { this.attrs[k] = v; } append(...n) { n.forEach((x) => this.children.push(x)); } }
  global.window = { WelcomeLogic: L, JarvisWidgets: Widgets };
  global.localStorage = { getItem: () => null, setItem() {} };
  global.document = { hidden: false, createElementNS: (ns, tag) => new SvgNode(tag), createElement: (tag) => el(tag) };
  global.fetch = async (url) => {
    urls.push(url);
    const body = answers[url.split("?")[0]];
    return body ? { ok: true, status: 200, json: async () => body } : { ok: false, status: 404, json: async () => ({ error: "Fehler" }) };
  };
  const tick = () => new Promise((resolve) => setTimeout(resolve, 5));
  const unique = () => Array.from(new Set(urls)).sort();
  const make = (host) => {
    global.location = { hostname: host };
    delete require.cache[require.resolve(path.join(web, "welcome_app.js"))];
    require(path.join(web, "welcome_app.js"));
    return global.window.WelcomeApp.create({ layer: el("div"), draw() {}, drawPanel() {}, render() {}, onOnline() {}, onAddress() {} });
  };

  // am PC: Lage und Laufwerke teilen sich eine Abfrage
  let app = make("127.0.0.1");
  assert.strictEqual(app.local, true);
  app.setEnabled(["pclage", "drives", "system", "weather", "news"]);
  await tick();
  assert.deepStrictEqual(unique(), ["/api/forecast", "/api/news", "/api/pc_lage", "/api/performance"]);
  assert.strictEqual(urls.filter((u) => u === "/api/pc_lage").length, 1, "zwei Fenster, eine Abfrage");
  assert.deepStrictEqual(app.extra.pclage, { status: "ok", data: answers["/api/pc_lage"].pc_lage });
  assert.deepStrictEqual(app.extra.forecast, { status: "ok", data: answers["/api/forecast"].forecast });
  assert.deepStrictEqual(app.extra.news.data, [{ title: "x" }]);
  // kleine Runde (alle paar Sekunden): nur das, was sich dauernd aendert
  urls.length = 0;
  app.loadNeeded(true);
  await tick();
  assert.deepStrictEqual(unique(), ["/api/pc_lage", "/api/performance"]);
  // grosse Runde: Lage, PC-Werte und Wetter neu, Nachrichten nicht (schon da)
  urls.length = 0;
  app.loadNeeded(false);
  await tick();
  assert.deepStrictEqual(unique(), ["/api/forecast", "/api/pc_lage", "/api/performance"]);
  // ausgeschaltete Faehigkeit und Fehler
  answers["/api/pc_lage"] = { disabled: true };
  await app.loadExtra("pclage", true);
  assert.deepStrictEqual(app.extra.pclage, { status: "disabled" });
  delete answers["/api/pc_lage"];
  await app.loadExtra("pclage", true);
  assert.deepStrictEqual(app.extra.pclage, { status: "error", error: "Fehler" });

  // das Laufwerke-Fenster allein reicht, um die Lage zu holen
  urls.length = 0;
  answers["/api/pc_lage"] = { pc_lage: {} };
  app.extra = {};
  app.setEnabled(["drives"]);
  await tick();
  assert.deepStrictEqual(unique(), ["/api/pc_lage"]);

  // nicht am PC (Handy ueber Remote): keine PC-Abfragen, Wetter und News schon
  urls.length = 0;
  answers["/api/pc_lage"] = { pc_lage: {} };
  app = make("gott-desktop.taild3a628.ts.net");
  assert.strictEqual(app.local, false);
  app.setEnabled(["pclage", "drives", "system", "weather", "news"]);
  await tick();
  assert.deepStrictEqual(unique(), ["/api/forecast", "/api/news"]);

  // Wetter-Suche: Ort wird kodiert, Antworten und Fehler
  urls.length = 0;
  const found = await app.searchForecast("Bad Homburg & Co/ä?");
  assert.strictEqual(urls[0], "/api/forecast?place=" + encodeURIComponent("Bad Homburg & Co/ä?"));
  assert.strictEqual(found.place, "Växjö");
  answers["/api/forecast"] = { disabled: true };
  await assert.rejects(() => app.searchForecast("Rom"), /ausgeschaltet/);
  answers["/api/forecast"] = {};
  await assert.rejects(() => app.searchForecast("Rom"), /Keine Vorhersage/);
  delete answers["/api/forecast"];
  await assert.rejects(() => app.searchForecast("Rom"), /Fehler/);

  // Symbole: SVG nur aus den festen Formen, unbekannter Name = Wolke
  const rain = app.icon("rain", 24);
  assert.strictEqual(rain.tag, "svg");
  assert.deepStrictEqual([rain.attrs.viewBox, rain.attrs.width, rain.attrs.height, rain.attrs.class, rain.attrs["aria-hidden"], rain.attrs.fill, rain.attrs.stroke],
    ["0 0 24 24", "24", "24", "wicon", "true", "none", "currentColor"]);
  assert.deepStrictEqual(rain.children.map((c) => c.tag), ["path", "path"]);
  assert.strictEqual(rain.children[0].attrs.d, L.WEATHER_ICONS.rain[0][1].d);
  assert.strictEqual(rain.attrs["stroke-linecap"], "round");
  assert.strictEqual(rain.attrs["stroke-linejoin"], "round");
  assert.strictEqual(rain.attrs["stroke-width"], "1.7");
  assert.strictEqual(app.icon("clear").attrs.width, "20");
  assert.deepStrictEqual(app.icon("clear").children.map((c) => c.tag), ["circle", "path"]);
  assert.strictEqual(app.icon("clear").children[0].attrs.r, "4");
  ["toString", "__proto__", "gibtsnicht", null, undefined, 5].forEach((k) => assert.deepStrictEqual(app.icon(k).children.map((c) => c.attrs.d), [L.WEATHER_ICONS.cloudy[0][1].d], String(k)));
}

wxDialogTest().then(appCoreTest).then(() => console.log("welcome OK"), (error) => { console.error(error); process.exit(1); });