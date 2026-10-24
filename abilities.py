"""Schalter fuer Faehigkeiten (Mark 5, Step 1.3).

Jede Aufgabe (Task) gehoert entweder zu den Grundfaehigkeiten (CORE_TASKS, immer an)
oder zu genau einer schaltbaren Faehigkeit (ABILITIES). Der Schalter steht in den
Einstellungen unter "Abilities" (settings.json, Kategorie "abilities").

Ist eine Faehigkeit aus, dann
- bekommt der Router ihre Aufgaben nicht als Auswahl (er weiss nur: "ausgeschaltet"),
- steht sie nicht unter "Was kannst du?" (dort steht, was ausgeschaltet ist),
- koennen Plaene sie nicht enthalten und wartende Rueckfragen sie nicht mehr ausfuehren,
- sagt Jarvis bei einem Versuch ehrlich, dass sie ausgeschaltet ist.

Neue Faehigkeit: hier eintragen (siehe DESIGN_ABILITIES.md). Kostet sie Geld oder beruehrt
sie Privates, dann ``default=False``. Der Vertragstest prueft, dass keine Aufgabe vergessen wird.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ability:
    id: str
    label: str
    description: str
    tasks: tuple
    default: bool = True


# Immer an: harmlos, ohne Netz, ohne Kosten
CORE_TASKS = ("GET_TIME", "GET_DATE", "CALCULATE", "GET_SYSTEM_INFO", "STOP_RINGING")

ABILITIES = (
    Ability("web_search", "Websuche",
            "Im Web suchen (Brave Search, braucht BRAVE_API_KEY). Der Suchbegriff geht an den Suchdienst.",
            ("SEARCH_WEB",)),
    Ability("weather", "Wetter",
            "Wetter und Vorhersage für einen Ort (Open-Meteo, kostenlos, ohne Schlüssel). Der Ortsname geht an open-meteo.com, ebenso beim Start dein Heimatort.",
            ("GET_WEATHER",)),
    Ability("news", "News",
            "Schlagzeilen aus den Quellen, die du unter News einschaltest (RSS, kostenlos, ohne Schlüssel). Es werden nur diese festen Seiten abgerufen.",
            ("GET_NEWS",)),
    Ability("translate", "Übersetzer",
            "Texte und Wendungen übersetzen. Die KI übersetzt in der Antwort (zählt zum KI-Tageslimit); der Text geht nur an OpenAI, wie jede Anfrage.",
            ("TRANSLATE",)),
    Ability("wikipedia", "Wikipedia",
            "Personen, Orte und Begriffe in Wikipedia nachschlagen (kostenlos, ohne Schlüssel). Der Suchbegriff geht an wikipedia.org; Antworten nennen die Quelle.",
            ("WIKI_LOOKUP",)),
    Ability("worldtime", "Weltuhr",
            "Uhrzeit und Zeitunterschied an anderen Orten der Welt. Die Zeit rechnet Jarvis selbst; den Ortsnamen sucht Open-Meteo (kostenlos, ohne Schlüssel).",
            ("GET_WORLD_TIME",)),
    Ability("convert", "Umrechnen",
            "Einheiten umrechnen (Länge, Gewicht, Temperatur, …) und Währungen mit den EZB-Referenzkursen. Einheiten rechnet Jarvis offline, für Währungen ruft er einmal pro Stunde die Kurstabelle der EZB ab.",
            ("CONVERT",)),
    Ability("pages", "Webseiten lesen",
            "Den Text eines Artikels oder einer Webseite abrufen und zusammenfassen. Artikel aus der News-Liste direkt, jeden anderen Link erst nach Rückfrage. Die Adresse geht an die jeweilige Webseite.",
            ("READ_PAGE",)),
    Ability("timers", "Timer", "Timer stellen, anzeigen und abbrechen.",
            ("START_TIMER", "LIST_TIMERS", "CANCEL_TIMER")),
    Ability("reminders", "Erinnerungen",
            "Erinnerungen zu einer Uhrzeit stellen (überstehen einen Neustart, stehen bis zum Ablauf im Kalender), anzeigen und löschen (reminders.json).",
            ("SET_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER")),
    Ability("alarm", "Wecker",
            "Wecker stellen (auch täglich oder werktags), anzeigen und löschen. Er läutet, bis du „Jarvis, Wecker aus“ sagst, und liest auf Wunsch kurz Termine und Wetter vor (reminders.json).",
            ("SET_ALARM", "LIST_ALARMS", "CANCEL_ALARM")),
    Ability("calendar", "Kalender-Termine", "Termine in den Kalender eintragen und vorlesen (widgets.json).",
            ("ADD_CALENDAR_EVENT", "LIST_CALENDAR_EVENTS")),
    Ability("volume", "Lautstärke", "Die Systemlautstärke einstellen.", ("SET_VOLUME",)),
    Ability("programs", "Programme",
            "Programme aus programs.json starten (mit Rückfrage) und laufende Programme zeigen.",
            ("FIND_PROGRAM", "START_PROGRAM", "GET_RUNNING_PROGRAMS")),
    Ability("files", "Dateien öffnen", "Dateien auf dem Computer öffnen (mit Rückfrage).", ("OPEN_FILE",)),
)

_BY_ID = {ability.id: ability for ability in ABILITIES}
_BY_TASK = {task: ability for ability in ABILITIES for task in ability.tasks}


def default_settings():
    """Die Voreinstellung fuer settings.json: {"web_search": True, ...}."""
    return {ability.id: ability.default for ability in ABILITIES}


def ability_of(task_type):
    """Die schaltbare Faehigkeit einer Aufgabe, oder None (Grundfaehigkeit / unbekannt)."""
    return _BY_TASK.get(task_type)


def is_known(ability_id):
    return ability_id in _BY_ID


def task_enabled(task_type, settings_manager):
    """Darf diese Aufgabe gerade ausgefuehrt werden? Grundfaehigkeiten immer; unbekannte Aufgaben nie hier entscheiden."""
    ability = _BY_TASK.get(task_type)
    if ability is None:
        return True
    return settings_manager.get("abilities", ability.id, ability.default) is True


def describe_all(settings_manager):
    """Fuer die Weboberflaeche: Liste aller schaltbaren Faehigkeiten mit aktuellem Stand."""
    return [
        {
            "id": ability.id,
            "label": ability.label,
            "description": ability.description,
            "enabled": settings_manager.get("abilities", ability.id, ability.default) is True,
        }
        for ability in ABILITIES
    ]
