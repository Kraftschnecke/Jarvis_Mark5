"""Kurzer gesprochener Tagesueberblick (Mark 5, Step 2.11): Datum, Termine, Erinnerungen, Wetter.

Wird beim Ausschalten eines Weckers vorgelesen (wenn der Wecker "briefing" hat) und ist die Grundlage fuer
das spaetere Tagesbriefing (2.12). Alle Teile sind einzeln abgesichert: Fehlt das Wetter oder ist der Kalender
kaputt, wird dieser Satz ausgelassen, der Rest bleibt.
"""

from datetime import datetime

CALENDAR_PREFIX = "⏰ "
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")
MAX_ITEMS = 5
MAX_TITLE = 60


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


def build_briefing(now, address, events=None, reminder_items=None, weather=None):
    """Der gesprochene Text. events/reminder_items/weather sind Funktionen (oder None = auslassen)."""
    today = now.strftime("%Y-%m-%d")
    parts = [f"{greeting(now.hour)}, {address}. Es ist {now.strftime('%H:%M')} Uhr, "
             f"{WEEKDAYS[now.weekday()]}, der {now.day}. {MONTHS[now.month - 1]}."]
    sources = ((events, lambda data: events_sentence(data)),
               (reminder_items, lambda data: reminders_sentence(data, today)),
               (weather, lambda data: data))
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
