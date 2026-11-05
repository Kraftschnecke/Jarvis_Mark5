// Prueft web/voice.js ohne Browser (wird von test_voice.py mit Node gestartet)
const assert = require("assert");
const path = require("path");
const V = require(path.join(__dirname, "..", "web", "voice.js"));
 
// --- cleanForSpeech
assert.strictEqual(V.cleanForSpeech("**Fett** und `Code`"), "Fett und Code");
assert.strictEqual(V.cleanForSpeech("Vorher ```print(1)``` nachher"), "Vorher nachher");
assert.strictEqual(V.cleanForSpeech("Siehe https://example.com/a?b=c jetzt"), "Siehe Link jetzt");
assert.strictEqual(V.cleanForSpeech("# Titel\n- eins\n- zwei"), "Titel\neins\nzwei");
assert.strictEqual(V.cleanForSpeech(null), "");
assert.strictEqual(V.cleanForSpeech(undefined), "");
assert.strictEqual(V.cleanForSpeech(42), "42");
 
// --- splitForSpeech
assert.deepStrictEqual(V.splitForSpeech("Eins. Zwei! Drei?"), ["Eins.", "Zwei!", "Drei?"]);
assert.deepStrictEqual(V.splitForSpeech("a\nb"), ["a", "b"]);
assert.deepStrictEqual(V.splitForSpeech(""), []);
const long = ("wort ".repeat(100)).trim();            // 499 Zeichen ohne Satzende
const parts = V.splitForSpeech(long, 50);
assert(parts.length > 5);
parts.forEach((p) => assert(p.length <= 50, p.length));
assert.strictEqual(parts.join(" "), long);            // nichts geht verloren
const solid = "x".repeat(130);                        // kein Leerzeichen
assert.deepStrictEqual(V.splitForSpeech(solid, 50).map((p) => p.length), [50, 50, 30]);
 
// --- pickVoice
const de1 = { lang: "de-DE", localService: false, name: "online" };
const de2 = { lang: "de_AT", localService: true, name: "lokal" };
const en = { lang: "en-US", localService: true, name: "en" };
assert.strictEqual(V.pickVoice([en, de1, de2]), de2);
assert.strictEqual(V.pickVoice([en, de1]), de1);
assert.strictEqual(V.pickVoice([en]), null);
assert.strictEqual(V.pickVoice([{ lang: "deu-x" }]), null);   // "deu" ist keine de-Stimme
assert.strictEqual(V.pickVoice(undefined), null);
 
// --- Sprachausgabe
function makeSynth(voices) {
  const synth = { spoken: [], cancelled: 0 };
  synth.speak = (u) => synth.spoken.push(u);
  synth.cancel = () => { synth.cancelled++; };
  synth.getVoices = () => voices;
  return synth;
}
class Utt { constructor(text) { this.text = text; } }
 
let synth = makeSynth([en, de2]);
let voice = V.createVoice({ synth, Utterance: Utt });
assert.strictEqual(voice.canSpeak(), true);
assert.strictEqual(voice.speak("**Hallo** Sir. Alles gut.", "Fast"), true);
assert.deepStrictEqual(synth.spoken.map((u) => u.text), ["Hallo Sir.", "Alles gut."]);
synth.spoken.forEach((u) => {
  assert.strictEqual(u.lang, "de-DE");
  assert.strictEqual(u.rate, V.SPEEDS.Fast);
  assert.strictEqual(u.voice, de2);
});
assert(synth.cancelled >= 1, "altes Vorlesen muss vor dem neuen abgebrochen werden");
 
synth = makeSynth([]); voice = V.createVoice({ synth, Utterance: Utt });
voice.speak("Test.", "Gibtsnicht");
assert.strictEqual(synth.spoken[0].rate, 1);                  // unbekannte Geschwindigkeit -> normal
assert.strictEqual("voice" in synth.spoken[0], false);        // keine deutsche Stimme -> keine erzwungen
assert.strictEqual(voice.speak("   ", "Normal"), false);       // nichts zu sagen
assert.strictEqual(voice.speak("```nur code```", "Normal"), false);
voice.stopSpeaking();
assert(synth.cancelled >= 1);
 
