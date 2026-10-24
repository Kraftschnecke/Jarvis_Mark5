"""Risikostufen und Rueckfrage vor Aktionen (Step 4.2).

safe laeuft sofort, confirm erst nach "Ja", forbidden nie. Durchgesetzt im
Executor; getestet auch mit Ja/Nein per Chat und per Button (/api/confirm).
"""

import contextlib
import io
import json
import re
import sys
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def stub_if_missing(name, **attrs):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


class FakeTimeout(Exception):
    pass


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing("requests", get=None, exceptions=types.SimpleNamespace(Timeout=FakeTimeout))
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

project_stub = types.ModuleType("project")
for name in (
    "search_projects", "get_conversations", "create_conversation",
    "load_conversation_messages", "save_message", "get_conversation",
    "rename_conversation", "create_project", "reset_conversation",
    "delete_conversation", "get_projects", "rename_project", "delete_project"
):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub



import re
import ast

import action_executor
import jarvis as jarvis_module
import risk
import server
import task_executor
from action import Action
from jarvis import Jarvis
from task import Task
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools.tool_result import ToolResult

registry = TaskRegistry()
register_all_tasks(registry)


def task_of(task_type, parameters=None):
    return task_executor.prepare_registered_task(registry, task_type, parameters)


# =====================================================================
# 1) Die Tabelle
# =====================================================================

# Jede Action, die der Executor kennt, ist eingestuft (sonst waere sie forbidden)
source = open(PROJECT_DIR / "action_executor.py", encoding="utf-8").read()
known_actions = set(re.findall(r'action\.name == "(\w+)"', source))
assert known_actions, "keine Actions gefunden"
assert known_actions <= set(risk.ACTION_RISK), known_actions - set(risk.ACTION_RISK)
assert set(risk.ACTION_RISK) <= known_actions                # keine Karteileichen

# Jede registrierte Task hat nur eingestufte Actions
for registered in registry.get_all():
    for action in registered.actions:
        assert action.name in risk.ACTION_RISK, (registered.task_type, action.name)

expected = {
    "GET_TIME": "safe", "GET_DATE": "safe", "CALCULATE": "safe",
    "GET_SYSTEM_INFO": "safe", "GET_RUNNING_PROGRAMS": "safe",
    "FIND_PROGRAM": "safe", "SEARCH_WEB": "safe", "START_TIMER": "safe",
    "LIST_TIMERS": "safe", "CANCEL_TIMER": "safe",
    "ADD_CALENDAR_EVENT": "safe", "LIST_CALENDAR_EVENTS": "safe",
    "SET_VOLUME": "safe", "GET_WEATHER": "safe", "GET_NEWS": "safe", "CONVERT": "safe", "WIKI_LOOKUP": "safe", "TRANSLATE": "safe", "SET_REMINDER": "safe", "LIST_REMINDERS": "safe", "CANCEL_REMINDER": "safe", "GET_WORLD_TIME": "safe",
    "SET_ALARM": "safe", "LIST_ALARMS": "safe", "CANCEL_ALARM": "safe", "STOP_RINGING": "safe",
    "OPEN_FILE": "confirm", "START_PROGRAM": "confirm",
    "READ_PAGE": "confirm",   # ohne Eintrag in der News-Liste: erst fragen (test_page.py prueft die Ausnahme)
}
for task_type, level in expected.items():
    assert risk.task_risk(task_of(task_type)) == level, task_type
assert {t.task_type for t in registry.get_all()} == set(expected)

# Unbekannte Action = verboten (Standard ist Nein)
assert risk.action_risk(Action("format_disk")) == "forbidden"
assert risk.action_risk(Action("")) == "forbidden"

# Eine Task ist so riskant wie ihre riskanteste Action
mixed = Task("X", "x")
mixed.add_action(Action("get_current_time"))
mixed.add_action(Action("open_program", {"path": "C:/a.exe"}))
assert risk.task_risk(mixed) == "confirm"
mixed.add_action(Action("unbekannt"))
assert risk.task_risk(mixed) == "forbidden"
assert risk.task_risk(Task("LEER", "x")) == "safe"

# OPEN_FILE: Programmdateien, Web- und Netzwerkadressen sind verboten, normale Dateien erfragt
for path in ("C:/x/boese.exe", "C:\\x\\boese.EXE", "boese.exe.", "run.ps1", "a.lnk",
             "https://evil.example/x.txt", "file:///C:/x.txt", "\\\\server\\share\\a.txt",
             "//server/a.txt", "C:/x/y.bat "):
    assert risk.task_risk(task_of("OPEN_FILE", {"path": path})) == "forbidden", path
for path in ("C:/Users/x/Dokumente/bericht.pdf", "C:/Users/x/bild.png", "C:/Users/x/Ordner"):
    assert risk.task_risk(task_of("OPEN_FILE", {"path": path})) == "confirm", path

