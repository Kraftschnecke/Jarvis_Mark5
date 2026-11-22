"""Mark 5 C2: Tester-Bereich (tester.py). Eigene Daten, nichts vom Besitzer, keine Folgen am Rechner."""
import importlib.abc
import json
import shutil
import sys
import tempfile
import threading
import types
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Der Testbereich darf Datenbank, Gedaechtnis, Projekte und das echte Jarvis weder importieren noch brauchen
FORBIDDEN_MODULES = {"db", "memory", "project", "workspace", "jarvis", "psycopg", "project_context",
                     "project_analyzer", "project_state", "database"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name in FORBIDDEN_MODULES:
            raise ImportError(f"Der Testbereich darf {name} nicht importieren")
        return None


sys.meta_path.insert(0, Blocker())


def stub_if_missing(name, **attrs):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


stub_if_missing("openai", OpenAI=object)
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing("requests")

import abilities
import action_log
import cost_guard
import profiles
import reminders
import remote_policy
import risk
import router
import tester
import widgets
from tester import REFUSAL, TesterJarvis
from tools import weather_tool

assert not (FORBIDDEN_MODULES & set(sys.modules)), FORBIDDEN_MODULES & set(sys.modules)


class FakeClient:
    def __init__(self, answer="Gerne."):
        self.calls = []
        self.answer = answer
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text=self.answer)


def chat_route():
    return {"kind": "CHAT", "task_type": None, "parameters": {},
            "command": {"intent": "NORMAL_MESSAGE", "project_name": None, "conversation_name": None, "new_conversation_name": None}}


def task_route(task_type, **parameters):
    route = chat_route()
    route.update(kind="TASK", task_type=task_type, parameters=parameters)
    return route


routes = []
routed = []
NO_REPEAT = {"repeat": "", "interval": "", "count": "", "until": ""}


def fake_route(client, message, registry, context=""):
    routed.append((registry, context))
    return routes.pop(0) if routes else chat_route()


tester.route_message = fake_route

tmp = Path(tempfile.mkdtemp())
store = profiles.ProfileStore(tmp / "profiles.json", tmp / "profiles")
bruder = store.create("Bruder")["id"]
other = store.create("Anderer")["id"]

# Der Besitzer: seine Dateien, seine Speicher als Standard
owner_widgets_path = tmp / "owner_widgets.json"
owner_reminders_path = tmp / "owner_reminders.json"
class OwnerRemote:
    """Der Apple-Kalender des Besitzers: liest nichts, und jeder Schreibversuch wird vermerkt."""
    write_name = "Moritz Kalender"

    def __init__(self):
        self.touched = []

    def events(self):
        return []

    def status(self):
        return {}

    def __getattr__(self, name):
        self.touched.append(name)
        raise AttributeError(name)


remote_spy = OwnerRemote()
owner_widgets = widgets.WidgetStore(owner_widgets_path, remote=remote_spy)
owner_reminders = reminders.ReminderStore(owner_reminders_path, calendar=lambda: owner_widgets)
widgets.set_default_store(owner_widgets)
reminders.set_default_store(owner_reminders)

logged = []
real_insert = action_log._insert
action_log._insert = lambda row: logged.append(row)
action_log.enable()


def make(profile=bruder, client=None, **kw):
    return TesterJarvis(profile, store.path_for(profile), store, client or FakeClient(), **kw)


# 1) Aufgaben: genau die erlaubten, alle harmlos
t = make()
allowed = tester.tester_task_types()
assert set(t.task_registry.tasks) == set(allowed), set(t.task_registry.tasks) ^ set(allowed)
for forbidden in ("OPEN_FILE", "START_PROGRAM", "SET_VOLUME", "START_TIMER", "CANCEL_TIMER", "LIST_TIMERS", "SET_ALARM",
                  "START_FOCUS", "STOP_RINGING", "GET_BRIEFING", "GET_SYSTEM_INFO", "READ_MAIL", "WRITE_NOTE", "OPEN_WEBSITE",
                  "READ_CLIPBOARD", "FIND_PROGRAM", "READ_PAGE", "SEARCH_HISTORY", "LOOK_AT_SCREEN"):
    assert t.task_registry.get(forbidden) is None, forbidden
