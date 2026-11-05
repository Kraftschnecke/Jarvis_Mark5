// Sprache (Step 6): Vorlesen und Sprechen.
//
// Vorlesen: entweder mit der Stimme von OpenAI (der Server liefert MP3, siehe
// speech.py) oder mit der Browser-Stimme. Faellt die OpenAI-Stimme aus, liest die
// Browser-Stimme den Rest vor. Sprechen: Web-Speech-API des Browsers. Der Server
// bekommt nie Audio, nur erkannten TEXT, genau wie bei getipptem Text.
//
// Die Textfunktionen und die Sprechlogik (createVoice) sind von der Seite getrennt,
// damit sie ohne Browser testbar sind.
(function (root) {
  "use strict";
 
  const SPEEDS = { Slow: 0.85, Normal: 1, Fast: 1.25 };           // Browser-Stimme
  const REMOTE_RATES = { Slow: 0.9, Normal: 1, Fast: 1.15 };       // abgespielte MP3
  const INPUT_LANGUAGES = { German: "de-DE", English: "en-US" };
  const MAX_CHUNK = 180;          // Chrome bricht lange Aeusserungen ab
  const MAX_REMOTE_CHUNK = 280;   // pro Anfrage an den Server
  const START_TIMEOUT = 10000;    // Mikrofon meldet sich nach dem Start nie: Zustand zuruecksetzen
  const MAX_LISTEN = 60000;       // so lange hoert Druecken-und-Halten hoechstens zu
  const STOP_TIMEOUT = 4000;      // nach "stop" kommt das Ende nie: Zustand zuruecksetzen
  const FATAL_TIMEOUT = 1500;     // nach einem harten Fehler kommt "onend" manchmal nie
  const LONG_SILENCE = 2500;      // so lange gehalten und nichts gehoert: das ist kein Versehen, sag es
  const FATAL_ERRORS = ["not-allowed", "service-not-allowed", "audio-capture", "network", "language-not-supported"];
 
  // Verstaendlicher Satz zu einem Fehlercode der Browser-Spracherkennung
  function describeSpeechError(code) {
    switch (code) {
      case "not-allowed":
      case "service-not-allowed":
        return "Der Browser darf das Mikrofon nicht benutzen. Erlaube es im Schloss-Symbol der Adressleiste. Unter Windows: Einstellungen, Datenschutz, Mikrofon und Sprache (Online-Spracherkennung) einschalten (" + code + ").";
      case "audio-capture":
        return "Es wurde kein Mikrofon gefunden oder es ist von einem anderen Programm belegt (audio-capture).";
      case "network":
        return "Die Spracherkennung des Browsers erreicht ihren Online-Dienst nicht. Prüfe Internet, VPN und Firewall (network).";
      case "no-speech":
        return "Ich habe nichts gehört. Ist in Windows das richtige Mikrofon eingestellt und nicht stumm? (no-speech)";
      case "language-not-supported":
        return "Der Browser kennt diese Eingabesprache nicht (language-not-supported).";
      case "unstable":
        return "Die Spracherkennung startet immer wieder neu und bricht ab. Meist fehlt die Mikrofon-Erlaubnis oder der Online-Dienst ist nicht erreichbar (unstable).";
      default:
        return "Spracheingabe nicht möglich (" + String(code) + ").";
    }
  }
 
  // Macht aus Markdown-Text etwas, das man vorlesen kann
  function cleanForSpeech(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(/```[\s\S]*?```/g, " ")          // Codebloecke nicht vorlesen
      .replace(/`([^`]*)`/g, "$1")
      .replace(/https?:\/\/\S+/g, " Link ")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/[*_#>]+/g, " ")
      .replace(/^\s*[-•]\s+/gm, "")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{2,}/g, "\n")
      .trim();
  }
 
  // Teilt Text in kurze Stuecke an Satzenden; zu lange Saetze an Leerzeichen
  function splitForSpeech(text, max) {
    max = max || MAX_CHUNK;
    const pieces = String(text).split(/(?<=[.!?:;])\s+|\n+/).map((p) => p.trim()).filter(Boolean);
    const chunks = [];
 
    pieces.forEach((piece) => {
      while (piece.length > max) {
        let cut = piece.lastIndexOf(" ", max);
        if (cut < max / 2) cut = max;
        chunks.push(piece.slice(0, cut).trim());
        piece = piece.slice(cut).trim();
      }
      if (piece) chunks.push(piece);
    });
 
    return chunks;
  }
 
  // Fuer die Server-Stimme: erster Satz allein (schnell hoerbar), den Rest zu
  // groesseren Stuecken zusammenfassen (weniger Anfragen)
  function groupForRemote(text) {
    const sentences = splitForSpeech(text, MAX_REMOTE_CHUNK);
    if (sentences.length <= 1) return sentences;
 
    const groups = [sentences[0]];
    let current = "";
 
    sentences.slice(1).forEach((sentence) => {
      if (current && (current + " " + sentence).length > MAX_REMOTE_CHUNK) {
        groups.push(current);
        current = sentence;
      } else {
        current = current ? current + " " + sentence : sentence;
      }
    });
    if (current) groups.push(current);
    return groups;
  }
 
  // "Sir" gehoert in keine Liste: Jarvis sagt es in beiden Sprachen
  const GERMAN_WORDS = ["der", "die", "das", "und", "ist", "nicht", "ich", "du", "sie", "ein", "eine",
    "zu", "mit", "auf", "für", "es", "wie", "was", "habe", "dein", "wird", "von", "den", "dem", "im",
    "bitte", "kann", "noch", "schon", "ja", "nein", "uhr", "heute", "guten", "tag", "abend", "morgen",
    "alle", "alles", "ordnung", "sind", "läuft", "laufen", "bin", "hier", "jetzt", "aber", "oder", "auch", "wir", "er"];
  const ENGLISH_WORDS = ["the", "and", "is", "are", "you", "your", "i", "it", "of", "to", "in", "that",
    "for", "with", "have", "has", "this", "what", "how", "can", "will", "not", "my", "be", "was", "do",
    "yes", "no", "time", "today", "please", "there", "good", "evening", "afternoon", "all", "am", "been",
    "here", "now", "they", "we", "he", "she", "would", "could", "should", "just", "so", "but", "if", "at",
    "on", "by", "from", "about", "one", "some", "or", "systems", "running", "well", "smoothly", "right",
    "ready", "done", "set", "sorry", "thank", "thanks", "hello", "hi", "minutes", "seconds", "timer"];
 
  // Grobe Sprache des Textes fuer die Browser-Stimme: "de-DE" oder "en-US" (Standard: deutsch)
  function detectLanguage(text) {
    const words = String(text).toLowerCase().match(/[a-zäöüß]+/g) || [];
    let de = 0;
    let en = 0;
    words.forEach((w) => {
      if (GERMAN_WORDS.includes(w)) de++;
      if (ENGLISH_WORDS.includes(w)) en++;
      if (/[äöüß]/.test(w)) de += 2;
    });
    return en > de ? "en-US" : "de-DE";
  }
 
  // Waehlt eine Stimme der Sprache (lokale zuerst), sonst keine Vorgabe
  function pickVoice(voices, lang) {
    const prefix = String(lang || "de-DE").slice(0, 2).toLowerCase();
    const match = (voices || []).filter((v) => new RegExp("^" + prefix + "(-|_|$)", "i").test(v.lang || ""));
    return match.find((v) => v.localService) || match[0] || null;
  }
 
  // env: { synth, Utterance, Recognition, Audio, fetchAudio, createObjectURL, revokeObjectURL,
  //        onSpeaking(bool), onFallback(error) }
  function createVoice(env) {
    const synth = env.synth || null;
    const Utterance = env.Utterance || null;
    const Recognition = env.Recognition || null;
    const AudioClass = env.Audio || null;
    const fetchAudio = env.fetchAudio || null;
    let recognition = null;
    let generation = 0;       // jede neue Ausgabe/jeder Stopp macht alte Ereignisse ungueltig
    let pending = 0;          // Stuecke, die noch nicht fertig gesprochen sind
    let controller = null;    // bricht laufende Anfragen an den Server ab
    let currentAudio = null;
    const onSpeaking = env.onSpeaking || function () {};
    const onFallback = env.onFallback || function () {};
    const later = env.setTimeout || ((fn, ms) => setTimeout(fn, ms));
    const cancel = env.clearTimeout || ((id) => clearTimeout(id));
    const now = env.now || (() => Date.now());
    let armGuard = null;      // setzt den Wachhund der laufenden Aufnahme neu (siehe startListening)
 
    function isSpeaking() { return pending > 0; }
    function canSpeak() { return Boolean((synth && Utterance) || (fetchAudio && AudioClass)); }
    function canListen() { return Boolean(Recognition); }
 
    function stopSpeaking() {
      generation++;
      const was = pending > 0;
      pending = 0;
      if (controller) { controller.abort(); controller = null; }
      if (currentAudio) { currentAudio.stop(); currentAudio = null; }
      if (synth) synth.cancel();
      if (was) onSpeaking(false);
    }
 
    function finishOne(mine) {
      if (mine !== generation) return;          // gehoert zu einer abgebrochenen Ausgabe
      pending = Math.max(0, pending - 1);
      if (pending === 0) onSpeaking(false);
    }
 
    // ---- Browser-Stimme
    function speakInBrowser(chunks, speedName, mine) {
      const rate = SPEEDS[speedName] || 1;
      // Die Sprache gilt fuer den ganzen Text: einzelne Saetze sind zu kurz zum Erkennen
      const lang = detectLanguage(chunks.join(" "));
 
      chunks.forEach((chunk) => {
        const utterance = new Utterance(chunk);
        const voice = pickVoice(synth.getVoices ? synth.getVoices() : [], lang);
        utterance.lang = lang;
        utterance.rate = rate;
        if (voice) utterance.voice = voice;
        utterance.onend = () => finishOne(mine);
        utterance.onerror = () => finishOne(mine);
        synth.speak(utterance);
      });
    }
 
    // ---- Server-Stimme (MP3)
    function playBlob(blob, rate, mine) {
      return new Promise((resolve, reject) => {
        const url = env.createObjectURL(blob);
        const audio = new AudioClass(url);
        let settled = false;
 
        function done(error) {
          if (settled) return;
          settled = true;
          if (env.revokeObjectURL) env.revokeObjectURL(url);
          if (currentAudio === handle) currentAudio = null;
          error ? reject(error) : resolve();
        }
 
        const handle = { stop() { try { audio.pause(); } catch (e) { /* schon fertig */ } done(); } };
        currentAudio = handle;
        audio.playbackRate = rate;
        audio.onended = () => done();
        audio.onerror = () => done(new Error("audio"));
 
        const started = audio.play();
        if (started && started.catch) started.catch((error) => done(error || new Error("play")));
      });
    }
 
    async function speakFromServer(chunks, speedName, mine) {
      const own = new AbortController();
      controller = own;
      const rate = REMOTE_RATES[speedName] || 1;
      let next = fetchAudio(chunks[0], own.signal);
 
      for (let i = 0; i < chunks.length; i++) {
        let blob;
 
        try {
          blob = await next;
          if (mine !== generation) return;
          next = i + 1 < chunks.length ? fetchAudio(chunks[i + 1], own.signal) : null;
          if (next) next.catch(() => {});       // Fehler zeigt sich erst, wenn wir ihn abwarten
          await playBlob(blob, rate, mine);
        } catch (error) {
          if (mine !== generation) return;
          // Server-Stimme fehlgeschlagen: Rest mit der Browser-Stimme
          onFallback(error);
          if (synth && Utterance) {
            // Die Browser-Stimme braucht kuerzere Stuecke als die Server-Stimme
            const rest = splitForSpeech(chunks.slice(i).join(" "));
            pending = rest.length;              // fertige Stuecke zaehlen nicht mehr
            speakInBrowser(rest, speedName, mine);
          } else {
            pending = 0;
            onSpeaking(false);
          }
          return;
        }
 
        if (mine !== generation) return;
        finishOne(mine);
      }
    }
 
    // engine: "OpenAI" (Server-Stimme) oder "Browser"
    function speak(text, speedName, engine) {
      const cleaned = cleanForSpeech(text);
      const useServer = engine === "OpenAI" && fetchAudio && AudioClass;
 
      if (!useServer && !(synth && Utterance)) return false;
 
      const chunks = useServer ? groupForRemote(cleaned) : splitForSpeech(cleaned);
      stopSpeaking();
      if (!chunks.length) return false;
 
      const mine = generation;
      pending = chunks.length;
      onSpeaking(true);
 
      if (useServer) speakFromServer(chunks, speedName, mine);
      else speakInBrowser(chunks, speedName, mine);
      return true;
    }
 
    // Push-to-talk: start() beim Druecken, stop() beim Loslassen.
    // handlers: { onText(text), onState("listening"|"idle"), onError(message) }
    // inputLanguage: "German" oder "English"
    function startListening(handlers, inputLanguage) {
      if (!canListen() || recognition) return false;
      stopSpeaking();   // J.A.R.V.I.S. soll sich nicht selbst zuhoeren
 
      const rec = new Recognition();
      let text = "";
      let timer = null;
      let finished = false;
      const startedAt = now();
      rec.lang = INPUT_LANGUAGES[inputLanguage] || "de-DE";
      // Druecken und Halten: Chrome beendet sonst von selbst, sobald du einen Satz oder eine Pause beendest
      rec.continuous = true;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
 
      // Ende der Aufnahme, genau einmal. Kommt "onend" nie (kommt bei Fehlern vor), beendet der Wachhund sie.
      function finish() {
        if (finished) return;
        finished = true;
        if (timer) { cancel(timer); timer = null; }
        if (recognition === rec) recognition = null;
        if (armGuard === guard) armGuard = null;
        handlers.onState("idle");
        text = text.trim();
        if (text) handlers.onText(text);
      }
      function guard(ms) {
        if (finished) return;
        if (timer) cancel(timer);
        timer = later(() => {
          timer = null;
          try { if (rec.abort) rec.abort(); } catch (error) { /* war schon beendet */ }
          finish();
        }, ms);
      }
 
      rec.onstart = () => guard(MAX_LISTEN);
      rec.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) text += event.results[i][0].transcript + " ";
        }
      };
      rec.onerror = (event) => {
        const code = event && event.error;
        if (code === "no-speech") {
          if (handlers.onError && now() - startedAt >= LONG_SILENCE) handlers.onError(code);
        } else if (code !== "aborted") {
          if (handlers.onError) handlers.onError(code);
        }
        if (FATAL_ERRORS.includes(code)) guard(FATAL_TIMEOUT);
      };
      rec.onend = finish;
 
      recognition = rec;
      armGuard = guard;
      try {
        rec.start();
      } catch (error) {
        recognition = null;
        armGuard = null;
        finished = true;
        return false;
      }
      guard(START_TIMEOUT);
      handlers.onState("listening");
      return true;
    }
 
    function stopListening() {
      if (recognition) {
        try { recognition.stop(); } catch (error) { /* schon beendet */ }
        if (armGuard) armGuard(STOP_TIMEOUT);
      }
    }
 
    function isListening() { return recognition !== null; }
 
    return { canSpeak, canListen, speak, stopSpeaking, isSpeaking, startListening, stopListening, isListening };
  }
 
  const api = {
    cleanForSpeech, splitForSpeech, groupForRemote, detectLanguage, pickVoice, createVoice, describeSpeechError,
    SPEEDS, REMOTE_RATES, INPUT_LANGUAGES,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisVoice = api;
})(typeof window !== "undefined" ? window : this);