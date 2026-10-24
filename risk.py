"""Risikostufen fuer Aktionen (Mark 4, Step 4.2).

Jede Action hat genau eine Stufe:

    safe       -> Jarvis fuehrt sie sofort aus.
    confirm    -> Jarvis fragt zuerst; ausgefuehrt wird nur nach deinem "Ja".
    forbidden  -> Jarvis fuehrt sie nie aus, auch nicht auf Nachfrage.

Eine Task ist so riskant wie ihre riskanteste Action (START_PROGRAM = erst
find_program: safe, dann open_program: confirm -> die ganze Task: confirm).

Wichtig fuer die Sicherheit:
- Eine Action, die hier NICHT steht, ist forbidden. Wer eine neue Action
  baut, muss sie bewusst einstufen (Standard = verboten, nicht erlaubt).
- Die Stufe haengt nur von Action-Name und Parametern ab, nie von dem,
  was das Sprachmodell sagt ("das ist harmlos" zaehlt nicht).
- Durchgesetzt wird sie in task_executor.execute_task, also an der
  einzigen Stelle, an der Actions ausgefuehrt werden. Wer das umgehen will,
  muss den Executor umgehen.
"""

import re
from pathlib import Path

import reminders
from tools import page_tool
from tools.file_tool import BLOCKED_EXTENSIONS, URI_PATTERN

SAFE = "safe"
CONFIRM = "confirm"
FORBIDDEN = "forbidden"

_ORDER = {SAFE: 0, CONFIRM: 1, FORBIDDEN: 2}

ACTION_RISK = {
    # reine Auskunft / harmlos
    "get_current_time": SAFE,
    "get_current_date": SAFE,
    "calculate": SAFE,
    "convert": SAFE,              # rechnet nur; Waehrungskurse kommen von der EZB
    "get_system_info": SAFE,
    "get_running_programs": SAFE,
    "find_program": SAFE,
    "search_web": SAFE,
    "get_news": SAFE,             # liest nur oeffentliche Schlagzeilen aus festen Feeds
    "read_page": SAFE,            # Grundstufe; action_risk() hebt fremde Adressen auf CONFIRM (siehe unten)
    "translate": SAFE,            # reine Textaufbereitung, kein Netz; uebersetzt wird in der Antwort
    "wiki_lookup": SAFE,          # liest nur Wikipedia; der Suchbegriff geht an wikipedia.org
    "get_world_time": SAFE,       # rechnet die Zeit; nur der Ortsname geht an die Ortssuche (Open-Meteo)
    "get_weather": SAFE,          # liest nur oeffentliche Wetterdaten (Open-Meteo)
    "start_timer": SAFE,
    "set_reminder": SAFE,         # lokaler Eintrag (reminders.json) plus Kalender, wie ein Termin
    "list_reminders": SAFE,
    "cancel_reminder": SAFE,      # eine einzelne; "alle" hebt action_risk() auf CONFIRM
    "set_alarm": SAFE,            # lokaler Eintrag (reminders.json), kein Kalender
    "list_alarms": SAFE,
    "get_briefing": SAFE,         # liest nur eigene Daten (Kalender, Ziele, Timer) und ruft Wetter/News ab, wenn diese an sind
    "cancel_alarm": SAFE,         # einer; "alle" oder die ganze Serie hebt action_risk() auf CONFIRM
    "stop_ringing": SAFE,         # schaltet nur aus, was gerade laeutet
    "list_timers": SAFE,
    "cancel_timer": SAFE,        # bricht nur einen eigenen Timer ab
    # schreibt nur in widgets.json, auf der Seite per Klick wieder loeschbar
    "add_calendar_event": SAFE,
    "list_calendar_events": SAFE,
    # veraendert nur die Lautstaerke, sofort wieder korrigierbar
    "set_volume": SAFE,
    # greift auf deinen Rechner zu: erst fragen
    "open_file": CONFIRM,
    "open_program": CONFIRM,
}


def _open_file_is_forbidden(path):
    """Dateien, die ohnehin nie geoeffnet werden, werden auch nicht erfragt."""
    if not isinstance(path, str) or not path.strip():
        return False         # fehlender Pfad: der Fehler kommt vom Tool selbst

    path = path.strip()

    if URI_PATTERN.match(path) or path.startswith(("\\\\", "//")):
        return True

    extension = Path(path.rstrip(" .").replace("\\", "/").split("/")[-1].rstrip(" .")).suffix.lower()

    return extension in BLOCKED_EXTENSIONS


def _is_series_scope(value):
    return isinstance(value, str) and value.strip().casefold() in ("series", "serie", "all", "alle", "ganze serie")


def higher(a, b):
    """Die riskantere von zwei Stufen."""
    return a if _ORDER[a] >= _ORDER[b] else b


def action_risk(action):
    level = ACTION_RISK.get(action.name, FORBIDDEN)

    if action.name == "open_file" and _open_file_is_forbidden(
        action.parameters.get("path")
    ):
        return FORBIDDEN

    # Eine Seite lesen: nur Artikel aus der zuletzt genannten News-Liste direkt. Jede andere Adresse
    # (selbst getippt oder vom Modell vorgeschlagen) wird erst nach deinem "Ja" geoeffnet.
    if action.name in ("cancel_reminder", "cancel_alarm") and (
        reminders.is_all(action.parameters.get("which"))
        or _is_series_scope(action.parameters.get("scope"))
    ):
        return higher(level, CONFIRM)        # alle Erinnerungen oder eine ganze Serie auf einmal: erst fragen

    if action.name == "read_page" and not page_tool.is_known_address(action.parameters):
        return higher(level, CONFIRM)

    return level


def task_risk(task):
    """Hoechste Stufe aller Actions. Eine Task ohne Actions ist 'safe'."""
    level = SAFE

    for action in task.actions or []:
        level = higher(level, action_risk(action))

    return level


def describe_task(task):
    """Kurzer Text fuer die Rueckfrage: was soll passieren, womit?"""
    details = []

    for action in task.actions:
        for name, value in action.parameters.items():
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()

                if text:
                    details.append(text[:200])

    return task.goal, details
