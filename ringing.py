"""Klingeln (Mark 5, 2.11): Wecker und Timer läuten, bis man sie ausschaltet.

Aufbau:
  - Ringer      Liste der gerade läutenden Dinge (Wecker/Timer), mit Auto-Ende.
  - Siren       spielt den Ton auf dem Computer (Windows: winsound, Endlosschleife).
  - stop_intent erkennt kurze Sätze wie "Jarvis, Wecker aus" OHNE KI-Aufruf.

Sicherheit: Der Ton läuft nur, solange mindestens ein Eintrag läutet. Jeder Eintrag
endet spätestens nach `max_minutes` von selbst. Es gibt keine Aktion, die von außen
etwas anderes tun könnte als: läuten, stoppen, schlummern.
"""

import io
import math
import re
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path

from background_tasks import submit_result

SOUNDS = ("Computer", "Browser", "Aus")
MAX_RINGING = 10
DEFAULT_MAX_MINUTES = 10
DEFAULT_SNOOZE_MINUTES = 5
MAX_SNOOZE_MINUTES = 60
MAX_LABEL_LENGTH = 40


def make_wav_bytes(sample_rate=8000):
    """Wecker-Muster als WAV: drei kurze Pieptöne, dann Pause (ca. 1,6 s, wird in Schleife gespielt)."""
    frames = bytearray()

    def tone(seconds, hz):
        for i in range(int(sample_rate * seconds)):
            fade = min(1.0, i / 80, (int(sample_rate * seconds) - i) / 80)   # kein Knacken an den Rändern
            frames.extend(struct.pack("<h", int(14000 * fade * math.sin(2 * math.pi * hz * i / sample_rate))))

    def silence(seconds):
        frames.extend(b"\x00\x00" * int(sample_rate * seconds))

    for _ in range(3):
        tone(0.18, 988)
        silence(0.10)
    silence(0.80)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


class Siren:
    """Spielt das Wecker-Muster in Endlosschleife (nur Windows; sonst still).

    `player` ist das winsound-Modul oder ein Ersatz mit PlaySound/SND_*-Konstanten
    (Tests). Ohne player wird winsound versucht; fehlt es, bleibt die Sirene still.
    """

    def __init__(self, player=None, folder=None):
        if player is None:
            try:
                import winsound as player
            except ImportError:
                player = None
        self.player = player
        self.folder = Path(folder) if folder else None
        self.path = None
        self.playing = False

    @property
    def available(self):
        return self.player is not None

    def _wav_path(self):
        if self.path is None or not self.path.exists():
            folder = self.folder or Path(tempfile.gettempdir())
            self.path = folder / "jarvis_alarm.wav"
            self.path.write_bytes(make_wav_bytes())
        return self.path

    def start(self):
        if self.playing or self.player is None:
            return False
        try:
            flags = self.player.SND_FILENAME | self.player.SND_ASYNC | self.player.SND_LOOP
            self.player.PlaySound(str(self._wav_path()), flags)
            self.playing = True
        except Exception as error:
            print(f"[WECKER] Ton konnte nicht gestartet werden: {type(error).__name__}")
            return False
        return True

    def stop(self):
        if not self.playing:
            return
        self.playing = False
        try:
            self.player.PlaySound(None, self.player.SND_PURGE)
        except Exception as error:
            print(f"[WECKER] Ton konnte nicht gestoppt werden: {type(error).__name__}")


def clean_label(label, default):
    text = label if isinstance(label, str) else ""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:MAX_LABEL_LENGTH].strip()
    return text or default


