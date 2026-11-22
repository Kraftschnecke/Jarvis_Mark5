"""Tester-Bereich (Mark 5, Schritt C2): Jarvis fuer einen Gast, mit eigenen Daten und ohne Zugriff auf den Rechner.

Siehe DESIGN_CLIENT.md, Abschnitt 3. Gebaut wie guest.py: Es gibt hier KEIN Gedaechtnis, KEINE Projekte, KEINE
Datenbank, keinen Workspace und kein Jarvis-Objekt (der Test sperrt diese Importe). Alles, was der Gast speichert,
liegt in seinem Ordner profiles/<id>/:

    conversation.json   seine Unterhaltung (die letzten 40 Nachrichten)
    widgets.json        Notizen, Listen, Ziele, Kalender
    reminders.json      Erinnerungen
    usage.json          Zaehler seiner KI-Aufrufe pro Tag

Wie es getrennt bleibt: Die Aufgaben greifen ueber widgets.default_store() / reminders.default_store() auf "den"
Speicher zu. Fuer die Dauer einer Gast-Nachricht zeigen diese Funktionen in DIESEM Thread auf den Speicher des Gastes
(use_store). Alle anderen Threads, also der PC des Besitzers, sehen unveraendert ihre eigenen Dateien.
"""
import hashlib
import json
import os
import tempfile
import threading
import time
from collections import deque
from contextlib import ExitStack
from datetime import date, datetime
from pathlib import Path

import abilities
import action_log
import cost_guard
import remote_policy
import reminders
import risk
import widgets
from brain import build_input, respond_to_task
from config import MODEL
from conversation import Conversation
from personality import jarvis_personality
from profiles import is_profile_id
from router import route_message
from task_executor import execute_registered_task, prepare_registered_task
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools import weather_tool

# Was ein Gast kann: Auskunft und seine eigenen Alltags-Daten. Nichts, was am PC des Besitzers klingelt oder ihn veraendert.
TESTER_ABILITIES = ("web_search", "weather", "news", "translate", "wikipedia", "worldtime", "convert",
                    "reminders", "calendar", "lists", "goals")
TESTER_CORE_TASKS = ("GET_TIME", "GET_DATE", "CALCULATE")

NO_ACTIVE = {"project_id": None, "conversation_id": None}
MAX_MESSAGES = 40
MAX_FEED = 100
MAX_CONTENT = 4000
RATE_WINDOW = 600

REFUSAL = "Das geht im Testbereich nicht. Ich kann plaudern, Auskunft geben und deine eigenen Listen, Ziele, Termine und Erinnerungen führen."

TESTER_NOTE = (
    "\n\nDu laeufst im Testbereich fuer einen Gast. Du kannst plaudern, Fragen beantworten und (ueber feste "
    "Funktionen) Auskunft geben sowie die eigenen Listen, Ziele, Kalender-Eintraege und Erinnerungen dieses Gastes "
    "fuehren. Du kannst nichts auf dem Computer tun: keine Programme, keine Dateien, keine Lautstaerke, keine Timer "
    "oder Wecker, keine Projekte. Behaupte nie, du haettest so etwas getan; sage ehrlich, dass das im Testbereich "
    "nicht geht. Du hast kein Gedaechtnis und kennst keine Daten ueber den Besitzer dieses Computers."
)


def tester_task_types():
    """Alle Aufgaben, die der Testbereich kennt."""
    by_id = {ability.id: ability for ability in abilities.ABILITIES}
    types = set(TESTER_CORE_TASKS)
    for ability_id in TESTER_ABILITIES:
        types.update(by_id[ability_id].tasks)
    return frozenset(types)


def build_tester_registry():
    """Nur die erlaubten Aufgaben sind registriert. Die anderen sind nicht gesperrt, sie sind gar nicht vorhanden."""
    full = TaskRegistry()
    register_all_tasks(full)
    registry = TaskRegistry()
    for task_type in sorted(tester_task_types()):
        task = full.get(task_type)
        if task is None:
            raise RuntimeError(f"Die Test-Aufgabe {task_type} gibt es nicht.")
        registry.register(task)
    return registry


