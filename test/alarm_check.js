// Prueft web/alarm.js ohne Browser (wird von test_alarm_ui.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const A = require(path.join(__dirname, "..", "web", "alarm.js"));

// Zeitformat
assert.strictEqual(A.formatSeconds(0), "0:00");
assert.strictEqual(A.formatSeconds(65), "1:05");
assert.strictEqual(A.formatSeconds(-3), "0:00");
assert.strictEqual(A.formatSeconds("x"), "0:00");
assert.strictEqual(A.formatSeconds(599.9), "9:59");

// Banner
assert.deepStrictEqual(A.bannerView({ ringing: [] }, false).show, false);
assert.deepStrictEqual(A.bannerView(null, false).show, false);
assert.deepStrictEqual(A.bannerView({}, false).show, false);
let view = A.bannerView({ ringing: [{ kind: "alarm", label: "Wecker", seconds: 42 }], sound: "Computer", snooze_minutes: 5 }, true);
assert.strictEqual(view.show, true);
assert.strictEqual(view.title, "⏰ Wecker");
assert.strictEqual(view.detail, "seit 0:42");
assert.strictEqual(view.hint, "", "Computer-Ton: kein Hinweis auf Browser-Sperre");
assert.strictEqual(view.snoozeLabel, "Schlummern (5 min)");
view = A.bannerView({ ringing: [{ kind: "timer", label: "Nudeln", seconds: 3 }], sound: "Browser", snooze_minutes: 10 }, true);
assert.strictEqual(view.title, "⏲ Nudeln");
assert(view.hint.includes("Klicke irgendwo"), view.hint);
assert.strictEqual(view.snoozeLabel, "Schlummern (10 min)");
view = A.bannerView({ ringing: [{ kind: "timer", label: "Nudeln", seconds: 3 }], sound: "Browser" }, false);
assert.strictEqual(view.hint, "", "entsperrt: kein Hinweis");
assert.strictEqual(view.snoozeLabel, "Schlummern (5 min)", "ohne Angabe 5");
view = A.bannerView({ ringing: [{ kind: "alarm", label: "Wecker", seconds: 1 }, { kind: "timer", label: "Ei", seconds: 2 }], sound: "Aus" }, true);
assert.strictEqual(view.title, "⏰ 2 läuten");
assert.strictEqual(view.detail, "Wecker, Ei");

// Steuerung mit Attrappen
class FakeParam {
  constructor() { this.calls = []; }
  setValueAtTime(v, t) { this.calls.push(["set", v, t]); }
  linearRampToValueAtTime(v, t) { this.calls.push(["ramp", v, t]); }
}
class FakeContext {
  static instances = [];
  constructor() { this.state = "suspended"; this.currentTime = 10; this.started = []; this.destination = {}; FakeContext.instances.push(this); }
  resume() { this.state = "running"; return Promise.resolve(); }
  createGain() { return { gain: new FakeParam(), connect() {} }; }
  createOscillator() {
    const ctx = this;
    return { frequency: {}, connect() {}, start(t) { ctx.started.push(t); }, stop() {} };
  }
}

function setup(responses) {
  const log = { banners: [], said: [], titles: [], calls: [], intervals: [], cleared: [] };
  let nextInterval = 1;
  const deps = {
    api: async (method, url, body) => {
      log.calls.push([method, url, body]);
      const r = responses.shift();
      if (r instanceof Error) throw r;
      return r;
    },
    AudioContext: FakeContext,
    setInterval: (fn, ms) => { const id = nextInterval++; log.intervals.push([id, fn, ms]); return id; },
    clearInterval: (id) => log.cleared.push(id),
    setBanner: (v) => log.banners.push(v),
    say: (t) => log.said.push(t),
    getTitle: () => "J.A.R.V.I.S.",
    setTitle: (t) => log.titles.push(t),
  };
  return { log, ctl: A.createController(deps) };
}

const ringingState = (sound, rings) => ({ ringing: rings, sound, version: 1, snooze_minutes: 5, server_sound: sound === "Computer" });
const alarm = { id: 1, kind: "alarm", label: "Wecker", seconds: 0 };

