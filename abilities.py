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
    Ability("briefing", "Tagesbriefing",
            "Kurzer Tagesüberblick auf Zuruf („Briefing“): Datum, Termine, Erinnerungen, Wetter, Ziele, offene Timer und Schlagzeilen. Wetter und News nur, wenn diese Fähigkeiten an sind (Open-Meteo und die News-Seiten). Der Text wird ohne KI zusammengesetzt. Auf Wunsch kommt er beim ersten Start des Tages von selbst (Seite Briefing).",
            ("GET_BRIEFING",)),
    Ability("focus", "Fokus-Timer",
            "Pomodoro-Sitzungen: Fokusphasen und Pausen im Wechsel (Standard 25/5 Minuten, 4 Runden, nach der 4. Runde lange Pause) mit Meldung und kurzem Ton bei jedem Wechsel. Die Sitzung liegt im Speicher und ist nach einem Neustart weg.",
            ("START_FOCUS", "FOCUS_STATUS", "STOP_FOCUS")),
    Ability("calendar", "Kalender-Termine", "Termine in den Kalender eintragen und vorlesen (widgets.json). Mit Apple-Kalender in der .env (CALDAV_…) zeigt Jarvis auch dessen Termine und schreibt einfache Termine nach Rückfrage in den einen Schreib-Kalender (auch am Handy).",
            ("ADD_CALENDAR_EVENT", "LIST_CALENDAR_EVENTS")),
    Ability("volume", "Lautstärke", "Die Systemlautstärke einstellen.", ("SET_VOLUME",)),
    Ability("music", "Musiksteuerung",
            "Musik mit den Windows-Medientasten steuern: abspielen/pausieren (eine Taste), nächster und vorheriger Titel. Wirkt auf den Player, den Windows gerade führt (Spotify, Browser …). Keine Konten, kein Netz; einen bestimmten Titel starten kann Jarvis damit nicht.",
            ("MEDIA_CONTROL",)),
    Ability("system", "Rechner-Grundfunktionen",
            "Ton stumm schalten, Bildschirm sperren, alle Fenster minimieren und die Helligkeit ändern (Helligkeit nur bei Bildschirmen, die Windows dimmen kann, meist Laptops). "
            "Nur das Sperren fragt vorher nach. Keine Konten, kein Netz; Jarvis schließt oder löscht dabei nichts.",
            ("SYSTEM_CONTROL",)),
    Ability("history", "Frühere Gespräche durchsuchen",
            "In deinen früheren Gesprächen mit Jarvis nachschlagen („Worüber haben wir letzte Woche beim Projekt X gesprochen?“, „Was hatte ich zu … gefragt?“). "
            "Nur lesen, nur in Jarvis' eigener Datenbank; es wird nichts geändert. Die gefundenen Ausschnitte gehen wie jede Antwort an OpenAI. Nachrichten der letzten Minute werden übersprungen.",
            ("SEARCH_HISTORY",)),
    Ability("goals", "Ziele und Gewohnheiten",
            "Fragen zu deinen Tageszielen beantworten: was heute offen ist, wie lang die Serie eines täglichen Ziels ist („Wie lange gehe ich schon ins Fitnessstudio?“) und wie die letzte Woche war. "
            "Nur lesen, aus dem Ziele-Widget (widgets.json); Ziele anlegen und abhaken machst du in der Seitenleiste. Die Abendfrage („Das ist heute noch offen“) schaltest du unter Goals ein.",
            ("GOAL_OVERVIEW",)),
    Ability("lists", "Einkaufs- und Packlisten",
            "Listen führen: „Setz Milch und Eier auf die Einkaufsliste“, „Was steht auf der Packliste?“, „Hak Milch ab“. Die Listen liegen lokal in widgets.json und sind im Widget Lists der Seitenleiste sichtbar und dort von Hand änderbar. "
            "Jarvis kann Einträge setzen, zeigen, abhaken und streichen; ganze Listen löschen geht nur in der Seitenleiste.",
            ("ADD_TO_LIST", "SHOW_LIST", "REMOVE_FROM_LIST")),
    Ability("browser", "Webseite im Browser öffnen",
            "Auf Wunsch eine Webseite oder eine Suche in einem neuen Tab deines Standardbrowsers öffnen. Nur https-Adressen (http wird zu https), keine anderen Adressarten, "
            "keine Rechnernamen, Zahlen- oder Heimnetz-Adressen. Immer erst nach deinem Ja, mit Anzeige der Adresse. Jarvis liest dabei nichts von der Seite und gibt nichts ein.",
            ("OPEN_WEBSITE",)),
    Ability("screen", "Bildschirm ansehen",
            "Auf Wunsch einmal ein Bild deines Hauptbildschirms aufnehmen und beschreiben oder eine Frage dazu beantworten (Was bedeutet diese Fehlermeldung?). "
            "Bei jedem Mal erst nach deinem Ja. Das Bild geht nur zum Antworten an OpenAI und wird nirgends gespeichert; alles, was gerade sichtbar ist, ist darin. "
            "Jarvis sieht nur zu: kein Klicken, kein Tippen, keine Dauerbeobachtung.",
            ("DESCRIBE_SCREEN",), default=False),
    Ability("clipboard", "Zwischenablage",
            "Den Text lesen, den du gerade kopiert hast, und ihn zusammenfassen, übersetzen oder eine Frage dazu beantworten. "
            "Nur lesen und nur Text (nichts in die Zwischenablage schreiben, keine Bilder oder Dateien). Immer erst nach deinem Ja; die Rückfrage zeigt den Inhalt nicht. "
            "Der Text (höchstens 9 000 Zeichen) geht wie jede Antwort an OpenAI und wird nicht gespeichert.",
            ("READ_CLIPBOARD",), default=False),
    Ability("mail", "E-Mail lesen",
            "Mails auflisten (Absender, Betreff, Datum; neue oder die letzten bis zu 20) und auf Wunsch den Text einer gezeigten Mail zusammenfassen, aus einem Postfach per IMAP, das nur du in der .env einträgst. "
            "Nur lesen: nichts senden, antworten, löschen oder als gelesen markieren, keine Anhänge. Immer erst nach deinem Ja. "
            "Absender, Betreff und der Text einer ausgewählten Mail gehen wie jede Antwort an OpenAI.",
            ("CHECK_MAIL", "READ_MAIL"), default=False),
    Ability("contacts", "Kontakte & Geburtstage",
            "Zu einem Kontakt aus deinem Apple-Adressbuch den Geburtstag, die Telefonnummer oder die E-Mail-Adresse nennen und die nächsten Geburtstage auflisten. "
            "Nur lesen (dieselben CALDAV_…-Zugangsdaten in der .env wie beim Kalender): nichts anlegen, ändern oder löschen. Immer erst nach deinem Ja. "
            "Nur das Gefragte (Name, Geburtstag, Nummer oder Adresse der Treffer) geht wie jede Antwort an OpenAI.",
            ("FIND_CONTACT", "UPCOMING_BIRTHDAYS"), default=False),
    Ability("programs", "Programme",
            "Programme aus programs.json starten (mit Rückfrage) und laufende Programme zeigen.",
            ("FIND_PROGRAM", "START_PROGRAM", "GET_RUNNING_PROGRAMS")),
    Ability("documents", "Dokumente",
            "Freigegebene Ordner anzeigen und Dateien darin nach Name oder Inhalt finden. Jarvis liest nur in Ordnern, die du selbst in den Einstellungen unter „Folders“ einträgst (folders.json); Dateien darin lesen (txt, md, csv, html, docx, pdf) und zusammenfassen. Per Chat lässt sich kein Ordner freigeben. Dateinamen, Textauszüge und der gelesene Text gehen wie jede Antwort an OpenAI.",
            ("LIST_FOLDERS", "FIND_FILES", "READ_DOCUMENT")),
    Ability("notes", "Notizen speichern",
            "Notizen als .txt- oder .md-Datei in einem freigegebenen Ordner speichern. Immer erst nach deinem Ja, mit Vorschau; "
            "nie ein bestehendes Dokument überschreiben (stattdessen „Name (2).txt“); nur Textdateien, nie Programme.",
            ("WRITE_NOTE",)),
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
