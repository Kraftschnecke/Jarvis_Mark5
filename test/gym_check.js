// Prueft das Gym-Fenster und das kleine Gym-Fenster (welcome_dialogs.js / welcome_panels.js) ohne Browser.
"use strict";
const assert = require("assert");
const path = require("path");
const web = path.join(__dirname, "..", "web");
const L = require(path.join(web, "welcome_logic.js"));
const Panels = require(path.join(web, "welcome_panels.js"));
const Dialogs = require(path.join(web, "welcome_dialogs.js"));

// ---- Eingaben und Texte
assert.strictEqual(L.parseWeight("62,5"), 62.5);
assert.strictEqual(L.parseWeight(" 60 "), 60);
assert.strictEqual(L.parseWeight(""), 0);
assert.strictEqual(L.parseWeight(undefined), 0);
for (const bad of ["abc", "-5", "1001", "5 kg", "1e3", "60.555", "12345", "6,5,5"]) assert.strictEqual(L.parseWeight(bad), null, bad);
assert.strictEqual(L.parseWeight("1000"), 1000);
assert.deepStrictEqual(L.parseReps("8 8 7"), [8, 8, 7]);
assert.deepStrictEqual(L.parseReps("8,8,7"), [8, 8, 7]);
assert.deepStrictEqual(L.parseReps("8/8/7"), [8, 8, 7]);
assert.deepStrictEqual(L.parseReps("3x8"), [8, 8, 8]);
assert.deepStrictEqual(L.parseReps("3 × 10"), [10, 10, 10]);
assert.deepStrictEqual(L.parseReps("12"), [12]);
assert.deepStrictEqual(L.parseReps("0 0"), [0, 0]);
for (const bad of ["", "   ", "a", "8 x", "8 -1", "101", "21x8", "0x8", "8.5", "8 8 abc", null, undefined]) assert.strictEqual(L.parseReps(bad), null, String(bad));
assert.strictEqual(L.parseReps("20x8").length, 20);
assert.strictEqual(L.repsText([8, 8, 7]), "8 8 7");
assert.strictEqual(L.repsText(null), "");
assert.strictEqual(L.kgText(62.5), "62,5 kg");
assert.strictEqual(L.kgText(60), "60 kg");
assert.strictEqual(L.kgText(0), "Körpergewicht");
assert.strictEqual(L.goalText({ weight: 60, sets: 3, reps: 8 }), "60 kg · 3 × 8");
assert.strictEqual(L.goalText({ weight: 0, sets: 4, reps: 6 }), "Körpergewicht · 4 × 6");
assert.strictEqual(L.resultText({ weight: 62.5, reps: [8, 8, 7] }), "62,5 kg · 8 8 7");
assert.deepStrictEqual(L.goalAsResult({ weight: 50, sets: 3, reps: 8 }), { weight: 50, reps: [8, 8, 8] });
assert.ok(L.WINDOWS.some((w) => w.id === "gym" && w.state === "built"));

// ---- Papier-DOM
class Node {
  constructor(tag, className, text) { this.tag = tag; this.className = className || ""; this.textContent = text === undefined ? "" : String(text); this.children = []; this.style = {}; this.value = ""; this.listeners = {}; this.classList = { add() {} }; }
  get tagName() { return this.tag.toUpperCase(); }
  setAttribute() {}
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type) { (this.listeners[type] || []).forEach((fn) => fn({ preventDefault() {}, stopPropagation() {}, key: "" })); }
  append(...nodes) { nodes.forEach((n) => this.children.push(n)); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  all() { return [this].concat(...this.children.map((c) => c.all())); }
  contains(node) { return this.all().includes(node); }
  text() { return [this.textContent].concat(this.children.map((c) => c.text())).join(" ").replace(/\s+/g, " ").trim(); }
  set innerHTML(value) { throw new Error("innerHTML darf nicht benutzt werden"); }
}
const el = (tag, className, text) => new Node(tag, className, text);
global.document = { activeElement: null };

const flush = () => new Promise((resolve) => setImmediate(resolve));

