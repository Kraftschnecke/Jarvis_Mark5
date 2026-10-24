"""Gesprochener Tagesueberblick (Mark 5, Steps 2.11 und 2.12).

Kurz beim Ausschalten eines Weckers (Datum, Termine, Erinnerungen, Wetter) und ausfuehrlich als Tagesbriefing
auf Zuruf oder beim ersten Start des Tages (zusaetzlich Ziele, offene Timer und Schlagzeilen).
Alle Teile sind einzeln abgesichert: Fehlt das Wetter oder ist der Kalender kaputt, wird dieser Satz
ausgelassen, der Rest bleibt. Der Text wird hier selbst zusammengesetzt, ohne KI: Schlagzeilen sind fremde
Texte und koennen so nie als Anweisung bei einem Modell landen.
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path

from tools.tool_result import ToolResult
from untrusted import clean_text

CALENDAR_PREFIX = "⏰ "
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")
MAX_ITEMS = 5
MAX_TITLE = 60
MAX_HEADLINE = 110
_TAGS = re.compile(r"<[^>]*>")
MAX_HEADLINES = 3
STATE_FILE = Path(__file__).parent / "briefing_state.json"


def greeting(hour):
    if hour < 11:
        return "Guten Morgen"
    if hour < 18:
        return "Guten Tag"
    return "Guten Abend"


def _short(text):
    return " ".join(str(text).split())[:MAX_TITLE]


def _more(shown, total):
    return f" und {total - shown} weitere" if total > shown else ""


def events_sentence(events):
    """Normale Termine von heute (die ⏰-Erinnerungen im Kalender kommen getrennt)."""
    own = [e for e in events if not str(e.get("title", "")).startswith(CALENDAR_PREFIX)]
    if not own:
        return "Heute stehen keine Termine an."
    own.sort(key=lambda e: (e.get("time") or "", e.get("title", "")))
    parts = [f"um {e['time']} {_short(e['title'])}" if e.get("time") else f"ganztägig {_short(e['title'])}"
             for e in own[:MAX_ITEMS]]
    count = len(own)
    head = "Heute steht ein Termin an: " if count == 1 else f"Heute stehen {count} Termine an: "
    return head + ", ".join(parts) + _more(len(parts), count) + "."


def reminders_sentence(items, today):
    """Erinnerungen, die heute noch kommen: [{"text", "due"}]."""
    todays = sorted((r for r in items if r["due"][:10] == today), key=lambda r: r["due"])
    if not todays:
        return None
    parts = [f"um {r['due'][11:16]} {_short(r['text'])}" for r in todays[:MAX_ITEMS]]
    return "Erinnerungen für heute: " + ", ".join(parts) + _more(len(parts), len(todays)) + "."


def goals_sentence(goals):
    """Ziele von heute: [{"text", "done"}]. Ohne Ziele kein Satz."""
    goals = [g for g in goals if isinstance(g, dict) and str(g.get("text", "")).strip()]
    if not goals:
        return None
    open_goals = [g for g in goals if not g.get("done")]
    if not open_goals:
        return "Alle Ziele für heute sind schon erledigt." if len(goals) > 1 else "Dein Ziel für heute ist schon erledigt."
    parts = [_short(g["text"]) for g in open_goals[:MAX_ITEMS]]
    done = len(goals) - len(open_goals)
    head = "Offenes Ziel für heute: " if len(open_goals) == 1 else "Offene Ziele für heute: "
    tail = f" ({done} von {len(goals)} erledigt)" if done else ""
    return head + ", ".join(parts) + _more(len(parts), len(open_goals)) + tail + "."


def timers_sentence(timers):
    """Laufende Timer: [{"name", "remaining"}] (Sekunden)."""
    from timer import DEFAULT_NAME, format_duration
    timers = [t for t in timers if isinstance(t, dict)]
    if not timers:
        return None
    parts = []
    for t in timers[:MAX_ITEMS]:
        name = "" if t.get("name") in (None, "", DEFAULT_NAME) else _short(t["name"]) + ", "
        parts.append(f"{name}noch {format_duration(max(1, int(t.get('remaining', 0))))}")
    if len(timers) == 1:
        return "Ein Timer läuft: " + parts[0] + "."
    return f"{len(timers)} Timer laufen: " + "; ".join(parts) + _more(len(parts), len(timers)) + "."


def news_sentence(items):
    """Schlagzeilen: [{"source", "title"}]. Fremder Text: bereinigt und gekuerzt."""
    lines = []
    for item in items[:MAX_HEADLINES]:
        if not isinstance(item, dict):
            continue
        title = " ".join(_TAGS.sub("", clean_text(str(item.get("title", "")), MAX_HEADLINE * 2)).split())[:MAX_HEADLINE]
        if not title:
            continue
        source = " ".join(clean_text(str(item.get("source", "")), 30).split())
        lines.append(f"{source}: {title}" if source else title)
    if not lines:
        return None
    return "Schlagzeilen: " + "; ".join(lines) + "."


def build_briefing(now, address, events=None, reminder_items=None, weather=None, goals=None, timers=None, news=None):
    """Der gesprochene Text. Alle Quellen sind Funktionen (oder None = auslassen)."""
    today = now.strftime("%Y-%m-%d")
    parts = [f"{greeting(now.hour)}, {address}. Es ist {now.strftime('%H:%M')} Uhr, "
             f"{WEEKDAYS[now.weekday()]}, der {now.day}. {MONTHS[now.month - 1]}."]
    sources = ((events, lambda data: events_sentence(data)),
               (reminder_items, lambda data: reminders_sentence(data, today)),
               (weather, lambda data: data),
               (goals, goals_sentence),
               (timers, timers_sentence),
               (news, news_sentence))
    for source, say in sources:
        if source is None:
            continue
        try:
            sentence = say(source())
        except Exception as error:            # ein Teil darf den Rest nie verhindern
            print(f"[BRIEFING] Teil ausgelassen: {type(error).__name__}")
            continue
        if sentence:
            parts.append(sentence)
    return " ".join(parts)


class DailyMarker:
    """Merkt sich in einer kleinen Datei, an welchem Tag das Briefing beim Start schon kam (briefing_state.json).

    Mehrere offene Tabs oder ein Neustart am selben Tag loesen es so nicht noch einmal aus.
    """

    def __init__(self, path=STATE_FILE):
        self.path = Path(path)
        self.lock = threading.Lock()

    def last_day(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            day = data.get("last_day") if isinstance(data, dict) else None
            return day if isinstance(day, str) else None
        except (OSError, ValueError):
            return None

    def is_due(self, today):
        return self.last_day() != today

    def mark(self, today):
        handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"last_day": today}, stream)
            os.replace(temp, self.path)
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass


_default_marker = None
_provider = None


def default_marker():
    global _default_marker
    if _default_marker is None:
        _default_marker = DailyMarker()
    return _default_marker


def set_default_marker(marker):
    global _default_marker
    _default_marker = marker


def set_provider(provider):
    """Jarvis haengt hier die Funktion ein, die das Tagesbriefing zusammenbaut (wie beim Ringer)."""
    global _provider
    _provider = provider


def get_briefing():
    """Aktion get_briefing: das Tagesbriefing als ToolResult (Daten: briefing)."""
    if _provider is None:
        return ToolResult(success=False, error="Das Tagesbriefing ist gerade nicht verfügbar.")
    try:
        text = _provider()
    except Exception as error:
        return ToolResult(success=False, error=f"Das Briefing konnte nicht erstellt werden ({type(error).__name__}).")
    return ToolResult(success=True, data={"briefing": text})
