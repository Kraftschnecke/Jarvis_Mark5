// Prueft web/sync.js ohne Browser (wird von test_sync.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const sync = require(path.join(__dirname, "..", "web", "sync.js"));

function setup(over) {
  const state = Object.assign({ hidden: false, apply_ok: true, calls: [], applied: [], responses: [] }, over);
  const ctl = sync.createSync({
    api: async (method, url) => {
      state.calls.push(method + " " + url);
      const next = state.responses.shift();
      if (next instanceof Error) throw next;
      return next;
    },
    canApply: () => state.apply_ok,
    apply: (data) => state.applied.push(data),
    isHidden: () => state.hidden,
  });
  return { state, ctl };
}

(async () => {
  assert.strictEqual(sync.INTERVAL_MS, 2000);

  // Start: die erste Antwort wird nur gemerkt, nichts neu gezeichnet, und es wird ohne known gefragt
  let t = setup();
  t.state.responses.push({ version: "v1", active: {}, messages: [{ role: "user", content: "a" }], projects: [] });
  assert.strictEqual(await t.ctl.poll(), false);
  assert.deepStrictEqual(t.state.calls, ["GET /api/sync"]);
  assert.strictEqual(t.ctl.version(), "v1");
  assert.strictEqual(t.state.applied.length, 0);

  // Danach wird mit known gefragt; gleiche Version: nichts passiert
  t.state.responses.push({ version: "v1", active: {} });
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.state.calls[1], "GET /api/sync?known=v1");
  assert.strictEqual(t.state.applied.length, 0);

  // Neue Version mit Verlauf: wird angewendet
  t.state.responses.push({ version: "v2", active: {}, messages: [{ role: "assistant", content: "b" }], projects: [] });
  assert.strictEqual(await t.ctl.poll(), true);
  assert.strictEqual(t.state.applied.length, 1);
  assert.strictEqual(t.state.applied[0].version, "v2");
  assert.strictEqual(t.ctl.version(), "v2");

  // Gleiche Version, aber trotzdem Verlauf dabei: nicht neu zeichnen
  t.state.responses.push({ version: "v2", active: {}, messages: [{ role: "user", content: "z" }], projects: [] });
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.state.applied.length, 1);

  // Eigene Aktion: naechste Antwort wird nur uebernommen (kein doppeltes Neuzeichnen), danach normal
  t.ctl.markOwnChange();
  t.state.responses.push({ version: "v3", active: {}, messages: [], projects: [] });
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.state.calls[t.state.calls.length - 1], "GET /api/sync");
  assert.strictEqual(t.ctl.version(), "v3");
  assert.strictEqual(t.state.applied.length, 1);
  t.state.responses.push({ version: "v4", active: {}, messages: [{ role: "user", content: "c" }], projects: [] });
  assert.strictEqual(await t.ctl.poll(), true);
  assert.strictEqual(t.state.applied.length, 2);

  // Versteckter Tab oder beschaeftigte Seite (Antwort laeuft, Rueckfrage offen): es wird gar nicht gefragt
  const callsBefore = t.state.calls.length;
  t.state.hidden = true;
  assert.strictEqual(await t.ctl.poll(), false);
  t.state.hidden = false;
  t.state.apply_ok = false;
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.state.calls.length, callsBefore);
  t.state.apply_ok = true;

  // Der Nutzer wird waehrend der Anfrage beschaeftigt: Antwort verworfen, Version bleibt, spaeter kommt sie an
  t = setup();
  t.state.responses.push({ version: "a", active: {}, messages: [], projects: [] });
  await t.ctl.poll();
  const ctl2 = sync.createSync({
    api: async () => { t.state.apply_ok = false; return { version: "b", active: {}, messages: [], projects: [] }; },
    canApply: () => t.state.apply_ok,
    apply: (d) => t.state.applied.push(d),
    isHidden: () => false,
  });
  await ctl2.poll();            // erste Antwort (adopt) wird verworfen, weil beschaeftigt
  assert.strictEqual(ctl2.version(), null);
  assert.strictEqual(t.state.applied.length, 0);

  // Der Nutzer wird waehrend einer spaeteren Anfrage beschaeftigt: nicht anwenden, Version bleibt alt
  t = setup();
  t.state.responses.push({ version: "k1", active: {}, messages: [], projects: [] });
  await t.ctl.poll();
  const ctl3 = sync.createSync({
    api: async () => { t.state.apply_ok = false; return { version: "k2", active: {}, messages: [{ role: "user", content: "m" }], projects: [] }; },
    canApply: () => t.state.apply_ok, apply: (d) => t.state.applied.push(d), isHidden: () => false,
  });
  t.state.apply_ok = true;
  await ctl3.poll();                      // adopt-Lauf, wird verworfen
  t.state.apply_ok = true;
  assert.strictEqual(ctl3.version(), null);
  // zweiter Lauf mit bekannter Version: busy waehrend der Anfrage
  const ctl4 = sync.createSync({
    api: (() => { let n = 0; return async () => { n += 1; if (n === 2) t.state.apply_ok = false; return { version: "k" + n, active: {}, messages: [{ role: "user", content: "m" }], projects: [] }; }; })(),
    canApply: () => t.state.apply_ok, apply: (d) => t.state.applied.push(d), isHidden: () => false,
  });
  await ctl4.poll();                      // merkt k1
  const appliedBefore = t.state.applied.length;
  await ctl4.poll();                      // k2 kommt, aber Seite ist beschaeftigt
  assert.strictEqual(t.state.applied.length, appliedBefore);
  assert.strictEqual(ctl4.version(), "k1");

  // Fehler (offline): kein Absturz, Version bleibt, naechster Versuch geht wieder
  t = setup();
  t.state.responses.push({ version: "x", active: {}, messages: [], projects: [] });
  await t.ctl.poll();
  t.state.responses.push(new Error("offline"));
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.ctl.version(), "x");
  t.state.responses.push({ version: "y", active: {}, messages: [{ role: "user", content: "d" }], projects: [] });
  assert.strictEqual(await t.ctl.poll(), true);

  // Antwort ohne Verlauf trotz neuer Version (kaputt): nichts zeichnen
  t = setup();
  t.state.responses.push({ version: "p", active: {}, messages: [], projects: [] });
  await t.ctl.poll();
  t.state.responses.push({ version: "q", active: {} });
  assert.strictEqual(await t.ctl.poll(), false);
  assert.strictEqual(t.state.applied.length, 0);

  // Zwei Abfragen gleichzeitig: nur eine laeuft
  t = setup();
  let release;
  const slow = sync.createSync({
    api: () => new Promise((resolve) => { release = () => resolve({ version: "s", active: {}, messages: [], projects: [] }); }),
    canApply: () => true, apply: () => {}, isHidden: () => false,
  });
  const first = slow.poll();
  assert.strictEqual(await slow.poll(), false);
  release();
  await first;
  assert.strictEqual(slow.version(), "s");

  // Zeitgeber: start registriert mit 2000 ms und kann gestoppt werden
  const seen = [];
  const stop = t.ctl.start({ setInterval: (fn, ms) => { seen.push(ms); return 7; }, clearInterval: (id) => seen.push("clear" + id) });
  stop();
  assert.deepStrictEqual(seen, [2000, "clear7"]);

  console.log("sync.js OK");
})().catch((error) => { console.error(error); process.exit(1); });