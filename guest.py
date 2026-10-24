"""Gastmodus (Step 6b): Jarvis zum Ausprobieren, ohne Zugriff auf deinen Rechner.

Gestartet mit  py server.py --guest  (nicht aus der Weboberflaeche schaltbar).
Im Gastmodus gibt es KEIN Jarvis-Objekt mit Datenbank, Gedaechtnis, Projekten oder
Aktionen, sondern nur dieses hier. Es kann:

    - plaudern (ohne dein Gedaechtnis, ohne Projekte, nichts wird gespeichert)
    - Uhrzeit, Datum, Rechnen, Websuche (die vier harmlosen Aufgaben)

Alles andere (Programme, Dateien, Lautstaerke, Timer, Plaene, Befehle, Einstellungen,
Erinnerungen, Projekte) gibt es hier nicht: Nicht nur "verboten", sondern gar nicht
eingebaut. Der Server laesst im Gastmodus ausserdem nur drei Adressen zu (siehe server.py).

Bekannte Grenze (Mark 5): Alle Gaeste teilen sich eine Unterhaltung, solange der
Server laeuft. Pro Besucher getrennte Sitzungen gehoeren zum Login in Mark 5.
"""

import tempfile
import time
from collections import deque
from pathlib import Path

import cost_guard
import risk
from brain import build_input, respond_to_task
from config import MODEL
from conversation import Conversation
from personality import jarvis_personality
from router import route_message
from settings_manager import SettingsManager
from task_executor import execute_registered_task, prepare_registered_task
from task_registry import TaskRegistry
from tasks import register_all_tasks

# Nur diese vier Aufgaben, und nur, solange sie "safe" sind (wird beim Start geprueft)
GUEST_TASKS = ("GET_TIME", "GET_DATE", "CALCULATE", "SEARCH_WEB")

MAX_MESSAGE_CHARS = 500
RATE_LIMIT_MESSAGES = 30       # pro Zeitfenster, schuetzt deine OpenAI-Kosten
RATE_LIMIT_SECONDS = 600
GUEST_AI_CALLS_PER_DAY = 200   # eigener Zaehler (usage_guest.json), zehrt nicht am Limit des Besitzers

WELCOME = (
    "Willkommen im Gastmodus. Ich kann mich unterhalten, die Uhrzeit und das Datum "
    "nennen, rechnen und im Web suchen. Auf diesem Rechner kann ich nichts tun."
)
REFUSAL = (
    "Das ist im Gastmodus nicht möglich. Ich kann mich unterhalten, die Uhrzeit und das "
    "Datum nennen, rechnen und im Web suchen."
)

GUEST_NOTE = (
    "\n\nDu laeufst im Gastmodus. Du kannst nur plaudern, Fragen beantworten und (ueber "
    "feste Funktionen) Uhrzeit, Datum, Rechnen und Websuche. Du kannst nichts auf dem Computer "
    "tun: keine Programme starten, keine Dateien oeffnen, keine Timer, keine Lautstaerke, "
    "keine Erinnerungen speichern oder anzeigen, keine Projekte. Behaupte nie, du haettest "
    "so etwas getan; sage ehrlich, dass das im Gastmodus nicht geht. Du kennst keine Daten "
    "ueber den Besitzer dieses Computers."
)


def build_guest_registry():
    """Nur die Gast-Aufgaben. Sie muessen harmlos sein, sonst startet der Gastmodus nicht."""
    full = TaskRegistry()
    register_all_tasks(full)
    registry = TaskRegistry()

    for task_type in GUEST_TASKS:
        task = full.get(task_type)

        if task is None or risk.task_risk(task) != risk.SAFE:
            raise RuntimeError(f"Die Gast-Aufgabe {task_type} ist nicht harmlos oder fehlt.")

        registry.register(task)

    return registry


class GuestJarvis:
    guest = True

    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.conversation = Conversation()
        self.task_registry = build_guest_registry()
        self.hits = deque()
        # Eigene, wegwerfbare Einstellungen (Standardwerte): fremde Besucher
        # koennen nichts aendern und deine echte settings.json wird nie gelesen.
        self.settings_manager = SettingsManager(Path(tempfile.mkdtemp()) / "guest_settings.json")

    # ---- Schnittstelle fuer den Server

    def apply_settings(self):
        pass

    def check_background_results(self):
        # Meldungen aus deinem Hintergrund (z.B. ein Timer) gehen den Gast nichts an
        return []

    def memory_enabled(self):
        return False

    # ---- Nachrichten

    def _limited(self):
        now = self.clock()

        while self.hits and now - self.hits[0] > RATE_LIMIT_SECONDS:
            self.hits.popleft()

        if len(self.hits) >= RATE_LIMIT_MESSAGES:
            return True

        self.hits.append(now)
        return False

    def process_message(self, message):
        if not isinstance(message, str) or not message.strip():
            return {"status": "response", "content": "Bitte schreibe etwas."}

        message = message.strip()

        if len(message) > MAX_MESSAGE_CHARS:
            return {
                "status": "response",
                "content": f"Bitte fasse dich kürzer (höchstens {MAX_MESSAGE_CHARS} Zeichen).",
            }

        if self._limited():
            minutes = RATE_LIMIT_SECONDS // 60
            return {
                "status": "response",
                "content": f"Im Gastmodus sind höchstens {RATE_LIMIT_MESSAGES} Nachrichten "
                           f"in {minutes} Minuten möglich. Bitte versuche es gleich noch einmal.",
            }

        try:
            answer = self._answer(message)
        except cost_guard.LimitReached:
            return {
                "status": "response",
                "content": "Der Gastmodus ist für heute ausgelastet. Bitte versuche es morgen wieder.",
            }
        except Exception:
            return {
                "status": "response",
                "content": "Das hat gerade nicht geklappt. Bitte versuche es noch einmal.",
            }

        return {"status": "response", "content": answer}

    def _answer(self, message):
        route = route_message(self.client, message, self.task_registry)

        # Befehle (Projekte, Reset, Beenden ...) und Plaene gibt es im Gastmodus nicht
        if route["kind"] in ("COMMAND", "PLAN"):
            return REFUSAL

        if route["kind"] == "TASK":
            task_type = route["task_type"]

            if not isinstance(task_type, str) or task_type not in GUEST_TASKS:
                return REFUSAL

            prepared = prepare_registered_task(
                self.task_registry, route["task_type"], route["parameters"]
            )

            if prepared is None or risk.task_risk(prepared) != risk.SAFE:
                return REFUSAL

            task = execute_registered_task(
                self.task_registry, route["task_type"], route["parameters"]
            )
            answer = respond_to_task(self.client, message, task)
        else:
            self.conversation.add_message("user", message)
            response = self.client.responses.create(
                model=MODEL,
                instructions=jarvis_personality() + GUEST_NOTE,
                input=build_input(self.conversation),
            )
            self.conversation.messages.pop()      # unten einheitlich eintragen
            answer = response.output_text

        self.conversation.add_message("user", message)
        self.conversation.add_message("assistant", answer)
        del self.conversation.messages[:-40]      # nur die letzten Nachrichten behalten
        return answer