levels_on = {"info": True, "daily": True, "pc": True}
assert allowed <= remote_policy.allowed_tasks(levels_on)                 # nie mehr als ein Handy mit allen Stufen
assert not (allowed & remote_policy.allowed_tasks({"info": False, "daily": False, "pc": True}))     # nichts aus "PC-Steuerung"
never = set()
for ability in abilities.ABILITIES:
    if ability.id in remote_policy.NEVER_REMOTE or ability.id in ("timers", "alarm", "focus", "briefing"):
        never.update(ability.tasks)
assert not (allowed & never), allowed & never
assert set(tester.TESTER_ABILITIES) <= set(remote_policy.LEVEL_ABILITIES["info"]) | set(remote_policy.LEVEL_ABILITIES["daily"])

# Wird eine Test-Aufgabe riskant, startet der Testbereich nicht
original = risk.ACTION_RISK["add_to_list"]
risk.ACTION_RISK["add_to_list"] = risk.CONFIRM
try:
    make(other)
    raise AssertionError("haette nicht starten duerfen")
except RuntimeError:
    pass
risk.ACTION_RISK["add_to_list"] = original

# Keine Stimme, kein Memory
assert not hasattr(t.client, "audio") and t.memory_enabled() is False and t.check_background_results() == []
for bad in ("../x", "owner", "", None):
    try:
        TesterJarvis(bad, tmp, store, FakeClient())
        raise AssertionError(bad)
    except ValueError:
        pass

# 2) Chat: Hinweis im Prompt, nur der eigene Verlauf, Datei geschrieben, Router bekommt keinen Kontext des Besitzers
client = FakeClient("Hallo Gast.")
t = make(client=client)
assert t.process_message("Wer bist du?") == {"status": "response", "content": "Hallo Gast."}
call = client.calls[-1]
assert "Testbereich" in call["instructions"] and "Behaupte nie" in call["instructions"] and "kein Gedaechtnis" in call["instructions"]
assert call["input"] == [{"role": "user", "content": "Wer bist du?"}]
assert routed[-1][0] is t.task_registry and routed[-1][1] == ""
t.process_message("Noch eine Frage")
assert [m["role"] for m in client.calls[-1]["input"]] == ["user", "assistant", "user"]
conv = tmp / "profiles" / bruder / "conversation.json"
assert [m["content"] for m in json.loads(conv.read_text(encoding="utf-8"))["messages"]] == ["Wer bist du?", "Hallo Gast.", "Noch eine Frage", "Hallo Gast."]
# neuer Prozess, gleiche Daten
t2 = make(client=client)
assert len(t2.messages()) == 4
# anderer Bereich sieht nichts davon
assert make(other).messages() == []
for i in range(60):
    t.process_message(f"Nachricht {i}")
    t.hits.clear()
assert len(t.messages()) == 40

# 3) Befehle, Plaene, abgeschaltete und fremde Aufgaben: feste Absage, kein weiterer Modellaufruf, Verlauf unveraendert
for intent in sorted(router.COMMAND_INTENTS):
    client = FakeClient(); t = make(other, client)
    route = chat_route(); route["kind"] = "COMMAND"; route["command"]["intent"] = intent
    routes.append(route)
    answer = t.process_message("irgendwas")["content"]
    assert (answer == REFUSAL or intent == "SHOW_CAPABILITIES"), intent
    assert client.calls == [], intent
for kind in ("PLAN", "DISABLED"):
    client = FakeClient(); t = make(other, client)
    route = chat_route(); route["kind"] = kind
    routes.append(route)
    assert t.process_message("x")["content"] == REFUSAL and client.calls == []
for bad in ("START_PROGRAM", "SET_ALARM", None, ["GET_TIME"], 5):
    client = FakeClient(); t = make(other, client)
    routes.append(task_route(bad))
    assert t.process_message("x")["content"] == REFUSAL and client.calls == [], bad
client = FakeClient(); t = make(other, client)
cap = chat_route(); cap["kind"] = "COMMAND"; cap["command"]["intent"] = "SHOW_CAPABILITIES"
routes.append(cap)
text = t.process_message("Was kannst du?")["content"]
assert "Packlisten" in text and "Erinnerungen" in text and "Timer" not in text and "Programme" not in text and client.calls == []