class Ringer:
    def __init__(self, siren=None, clock=time.monotonic):
        self.siren = siren if siren is not None else Siren()
        self.clock = clock
        self.sound = "Computer"          # Computer | Browser | Aus
        self.ring_timers = True
        self.max_minutes = DEFAULT_MAX_MINUTES
        self.snooze_minutes = DEFAULT_SNOOZE_MINUTES
        self.briefing_default = True     # neue Wecker sprechen beim Ausschalten kurz den Tag an
        self.snooze_handler = None       # callable(ring, minutes) -> None; plant das erneute Läuten
        self.briefing_provider = None    # callable() -> Text; wird beim Ausschalten eines Weckers gesprochen
        self._lock = threading.Lock()
        self._rings = {}
        self._next_id = 1
        self.version = 0                 # zählt jede Änderung: die Oberfläche merkt sofort, dass sich etwas tut

    # --- Einstellungen -------------------------------------------------
    def configure(self, sound=None, ring_timers=None, max_minutes=None, snooze_minutes=None, briefing=None):
        with self._lock:
            if isinstance(briefing, bool):
                self.briefing_default = briefing
            if sound in SOUNDS:
                self.sound = sound
            if isinstance(ring_timers, bool):
                self.ring_timers = ring_timers
            if isinstance(max_minutes, int) and not isinstance(max_minutes, bool) and 1 <= max_minutes <= 60:
                self.max_minutes = max_minutes
            if isinstance(snooze_minutes, int) and not isinstance(snooze_minutes, bool) \
                    and 1 <= snooze_minutes <= MAX_SNOOZE_MINUTES:
                self.snooze_minutes = snooze_minutes
            sound_off = self.sound != "Computer"
        if sound_off:
            self.siren.stop()
        else:
            self._update_siren()

    # --- Läuten --------------------------------------------------------
    def start(self, kind, label, briefing=False, **extra):
        """Lässt etwas läuten. Gibt den Eintrag zurück (None, wenn zu viele läuten)."""
        if kind not in ("alarm", "timer"):
            raise ValueError("kind muss 'alarm' oder 'timer' sein")
        with self._lock:
            if len(self._rings) >= MAX_RINGING:
                return None
            ring = {
                "id": self._next_id, "kind": kind,
                "label": clean_label(label, "Wecker" if kind == "alarm" else "Timer"),
                "briefing": bool(briefing), "started": self.clock(), **extra,
            }
            self._next_id += 1
            self._rings[ring["id"]] = ring
            self.version += 1
        self._update_siren()
        return dict(ring)

    def active(self):
        now = self.clock()
        with self._lock:
            rings = sorted(self._rings.values(), key=lambda r: r["id"])
            limit = self.max_minutes * 60
            return [{"id": r["id"], "kind": r["kind"], "label": r["label"], "briefing": r["briefing"],
                     "seconds": int(now - r["started"]),
                     "remaining": max(0, int(limit - (now - r["started"])))} for r in rings]

    def is_ringing(self):
        with self._lock:
            return bool(self._rings)

    def state(self):
        """Für /api/ringing: was läutet, und wer macht den Ton?"""
        rings = self.active()
        return {"ringing": rings, "sound": self.sound, "version": self.version,
                "snooze_minutes": self.snooze_minutes, "server_sound": bool(self.siren.playing)}

    def _update_siren(self):
        with self._lock:
            should = bool(self._rings) and self.sound == "Computer"
        if should:
            self.siren.start()
        else:
            self.siren.stop()

    # --- Beenden -------------------------------------------------------
    def stop(self, which=None, kind=None):
        """Schaltet aus: eine Nummer (id), alles einer Art (kind) oder alles. Gibt die beendeten Einträge zurück."""
        with self._lock:
            if which is not None:
                chosen = [self._rings[which]] if which in self._rings else []
            else:
                chosen = [r for r in self._rings.values() if kind in (None, r["kind"])]
                if kind is not None and not chosen:      # "Wecker aus", es läutet aber nur ein Timer: gemeint ist trotzdem "Ruhe"
                    chosen = list(self._rings.values())
            for ring in chosen:
                del self._rings[ring["id"]]
            if chosen:
                self.version += 1
        self._update_siren()
        return [dict(r) for r in chosen]

    def snooze(self, minutes=None, which=None, kind=None):
        """Schaltet aus und lässt es in `minutes` Minuten wieder läuten (über snooze_handler)."""
        try:
            minutes = int(minutes) if minutes is not None else self.snooze_minutes
        except (TypeError, ValueError):
            minutes = self.snooze_minutes
        minutes = max(1, min(MAX_SNOOZE_MINUTES, minutes))
        stopped = self.stop(which=which, kind=kind)
        handler = self.snooze_handler
        if handler is not None:
            for ring in stopped:
                try:
                    handler(ring, minutes)
                except Exception as error:
                    print(f"[WECKER] Schlummern fehlgeschlagen: {type(error).__name__}: {error}")
        return stopped, minutes

    def expire(self):
        """Beendet alles, was länger als max_minutes läutet; meldet es im Hintergrund. Gibt die Einträge zurück."""
        now = self.clock()
        with self._lock:
            limit = self.max_minutes * 60
            old = [r for r in self._rings.values() if now - r["started"] >= limit]
            for ring in old:
                del self._rings[ring["id"]]
            if old:
                self.version += 1
        if old:
            self._update_siren()
            for ring in old:
                submit_result({"type": "RINGING_EXPIRED",
                               "data": {"label": ring["label"], "kind": ring["kind"], "minutes": self.max_minutes}})
        return [dict(r) for r in old]

    def stop_all_for_shutdown(self):
        self.stop()


# --- Kurzbefehle ohne KI ------------------------------------------------------------

_STOP_VERBS = r"(?:aus|stop|stopp|stoppen|ausschalten|abschalten|abstellen|ausmachen|ausstellen|beenden|ruhe)"
_NOUN = r"(?P<noun>wecker|alarm|timer|klingeln|klingelton|alles)"
_STOP_PATTERNS = (
    re.compile(rf"(?:stop|stopp|aus|ruhe|genug|halt|sei still)"),
    re.compile(rf"(?:den |der |die |das )?{_NOUN}(?: bitte)? {_STOP_VERBS}"),
    re.compile(rf"(?:wecker|alarm|timer|klingeln)? ?(?:stoppen|ausschalten|abschalten|abstellen|ausmachen|ausstellen|beenden)(?: bitte)?"),
    re.compile(rf"(?:stell|mach|schalte?|schalt)(?: bitte)? (?:den |die |das )?{_NOUN}(?: bitte)? (?:aus|ab)"),
)
_SNOOZE_PATTERNS = (
    re.compile(r"(?:snooze|schlummern|schlummer|schlummermodus)(?: (?P<min>\d{1,2}) ?(?:min|minuten?))?"),
    re.compile(r"(?:noch|in) (?P<min>\d{1,2}) ?(?:min|minuten?)(?: noch)?(?: schlafen)?"),
    re.compile(r"(?:noch )?(?:ein|5) ?(?:paar )?(?:minuten|moment)(?: noch)?"),
)
_POLITE = re.compile(r"^(?:(?:hey|hi|ok|okay|jarvis|bitte)[ ,]+)+|(?:[ ,]+(?:bitte|jarvis|danke))+$")


