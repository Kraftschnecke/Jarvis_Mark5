"""Schalter fuer Faehigkeiten (Mark 5, Step 1.3): ausgeschaltet = unsichtbar, nicht ausfuehrbar, ehrlich gemeldet."""

import contextlib
import io
import sys
import tempfile
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


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("requests")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
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

import abilities
import capabilities
import jarvis as jarvis_module
import plan as plan_module
import router
import server
import task_executor
from jarvis import Jarvis
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks

settings = SettingsManager(Path(tempfile.mkdtemp()) / "s.json")
registry = TaskRegistry(is_enabled=lambda t: abilities.task_enabled(t, settings))
register_all_tasks(registry)
ALL = len(registry.get_all())

# 1) Voreinstellung: alles an wie bisher, nichts disabled
assert ALL == 25 and registry.get_disabled() == []
assert registry.get("SEARCH_WEB") is not None and not registry.is_disabled("SEARCH_WEB")

# 2) Ausschalten: Aufgabe verschwindet ueberall, Grundfaehigkeiten bleiben
settings.set("abilities", "web_search", False)
assert registry.get("SEARCH_WEB") is None and registry.is_disabled("SEARCH_WEB")
assert len(registry.get_all()) == ALL - 1 and [t.task_type for t in registry.get_disabled()] == ["SEARCH_WEB"]
assert registry.get("GET_TIME") is not None, "Grundfaehigkeiten lassen sich nicht ausschalten"
assert not registry.is_disabled("GIBTS_NICHT")

# 3) Mehrere Aufgaben einer Faehigkeit gehen zusammen aus
settings.set("abilities", "timers", False)
assert {t.task_type for t in registry.get_disabled()} == {"SEARCH_WEB", "START_TIMER", "LIST_TIMERS", "CANCEL_TIMER"}

# 4) Router: Aufgabe nicht mehr zur Auswahl, aber als "ausgeschaltet" bekannt
prompt = router.build_prompt("Suche im Web nach Katzen", registry)
tasks_part = prompt.split("- TASK")[1].split("- PLAN")[0]
assert "- GET_TIME:" in tasks_part and "- ADD_CALENDAR_EVENT:" in tasks_part
assert tasks_part.index("SWITCHED OFF") < tasks_part.index("- SEARCH_WEB:")
assert "- SEARCH_WEB:" in tasks_part.split("SWITCHED OFF")[1] and "- SEARCH_WEB:" not in tasks_part.split("SWITCHED OFF")[0]
settings.set("abilities", "web_search", True)
settings.set("abilities", "timers", True)
assert "SWITCHED OFF" not in router.build_prompt("x", registry), "Ohne Ausgeschaltetes kein Zusatztext"
settings.set("abilities", "web_search", False)

route = router.normalize_route({"kind": "TASK", "task_type": "SEARCH_WEB", "parameters": {"query": "x"}}, registry)
assert route["kind"] == "DISABLED" and route["task_type"] == "SEARCH_WEB" and route["parameters"] == {}
route = router.normalize_route({"kind": "TASK", "task_type": "GET_TIME", "parameters": {}}, registry)
assert route["kind"] == "TASK"
route = router.normalize_route({"kind": "TASK", "task_type": "GIBTS_NICHT"}, registry)
assert route["kind"] == "CHAT", "Unbekanntes bleibt Chat"

# 5) Ausfuehrung: eine ausgeschaltete Aufgabe laeuft nicht, auch nicht direkt
assert task_executor.prepare_registered_task(registry, "SEARCH_WEB", {"query": "x"}) is None
assert task_executor.execute_registered_task(registry, "SEARCH_WEB", {"query": "x"}) is None

# 6) Plan mit ausgeschalteter Aufgabe wird abgelehnt
plan_json = {"steps": [{"task_type": "SEARCH_WEB", "parameters": {"query": "Wetter"}},
                       {"task_type": "GET_TIME", "parameters": {}}]}
try:
    plan_module.parse_plan(plan_json, registry)
    raise AssertionError("Plan mit ausgeschalteter Aufgabe darf nicht gelten")
except Exception as error:
    assert not isinstance(error, AssertionError), error

# 7) Faehigkeitenliste: nennt das Ausgeschaltete getrennt, ohne die Aufgabe bei den Aufgaben
text = capabilities.describe_capabilities(registry, "Chef")
task_section = text.split("**Aufgaben**\n")[1].split("\n\n")[0].splitlines()
assert len(task_section) == len(registry.get_all())
assert not any("Websuche" in line for line in task_section)
assert "**Ausgeschaltet**" in text and "- Websuche" in text.split("**Ausgeschaltet**")[1].split("**")[0]
assert "Abilities" in text
settings.set("abilities", "web_search", True)
assert "**Ausgeschaltet**" not in capabilities.describe_capabilities(registry, "Chef")
settings.set("abilities", "web_search", False)

# 8) Jarvis: feste Antwort ohne KI, und eine wartende Rueckfrage laeuft nach dem Ausschalten nicht mehr
j = object.__new__(Jarvis)
j.task_registry = registry
j.pending_project_confirmation = None
answer = j.disabled_message("SEARCH_WEB")
assert "Websuche" in answer and "ausgeschaltet" in answer and "Abilities" in answer

executed = []
jarvis_module.execute_task = lambda task, confirmed=False: executed.append(task)
logged = []
jarvis_module.action_log.record = lambda task, *a, **k: logged.append((task.task_type, a))
settings.set("abilities", "files", True)
pending_task = task_executor.prepare_registered_task(registry, "OPEN_FILE", {"path": "C:\\Windows\\win.ini"})
assert pending_task is not None
settings.set("abilities", "files", False)         # nach der Rueckfrage ausgeschaltet
with contextlib.redirect_stdout(io.StringIO()):
    result = j._finish_pending_action({"task": pending_task}, True)
assert executed == [] and "ausgeschaltet" in result and logged == [("OPEN_FILE", ("refused", "BLOCKED"))], (executed, result, logged)

# 9) Server: Schalter sind aenderbar (nur Wahrheitswerte), Oberflaeche bekommt die Liste
for ability in abilities.ABILITIES:
    check = server.EDITABLE_SETTINGS[("abilities", ability.id)]
    assert check(True) and check(False) and not check("ja") and not check(1) and not check(None)
assert ("abilities", "gibtsnicht") not in server.EDITABLE_SETTINGS
fake = types.SimpleNamespace(guest=False, settings_manager=settings)
state = server.settings_state(fake)
listed = {a["id"]: a for a in state["abilities"]}
assert set(listed) == {a.id for a in abilities.ABILITIES}
assert listed["web_search"]["enabled"] is False and listed["timers"]["enabled"] is True
assert all(a["label"] and a["description"] for a in state["abilities"])

# 10) Ohne Pruefung (Gast-Registry, Tests) sind alle Aufgaben an
assert len(TaskRegistry().get_all()) == 0
plain = TaskRegistry()
register_all_tasks(plain)
assert len(plain.get_all()) == ALL and plain.get_disabled() == []

print("ALL TESTS PASSED")