# 4) Isolation: Listen, Erinnerungen, Termine, Ziele landen NUR im Bereich des Gastes
owner_before = {p: p.read_text(encoding="utf-8") if p.exists() else None for p in (owner_widgets_path, owner_reminders_path)}
owner_calls = []
seen_by_other_thread = []
real_add = widgets.WidgetStore.add_series


def spying_add(self, *a, **k):
    # waehrend der Gast arbeitet, sieht ein anderer Thread (der Besitzer) weiter seine eigenen Speicher
    worker = threading.Thread(target=lambda: seen_by_other_thread.append((widgets.default_store() is owner_widgets, reminders.default_store() is owner_reminders)))
    worker.start(); worker.join()
    owner_calls.append(self)
    return real_add(self, *a, **k)


widgets.WidgetStore.add_series = spying_add
client = FakeClient("Erledigt.")
t = make(client=client)
today = (date.today() + timedelta(days=1)).isoformat()      # morgen: nie "schon vorbei"
routes.extend([
    task_route("ADD_TO_LIST", list="Einkauf", items="Milch, Eier"),
    task_route("ADD_CALENDAR_EVENT", title="Zahnarzt", date=today, time="10:00", **NO_REPEAT),
    task_route("SET_REMINDER", text="Wasser trinken", date=today, time="23:59", **NO_REPEAT),
])
for text in ("Milch auf die Liste", "Zahnarzt heute", "Erinnere mich"):
    assert t.process_message(text)["content"] == "Erledigt.", text
    t.hits.clear()
widgets.WidgetStore.add_series = real_add

mine = json.loads((tmp / "profiles" / bruder / "widgets.json").read_text(encoding="utf-8"))
assert any("Milch" in json.dumps(item) for item in mine["lists"].values() if True) if isinstance(mine.get("lists"), dict) else "Milch" in json.dumps(mine["lists"])
assert "Zahnarzt" in json.dumps(mine)
assert "Wasser trinken" in (tmp / "profiles" / bruder / "reminders.json").read_text(encoding="utf-8")
assert owner_calls and all(call is not owner_widgets for call in owner_calls)
assert seen_by_other_thread == [(True, True)]
assert {p: p.read_text(encoding="utf-8") if p.exists() else None for p in (owner_widgets_path, owner_reminders_path)} == owner_before
assert widgets.default_store() is owner_widgets and reminders.default_store() is owner_reminders     # nach dem Block wieder normal
assert not (tmp / "profiles" / other / "widgets.json").exists()            # der andere Gast: nichts
assert "Zahnarzt" in json.dumps(t.widget_store.get()) and "Zahnarzt" not in json.dumps(owner_widgets.get())

# Selbst bei einem Fehler mitten in der Aufgabe bleibt der Standard nicht beim Gast haengen
routes.append(task_route("ADD_CALENDAR_EVENT", title="Kaputt", date="kein-datum", time="10:00", **NO_REPEAT))
t.hits.clear()
t.process_message("kaputt")
assert widgets.default_store() is owner_widgets and reminders.default_store() is owner_reminders

# Zweite Sicherung: selbst der echte Schreibweg (Datenbank) wird im Gast-Thread nicht betreten (db ist hier gesperrt)
action_log._insert = real_insert
with action_log.silenced():
    assert action_log._insert(("X",) * 7) is None
try:
    action_log._insert(("X",) * 7)
    raise AssertionError("ausserhalb des Gast-Blocks muss die Datenbank gebraucht werden")
except ImportError:
    pass
action_log._insert = lambda row: logged.append(row)

# Kein Eintrag im Aktionsprotokoll des Besitzers; der Besitzer selbst protokolliert weiter
assert logged == [], logged
import task_executor
owner_task = task_executor.execute_registered_task(tester.build_tester_registry(), "GET_TIME", {})
assert len(logged) == 1 and logged[0][0] == "GET_TIME"
logged.clear()