def _normalize(message):
    text = message.casefold().replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss")
    text = re.sub(r"[^\w ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    previous = None
    while previous != text:                       # "hey jarvis bitte ..." -> Kern
        previous = text
        text = _POLITE.sub("", text).strip()
    return text


def stop_intent(message):
    """Erkennt "Wecker aus" & Co. -> ("stop", kind|None, None) / ("snooze", kind|None, Minuten|None) / None.

    Nur kurze Sätze, die GANZ so lauten. Alles andere geht den normalen Weg
    (Router), damit "stopp die Musik" oder ein langer Satz nichts Falsches ausschaltet.
    """
    if not isinstance(message, str) or len(message) > 60:
        return None
    text = _normalize(message)
    if not text or len(text.split()) > 6:
        return None
    for pattern in _SNOOZE_PATTERNS:
        found = pattern.fullmatch(text)
        if found:
            minutes = found.groupdict().get("min")
            return ("snooze", None, int(minutes) if minutes else None)
    for pattern in _STOP_PATTERNS:
        found = pattern.fullmatch(text)
        if found:
            noun = found.groupdict().get("noun") or text.split()[0]
            kind = "alarm" if noun in ("wecker", "alarm") else "timer" if noun == "timer" else None
            return ("stop", kind, None)
    return None


def handle_message(message, address, ringer=None):
    """Schneller Weg: Läutet etwas und die Nachricht ist ein Kurzbefehl -> Antworttext, sonst None."""
    ringer = ringer or default_ringer()
    if not ringer.is_ringing():
        return None
    intent = stop_intent(message)
    if intent is None:
        return None
    action, kind, minutes = intent
    if action == "snooze":
        stopped, minutes = ringer.snooze(minutes, kind=kind)
        if not stopped:
            return None
        return snooze_message(minutes, address)
    stopped = ringer.stop(kind=kind)
    if not stopped:
        return None
    return stop_message(stopped, address, ringer)


def snooze_message(minutes, address):
    return f"{address}, ich wecke dich in {minutes} {'Minute' if minutes == 1 else 'Minuten'} wieder."


def stop_message(stopped, address, ringer=None):
    ringer = ringer or default_ringer()
    names = ", ".join(r["label"] for r in stopped)
    kinds = {r["kind"] for r in stopped}
    text = f"{address}, {'Wecker' if kinds == {'alarm'} else 'Timer' if kinds == {'timer'} else 'Alles'} aus"
    text += f" ({names})." if len(stopped) > 1 or names not in ("Wecker", "Timer") else "."
    if any(r["kind"] == "alarm" and r["briefing"] for r in stopped) and ringer.briefing_provider:
        try:
            brief = ringer.briefing_provider()
        except Exception as error:
            print(f"[WECKER] Briefing fehlgeschlagen: {type(error).__name__}: {error}")
            brief = None
        if brief:
            text += " " + brief
    return text


# --- Standard-Ringer und Hintergrund-Takt ---------------------------------------------

_default_ringer = None
_ticker = None
_ticker_stop = threading.Event()


def default_ringer():
    global _default_ringer
    if _default_ringer is None:
        _default_ringer = Ringer()
    return _default_ringer


def set_default_ringer(ringer):
    global _default_ringer
    _default_ringer = ringer


def timer_finished(name, seconds):
    """Wird von timer.run_timer aufgerufen: läutet, wenn „Timer läuten“ an ist. True, wenn es läutet."""
    ringer = default_ringer()
    if not ringer.ring_timers:
        return False
    return ringer.start("timer", name, seconds=seconds) is not None


def start_ticker(interval=1.0):
    """Hintergrund-Thread: beendet zu lange Läutende. Ruft man ihn zweimal auf, läuft nur einer."""
    global _ticker
    if _ticker is not None and _ticker.is_alive():
        return _ticker
    _ticker_stop.clear()

    def loop():
        while not _ticker_stop.wait(interval):
            try:
                default_ringer().expire()
            except Exception as error:
                print(f"[WECKER] Fehler im Takt: {type(error).__name__}: {error}")

    _ticker = threading.Thread(target=loop, daemon=True, name="ringing-ticker")
    _ticker.start()
    return _ticker


def stop_ticker():
    _ticker_stop.set()
    default_ringer().stop_all_for_shutdown()