// ohne Unterstuetzung: kein Absturz, ehrliche Antwort
const none = V.createVoice({});
assert.strictEqual(none.canSpeak(), false);
assert.strictEqual(none.canListen(), false);
assert.strictEqual(none.speak("Hallo"), false);
none.stopSpeaking(); none.stopListening();
assert.strictEqual(none.startListening({ onState() {}, onText() {} }), false);
 
 
// --- Sprechzustand und Stopp
{
  const events = [];
  const sy = makeSynth([]);
  const v = V.createVoice({ synth: sy, Utterance: Utt, onSpeaking: (x) => events.push(x) });
  assert.strictEqual(v.isSpeaking(), false);
  v.speak("Eins. Zwei.", "Normal");
  assert.strictEqual(v.isSpeaking(), true);
  assert.deepStrictEqual(events, [true]);
  sy.spoken[0].onend();
  assert.strictEqual(v.isSpeaking(), true);                // noch ein Stueck offen
  sy.spoken[1].onend();
  assert.strictEqual(v.isSpeaking(), false);
  assert.deepStrictEqual(events, [true, false]);
 
  // Stopp mittendrin: sofort "nicht mehr sprechend", spaete Ereignisse alter Stuecke stoeren nicht
  v.speak("Eins. Zwei.", "Normal");
  const old = sy.spoken.slice(-2);
  v.stopSpeaking();
  assert.strictEqual(v.isSpeaking(), false);
  assert.deepStrictEqual(events, [true, false, true, false]);
  v.speak("Neu.", "Normal");
  old.forEach((u) => u.onend());                           // Browser meldet Ende der abgebrochenen Stuecke
  assert.strictEqual(v.isSpeaking(), true, "alte Ereignisse duerfen die neue Ausgabe nicht beenden");
  sy.spoken[sy.spoken.length - 1].onerror();
  assert.strictEqual(v.isSpeaking(), false);
 
  // Stopp ohne Sprechen meldet nichts
  const n = events.length;
  v.stopSpeaking();
  assert.strictEqual(events.length, n);
}
 
// --- Spracheingabe
class Rec {
  constructor() { Rec.last = this; this.started = 0; this.stopped = 0; }
  start() { this.started++; if (Rec.failStart) throw new Error("busy"); }
  stop() { this.stopped++; }
}
function result(text, isFinal) { return { resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal })] }; }
 
synth = makeSynth([]);
voice = V.createVoice({ synth, Utterance: Utt, Recognition: Rec });
assert.strictEqual(voice.canListen(), true);
const log = { states: [], texts: [], errors: [] };
const handlers = {
  onState: (s) => log.states.push(s),
  onText: (t) => log.texts.push(t),
  onError: (e) => log.errors.push(e),
};
const before = synth.cancelled;
assert.strictEqual(voice.startListening(handlers), true);
assert(synth.cancelled > before, "beim Sprechen muss das Vorlesen stoppen");
assert.strictEqual(Rec.last.lang, "de-DE");
assert.strictEqual(Rec.last.continuous, true, "Druecken und Halten: nicht nach dem ersten Satz von selbst beenden");
assert.strictEqual(Rec.last.interimResults, false);
assert.strictEqual(voice.isListening(), true);
assert.strictEqual(voice.startListening(handlers), false);     // nicht doppelt
assert.strictEqual(Rec.last.started, 1);
voice.stopListening();
assert.strictEqual(Rec.last.stopped, 1);
 
