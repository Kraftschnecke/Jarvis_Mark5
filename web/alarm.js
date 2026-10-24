// Wecker und Timer laeuten (Step 2.11): Banner mit "Aus" und "Schlummern", Ton im Browser (WebAudio),
// blinkender Tab-Titel. Die Logik ist von der Seite getrennt (alles kommt ueber `deps`), damit Node sie testen kann.
(function (root) {
  "use strict";

  const PERIOD_SECONDS = 1.64;            // wie das Muster im Server (ringing.make_wav_bytes)
  const BEEP_STARTS = [0, 0.28, 0.56];
  const BEEP_SECONDS = 0.18;
  const BEEP_HZ = 988;

  function formatSeconds(seconds) {
    seconds = Math.max(0, Math.floor(Number(seconds) || 0));
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }

  // state wie von /api/ringing -> was das Banner zeigt
  function bannerView(state, locked) {
    const rings = (state && Array.isArray(state.ringing)) ? state.ringing : [];
    if (!rings.length) return { show: false, title: "", detail: "", hint: "", snoozeLabel: "" };
    const icon = (r) => (r.kind === "timer" ? "⏲" : "⏰");
    const first = rings[0];
    const title = rings.length === 1 ? icon(first) + " " + first.label : "⏰ " + rings.length + " läuten";
    const detail = rings.length === 1
      ? "seit " + formatSeconds(first.seconds)
      : rings.map((r) => r.label).join(", ");
    const hint = locked && state.sound === "Browser"
      ? "Klicke irgendwo auf die Seite, damit der Browser den Ton abspielen darf."
      : "";
    const minutes = Number(state.snooze_minutes) || 5;
    return { show: true, title: title, detail: detail, hint: hint, snoozeLabel: "Schlummern (" + minutes + " min)" };
  }

  // deps: api(method, path, body), AudioContext (Klasse oder null), setInterval, clearInterval,
  //       setBanner(view), say(text), getTitle(), setTitle(text)
  function createController(deps) {
    const originalTitle = deps.getTitle();
    const ctrl = { state: null, ctx: null, beepTimer: null, blinkOn: false, titleChanged: false, busy: false };

    function ensureContext() {
      if (!ctrl.ctx && deps.AudioContext) {
        try { ctrl.ctx = new deps.AudioContext(); } catch (error) { ctrl.ctx = null; }
      }
      return ctrl.ctx;
    }

    function locked() {
      return !ctrl.ctx || ctrl.ctx.state !== "running";
    }

    function beepOnce() {
      const ctx = ctrl.ctx;
      if (!ctx || ctx.state !== "running") return false;
      const t0 = ctx.currentTime;
      BEEP_STARTS.forEach((offset) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const start = t0 + offset;
        osc.frequency.value = BEEP_HZ;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.linearRampToValueAtTime(0.35, start + 0.02);
        gain.gain.setValueAtTime(0.35, start + BEEP_SECONDS - 0.03);
        gain.gain.linearRampToValueAtTime(0.0001, start + BEEP_SECONDS);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(start);
        osc.stop(start + BEEP_SECONDS + 0.02);
      });
      return true;
    }

    function startBeeps() {
      if (ctrl.beepTimer !== null) return;
      ensureContext();
      beepOnce();
      ctrl.beepTimer = deps.setInterval(beepOnce, PERIOD_SECONDS * 1000);
    }

    function stopBeeps() {
      if (ctrl.beepTimer === null) return;
      deps.clearInterval(ctrl.beepTimer);
      ctrl.beepTimer = null;
    }

    // Auf eine Bedienung der Seite (Klick/Taste) hin: der Browser erlaubt Ton erst nach einer Geste
    function unlock() {
      const ctx = ensureContext();
      if (ctx && ctx.state === "suspended" && typeof ctx.resume === "function") {
        const result = ctx.resume();
        if (result && typeof result.then === "function") result.then(render, () => {});
      }
      render();
    }

    function render() {
      deps.setBanner(bannerView(ctrl.state, locked()));
    }

    function update(state) {
      ctrl.state = state;
      const rings = Array.isArray(state && state.ringing) ? state.ringing : [];
      if (rings.length && state.sound === "Browser") startBeeps(); else stopBeeps();
      if (rings.length) {
        ctrl.blinkOn = !ctrl.blinkOn;
        ctrl.titleChanged = true;
        deps.setTitle(ctrl.blinkOn ? "⏰ " + rings[0].label : originalTitle);
      } else if (ctrl.titleChanged) {
        ctrl.blinkOn = false;
        ctrl.titleChanged = false;
        deps.setTitle(originalTitle);       // nur zurueck, wenn wir ihn veraendert haben
      }
      render();
    }

    async function poll() {
      try {
        update(await deps.api("GET", "/api/ringing"));
      } catch (error) {
        /* Server nicht erreichbar: der Rest der Seite zeigt OFFLINE */
      }
    }

    async function act(body) {
      if (ctrl.busy) return;
      ctrl.busy = true;
      try {
        const result = await deps.api("POST", "/api/ringing/stop", body);
        if (result.reply) deps.say(result.reply);
        update(result.state);
      } catch (error) {
        /* beim naechsten Abruf stimmt der Stand wieder */
      } finally {
        ctrl.busy = false;
      }
    }

    return {
      poll: poll,
      update: update,
      unlock: unlock,
      stop: () => act({}),
      snooze: () => act({ snooze: true }),
      _ctrl: ctrl,
      _beepOnce: beepOnce,
    };
  }

  const api = { formatSeconds, bannerView, createController, PERIOD_SECONDS, BEEP_HZ };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisAlarm = api;
})(typeof window !== "undefined" ? window : globalThis);
