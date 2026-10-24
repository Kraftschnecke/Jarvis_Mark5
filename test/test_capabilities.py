"""Faehigkeitenliste (Step 5.4): wird aus der Registry erzeugt, nennt nur Echtes."""

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







import contextlib
import io

import capabilities
import jarvis as jarvis_module
import plan as plan_module
import plan_executor
import router
from action import Action
from capabilities import COMMAND_TEXT, describe_capabilities
from jarvis import Jarvis
from task import Task
from task_registry import TaskRegistry
from tasks import register_all_tasks

registry = TaskRegistry()
register_all_tasks(registry)

text = describe_capabilities(registry, "Chef")

# 1) Jeder Befehl des Routers hat einen Text, und es gibt keinen Text ohne Befehl
assert set(COMMAND_TEXT) == set(router.COMMAND_INTENTS), set(COMMAND_TEXT) ^ set(router.COMMAND_INTENTS)
for intent in router.COMMAND_INTENTS:
    assert f"- {COMMAND_TEXT[intent]}" in text, intent

# 2) Jede registrierte Aufgabe steht drin (mit ihrem Ziel), und nur diese
task_section = text.split("**Aufgaben**\n")[1].split("\n\n")[0].splitlines()
assert len(task_section) == len(list(registry.get_all()))
for task in registry.get_all():
    assert any(line.startswith(f"- {task.goal}") for line in task_section), task.task_type

# 3) Hinweis "ich frage vorher nach" genau bei den Aufgaben der Stufe confirm
asking = {t.goal for t in registry.get_all() if t.task_type in ("START_PROGRAM", "OPEN_FILE", "READ_PAGE")}
for task in registry.get_all():
    line = next(l for l in task_section if l.startswith(f"- {task.goal}"))
    assert ("(ich frage vorher nach)" in line) == (task.goal in asking), line

# 4) Neue Aufgabe erscheint von selbst, entfernte verschwindet (nichts von Hand gepflegt)
extra = Task("MAIL_SENDEN", "Eine E-Mail senden")
extra.add_action(Action("open_file", {"path": None}))                # Stufe confirm
registry.register(extra)
with_extra = describe_capabilities(registry, "Chef")
assert "- Eine E-Mail senden (ich frage vorher nach)" in with_extra
del registry.tasks["MAIL_SENDEN"]
assert "E-Mail" not in describe_capabilities(registry, "Chef")

# Eine Aufgabe mit einer gar nicht eingestuften Action ist verboten: Zeile ohne Zusatz, aber vorhanden
odd = Task("ODD", "Etwas Eigenes")
odd.add_action(Action("gibt_es_nicht"))
registry.register(odd)
assert "- Etwas Eigenes\n" in describe_capabilities(registry, "Chef") + "\n"
del registry.tasks["ODD"]

# 5) Zahlen kommen aus den echten Grenzen
assert f"bis zu {plan_module.MAX_STEPS} dieser Aufgaben" in text
assert f"höchstens {plan_executor.MAX_SECONDS} Sekunden" in text
original = capabilities.MAX_STEPS
capabilities.MAX_STEPS = 3
assert "bis zu 3 dieser Aufgaben" in describe_capabilities(registry, "Chef")
capabilities.MAX_STEPS = original

# 6) Anrede und Gedaechtnis-Schalter
assert text.startswith("Das kann ich, Chef:")
assert describe_capabilities(registry, "Sir").startswith("Das kann ich, Sir:")
assert "ausgeschaltet" not in text
assert "Das Gedächtnis ist gerade ausgeschaltet." in describe_capabilities(registry, "Chef", memory_enabled=False)

# 7) Ehrlich: sagt klar, dass es sonst nichts kann; nennt nichts, was es nicht gibt
assert "Alles andere kann ich nicht" in text
assert "Termin" in text and "Kalender" in text      # seit Etappe C (ADD_CALENDAR_EVENT)
for invented in ("E-Mail", "Google", "Smart", "Kamera"):
    assert invented not in text, invented

# Sprache gibt es seit Step 6 und ist aus, bis man sie einschaltet
assert "Voice" in text and "vorlesen" in text and "aus, bis du es" in text and "Weckwort" in text

# 8) Router kennt den Befehl
assert "SHOW_CAPABILITIES" in router.build_prompt("was kannst du?", registry)
route = router.normalize_route({"kind": "COMMAND", "intent": "SHOW_CAPABILITIES"}, registry)
assert route["kind"] == "COMMAND" and route["command"]["intent"] == "SHOW_CAPABILITIES"

# 9) Im Chat: feste Antwort, kein Modell-Aufruf
calls = []
jarvis_module.route_message = lambda client, message, reg: {
    "kind": "COMMAND", "task_type": None, "parameters": {},
    "command": {"intent": "SHOW_CAPABILITIES", "project_name": None,
                "conversation_name": None, "new_conversation_name": None}}

j = object.__new__(Jarvis)
j.client = None                                                  # jeder Modell-Aufruf waere ein Fehler
j.task_registry = registry
j.pending_project_confirmation = None
j.settings_manager = types.SimpleNamespace(get=lambda c, k, d=None: True if k == "enabled" else "Chef")
with contextlib.redirect_stdout(io.StringIO()):
    out = j.process_message("Was kannst du?")
from personality import get_address
assert out["status"] == "response" and out["content"] == describe_capabilities(registry, get_address())

print("ALL TESTS PASSED")