# Beschreibung fuer die Rueckfrage: nur Text, ohne Steuerzeichen, gekuerzt
goal, details = risk.describe_task(task_of("OPEN_FILE", {"path": "C:/a\nb\x00c.pdf" + "x" * 500}))
assert goal == "Eine Datei auf dem Computer öffnen"
assert len(details) == 1 and "\n" not in details[0] and "\x00" not in details[0]
assert len(details[0]) <= 200

# =====================================================================
# 2) Der Executor setzt die Stufe durch
# =====================================================================

ran = []


def spy(action):
    ran.append(action.name)

    if action.name == "find_program":
        return ToolResult(success=True, data="C:/Programme/steam.exe")

    return ToolResult(success=True, data="ok")


task_executor.execute_action = spy

# confirm ohne Bestaetigung: nichts laeuft, auch nicht die harmlose erste Action
task = task_of("START_PROGRAM", {"program": "steam"})
task_executor.execute_task(task)
assert task.status == "BLOCKED" and ran == [] and task.error
assert all(a.status == "PENDING" for a in task.actions)

# ... mit Bestaetigung laeuft sie
task = task_of("START_PROGRAM", {"program": "steam"})
task_executor.execute_task(task, confirmed=True)
assert task.status == "COMPLETED" and ran == ["find_program", "open_program"]

# forbidden laeuft nie, auch nicht mit Bestaetigung
ran.clear()
for confirmed in (False, True):
    task = task_of("OPEN_FILE", {"path": "C:/x/boese.exe"})
    task_executor.execute_task(task, confirmed=confirmed)
    assert task.status == "BLOCKED" and ran == []

unknown = Task("UNBEKANNT", "x")
unknown.add_action(Action("format_disk"))
task_executor.execute_task(unknown, confirmed=True)
assert unknown.status == "BLOCKED" and ran == []

# safe laeuft einfach
task = task_executor.execute_registered_task(registry, "GET_TIME")
assert task.status == "COMPLETED" and ran == ["get_current_time"]

# =====================================================================
# 3) Ablauf in Jarvis: Rueckfrage, Ja/Nein per Chat und per Button
# =====================================================================

routes = []
model_calls = []


class FakeClient:
    responses = None

    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        model_calls.append(kwargs)
        return types.SimpleNamespace(output_text="Erledigt.")


def route_for(task_type, parameters):
    return {
        "kind": "TASK", "task_type": task_type, "parameters": parameters,
        "command": {"intent": "NORMAL_MESSAGE", "project_name": None,
                    "conversation_name": None, "new_conversation_name": None},
    }


chat_calls = []
jarvis_module.route_message = lambda client, message, reg: routes.pop(0)


def make_jarvis():
    j = object.__new__(Jarvis)
    j.client = FakeClient()
    j.task_registry = registry
    j.pending_project_confirmation = None
    j.process_normal_message = lambda m: chat_calls.append(m) or {
        "status": "response", "content": "Chat"}
    return j


def run(j, message):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        return j.process_message(message)


def reset():
    ran.clear()
    routes.clear()
    model_calls.clear()
    chat_calls.clear()


# a) Rueckfrage: nichts passiert, bevor der Nutzer ja sagt
reset()
j = make_jarvis()
routes.append(route_for("START_PROGRAM", {"program": "steam"}))
out = run(j, "Starte Steam")
assert out["status"] == "confirmation" and ran == [] and model_calls == []
assert out["confirmation"]["title"] == "Ein Programm auf dem Computer öffnen oder starten"
assert out["confirmation"]["details"] == ["steam"]
assert "steam" in out["content"] and "ja" in out["content"]
action_id = out["confirmation"]["id"]
assert len(action_id) == 16 and j.pending_action["id"] == action_id

# b) Button "Ausfuehren": laeuft genau einmal
out = j.confirm_action(action_id, True)
assert out == {"status": "response", "content": "Erledigt."}
assert ran == ["find_program", "open_program"] and len(model_calls) == 1
out = j.confirm_action(action_id, True)                       # zweites Mal
assert "nicht mehr gueltig" in out["content"] and len(ran) == 2

# c) Button "Abbrechen"
reset()
routes.append(route_for("START_PROGRAM", {"program": "steam"}))
out = run(j, "Starte Steam")
out = j.confirm_action(out["confirmation"]["id"], False)
assert "nichts ausgefuehrt" in out["content"] and ran == [] and model_calls == []
assert j.pending_action is None

# d) Falsche Nummer, fehlende Nummer, falscher Typ: nichts laeuft, Rueckfrage ist verbraucht
for bad_id in ("0000000000000000", "", None, 5, ["x"]):
    reset()
    routes.append(route_for("START_PROGRAM", {"program": "steam"}))
    good = run(j, "Starte Steam")["confirmation"]["id"]
    out = j.confirm_action(bad_id, True)
    assert "nicht mehr gueltig" in out["content"] and ran == [], bad_id
    assert "nicht mehr gueltig" in j.confirm_action(good, True)["content"]   # auch die richtige zu spaet
    assert ran == []