class TesterJarvis:
    tester = True

    def __init__(self, profile_id, folder, profiles, client, clock=time.monotonic, today=date.today, now=datetime.now):
        if not is_profile_id(profile_id):
            raise ValueError("Ungueltiger Bereich.")
        self.profile_id = profile_id
        self.folder = Path(folder)
        self.profiles = profiles
        self.clock = clock
        self.hits = deque()
        self._epoch = profiles.epoch(profile_id)
        self._lock = threading.Lock()
        self.folder.mkdir(parents=True, exist_ok=True)

        # Eigene Speicher: kein Apple-Kalender (remote=None), also nie ein Eintrag im Kalender des Besitzers
        self.widget_store = widgets.WidgetStore(self.folder / "widgets.json", today=today, remote=None)
        self.reminder_store = reminders.ReminderStore(self.folder / "reminders.json", now=now, calendar=lambda: self.widget_store)
        self.counter = cost_guard.UsageCounter(self.folder / "usage.json", self._cost_limits)
        self.client = cost_guard.guard_ai_only(client, self.counter)
        self.task_registry = build_tester_registry()
        # Faellige Erinnerungen dieses Gastes: eigener Takt, eigene Meldungen, nie ein Alarmton am PC (ring tut nichts)
        self.scheduler = reminders.ReminderScheduler(self.reminder_store, submit=self._deliver, ring=lambda label, briefing: None)
        self._feed = []
        self._feed_last = 0
        self._feed_lock = threading.Lock()
        # Nie die Heimatstadt des Besitzers: "Wetter" ohne Ort bekommt hier keinen
        self.weather = weather_tool.WeatherService(home=lambda: "")

        with self._scope():
            for task_type in tester_task_types():
                task = self.task_registry.get(task_type)
                if task is not None and risk.task_risk(task) != risk.SAFE:
                    raise RuntimeError(f"Die Test-Aufgabe {task_type} ist nicht harmlos.")

    # ---- Schnittstelle fuer den Server

    def limits(self):
        profile = self.profiles.get(self.profile_id)
        return profile["limits"] if profile is not None else None

    def _cost_limits(self):
        limits = self.limits()
        # speech: 1 und nie gezaehlt, es gibt keine Stimme (AiOnlyClient). 0 wuerde "unbegrenzt" heissen.
        return {"ai": limits["ai_per_day"] if limits else 1, "speech": 1}

    def memory_enabled(self):
        return False

    def ready(self):
        """Der Ordner kann durch "Bereich zuruecksetzen" weg sein: vor jeder Anfrage wieder anlegen (nur, wenn es den Bereich noch gibt)."""
        if self.limits() is not None:
            self.folder.mkdir(parents=True, exist_ok=True)
            return True
        return False

    # ---- Erinnerungen: faellig werden, melden (nur in der App dieses Gastes)

    def _deliver(self, result):
        if not isinstance(result, dict) or result.get("type") != "REMINDER_DUE":
            return          # Wecker gibt es im Testbereich nicht
        data = result.get("data") or {}
        message = f"Erinnerung: {data.get('text', '')}"
        notes = []
        if data.get("missed"):
            notes.append(f"fällig war sie {reminders.describe_due(data['due'])}, da war ich nicht aktiv")
        if data.get("next_due"):
            notes.append(f"die nächste kommt {reminders.describe_due(data['next_due'])}")
        elif data.get("last_of_series"):
            notes.append("das war die letzte dieser Serie")
        text = message + (f" ({'; '.join(notes)})" if notes else "")
        with self._feed_lock:
            self._feed_last += 1
            self._feed.append((self._feed_last, text))
            del self._feed[:-MAX_FEED]

    def check_reminders(self):
        """Faellige Erinnerungen melden. Gibt es den Bereich nicht mehr, passiert nichts (und nichts wird angelegt)."""
        if not self.ready():
            return 0
        return self.scheduler.check()

    def background(self, after=None):
        """Wie /api/background beim Besitzer: ohne `after` nur der Stand, mit `after` alles danach."""
        with self._feed_lock:
            if after is None:
                return {"messages": [], "last": self._feed_last}
            return {"messages": [{"id": i, "text": t} for i, t in self._feed if i > after], "last": self._feed_last}

    def clear_conversation(self):
        self._save_messages([])

    def sync_state(self, known=""):
        """Wie server.sync_state, nur fuer die eigene Unterhaltung: kurzer Fingerabdruck, bei Aenderung kommt der Verlauf mit."""
        messages = self.messages()
        version = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
        state = {"version": version, "active": NO_ACTIVE}
        if known != version:
            state["messages"] = messages
            state["projects"] = []
        return state

    def check_background_results(self):
        return []

    def _scope(self):
        stack = ExitStack()
        stack.enter_context(widgets.use_store(self.widget_store))
        stack.enter_context(reminders.use_store(self.reminder_store))
        stack.enter_context(weather_tool.use_service(self.weather))
        stack.enter_context(action_log.silenced())
        return stack

    # ---- Unterhaltung (Datei = Wahrheit, nichts im Speicher, damit "Bereich zuruecksetzen" sofort wirkt)

    def messages(self):
        try:
            data = json.loads((self.folder / "conversation.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("messages") if isinstance(data, dict) else None
        clean = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                clean.append({"role": item["role"], "content": item["content"][:MAX_CONTENT]})
        return clean[-MAX_MESSAGES:]

    def _save_messages(self, messages):
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"messages": messages[-MAX_MESSAGES:]}, ensure_ascii=False)
        handle, temp = tempfile.mkstemp(dir=str(self.folder), prefix=".conv_", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(payload)
            os.replace(temp, self.folder / "conversation.json")
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass

    # ---- Nachrichten

    def _limited(self, per_window):
        epoch = self.profiles.epoch(self.profile_id)
        if epoch != self._epoch:
            self._epoch = epoch
            self.hits.clear()          # "Zaehler zuruecksetzen" oder "Bereich zuruecksetzen" am PC
        now = self.clock()
        while self.hits and now - self.hits[0] > RATE_WINDOW:
            self.hits.popleft()
        if per_window and len(self.hits) >= per_window:
            return True
        self.hits.append(now)
        return False

    def process_message(self, text):
        with self._lock:
            return self._process(text)

    def _process(self, text):
        if not isinstance(text, str) or not text.strip():
            return {"status": "response", "content": "Bitte schreibe etwas."}
        text = text.strip()
        if len(text) > remote_policy.MAX_REMOTE_MESSAGE_CHARS:
            return {"status": "response", "content": f"Bitte fasse dich kürzer (höchstens {remote_policy.MAX_REMOTE_MESSAGE_CHARS} Zeichen)."}

        limits = self.limits()
        if limits is None:
            return {"status": "response", "content": "Dieser Bereich existiert nicht mehr."}
        if self._limited(limits["messages_per_10min"]):
            return {"status": "response", "content": f"Im Testbereich sind höchstens {limits['messages_per_10min']} Nachrichten in 10 Minuten möglich. Bitte warte kurz."}

        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            with self._scope():
                answer = self._answer(text)
        except cost_guard.LimitReached:
            return {"status": "response", "content": "Das Tageslimit für KI-Anfragen ist erreicht. Der Besitzer kann es erhöhen oder zurücksetzen."}
        except Exception:
            return {"status": "response", "content": "Das hat gerade nicht geklappt. Bitte versuche es noch einmal."}

        history = self.messages() + [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        self._save_messages(history)
        return {"status": "response", "content": answer}

    def capabilities_text(self):
        labels = [a.label for a in abilities.ABILITIES if a.id in TESTER_ABILITIES]
        return "Im Testbereich kann ich dir helfen mit: " + ", ".join(labels) + ". Außerdem plaudere ich gern mit dir."

    def _answer(self, text):
        route = route_message(self.client, text, self.task_registry)

        if route["kind"] == "COMMAND":
            if isinstance(route.get("command"), dict) and route["command"].get("intent") == "SHOW_CAPABILITIES":
                return self.capabilities_text()
            return REFUSAL

        if route["kind"] in ("PLAN", "DISABLED"):
            return REFUSAL

        if route["kind"] == "TASK":
            task_type = route["task_type"]
            if not isinstance(task_type, str) or task_type not in tester_task_types():
                return REFUSAL
            prepared = prepare_registered_task(self.task_registry, task_type, route["parameters"])
            if prepared is None or risk.task_risk(prepared) != risk.SAFE:
                return REFUSAL
            task = execute_registered_task(self.task_registry, task_type, route["parameters"])
            return respond_to_task(self.client, text, task)

        conversation = Conversation()
        conversation.load_messages(self.messages())
        conversation.add_message("user", text)
        response = self.client.responses.create(
            model=MODEL,
            instructions=jarvis_personality() + TESTER_NOTE,
            input=build_input(conversation),
        )
        return response.output_text
