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
import widgets
from tools import browser_tool, clipboard_tool, contacts_tool, mail_tool, note_tool, page_tool, screen_tool, system_tool
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
    "start_focus": SAFE,          # nur ein lokaler Zaehler im Speicher, keine Aussenwirkung
    "focus_status": SAFE,
    "stop_focus": SAFE,
    "read_document": SAFE,        # nur lesen, nur in den freigegebenen Ordnern (folders.resolve)
    "find_files": SAFE,           # nur lesen, nur in den freigegebenen Ordnern (folders.py walk)
    "list_folders": SAFE,         # zeigt nur die vom Nutzer eingetragene Liste
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
    # drueckt nur eine Medientaste (Play/Pause, Weiter, Zurueck), sofort wieder umkehrbar
    "media_control": SAFE,
    # Stumm, Desktop zeigen, Helligkeit: sofort umkehrbar, nichts geht verloren (Step 2.23). Nur "lock" fragt (siehe action_risk)
    "system_control": SAFE,
    # liest den Text der Zwischenablage (kann Privates enthalten, geht an das Sprachmodell): immer erst fragen (Step 2.24)
    "read_clipboard": CONFIRM,
    # nimmt ein Bild des Bildschirms auf, das an das Sprachmodell geht: bei JEDEM Mal erst fragen (Step 2.25)
    "describe_screen": CONFIRM,
    # oeffnet eine Adresse im Browser (nur https, Adresse wird in der Rueckfrage gezeigt): immer erst fragen (Step 2.26)
    "open_website": CONFIRM,
    # liest nur die eigenen frueheren Gespraeche in der Datenbank (nichts wird geaendert) (Step 2.27)
    "search_history": SAFE,
    "goal_overview": SAFE,
    "add_to_list": SAFE,          # lokale Liste in widgets.json, sichtbar und aenderbar im Widget
    "show_list": SAFE,
    "remove_from_list": SAFE,     # ein einzelner Eintrag; ganze Listen loescht nur die Seite
    # liest Absender/Betreff aus einem privaten Postfach (nur lesen): immer erst fragen
    "check_mail": CONFIRM,
    # liest Kontaktdaten (Namen, Nummern, Geburtstage) aus dem Apple-Adressbuch, nur lesen; die Antwort geht an das Sprachmodell: immer erst fragen
    "find_contact": CONFIRM,
    "upcoming_birthdays": CONFIRM,
    "read_mail": CONFIRM,         # liest den Text einer Mail (privat, geht an das Sprachmodell): immer erst fragen
    # greift auf deinen Rechner zu: erst fragen
    "write_note": CONFIRM,        # schreibt eine Datei: immer erst fragen (Vorschau), nur .txt/.md, nie ueberschreiben
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


def _writes_to_apple(parameters):
    """True, wenn dieser Termin (ohne Wiederholung) in den Apple-Kalender gehen wuerde."""
    if not widgets.default_store().remote_write_enabled():
        return False
    repeat = parameters.get("repeat")
    return not (isinstance(repeat, str) and repeat.strip() and repeat.strip().lower() not in ("none", "null", "leer", "-"))


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

    # Ein einfacher Termin per Chat landet im echten Apple-Kalender (und am Handy): erst fragen. Serien bleiben lokal.
    if action.name == "add_calendar_event" and _writes_to_apple(action.parameters):
        return higher(level, CONFIRM)

    # Den Bildschirm sperren unterbricht deine Arbeit und braucht dein Passwort zum Entsperren: erst fragen
    if action.name == "system_control" and system_tool.normalize_command(action.parameters.get("command")) == "lock":
        return higher(level, CONFIRM)

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
    goal = task.goal

    for action in task.actions:
        if action.name == "write_note":
            goal = "Notiz in eine Datei schreiben"               # kurz: das lange Aufgabenziel enthaelt Beispielsaetze fuer den Router
            p = action.parameters
            details += note_tool.default_writer().describe(p.get("filename", ""), p.get("content", ""), p.get("folder", ""), p.get("mode", "new"))
            continue

        if action.name == "check_mail":
            goal = "E-Mail-Betreffzeilen abrufen"
            details += mail_tool.describe(action.parameters.get("account", ""))
            continue

        if action.name == "add_calendar_event" and _writes_to_apple(action.parameters):
            goal = "Termin in den Apple-Kalender eintragen"
            p = action.parameters
            when = " ".join(str(p.get(k) or "").strip() for k in ("date", "time") if isinstance(p.get(k), str) and p.get(k).strip())
            details += [str(p.get("title") or "")[:100], when,
                        f"Kalender: {widgets.default_store().remote.write_name} (erscheint auch auf deinem Handy)"]
            continue

        if action.name == "open_website":
            goal = "Im Browser öffnen"
            details += browser_tool.describe(action.parameters.get("url", ""), action.parameters.get("query", ""))
            continue

        if action.name == "describe_screen":
            goal = "Bildschirm ansehen"
            details += screen_tool.describe(action.parameters.get("question", ""))
            continue

        if action.name == "read_clipboard":
            goal = "Zwischenablage lesen"
            details += clipboard_tool.describe(action.parameters.get("question", ""))
            continue

        if action.name == "system_control":
            goal = "Rechnerbefehl ausführen"
            details += system_tool.describe(action.parameters.get("command", ""), action.parameters.get("value", ""))
            continue

        if action.name == "find_contact":
            goal = "Kontaktdaten aus dem Adressbuch abrufen"
            details += contacts_tool.describe_find(action.parameters.get("name", ""), action.parameters.get("topic", ""))
            continue

        if action.name == "upcoming_birthdays":
            goal = "Geburtstage aus dem Adressbuch abrufen"
            details += contacts_tool.describe_birthdays(action.parameters.get("days", ""))
            continue

        if action.name == "read_mail":
            goal = "E-Mail lesen und zusammenfassen"
            details += mail_tool.describe_read(action.parameters.get("which", ""))
            continue

        for name, value in action.parameters.items():
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()

                if text:
                    details.append(text[:200])

    return goal, details