# Wird eine Aufgabe nach dem Start riskant, wird sie abgelehnt und nicht ausgefuehrt
t = make(client=FakeClient())
risk.ACTION_RISK["add_to_list"] = risk.CONFIRM
routes.append(task_route("ADD_TO_LIST", list="Verboten", items="Gift"))
client_calls = len(t.client.responses._target.calls)
assert t.process_message("Setz Gift auf die Liste")["content"] == REFUSAL
assert len(t.client.responses._target.calls) == client_calls and "Gift" not in t.widget_store.path.read_text(encoding="utf-8")
risk.ACTION_RISK["add_to_list"] = original

# 5) Wetter ohne Ort: nie der Heimatort des Besitzers
owner_weather = weather_tool.WeatherService(home=lambda: "Hamburg")
weather_tool.set_default_service(owner_weather)
t = make(client=FakeClient())          # erst jetzt gebaut: der Besitzer hat schon seinen Wetterdienst gesetzt
inside = []
real_execute = tester.execute_registered_task
tester.execute_registered_task = lambda *a, **k: (inside.append(weather_tool.default_service().home()), real_execute(*a, **k))[1]
t.hits.clear()
routes.append(task_route("GET_TIME"))
t.process_message("Zeit")
tester.execute_registered_task = real_execute
assert inside == [""] and weather_tool.default_service() is owner_weather and owner_weather.home() == "Hamburg"

# 6) Der Apple-Kalender des Besitzers wird nie angefasst (kein remote im Gast-Speicher)
assert remote_spy.touched == []
assert t.widget_store.remote is None and t.widget_store.remote_write_enabled() is False

# 7) Limits: Nachrichten pro 10 Minuten (live aenderbar), KI-Aufrufe pro Tag (eigener Zaehler), 0 = unbegrenzt
clock = [1000.0]
client = FakeClient()
lim = store.create("Limit")["id"]
t = make(lim, client, clock=lambda: clock[0])
store.set_limits(lim, messages_per_10min=2, ai_per_day=100)
assert t.process_message("a")["content"] == "Gerne." and t.process_message("b")["content"] == "Gerne."
blocked = t.process_message("c")["content"]
assert "höchstens 2 Nachrichten" in blocked and len(client.calls) == 2
clock[0] += 601
assert t.process_message("d")["content"] == "Gerne."                           # Fenster vorbei
store.set_limits(lim, messages_per_10min=0)                                    # ab sofort unbegrenzt
for _ in range(5):
    assert t.process_message("e")["content"] == "Gerne."
store.set_limits(lim, messages_per_10min=0, ai_per_day=3)
used = (tmp / "profiles" / lim / "usage.json")
before = len(client.calls)
answers = [t.process_message("f")["content"] for _ in range(4)]
assert "Tageslimit" in answers[-1] and len(client.calls) - before <= 3
total_today = json.loads(used.read_text(encoding="utf-8"))["counts"]["ai"]
assert total_today >= 3 and total_today == len(client.calls)                    # jeder Aufruf gezaehlt, keiner doppelt
store.set_limits(lim, ai_per_day=0)
assert t.process_message("g")["content"] == "Gerne."                           # 0 = unbegrenzt
# Zaehler sind pro Bereich: der Besitzer-Zaehler und der des anderen Gastes bleiben leer
assert not (tmp / "profiles" / other / "usage.json").exists() or json.loads((tmp / "profiles" / other / "usage.json").read_text(encoding="utf-8"))["counts"]["ai"] == 0

# Leere, lange und falsche Eingaben kosten nichts
client = FakeClient(); t = make(other, client)
for bad in ("", "   ", None, 5, ["x"]):
    assert t.process_message(bad)["content"] == "Bitte schreibe etwas."
assert "kürzer" in t.process_message("x" * 1001)["content"] and client.calls == []

# 8) Bereich zuruecksetzen: Verlauf, Listen, Zaehler weg, der Gast arbeitet danach sauber weiter
client = FakeClient("Neu.")
t = make(other, client)
t.process_message("Hallo")
assert t.messages()
store.reset_data(other)
assert t.messages() == []
assert t.process_message("Nochmal")["content"] == "Neu." and [m["content"] for m in t.messages()] == ["Nochmal", "Neu."]
assert [m["role"] for m in client.calls[-1]["input"]] == ["user"]               # nichts vom alten Verlauf