function exercise(id, name, weight, sets, reps, extra) { return Object.assign({ id, name, weight, sets, reps, note: "", today: null, last: null }, extra); }
function todayView(over) {
  return Object.assign({ date: "2026-11-24", has_plan: true, weekday: 1, label: "Dienstag", name: "Pull", offday: false, logged: 0, total: 2,
    exercises: [exercise("a1", "Klimmzüge", 0, 4, 6), exercise("b2", "Rudern <b>x</b>", 50, 3, 8, { note: "Pause 2 min", last: { date: "2026-11-17", weight: 47.5, reps: [8, 8, 8] } })] }, over);
}
function planDays(over) {
  const days = [];
  for (let i = 0; i < 7; i += 1) days.push({ weekday: i, label: ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][i], name: "Offday", offday: true, exercises: [] });
  days[1] = Object.assign({}, days[1], { name: "Pull", offday: false, exercises: [exercise("a1", "Klimmzüge", 0, 4, 6), exercise("b2", "Rudern <b>x</b>", 50, 3, 8, { note: "Pause 2 min" })] });
  return days.map((d, i) => (over && over[i]) || d);
}
const gymData = (today, plan) => ({ status: "ok", data: { today: today || todayView(), plan: { days: planDays(), has_plan: true } } });

function makeApp(gym, over) {
  const calls = [];
  const app = Object.assign({
    el, L, W: {}, local: true, compact: false, data: { goals: [], events: [], lists: [] }, extra: { gym }, api: async (method, p, body) => { calls.push([method, p, body]); return app.reply(p, body); },
    reply: () => { throw new Error("keine Antwort vorbereitet"); }, loads: [],
    loadExtra(name, force) { app.loads.push([name, force]); },
    setGym(data) { app.extra.gym = { status: "ok", data: { today: data.today, plan: data.plan } }; if (data.widgets) app.data = data.widgets; },
    focusNow: () => ({ active: false }), timersNow: () => [],
  }, over);
  app.calls = calls;
  return app;
}

function openGym(app) {
  let opened = null;
  const fns = [];
  app.openWindow = (spec, build) => { const body = el("div"); build(body, { onData: (fn) => fns.push(fn), onTick() {}, close() {} }); opened = { spec, body }; };
  Dialogs.create(app).gym();
  return { spec: opened.spec, body: opened.body, fns, view: () => opened.body.text(), nodes: () => opened.body.all(),
    inputs: () => opened.body.all().filter((n) => n.tag === "input"), button: (label) => opened.body.all().find((n) => n.tag === "button" && n.textContent === label),
    buttons: () => opened.body.all().filter((n) => n.tag === "button").map((n) => n.textContent), note: () => opened.body.all().find((n) => n.className === "note").textContent };
}

