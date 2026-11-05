"""Fokus-Timer / Pomodoro (Mark 5, Step 2.13).

Eine Sitzung besteht aus mehreren Fokusphasen mit Pausen dazwischen (Standard: 25 Minuten Fokus, 5 Minuten Pause,
4 Runden; nach jeder 4. Runde eine lange Pause, wenn noch Runden folgen). Bei jedem Wechsel kommt eine Meldung im
Hintergrund (FOCUS_PHASE) und, wenn der Ton "Computer" eingestellt ist, ein kurzer Ton. Es laeuft hoechstens eine
Sitzung gleichzeitig. Sie liegt im Speicher: Nach einem Neustart des Servers ist sie weg (wie die Timer).

Die Zeit liest `clock`, Meldung und Ton kommen von aussen (`submit`, `chime`): So laeuft alles im Test ohne
echtes Warten. Ein Hintergrund-Thread ruft einmal pro Sekunde `tick()` auf.
"""

import math
import re
import threading
import time

import ringing
from background_tasks import submit_result
from untrusted import clean_text

DEFAULT_WORK = 25
DEFAULT_BREAK = 5
DEFAULT_LONG_BREAK = 15
DEFAULT_ROUNDS = 4
LONG_EVERY = 4                      # nach jeder 4. Fokusphase eine lange Pause (wenn noch etwas folgt)
LIMITS = {"work": (1, 120), "break": (1, 60), "long": (1, 60), "rounds": (1, 12)}
MAX_LABEL = 40
_NONE_WORDS = ("", "standard", "default", "none", "null", "-", "ohne", "keine", "keiner", "auto")
PHASE_NAMES = {"work": "Fokus", "break": "Pause", "long_break": "lange Pause"}


class FocusError(ValueError):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen darf."""


def parse_number(value, default, key, what):
    """Ganze Zahl im erlaubten Bereich. Nichts oder "standard" -> default."""
    low, high = LIMITS[key]
    if value is None or (isinstance(value, str) and value.strip().casefold() in _NONE_WORDS):
        return default
    if isinstance(value, bool):
        raise FocusError(f"{what}: Das habe ich nicht als Zahl verstanden.")
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError:
        raise FocusError(f"{what}: „{clean_text(str(value), 20)}“ habe ich nicht als Zahl verstanden.") from None
    if number != int(number):
        raise FocusError(f"{what}: bitte eine ganze Zahl.")
    number = int(number)
    if not low <= number <= high:
        raise FocusError(f"{what}: erlaubt sind {low} bis {high}.")
    return number


def clean_label(label):
    text = clean_text(label, 200) if isinstance(label, str) else ""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:MAX_LABEL].strip()
    return "" if text.casefold() in _NONE_WORDS else text


class FocusManager:
    def __init__(self, clock=time.time, submit=submit_result, chime=None, auto_thread=True):
        self.auto_thread = auto_thread
        self.clock = clock
        self.submit = submit
        self.chime = chime if chime is not None else (lambda: None)
        self.defaults = {"work": DEFAULT_WORK, "break": DEFAULT_BREAK, "long": DEFAULT_LONG_BREAK, "rounds": DEFAULT_ROUNDS}
        self._lock = threading.Lock()
        self._session = None
        self._thread = None
        self._quit = threading.Event()

    def configure(self, work=None, brk=None, long=None, rounds=None):
        """Neue Voreinstellungen (aus den Einstellungen). Ungueltiges wird ignoriert; eine laufende Sitzung bleibt."""
        for key, value in (("work", work), ("break", brk), ("long", long), ("rounds", rounds)):
            low, high = LIMITS[key]
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
                self.defaults[key] = value

    # --- Sitzung -------------------------------------------------------
    def start(self, label=None, work=None, brk=None, long=None, rounds=None):
        """Startet eine Sitzung (Werte als Zahl oder Text). Gibt den Zustand zurueck."""
        work = parse_number(work, self.defaults["work"], "work", "Fokusphase")
        brk = parse_number(brk, self.defaults["break"], "break", "Pause")
        long = parse_number(long, self.defaults["long"], "long", "Lange Pause")
        rounds = parse_number(rounds, self.defaults["rounds"], "rounds", "Runden")
        label = clean_label(label)
        with self._lock:
            if self._session is not None:
                s = self._session
                raise FocusError(f"Es läuft schon eine Fokus-Sitzung (Runde {s['round']} von {s['rounds']}). "
                                 "Beende sie zuerst mit „Fokus beenden“.")
            now = self.clock()
            self._session = {"label": label, "work": work, "break": brk, "long": long, "rounds": rounds,
                             "round": 1, "phase": "work", "ends": now + work * 60}
        if self.auto_thread:
            self.ensure_thread()
        return self.state()

    def stop(self):
        """Beendet die Sitzung. Gibt eine Zusammenfassung zurueck, None wenn keine lief."""
        with self._lock:
            s, self._session = self._session, None
        if s is None:
            return None
        done = s["round"] - 1 if s["phase"] == "work" else s["round"]
        return {"label": s["label"], "completed_rounds": done, "rounds": s["rounds"]}

    def state(self):
        with self._lock:
            s = self._session
            if s is None:
                return {"active": False}
            remaining = max(0, int(math.ceil(s["ends"] - self.clock())))
            return {"active": True, "phase": s["phase"], "phase_name": PHASE_NAMES[s["phase"]], "round": s["round"],
                    "rounds": s["rounds"], "remaining": remaining, "label": s["label"],
                    "work_minutes": s["work"], "break_minutes": s["break"], "long_break_minutes": s["long"]}

    def tick(self):
        """Wechselt die Phase, wenn ihre Zeit um ist. Gibt die Meldung zurueck (oder None)."""
        with self._lock:
            s = self._session
            if s is None:
                return None
            now = self.clock()
            if now < s["ends"]:
                return None
            event = {"label": s["label"], "rounds": s["rounds"]}
            if s["phase"] == "work":
                event.update(done="work", round=s["round"])
                if s["round"] >= s["rounds"]:
                    self._session = None
                    event.update(next=None, minutes=0, finished=True)
                else:
                    long_break = s["round"] % LONG_EVERY == 0
                    s["phase"] = "long_break" if long_break else "break"
                    minutes = s["long"] if long_break else s["break"]
                    s["ends"] = now + minutes * 60
                    event.update(next=s["phase"], minutes=minutes, finished=False)
            else:
                s["round"] += 1
                s["phase"] = "work"
                s["ends"] = now + s["work"] * 60
                event.update(done="break", round=s["round"], next="work", minutes=s["work"], finished=False)
        try:
            self.submit({"type": "FOCUS_PHASE", "data": event})
        finally:
            try:
                self.chime()
            except Exception as error:
                print(f"[FOKUS] Ton fehlgeschlagen: {type(error).__name__}")
        return event

    # --- Hintergrund-Thread --------------------------------------------
    def ensure_thread(self, interval=1.0):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._quit.clear()
            self._thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
            self._thread.start()

    def _run(self, interval):
        while not self._quit.wait(interval):
            try:
                self.tick()
            except Exception as error:               # der Takt darf nie sterben
                print(f"[FOKUS] Takt-Fehler: {type(error).__name__}")

    def shutdown(self):
        self._quit.set()


_default = None


def default_manager():
    global _default
    if _default is None:
        _default = FocusManager(chime=ringing.chime)
    return _default


def set_default_manager(manager):
    global _default
    _default = manager