const rec = Rec.last;
rec.onresult(result("Wie spät", false));                        // Zwischenstand zaehlt nicht
rec.onresult(result("Wie spät ist es", true));
rec.onend();
assert.deepStrictEqual(log.texts, ["Wie spät ist es"]);
assert.deepStrictEqual(log.states, ["listening", "idle"]);
assert.strictEqual(voice.isListening(), false);
 
// Stille: nichts wird gesendet
assert.strictEqual(voice.startListening(handlers), true);
Rec.last.onerror({ error: "no-speech" });
Rec.last.onend();
assert.deepStrictEqual(log.texts, ["Wie spät ist es"]);
assert.deepStrictEqual(log.errors, []);
 
// Echter Fehler wird gemeldet, Text trotzdem nicht gesendet
assert.strictEqual(voice.startListening(handlers), true);
Rec.last.onerror({ error: "not-allowed" });
Rec.last.onend();
assert.deepStrictEqual(log.errors, ["not-allowed"]);
assert.strictEqual(log.texts.length, 1);
 
// start() schlaegt fehl -> Zustand sauber
Rec.failStart = true;
assert.strictEqual(voice.startListening(handlers), false);
assert.strictEqual(voice.isListening(), false);
Rec.failStart = false;
assert.strictEqual(voice.startListening(handlers), true);
 
 
// --- Sprache erkennen (fuer die Browser-Stimme)
assert.strictEqual(V.detectLanguage("Guten Tag, Sir. Alle Systeme laufen."), "de-DE");
assert.strictEqual(V.detectLanguage("Good evening, sir. All systems are running smoothly."), "en-US");
assert.strictEqual(V.detectLanguage("What time is it? It is half past two."), "en-US");
assert.strictEqual(V.detectLanguage("Es ist schon spät, ich habe den Timer gestellt."), "de-DE");
assert.strictEqual(V.detectLanguage("Nudeln"), "de-DE");        // unklar: deutsch
assert.strictEqual(V.detectLanguage(""), "de-DE");
assert.strictEqual(V.detectLanguage(null), "de-DE");
assert.strictEqual(V.detectLanguage("Über uns"), "de-DE");
assert.strictEqual(V.detectLanguage("Jawohl, Sir."), "de-DE");   // "Sir" sagt Jarvis in beiden Sprachen
assert.strictEqual(V.detectLanguage("Very well, Sir."), "en-US");
{
  const sy = makeSynth([{ lang: "de-DE", name: "de" }, { lang: "en-GB", name: "en" }]);
  const v = V.createVoice({ synth: sy, Utterance: Utt });
  v.speak("Good evening, sir. All is well.", "Normal");
  assert.strictEqual(sy.spoken[0].lang, "en-US");
  assert.strictEqual(sy.spoken[0].voice.name, "en");
  v.speak("Guten Abend, Sir. Alles in Ordnung.", "Normal");
  assert.strictEqual(sy.spoken[sy.spoken.length - 1].lang, "de-DE");
  assert.strictEqual(sy.spoken[sy.spoken.length - 1].voice.name, "de");
}
assert.strictEqual(V.pickVoice([{ lang: "en-GB" }], "en-US").lang, "en-GB");
assert.strictEqual(V.pickVoice([{ lang: "de-DE" }], "en-US"), null);
 
// --- Gruppieren fuer die Server-Stimme: erster Satz allein, Rest zusammengefasst
assert.deepStrictEqual(V.groupForRemote(""), []);
assert.deepStrictEqual(V.groupForRemote("Nur ein Satz."), ["Nur ein Satz."]);
assert.deepStrictEqual(V.groupForRemote("Eins. Zwei. Drei."), ["Eins.", "Zwei. Drei."]);
{
  const sentence = "Dies ist ein Satz mit ungefaehr vierzig Zeichen.";       // 48
  const many = Array(12).fill(sentence).join(" ");
  const groups = V.groupForRemote(many);
  assert.strictEqual(groups[0], sentence);
  groups.forEach((g) => assert(g.length <= 280, g.length));
  assert.strictEqual(groups.join(" "), many);                                 // nichts geht verloren
  assert(groups.length < 12 && groups.length > 2);
}
 