# e) Abgelaufen (nach 120 s)
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/bericht.pdf"}))
out = run(j, "Oeffne bericht.pdf")
j.pending_action["expires"] -= 1000
assert "nicht mehr gueltig" in j.confirm_action(out["confirmation"]["id"], True)["content"]
assert ran == []

# f) Chat-Antwort "ja" / "nein" (CLI)
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/bericht.pdf"}))
run(j, "Oeffne bericht.pdf")
out = run(j, "Ja!")
assert out["status"] == "response" and out["content"] == "Erledigt." and ran == ["open_file"]
assert routes == [] and chat_calls == []                      # "Ja" ging NICHT durch den Router

reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/bericht.pdf"}))
run(j, "Oeffne bericht.pdf")
out = run(j, "nein")
assert "nichts ausgefuehrt" in out["content"] and ran == []

# g) Etwas anderes als ja/nein verwirft die Rueckfrage; ein spaeteres "ja" tut nichts
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/bericht.pdf"}))
run(j, "Oeffne bericht.pdf")
routes.append(route_for("CHAT", {}) | {"kind": "CHAT", "task_type": None})
run(j, "Wie spaet ist es eigentlich")
assert j.pending_action is None
routes.append({"kind": "CHAT", "task_type": None, "parameters": {},
               "command": {"intent": "NORMAL_MESSAGE"}})
run(j, "ja")
assert ran == []

# h) Neue Rueckfrage ersetzt die alte: die alte Nummer gilt nicht mehr
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
first = run(j, "Oeffne a.pdf")["confirmation"]["id"]
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/b.pdf"}))
second = run(j, "Oeffne b.pdf")["confirmation"]["id"]
assert first != second
assert "nicht mehr gueltig" in j.confirm_action(first, True)["content"] and ran == []

# i) clear_pending (Projekt-/Konversationswechsel) verwirft die Rueckfrage
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
pid = run(j, "Oeffne a.pdf")["confirmation"]["id"]
j.clear_pending()
assert "nicht mehr gueltig" in j.confirm_action(pid, True)["content"] and ran == []

# j) Verboten: feste Antwort, keine Rueckfrage, kein Modell, nichts laeuft
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/boese.exe"}))
out = run(j, "Oeffne boese.exe")
assert out["status"] == "response" and "darf ich nicht" in out["content"]
assert j.pending_action is None and ran == [] and model_calls == []
assert "confirmation" not in out

# k) Sicher: sofort, ohne Rueckfrage
reset()
routes.append(route_for("GET_TIME", {}))
out = run(j, "Wie spaet ist es")
assert out == {"status": "response", "content": "Erledigt."} and ran == ["get_current_time"]

# l) Fehler bei der Ausfuehrung nach "Ja": Meldung statt Absturz
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
cid = run(j, "Oeffne a.pdf")["confirmation"]["id"]
j.client = types.SimpleNamespace(responses=types.SimpleNamespace(
    create=lambda **kw: (_ for _ in ()).throw(RuntimeError("Netz weg"))))
with contextlib.redirect_stderr(io.StringIO()):
    out = j.confirm_action(cid, True)
assert "Fehler" in out["content"] and "Netz weg" in out["content"]

# =====================================================================
# 4) Web-Schnittstelle /api/confirm
# =====================================================================

j = make_jarvis()
reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
cid = run(j, "Oeffne a.pdf")["confirmation"]["id"]

# "approve" muss genau true sein: der Text "true", 1 oder fehlend zaehlt als Nein
for not_true in ("true", 1, None, "ja", [True]):
    reset()
    routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
    cid = run(j, "Oeffne a.pdf")["confirmation"]["id"]
    body = {"id": cid} if not_true is None else {"id": cid, "approve": not_true}
    out = server.api_post(j, "/api/confirm", body)
    assert out["status"] == "response" and ran == [], not_true

for bad in ({}, {"approve": True}, {"id": "", "approve": True}, {"id": 5, "approve": True}):
    try:
        server.api_post(j, "/api/confirm", bad)
        raise AssertionError(f"haette 400 geben muessen: {bad}")
    except server.ApiError as error:
        assert error.status == 400

reset()
routes.append(route_for("OPEN_FILE", {"path": "C:/Users/x/a.pdf"}))
cid = run(j, "Oeffne a.pdf")["confirmation"]["id"]
out = server.api_post(j, "/api/confirm", {"id": cid, "approve": True})
assert out == {"status": "response", "content": "Erledigt."} and ran == ["open_file"]

print("ALL TESTS PASSED")