# Bereich geloescht: keine Antwort mehr, nichts wird neu angelegt
store.delete(other)
assert "existiert nicht mehr" in t.process_message("Hallo?")["content"]
assert not (tmp / "profiles" / other).exists()

# 9) Ein Fehler der KI zeigt nichts Internes
class Broken(FakeClient):
    def create(self, **kwargs):
        raise RuntimeError("geheimer Schluessel sk-123")


t = make(bruder, Broken())
answer = t.process_message("Hallo")["content"]
assert "sk-123" not in answer and "nicht geklappt" in answer


# 10) Erinnerungen (C3b): faellig werden, nur in der Meldung dieses Gastes, nie am PC des Besitzers
import background_tasks
import ringing
rings = []
ringing.default_ringer().start = lambda *a, **k: rings.append(a)
while not background_tasks.result_queue.empty():
    background_tasks.result_queue.get()
fire_a = make(bruder, FakeClient())
fire_b = make(store.create("Dritter")["id"], FakeClient())


def write_due(tester_obj, items):
    (tester_obj.folder / "reminders.json").write_text(json.dumps({"reminders": items}), encoding="utf-8")


now_text = datetime.now().strftime("%Y-%m-%dT%H:%M")
write_due(fire_a, [
    {"id": "r1", "text": "Wasser trinken", "due": now_text, "event_id": None},
    {"id": "r2", "text": "Uralt", "due": "2020-01-01T10:00", "event_id": None},
    {"id": "r3", "text": "Spaeter", "due": "2999-01-01T10:00", "event_id": None},
])
assert fire_a.background() == {"messages": [], "last": 0} and fire_a.background(0) == {"messages": [], "last": 0}
assert fire_a.check_reminders() == 2
feed = fire_a.background(0)
texts = [m["text"] for m in feed["messages"]]
assert feed["last"] == 2 and [m["id"] for m in feed["messages"]] == [1, 2]
assert any(t == "Erinnerung: Wasser trinken" for t in texts), texts
assert any(t.startswith("Erinnerung: Uralt (fällig war sie") and "da war ich nicht aktiv" in t for t in texts), texts
assert fire_a.background(1)["messages"] == [m for m in feed["messages"] if m["id"] == 2] and fire_a.background(2)["messages"] == []
assert fire_a.background() == {"messages": [], "last": 2}
assert fire_a.check_reminders() == 0                                        # jede Erinnerung nur einmal
assert "Spaeter" in (fire_a.folder / "reminders.json").read_text(encoding="utf-8")
# Nichts davon beim anderen Gast, beim Besitzer-Hintergrund oder am Wecker des PCs
assert fire_b.background(0) == {"messages": [], "last": 0}
assert background_tasks.result_queue.empty() and rings == []
assert not any("Wasser" in str(m) for m in logged)
# Serie: "die naechste kommt ..."
write_due(fire_a, [])
fire_a.reminder_store.add("Tabletten", (date.today() + timedelta(days=1)).isoformat(), "08:00", "taeglich", None, 5, None)
series = json.loads((fire_a.folder / "reminders.json").read_text(encoding="utf-8"))
series["reminders"][0]["due"] = now_text                                      # jetzt faellig, die Serie geht weiter
(fire_a.folder / "reminders.json").write_text(json.dumps(series), encoding="utf-8")
fire_a.check_reminders()
assert any("Tabletten (die nächste kommt" in m["text"] for m in fire_a.background(2)["messages"]), fire_a.background(2)
# Ein Wecker im Bereich (gibt es hier nie) klingelt nicht und meldet nichts
write_due(fire_a, [{"id": "r5", "text": "Wecker", "due": now_text, "event_id": None, "kind": "alarm"}])
before = fire_a.background()["last"]
fire_a.check_reminders()
assert fire_a.background()["last"] == before and rings == []
# Es werden nur die letzten 100 aufgehoben
for i in range(120):
    fire_a._deliver({"type": "REMINDER_DUE", "data": {"text": f"n{i}", "due": now_text}})
assert len(fire_a.background(0)["messages"]) == 100
# Bereich geloescht: nichts wird gemeldet, nichts neu angelegt
store.delete(bruder)
assert fire_a.check_reminders() == 0 and not fire_a.folder.exists()

print("ALL TESTS PASSED")
