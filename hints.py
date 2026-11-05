"""Proaktive Hinweise (Mark 5, Step 2.29): nur Anzeige im Chat, Jarvis fuehrt dabei NIE etwas aus.

Zwei Arten, beide aus (opt-in) und einzeln einschaltbar:
  - Termin in X Minuten (Kalender, auch Apple; Erinnerungen und Wecker melden sich selbst und zaehlen hier nicht),
  - Wetter fuer morgen (ab einer Abendstunde, einmal pro Tag, am Heimatort).
Abgelaufene Timer meldet schon der Ringer (Step 2.9): sie brauchen hier keinen zweiten Hinweis.
Die Texte werden ohne KI zusammengesetzt; Termintitel (bei Apple fremder Text) werden bereinigt und gekuerzt.
Jeder Hinweis kommt hoechstens einmal: die Datei hints_state.json merkt sich die schon gezeigten Hinweise des Tages.
"""

import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from untrusted import clean_text

CALENDAR_PREFIX = "⏰ "
MAX_TITLE = 60
_TAGS = re.compile(r"<[^>]*>")
STATE_FILE = Path(__file__).parent / "hints_state.json"


def _title(text):
    return " ".join(_TAGS.sub("", clean_text(str(text), MAX_TITLE * 2)).split())[:MAX_TITLE]


def appointment_hints(events, now, minutes):
    """Termine, die in hoechstens `minutes` Minuten (und noch nicht vorbei) beginnen: [{"id", "kind", "text"}]."""
    found = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        at, title = event.get("time"), _title(event.get("title", ""))
        if not title or str(event.get("title", "")).startswith(CALENDAR_PREFIX):
            continue
        try:                                                      # ohne Uhrzeit (ganztaegig) oder Datum geht das schief: auslassen
            start = datetime.strptime(f"{event.get('date')} {at}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        left = (start - now).total_seconds() / 60
        if left <= 0 or left > minutes:
            continue
        wait = max(1, int(left + 0.999))                          # aufgerundet: "in 1 Minute" statt "in 0"
        found.append((start, {"id": f"appt:{event['date']}:{at}:{title}", "kind": "appointment",
                              "text": f"In {wait} {'Minute' if wait == 1 else 'Minuten'}: {title} um {at} Uhr."}))
    return [hint for _, hint in sorted(found, key=lambda pair: pair[0])]


def weather_hint(data, tomorrow):
    """Der Satz zum Wetter von morgen aus den Daten von WeatherService.get_weather, oder None ohne brauchbare Angaben."""
    if not isinstance(data, dict):
        return None
    place = str(data.get("place", "")).split(",")[0].strip()
    parts = []
    if data.get("condition"):
        parts.append(str(data["condition"]))
    low, high = data.get("low"), data.get("high")
    if low is not None and high is not None:
        parts.append(f"{low} bis {high} °C")
    elif high is not None:
        parts.append(f"bis {high} °C")
    rain = data.get("rain_chance_percent")
    if isinstance(rain, (int, float)) and not isinstance(rain, bool) and rain >= 30:
        parts.append(f"Regenwahrscheinlichkeit {rain} %")
    if not parts:
        return None
    where = f" in {place}" if place else ""
    return {"id": f"weather:{tomorrow}", "kind": "weather", "text": f"Morgen{where}: " + ", ".join(parts) + "."}


class HintLog:
    """Merkt sich in hints_state.json, welche Hinweise heute schon kamen (ein neuer Tag beginnt leer)."""

    def __init__(self, path=STATE_FILE):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _read(self, day):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, dict) or data.get("day") != day or not isinstance(data.get("shown"), list):
            return []
        return [i for i in data["shown"] if isinstance(i, str)]

    def seen(self, hint_id, day):
        return hint_id in self._read(day)

    def mark(self, hint_id, day):
        shown = self._read(day)
        if hint_id not in shown:
            shown.append(hint_id)
        handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"day": day, "shown": shown[-200:]}, stream, ensure_ascii=False)
            os.replace(temp, self.path)
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass


_default_log = None


def default_log():
    global _default_log
    if _default_log is None:
        _default_log = HintLog()
    return _default_log


def set_default_log(log):
    """Nur fuer Tests."""
    global _default_log
    _default_log = log