(async () => {
  // Computer-Ton: Banner und blinkender Titel, aber KEIN Ton im Browser
  let { log, ctl } = setup([ringingState("Computer", [alarm]), ringingState("Computer", [alarm]), ringingState("Computer", [])]);
  await ctl.poll();
  assert.strictEqual(log.banners.at(-1).show, true);
  assert.strictEqual(log.intervals.length, 0, "kein Browser-Ton bei Computer-Ton");
  assert.strictEqual(FakeContext.instances.length, 0);
  assert.deepStrictEqual(log.titles, ["⏰ Wecker"]);
  await ctl.poll();
  assert.deepStrictEqual(log.titles, ["⏰ Wecker", "J.A.R.V.I.S."], "Titel blinkt");
  await ctl.poll();
  assert.strictEqual(log.banners.at(-1).show, false);
  assert.strictEqual(log.titles.at(-1), "J.A.R.V.I.S.");

  // Browser-Ton: ohne Geste gesperrt (Hinweis), nach unlock() laeuft der Ton in Schleife, danach stoppt er
  FakeContext.instances.length = 0;
  ({ log, ctl } = setup([ringingState("Browser", [alarm]), ringingState("Browser", [])]));
  await ctl.poll();
  assert.strictEqual(log.intervals.length, 1, "Schleife gestartet");
  assert(Math.abs(log.intervals[0][2] - 1640) < 1, String(log.intervals[0][2]));
  assert(log.banners.at(-1).hint.includes("Klicke"), "gesperrt: Hinweis");
  assert.strictEqual(FakeContext.instances[0].started.length, 0, "gesperrt: kein Ton");
  ctl.unlock();
  await Promise.resolve();
  assert.strictEqual(log.banners.at(-1).hint, "", "nach Klick: kein Hinweis");
  assert.strictEqual(ctl._beepOnce(), true);
  assert.deepStrictEqual(FakeContext.instances[0].started, [10, 10.28, 10.56], "drei Pieptoene pro Runde");
  log.intervals[0][1]();                      // naechste Runde der Schleife
  assert.strictEqual(FakeContext.instances[0].started.length, 6);
  await ctl.poll();                           // nichts laeutet mehr
  assert.deepStrictEqual(log.cleared, [1], "Schleife beendet");
  assert.strictEqual(ctl._ctrl.beepTimer, null);

  // Zweimal dasselbe melden startet keine zweite Schleife
  ({ log, ctl } = setup([ringingState("Browser", [alarm]), ringingState("Browser", [alarm])]));
  await ctl.poll(); await ctl.poll();
  assert.strictEqual(log.intervals.length, 1);

  // Umschalten von Browser auf Aus waehrend es laeutet: Ton stoppt, Banner bleibt
  ({ log, ctl } = setup([ringingState("Browser", [alarm]), ringingState("Aus", [alarm])]));
  await ctl.poll(); await ctl.poll();
  assert.deepStrictEqual(log.cleared, [1]);
  assert.strictEqual(log.banners.at(-1).show, true);

  // Ausschalten: sendet POST, spricht die Antwort, aktualisiert das Banner
  ({ log, ctl } = setup([{ stopped: ["Wecker"], reply: "Sir, Wecker aus. Heute: nichts.", state: ringingState("Computer", []) }]));
  await ctl.stop();
  assert.deepStrictEqual(log.calls, [["POST", "/api/ringing/stop", {}]]);
  assert.deepStrictEqual(log.said, ["Sir, Wecker aus. Heute: nichts."]);
  assert.strictEqual(log.banners.at(-1).show, false);

  // Schlummern
  ({ log, ctl } = setup([{ stopped: ["Wecker"], reply: "Sir, ich wecke dich in 5 Minuten wieder.", state: ringingState("Computer", []) }]));
  await ctl.snooze();
  assert.deepStrictEqual(log.calls, [["POST", "/api/ringing/stop", { snooze: true }]]);
  assert.deepStrictEqual(log.said, ["Sir, ich wecke dich in 5 Minuten wieder."]);

  // Leere Antwort wird nicht gesprochen; Fehler (Server weg) lassen die Seite heil
  ({ log, ctl } = setup([{ stopped: [], reply: "", state: ringingState("Computer", []) }, new Error("offline"), new Error("offline")]));
  await ctl.stop();
  assert.deepStrictEqual(log.said, []);
  await ctl.stop();                           // Fehler: kein Absturz, danach wieder bedienbar
  await ctl.poll();
  assert.strictEqual(ctl._ctrl.busy, false);

  // Doppelklick: zweiter Klick waehrend der erste laeuft wird ignoriert
  let release;
  const slow = new Promise((resolve) => { release = resolve; });
  ({ log, ctl } = setup([]));
  const slowCtl = A.createController({
    api: async (m, u, b) => { log.calls.push([m, u, b]); await slow; return { reply: "", state: ringingState("Computer", []) }; },
    AudioContext: null, setInterval() { return 1; }, clearInterval() {}, setBanner() {}, say() {}, getTitle: () => "t", setTitle() {},
  });
  const first = slowCtl.stop();
  await slowCtl.stop();
  release();
  await first;
  assert.strictEqual(log.calls.length, 1, "nur ein Request");

  // Ohne WebAudio (alte Browser): kein Absturz
  ({ log, ctl } = setup([ringingState("Browser", [alarm])]));
  const noAudio = A.createController({
    api: async () => ringingState("Browser", [alarm]), AudioContext: null, setInterval() { return 1; }, clearInterval() {},
    setBanner: (v) => log.banners.push(v), say() {}, getTitle: () => "t", setTitle() {},
  });
  await noAudio.poll();
  noAudio.unlock();
  assert.strictEqual(log.banners.at(-1).show, true);
  assert(log.banners.at(-1).hint.includes("Klicke"));

  console.log("ALARM UI OK");
})().catch((error) => { console.error(error); process.exit(1); });
