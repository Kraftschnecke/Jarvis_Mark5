"""Timer mit Namen (Step 6b): starten, auflisten, einzeln abbrechen.

Jeder Timer ist ein Eintrag in einer Liste im Speicher (nicht in der Datenbank:
Beim Neustart des Servers sind alle Timer weg, wie bisher). Jeder wartet in einem
eigenen Thread auf ein Event: Läuft die Zeit ab, meldet er sich im Hintergrund,
wird er abgebrochen, endet er still.
"""

import math
import re
import threading
import time

import ringing
from background_tasks import submit_result
from untrusted import clean_text

MAX_TIMER_SECONDS = 24 * 3600
MAX_ACTIVE_TIMERS = 10
MAX_NAME_LENGTH = 40
DEFAULT_NAME = "Timer"


class TimerError(ValueError):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen darf."""


_lock = threading.Lock()
_timers = {}
_next_id = 1


class ActiveTimer:
    def __init__(self, timer_id, name, seconds):
        self.id = timer_id
        self.name = name
        self.seconds = seconds
        self.ends_at = time.time() + seconds
        self.cancelled = threading.Event()


def clean_name(name):
    """Kurzer, einzeiliger Name ohne Steuerzeichen. Leer oder kein Text -> "Timer"."""
    text = clean_text(name, 1000) if isinstance(name, str) else ""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:MAX_NAME_LENGTH].strip()
    return text or DEFAULT_NAME


def start_timer(seconds, name=None):
    global _next_id

    with _lock:
        if len(_timers) >= MAX_ACTIVE_TIMERS:
            raise TimerError(f"Es laufen schon {MAX_ACTIVE_TIMERS} Timer. Brich zuerst einen ab.")

        entry = ActiveTimer(_next_id, clean_name(name), seconds)
        _next_id += 1
        _timers[entry.id] = entry

    thread = threading.Thread(target=run_timer, args=(entry,), daemon=True)
    thread.start()
    return entry


def run_timer(entry):
    fired = not entry.cancelled.wait(entry.seconds)

    with _lock:
        _timers.pop(entry.id, None)

    if fired:
        ringing.timer_finished(entry.name, entry.seconds)      # läutet, bis man "Timer aus" sagt (wenn eingeschaltet)
        submit_result({
            "type": "TIMER_FINISHED",
            "data": {"seconds": entry.seconds, "name": entry.name},
        })


def list_timers():
    """Laufende Timer, der naechste zuerst: [{id, name, seconds, remaining}]."""
    now = time.time()

    with _lock:
        entries = sorted(_timers.values(), key=lambda t: t.ends_at)

    return [
        {"id": t.id, "name": t.name, "seconds": t.seconds,
         "remaining": max(0, int(math.ceil(t.ends_at - now)))}
        for t in entries
    ]


def cancel_timer_by_id(timer_id):
    """True, wenn es den Timer gab und er abgebrochen wurde."""
    with _lock:
        entry = _timers.pop(timer_id, None)

    if entry is None:
        return False

    entry.cancelled.set()
    return True


PENDING_SECONDS = 120
_pending = None          # {"ids": [...], "until": Zeitpunkt}: Rueckfrage "welchen meinst du?"

_ORDINALS = {
    "erste": 1, "ersten": 1, "erster": 1, "zweite": 2, "zweiten": 2, "zweiter": 2,
    "dritte": 3, "dritten": 3, "dritter": 3, "vierte": 4, "vierten": 4, "vierter": 4,
    "fuenfte": 5, "fünfte": 5, "fuenften": 5, "fünften": 5,
}
_FILLER = r"(?:(?:den|der|die|das|timer|nummer|nr\.?|no\.?|bitte|mal)\s+)*"


def describe(timers):
    """'1: Nudeln (noch 4:10), 2: Ei (noch 0:45)': die Nummer zaehlt vom kuerzesten."""
    parts = []

    for number, t in enumerate(timers, start=1):
        r = t["remaining"]
        shown = f"{r // 3600}:{r % 3600 // 60:02d}:{r % 60:02d}" if r >= 3600 else f"{r // 60}:{r % 60:02d}"
        parts.append(f"{number}: {t['name']} (noch {shown})")

    return ", ".join(parts)


def pick(selector, candidates):
    """Welche der Kandidaten (kuerzester zuerst) meint der Nutzer? Liste oder None.

    Gilt: Nummer ("2", "Nummer 2", "der zweite"), "den kuerzeren/kuerzesten/naechsten",
    "den laengeren/laengsten/letzten", "beide/alle". Alles andere: None.
    """
    if not isinstance(selector, str) or not candidates:
        return None

    text = selector.strip().casefold().rstrip(".!?, ")
    text = text.replace("ü", "ue").replace("ä", "ae").replace("ö", "oe")
    text = re.sub(r"\s+", " ", text)

    if re.fullmatch(_FILLER + r"(beide|alle)(?: timer)?", text):
        return list(candidates)

    if re.fullmatch(_FILLER + r"(kuerzer\w*|kuerzest\w*|naechst\w*)", text):
        return [candidates[0]]

    if re.fullmatch(_FILLER + r"(laenger\w*|laengst\w*|letzt\w*)", text):
        return [candidates[-1]]

    number = None
    found = re.fullmatch(_FILLER + r"(\d{1,2})\.?", text)

    if found:
        number = int(found.group(1))
    else:
        word = re.fullmatch(_FILLER + r"([a-z]+)", text)
        if word:
            number = {k.replace("ü", "ue"): v for k, v in _ORDINALS.items()}.get(word.group(1))

    if number is not None and 1 <= number <= len(candidates):
        return [candidates[number - 1]]

    return None


def _remember_choice(candidates):
    global _pending
    # Die Liste von jetzt gilt: Nummer 1 bleibt Nummer 1, auch wenn inzwischen einer ablaeuft
    _pending = {"timers": [dict(t) for t in candidates], "until": time.monotonic() + PENDING_SECONDS}


def clear_choice():
    global _pending
    _pending = None


def answer_pending(message):
    """Antwort auf "Welchen meinst du?". None, wenn nichts offen ist oder die Nachricht keine Auswahl ist.

    Die Rueckfrage gilt nur fuer die direkt folgende Nachricht (wie bei Aktionen):
    passt sie nicht, wird sie verworfen und die Nachricht normal behandelt.
    """
    global _pending
    pending, _pending = _pending, None

    if pending is None or time.monotonic() > pending["until"]:
        return None

    chosen = pick(message, pending["timers"])

    if chosen is None:
        return None

    names = []

    for t in chosen:
        if cancel_timer_by_id(t["id"]):
            names.append(t["name"])

    if not names:
        return "Dieser Timer ist schon abgelaufen."

    return "Timer abgebrochen: " + ", ".join(names) + "."


def _ask_which(candidates):
    _remember_choice(candidates)
    raise TimerError(
        f"Das ist nicht eindeutig. Es laufen: {describe(candidates)}. Welchen meinst du? "
        "Sag zum Beispiel „den kürzeren“ oder „Nummer 2“ (oder „beide“)."
    )


def cancel_timer(name=None):
    """Bricht Timer ab und gibt deren Namen zurueck (Text, mit Komma getrennt).

    "name" ist ein Name, eine Nummer (1 = laeuft am kuerzesten), "kuerzester",
    "laengster" oder "alle". Ohne Namen (oder "Timer") nur, wenn genau einer laeuft.
    Ist es nicht eindeutig, wird nichts abgebrochen: Jarvis fragt nach, und die
    naechste Nachricht ("2", "den kuerzeren") waehlt aus (answer_pending).
    """
    running = list_timers()

    if not running:
        raise TimerError("Es läuft kein Timer.")

    given = isinstance(name, str) and name.strip() != ""
    wanted = clean_name(name).casefold() if given else DEFAULT_NAME.casefold()
    unspecific = wanted == DEFAULT_NAME.casefold()

    if len(running) == 1 and unspecific:
        matches = running
    else:
        matches = [t for t in running if t["name"].casefold() == wanted]

        if not matches and given:
            matches = pick(name, running) or []

        if not matches:
            if not unspecific:
                raise TimerError(
                    f"Einen Timer mit diesem Namen gibt es nicht. Es laufen: {describe(running)}."
                )
            _ask_which(running)

        chosen_by_selector = given and not any(t["name"].casefold() == wanted for t in running)

        if len(matches) > 1 and not (chosen_by_selector and pick(name, running) == matches):
            _ask_which(matches)

    names = [t["name"] for t in matches if cancel_timer_by_id(t["id"])]
    return ", ".join(names)


def format_duration(seconds):
    """Dauer lesbar: 45 Sekunden, 5 Minuten, 1 Stunde 5 Minuten."""
    seconds = int(seconds)

    if seconds < 60:
        return f"{seconds} Sekunden"

    minutes, rest = divmod(seconds, 60)

    if minutes < 60:
        return f"{minutes} Minuten" + (f" {rest} Sekunden" if rest else "")

    hours, minutes = divmod(minutes, 60)
    text = f"{hours} Stunde" if hours == 1 else f"{hours} Stunden"
    return text + (f" {minutes} Minuten" if minutes else "")


# Das Modell antwortet oft in der Sprache des Nutzers ("Minuten"): beides gilt.
UNIT_SECONDS = {
    "seconds": 1, "second": 1, "sec": 1, "s": 1, "sekunden": 1, "sekunde": 1,
    "minutes": 60, "minute": 60, "min": 60, "minuten": 60,
    "hours": 3600, "hour": 3600, "h": 3600, "stunden": 3600, "stunde": 3600,
}


def convert_to_seconds(value, unit):
    """Dauer in Sekunden. Ungueltiges (Text, 0, negativ, mehr als 24 h) ist ein Fehler.

    Vorher wurde "5" mit "minutes" zu "5" * 60 (ein langer Text) und der Timer
    starb unbemerkt im Hintergrund.
    """
    if isinstance(unit, str) and unit.strip().lower() in UNIT_SECONDS:
        factor = UNIT_SECONDS[unit.strip().lower()]
    else:
        raise ValueError(f"Unknown time unit: {unit}")

    if isinstance(value, str):
        try:
            value = float(value.strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"Invalid timer duration: {value}") from None

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid timer duration: {value}")

    seconds = value * factor

    if seconds <= 0 or seconds > MAX_TIMER_SECONDS:
        raise ValueError("Der Timer muss zwischen 1 Sekunde und 24 Stunden liegen.")

    return seconds