// --- Server-Stimme (MP3)
class FakeAudio {
  constructor(url) { this.url = url; FakeAudio.all.push(this); }
  play() {
    this.played = true;
    FakeAudio.playing = this;
    if (FakeAudio.auto) setTimeout(() => this.onended && this.onended(), 0);
    return Promise.resolve();
  }
  pause() { this.paused = true; }
}
FakeAudio.all = [];
FakeAudio.auto = true;
 
function remoteEnv(overrides) {
  const log = { fetched: [], urls: [], revoked: [], speaking: [], fallbacks: [], signals: [] };
  const sy = makeSynth([]);
  const env = Object.assign({
    synth: sy, Utterance: Utt, Audio: FakeAudio,
    fetchAudio: (text, signal) => { log.fetched.push(text); log.signals.push(signal); return Promise.resolve("blob:" + text); },
    createObjectURL: (blob) => { log.urls.push(blob); return "url:" + blob; },
    revokeObjectURL: (url) => log.revoked.push(url),
    onSpeaking: (x) => log.speaking.push(x),
    onFallback: (e) => log.fallbacks.push(e),
  }, overrides || {});
  return { env, log, synth: sy };
}
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 20));
 
(async () => {
  // Normalfall: Stuecke der Reihe nach, mit Abspielgeschwindigkeit, Zustand sauber
  {
    FakeAudio.all = []; FakeAudio.auto = true;
    const { env, log, synth: sy } = remoteEnv();
    const v = V.createVoice(env);
    assert.strictEqual(v.canSpeak(), true);
    assert.strictEqual(v.speak("Eins. Zwei. Drei.", "Fast", "OpenAI"), true);
    assert.strictEqual(v.isSpeaking(), true);
    await tick(60);
    assert.deepStrictEqual(log.fetched, ["Eins.", "Zwei. Drei."]);
    assert.strictEqual(FakeAudio.all.length, 2);
    FakeAudio.all.forEach((a) => assert.strictEqual(a.playbackRate, V.REMOTE_RATES.Fast));
    assert.strictEqual(sy.spoken.length, 0, "mit Server-Stimme spricht der Browser nicht");
    assert.strictEqual(v.isSpeaking(), false);
    assert.deepStrictEqual(log.speaking, [true, false]);
    assert.strictEqual(log.revoked.length, 2, "Abgespieltes wird freigegeben");
    assert.deepStrictEqual(log.fallbacks, []);
  }
 
  // Vorab-Laden: das naechste Stueck wird angefragt, waehrend das erste noch laeuft
  {
    FakeAudio.all = []; FakeAudio.auto = false;
    const { env, log } = remoteEnv();
    const v = V.createVoice(env);
    v.speak("Eins. Zwei. Drei.", "Normal", "OpenAI");
    await tick();
    assert.strictEqual(FakeAudio.all.length, 1);
    assert.deepStrictEqual(log.fetched, ["Eins.", "Zwei. Drei."]);
    FakeAudio.auto = true;
    FakeAudio.all[0].onended();
    await tick(60);
    assert.strictEqual(FakeAudio.all.length, 2);
    assert.strictEqual(v.isSpeaking(), false);
  }
 
  // Stopp mittendrin: Audio pausiert, Anfrage abgebrochen, nichts spielt weiter
  {
    FakeAudio.all = []; FakeAudio.auto = false;
    const { env, log } = remoteEnv();
    const v = V.createVoice(env);
    v.speak("Eins. Zwei. Drei.", "Normal", "OpenAI");
    await tick();
    assert.strictEqual(v.isSpeaking(), true);
    v.stopSpeaking();
    assert.strictEqual(v.isSpeaking(), false);
    assert.strictEqual(FakeAudio.all[0].paused, true);
    assert.strictEqual(log.signals[0].aborted, true);
    assert.deepStrictEqual(log.speaking, [true, false]);
    await tick(60);
    assert.strictEqual(FakeAudio.all.length, 1, "nach dem Stopp wird kein weiteres Stueck gestartet");
    assert.strictEqual(log.fallbacks.length, 0);
    assert.strictEqual(log.revoked.length, 1);
  }
 
  // Neue Ausgabe waehrend der alten: nur die neue spielt
  {
    FakeAudio.all = []; FakeAudio.auto = false;
    const { env, log } = remoteEnv();
    const v = V.createVoice(env);
    v.speak("Alt eins. Alt zwei. Alt drei.", "Normal", "OpenAI");
    await tick();
    v.speak("Neu.", "Normal", "OpenAI");
    await tick();
    assert.strictEqual(FakeAudio.all[0].paused, true);
    assert.strictEqual(FakeAudio.all.length, 2);
    assert.strictEqual(FakeAudio.all[1].url, "url:blob:Neu.");
    FakeAudio.auto = true;
    FakeAudio.all[1].onended();
    await tick(40);
    assert.strictEqual(v.isSpeaking(), false);
    assert.strictEqual(log.speaking[log.speaking.length - 1], false);
    assert.strictEqual(log.fetched.filter((t) => t.startsWith("Alt")).length, 2, "nur vorab geladen, nicht abgespielt");
  }
 
  // Server fehlt (erste Anfrage scheitert): Browser-Stimme liest alles, einmal gemeldet
  {
    FakeAudio.all = []; FakeAudio.auto = true;
    const { env, log, synth: sy } = remoteEnv({ fetchAudio: () => Promise.reject(new Error("speak 502")) });
    const v = V.createVoice(env);
    v.speak("Good evening, sir. All is well.", "Normal", "OpenAI");
    await tick(40);
    assert.strictEqual(log.fallbacks.length, 1);
    assert.deepStrictEqual(sy.spoken.map((u) => u.text), ["Good evening, sir.", "All is well."]);
    assert.strictEqual(sy.spoken[0].lang, "en-US");
    assert.strictEqual(FakeAudio.all.length, 0);
    assert.strictEqual(v.isSpeaking(), true);
    sy.spoken.forEach((u) => u.onend());
    assert.strictEqual(v.isSpeaking(), false);
    assert.deepStrictEqual(log.speaking, [true, false]);
  }
 
  // Server faellt beim zweiten Stueck aus: nur der Rest kommt aus dem Browser
  {
    FakeAudio.all = []; FakeAudio.auto = true;
    let n = 0;
    const { env, log, synth: sy } = remoteEnv({
      fetchAudio: (text) => (++n === 1 ? Promise.resolve("blob:" + text) : Promise.reject(new Error("weg"))),
    });
    const v = V.createVoice(env);
    v.speak("Eins. Zwei. Drei.", "Normal", "OpenAI");
    await tick(60);
    assert.strictEqual(FakeAudio.all.length, 1);
    assert.deepStrictEqual(sy.spoken.map((u) => u.text), ["Zwei.", "Drei."]);
    assert.strictEqual(log.fallbacks.length, 1);
    assert.strictEqual(v.isSpeaking(), true);
    sy.spoken.forEach((u) => u.onend());
    assert.strictEqual(v.isSpeaking(), false);
  }
 
  // Abspielen scheitert (z.B. Browser blockiert): ebenfalls Rueckfall
  {
    FakeAudio.all = []; FakeAudio.auto = true;
    class BlockedAudio extends FakeAudio { play() { return Promise.reject(new Error("NotAllowedError")); } }
    const { env, log, synth: sy } = remoteEnv({ Audio: BlockedAudio });
    const v = V.createVoice(env);
    v.speak("Hallo Sir.", "Normal", "OpenAI");
    await tick(40);
    assert.strictEqual(log.fallbacks.length, 1);
    assert.deepStrictEqual(sy.spoken.map((u) => u.text), ["Hallo Sir."]);
  }
 
  // Fehler ohne Browser-Stimme: sauber beenden, nicht haengen bleiben
  {
    const { env, log } = remoteEnv({ synth: null, Utterance: null, fetchAudio: () => Promise.reject(new Error("x")) });
    const v = V.createVoice(env);
    v.speak("Hallo Sir.", "Normal", "OpenAI");
    await tick(40);
    assert.strictEqual(v.isSpeaking(), false);
    assert.deepStrictEqual(log.speaking, [true, false]);
    assert.strictEqual(log.fallbacks.length, 1);
  }
 
  // Engine "Browser": der Server wird nie gefragt
  {
    FakeAudio.all = [];
    const { env, log, synth: sy } = remoteEnv();
    const v = V.createVoice(env);
    v.speak("Hallo Sir.", "Normal", "Browser");
    v.speak("Hallo Sir.", "Normal");
    assert.deepStrictEqual(log.fetched, []);
    assert.strictEqual(sy.spoken.length, 2);
    assert.strictEqual(FakeAudio.all.length, 0);
  }
 
  // Engine "OpenAI" ohne Wiedergabemoeglichkeit: Browser-Stimme
  {
    const { env, log, synth: sy } = remoteEnv({ Audio: null });
    const v = V.createVoice(env);
    v.speak("Hallo Sir.", "Normal", "OpenAI");
    assert.deepStrictEqual(log.fetched, []);
    assert.strictEqual(sy.spoken.length, 1);
  }
 
  // Nichts kann sprechen
  {
    const v = V.createVoice({});
    assert.strictEqual(v.canSpeak(), false);
    assert.strictEqual(v.speak("Hallo", "Normal", "OpenAI"), false);
  }
 
  // Eingabesprache
  {
    const synthI = makeSynth([]);
    const v = V.createVoice({ synth: synthI, Utterance: Utt, Recognition: Rec });
    const h = { onState() {}, onText() {} };
    v.startListening(h, "English");
    assert.strictEqual(Rec.last.lang, "en-US");
    Rec.last.onend();
    v.startListening(h, "German");
    assert.strictEqual(Rec.last.lang, "de-DE");
    Rec.last.onend();
    v.startListening(h, "Klingon");
    assert.strictEqual(Rec.last.lang, "de-DE");
    Rec.last.onend();
    v.startListening(h);
    assert.strictEqual(Rec.last.lang, "de-DE");
  }
 
  // --- Wachhund und Fehlertexte (Druecken und Halten darf nie haengen bleiben)
  {
    const timers = [];
    let clock = 0;
    const env = {
      synth: makeSynth([]), Utterance: Utt, Recognition: Rec,
      setTimeout: (fn, ms) => { const t = { fn, ms, live: true }; timers.push(t); return t; },
      clearTimeout: (t) => { if (t) t.live = false; },
      now: () => clock,
    };
    const fire = () => { const t = timers.filter((x) => x.live).pop(); assert(t, "kein Wachhund aktiv"); t.live = false; t.fn(); return t.ms; };
    const live = () => timers.filter((x) => x.live);
    const mk = () => { const l = { states: [], texts: [], errors: [] };
      return { l, h: { onState: (x) => l.states.push(x), onText: (x) => l.texts.push(x), onError: (x) => l.errors.push(x) } }; };
 
    // a) Mikrofon meldet sich nie: nach 10 s wieder frei, naechster Druck geht
    let { l, h } = mk();
    const v = V.createVoice(env);
    assert.strictEqual(v.startListening(h), true);
    assert.strictEqual(live().length, 1);
    assert.strictEqual(fire(), 10000);
    assert.strictEqual(v.isListening(), false);
    assert.deepStrictEqual(l.states, ["listening", "idle"]);
    assert.strictEqual(v.startListening(h), true, "nach dem Haenger muss es wieder gehen");
    // b) Mikrofon laeuft: onstart setzt auf die Hoechstdauer (60 s)
    Rec.last.onstart();
    assert.strictEqual(live().length, 1);
    assert.strictEqual(live()[0].ms, 60000);
    // c) Loslassen: stop(), kommt onend nie, setzt nach 4 s der Wachhund zurueck und der Text geht trotzdem raus
    Rec.last.onresult(result("Wie spät ist es", true));
    v.stopListening();
    assert.strictEqual(Rec.last.stopped >= 1, true);
    assert.strictEqual(live().length, 1);
    assert.strictEqual(live()[0].ms, 4000);
    fire();
    assert.strictEqual(v.isListening(), false);
    assert.deepStrictEqual(l.texts, ["Wie spät ist es"]);
    // d) spaetes echtes onend nach dem Wachhund: nichts doppelt
    const before = l.states.length;
    Rec.last.onend();
    assert.strictEqual(l.states.length, before);
    assert.deepStrictEqual(l.texts, ["Wie spät ist es"]);
    assert.strictEqual(live().length, 0);
 
    // e) harter Fehler ohne onend: gemeldet, nach 1,5 s frei
    ({ l, h } = mk());
    assert.strictEqual(v.startListening(h), true);
    Rec.last.onerror({ error: "network" });
    assert.deepStrictEqual(l.errors, ["network"]);
    assert.strictEqual(live().pop().ms, 1500);
    fire();
    assert.strictEqual(v.isListening(), false);
    // normales onend nach Fehler: Wachhund aus
    assert.strictEqual(v.startListening(h), true);
    Rec.last.onerror({ error: "not-allowed" });
    Rec.last.onend();
    assert.strictEqual(live().length, 0);
    assert.deepStrictEqual(l.errors, ["network", "not-allowed"]);
 
    // f) Stille: kurz = still, lang gehalten = Hinweis
    ({ l, h } = mk());
    clock = 0;
    assert.strictEqual(v.startListening(h), true);
    clock = 2000;
    Rec.last.onerror({ error: "no-speech" }); Rec.last.onend();
    assert.deepStrictEqual(l.errors, [], "kurzes Antippen ist kein Fehler");
    assert.strictEqual(v.startListening(h), true);
    clock = 2000 + 2500;
    Rec.last.onerror({ error: "no-speech" }); Rec.last.onend();
    assert.deepStrictEqual(l.errors, ["no-speech"], "lang gehalten und nichts gehoert");
    // "aborted" bleibt still
    assert.strictEqual(v.startListening(h), true);
    Rec.last.onerror({ error: "aborted" }); Rec.last.onend();
    assert.deepStrictEqual(l.errors, ["no-speech"]);
 
    // g) start() wirft: kein Wachhund, Zustand frei
    Rec.failStart = true;
    const n = live().length;
    assert.strictEqual(v.startListening(h), false);
    assert.strictEqual(live().length, n);
    Rec.failStart = false;
    assert.strictEqual(v.isListening(), false);
    // h) stopListening ohne Aufnahme tut nichts
    v.stopListening();
 
    // i) Fehlertexte
    for (const code of ["not-allowed", "service-not-allowed", "audio-capture", "network", "no-speech", "language-not-supported", "unstable"]) {
      const text = V.describeSpeechError(code);
      assert(text.includes("(" + code + ")") && text.length > 40, code);
    }
    assert(V.describeSpeechError("not-allowed").includes("Mikrofon") && V.describeSpeechError("network").includes("Online-Dienst"));
    assert.strictEqual(V.describeSpeechError("kaputt"), "Spracheingabe nicht möglich (kaputt).");
    assert.strictEqual(V.describeSpeechError(undefined), "Spracheingabe nicht möglich (undefined).");
  }
 
  console.log("voice.js OK");
})().catch((error) => { console.error(error); process.exit(1); });