(async () => {
  // ---- kleines Fenster
  const draw = (panel) => { const body = el("div"); panel.draw(body); return body.text(); };
  let app = makeApp(gymData());
  let panel = Panels.create(app).gym;
  assert.strictEqual(panel.title, "Gym");
  assert.strictEqual(panel.extra(), "Pull");
  let text = draw(panel);
  assert.ok(text.includes("Klimmzüge · Körpergewicht · 4 × 6") && text.includes("Rudern <b>x</b> · 50 kg · 3 × 8") && text.includes("0 von 2 eingetragen"), text);
  app = makeApp(gymData(todayView({ logged: 1, exercises: [exercise("a1", "Klimmzüge", 0, 4, 6, { today: { weight: 0, reps: [6, 6, 6, 6] } }), exercise("b2", "Rudern", 50, 3, 8)] })));
  const bodyNode = el("div");
  Panels.create(app).gym.draw(bodyNode);
  assert.ok(bodyNode.all().filter((n) => n.className === "wbox d").length === 1 && bodyNode.all().filter((n) => n.className === "wbox").length === 1);
  assert.ok(bodyNode.text().includes("1 von 2 eingetragen"));
  app = makeApp(gymData(todayView({ has_plan: false, name: "Offday", offday: true, exercises: [], total: 0 })));
  assert.strictEqual(draw(Panels.create(app).gym), "Noch kein Plan. Klick, um ihn anzulegen.");
  assert.strictEqual(Panels.create(app).gym.extra(), "");
  app = makeApp(gymData(todayView({ has_plan: false, exercises: [], total: 0 })), { local: false });
  assert.strictEqual(draw(Panels.create(app).gym), "Noch kein Plan (am PC anlegen).");
  app = makeApp(gymData(todayView({ name: "Offday", offday: true, exercises: [], total: 0 })));
  assert.strictEqual(draw(Panels.create(app).gym), "Offday: Ruhetag.");
  assert.strictEqual(Panels.create(app).gym.extra(), "Offday");
  app = makeApp(gymData(todayView({ name: "Cardio", exercises: [], total: 0 })));
  assert.strictEqual(draw(Panels.create(app).gym), "Cardio: keine Übungen eingetragen.");
  assert.strictEqual(draw(Panels.create(makeApp(undefined)).gym), "Lade …");
  assert.strictEqual(draw(Panels.create(makeApp({ status: "error", error: "Gym ist hier nicht eingerichtet." })).gym), "Gym ist hier nicht eingerichtet.");
  assert.strictEqual(draw(Panels.create(makeApp({ status: "disabled" })).gym), "In den Einstellungen ausgeschaltet.");
  app = makeApp(gymData(), { compact: true });
  assert.ok(draw(Panels.create(app).gym).includes("Klimmzüge") && Panels.create(app).gym.extra() === "Pull");

  // ---- grosses Fenster: heute
  app = makeApp(gymData());
  let w = openGym(app);
  assert.strictEqual(w.spec.title, "Gym");
  assert.deepStrictEqual(app.loads, [["gym", true]], "beim Oeffnen frisch holen");
  assert.ok(w.view().includes("Dienstag: Pull") && w.view().includes("0 von 2 eingetragen"), w.view());
  assert.ok(w.view().includes("Ziel: Körpergewicht · 4 × 6") && w.view().includes("Ziel: 50 kg · 3 × 8") && w.view().includes("Pause 2 min"), w.view());
  assert.ok(w.view().includes("Letztes Mal (17.11.): 47,5 kg · 8 8 8") && w.view().includes("Rudern <b>x</b>"), w.view());      // Text bleibt Text
  let inputs = w.inputs().filter((n) => n.className.includes("gym-kg") || n.className.includes("gym-reps"));
  assert.deepStrictEqual(inputs.map((n) => n.value), ["0", "6 6 6 6", "50", "8 8 8"], "Felder sind mit dem Ziel vorbelegt");

  // ungueltige Eingabe: nichts wird gesendet, Hinweis steht da
  inputs[2].value = "viel";
  inputs[2].fire("input");
  w.nodes().filter((n) => n.tag === "form")[1].fire("submit");
  await flush();
  assert.strictEqual(app.calls.length, 0);
  assert.ok(w.note().includes("Gewicht bitte als Zahl"), w.note());
  inputs[2].value = "52,5";
  inputs[2].fire("input");
  inputs[3].value = "8 8 x";
  inputs[3].fire("input");
  w.nodes().filter((n) => n.tag === "form")[1].fire("submit");
  await flush();
  assert.strictEqual(app.calls.length, 0);
  assert.ok(w.note().includes("Wiederholungen je Satz"), w.note());

  // gueltig: sendet geparst; Antwort: neues Ziel
  inputs[3].value = "8,8,8";
  inputs[3].fire("input");
  const improvedToday = todayView({ logged: 1, exercises: [exercise("a1", "Klimmzüge", 0, 4, 6), exercise("b2", "Rudern <b>x</b>", 52.5, 3, 8, { today: { name: "Rudern", weight: 52.5, reps: [8, 8, 8], improved: true } })] });
  app.reply = (p, body) => ({ today: improvedToday, plan: { days: planDays(), has_plan: true }, result: { improved: true, goal: { weight: 52.5, sets: 3, reps: 8 }, entry: {} }, widgets: { goals: [{ text: "Gym: Pull", done: false, daily: true, managed: "gym" }] } });
  w.nodes().filter((n) => n.tag === "form")[1].fire("submit");
  await flush();
  assert.deepStrictEqual(app.calls, [["POST", "/api/gym/log", { exercise: "b2", weight: 52.5, reps: [8, 8, 8] }]]);
  assert.ok(w.note().includes("Rudern <b>x</b>: neues Ziel 52,5 kg · 3 × 8."), w.note());
  assert.ok(w.view().includes("✓ Heute: 52,5 kg · 8 8 8") && w.view().includes("Neues Ziel!") && w.view().includes("1 von 2 eingetragen"), w.view());
  assert.strictEqual(app.data.goals[0].text, "Gym: Pull", "Tagesziele wurden aus der Antwort uebernommen");
  assert.ok(w.buttons().includes("Ändern") && w.buttons().includes("Löschen"));

  // "Wie Ziel": sendet genau das Ziel, ohne Neu-Ziel-Hinweis
  app.calls.length = 0;
  app.reply = () => ({ today: todayView({ logged: 1, exercises: [exercise("a1", "Klimmzüge", 0, 4, 6, { today: { name: "K", weight: 0, reps: [6, 6, 6, 6] } }), exercise("b2", "Rudern", 52.5, 3, 8)] }), plan: { days: planDays(), has_plan: true }, result: { improved: false, goal: { weight: 0, sets: 4, reps: 6 }, entry: {} } });
  w.button("Wie Ziel").fire("click");
  await flush();
  assert.deepStrictEqual(app.calls, [["POST", "/api/gym/log", { exercise: "a1", weight: 0, reps: [6, 6, 6, 6] }]]);        // die erste offene Uebung
  assert.ok(w.note().includes("Klimmzüge: eingetragen.") && !w.note().includes("neues Ziel"), w.note());

  // Ergebnis aendern: Felder mit dem Eingetragenen, und Loeschen
  w.nodes().filter((n) => n.tag === "button" && n.textContent === "Ändern")[0].fire("click");
  inputs = w.inputs().filter((n) => n.className.includes("gym-kg") || n.className.includes("gym-reps"));
  assert.deepStrictEqual(inputs.slice(0, 2).map((n) => n.value), ["0", "6 6 6 6"]);
  w = openGym(app);
  app.reply = () => ({ today: todayView(), plan: { days: planDays(), has_plan: true }, result: null });
  app.calls.length = 0;
  w.button("Löschen").fire("click");
  await flush();
  assert.deepStrictEqual(app.calls, [["POST", "/api/gym/clear", { exercise: "a1" }]]);

  // Serverfehler: Hinweis, nichts bricht
  app = makeApp(gymData());
  w = openGym(app);
  app.reply = () => { throw new Error("Nachtragen geht höchstens 7 Tage zurück."); };
  w.button("Wie Ziel").fire("click");
  await flush();
  assert.ok(w.note().includes("Nicht gespeichert: Nachtragen geht höchstens 7 Tage zurück."), w.note());
  assert.ok(w.view().includes("Klimmzüge"), "Fenster bleibt benutzbar");

  // Waehrend du tippst, wird nicht neu gezeichnet; danach schon
  app = makeApp(gymData());
  w = openGym(app);
  const typingField = w.inputs()[0];
  global.document.activeElement = typingField;
  const before = w.inputs()[0];
  app.extra.gym = gymData(todayView({ name: "Neu" }));
  w.fns.forEach((fn) => fn());
  assert.ok(w.view().includes("Pull") && !w.view().includes("Neu"), "kein Neuzeichnen im Tippen");
  global.document.activeElement = null;
  w.fns.forEach((fn) => fn());
  assert.ok(w.view().includes("Dienstag: Neu") && before, w.view());

  // Zustaende: Laden, Fehler, kein Plan (PC / Handy), Offday, keine Uebungen
  assert.ok(openGym(makeApp(undefined)).view().includes("Lade …"));
  assert.ok(openGym(makeApp({ status: "error", error: "Gym ist hier nicht eingerichtet." })).view().includes("Gym ist hier nicht eingerichtet."));
  assert.ok(openGym(makeApp({ status: "disabled" })).view().includes("ausgeschaltet"));
  const noPlan = { status: "ok", data: { today: todayView({ has_plan: false, exercises: [], total: 0 }), plan: { days: planDays([]).map((d) => Object.assign({}, d, { name: "Offday", offday: true, exercises: [] })), has_plan: false } } };
  w = openGym(makeApp(noPlan));
  assert.ok(w.view().includes("Noch kein Plan. Unten kannst du ihn anlegen.") && w.buttons().includes("Plan anlegen"));
  w = openGym(makeApp(noPlan, { local: false }));
  assert.ok(w.view().includes("Den legst du am PC an.") && !w.buttons().includes("Plan anlegen") && w.view().includes("Den Plan änderst du am PC"), w.view());
  w = openGym(makeApp(gymData(todayView({ name: "Offday", offday: true, exercises: [], total: 0 }))));
  assert.ok(w.view().includes("Dienstag: Offday") && w.view().includes("von selbst erledigt") && w.inputs().length === 0);
  w = openGym(makeApp(gymData(todayView({ name: "Cardio", exercises: [], total: 0 }))));
  assert.ok(w.view().includes("keine Übungen eingetragen"));

  // ---- Wochenplan: ansehen am Handy, aendern am PC
  w = openGym(makeApp(gymData(), { local: false }));
  assert.ok(w.view().includes("Montag Offday") && w.view().includes("Dienstag Pull · Klimmzüge Körpergewicht · 4 × 6, Rudern <b>x</b> 50 kg · 3 × 8"), w.view());
  assert.ok(!w.buttons().includes("Plan bearbeiten") && w.view().includes("Den Plan änderst du am PC"));
  app = makeApp(gymData());
  w = openGym(app);
  assert.ok(w.buttons().includes("Plan bearbeiten"));
  w.button("Plan bearbeiten").fire("click");
  assert.ok(w.buttons().includes("Plan speichern") && w.buttons().includes("Abbrechen") && !w.buttons().includes("Plan bearbeiten"));
  assert.strictEqual(w.buttons().filter((b) => b === "+ Übung").length, 7);
  const field = (placeholder, nth) => w.inputs().filter((n) => n.placeholder === placeholder)[nth || 0];
  assert.strictEqual(w.inputs().filter((n) => n.placeholder.startsWith("Tagesname")).length, 7);
  w.button("Abbrechen").fire("click");
  assert.ok(w.buttons().includes("Plan bearbeiten"));
  w.button("Plan bearbeiten").fire("click");

  // aendern: Mittwoch bekommt einen Namen und eine Uebung, Dienstag: Rudern schwerer, Klimmzuege weg (Name leer)
  const dayNames = w.inputs().filter((n) => n.placeholder.startsWith("Tagesname"));
  dayNames[2].value = "Push";
  dayNames[2].fire("input");
  w.nodes().filter((n) => n.tag === "button" && n.textContent === "+ Übung")[2].fire("click");
  const lastExercise = () => w.nodes().filter((n) => n.className === "gym-ex").slice(-1)[0].children;
  assert.strictEqual(lastExercise().length, 6);
  lastExercise()[0].value = "Bankdrücken";
  lastExercise()[0].fire("input");
  lastExercise()[1].value = "62,5";
  lastExercise()[1].fire("input");
  const tuesday = w.nodes().filter((n) => n.className === "gym-ex").slice(0, 2);
  tuesday[0].children[0].value = "";
  tuesday[0].children[0].fire("input");
  tuesday[1].children[1].value = "55";
  tuesday[1].children[1].fire("input");
  app.reply = (p, body) => ({ today: todayView(), plan: { days: planDays(), has_plan: true }, result: null, widgets: { goals: [] } });
  w.button("Plan speichern").fire("click");
  await flush();
  assert.strictEqual(app.calls.length, 1);
  const [method, route, sent] = app.calls[0];
  assert.strictEqual(method + route, "POST/api/gym/plan");
  assert.deepStrictEqual(sent.days.map((d) => [d.weekday, d.name, d.exercises.length]), [[1, "Pull", 1], [2, "Push", 1]]);
  assert.deepStrictEqual(sent.days[0].exercises[0], { name: "Rudern <b>x</b>", weight: 55, sets: 3, reps: 8, note: "Pause 2 min", id: "b2" });   // alte Uebung behaelt ihre ID
  assert.deepStrictEqual(sent.days[1].exercises[0], { name: "Bankdrücken", weight: 62.5, sets: 3, reps: 8, note: "" });                        // neue Uebung ohne ID
  assert.ok(w.note() === "Plan gespeichert." && w.buttons().includes("Plan bearbeiten"), w.note());

  // ungueltige Zahl im Editor: nicht senden, Hinweis mit Tag und Uebung
  w.button("Plan bearbeiten").fire("click");
  app.calls.length = 0;
  const ex0 = w.nodes().filter((n) => n.className === "gym-ex")[0].children;
  ex0[2].value = "0";
  ex0[2].fire("input");
  w.button("Plan speichern").fire("click");
  await flush();
  assert.strictEqual(app.calls.length, 0);
  assert.ok(w.note().includes("Dienstag, Klimmzüge: Gewicht, Sätze und Wiederholungen müssen Zahlen sein"), w.note());
  ex0[2].value = "4";
  ex0[2].fire("input");
  ex0[1].value = "schwer";
  ex0[1].fire("input");
  w.button("Plan speichern").fire("click");
  await flush();
  assert.strictEqual(app.calls.length, 0);
  assert.ok(w.note().includes("Klimmzüge"), w.note());
  // Serverfehler beim Speichern: Editor bleibt offen
  ex0[1].value = "0";
  ex0[1].fire("input");
  app.reply = () => { throw new Error("Höchstens 12 Übungen pro Tag."); };
  w.button("Plan speichern").fire("click");
  await flush();
  assert.ok(w.note().includes("Nicht gespeichert: Höchstens 12 Übungen pro Tag.") && w.buttons().includes("Plan speichern"), w.note());

  // ---- Tagesziele-Fenster: festes Gym-Ziel ohne Loeschen/Umstellen (siehe welcome_check.js fuer den Rest)
  let goalsBody = null;
  const gapp = makeApp(gymData(), { data: { goals: [{ text: "Gym: Push", done: false, daily: true, streak: 3, managed: "gym" }, { text: "Gym: Offday", done: true, daily: true, streak: 1, managed: "gym" }, { text: "Lesen", done: false, daily: true, streak: 0 }], week: [], events: [], lists: [] },
    openWindow: (spec, build) => { goalsBody = el("div"); build(goalsBody, { onData() {}, onTick() {}, close() {} }); } });
  Dialogs.create(gapp).goals();
  const goalRows = goalsBody.all().filter((n) => n.className.startsWith("goal-row"));
  assert.strictEqual(goalRows.length, 3);
  const buttonsIn = (row) => row.all().filter((n) => n.tag === "button");
  assert.strictEqual(buttonsIn(goalRows[0]).length, 0, "Gym-Ziel: kein Loeschen, kein Wiederholen");
  assert.strictEqual(buttonsIn(goalRows[1]).length, 0);
  assert.strictEqual(buttonsIn(goalRows[2]).length, 2, "normales Ziel behaelt beide Knoepfe");
  assert.ok(goalRows[0].text().includes("Gym: Push") && goalRows[0].text().includes("3 Tage"));
  assert.strictEqual(goalRows[0].all().find((n) => n.tag === "input").disabled !== true, true, "Trainingstag: Haken moeglich");
  assert.strictEqual(goalRows[1].all().find((n) => n.tag === "input").disabled, true, "Offday: Haken fest");

  console.log("gym OK");
})().catch((error) => { console.error(error); process.exit(1); });
