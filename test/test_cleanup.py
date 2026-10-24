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


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing("requests")
# pycaw wird absichtlich NICHT global gestubbt: das Modul muss ohne pycaw
# importierbar sein (Windows-only Abhaengigkeit steckt jetzt in set_volume).

project_stub = types.ModuleType("project")
for name in (
    "search_projects", "get_conversations", "create_conversation",
    "load_conversation_messages", "save_message", "get_conversation",
    "rename_conversation", "create_project", "reset_conversation",
    "delete_conversation", "get_projects", "rename_project", "delete_project"
):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub

import action_executor
import tasks
import jarvis as jarvis_module
import task_executor
from action import Action
from task import Task
from task_registry import TaskRegistry
from tools import volume_tool


def calc(expression):
    return action_executor.execute_action(
        Action("calculate", {"expression": expression})
    )


# ---------- Rechner ----------
assert calc("2 + 3 * 4") == 14
assert calc("(1 + 2) * 3") == 9
assert calc("10 / 4") == 2.5
assert calc("-5 + 3") == -2          # neu: negative Zahlen
assert calc("2 * -3") == -6
assert calc("--2") == 2
assert calc("+4") == 4
assert calc("-(2 + 3)") == -5

assert calc("2 ** 3") == 8           # Mark 5, Step 2.3: Potenzen und Prozent (mehr in test_calc.py)

for bad in (
    "__import__('os')", "abs(-1)", "x + 1", "True + 1",
    "1j", "'a' * 3", "[1, 2]", "", "2 +", "10 % 3"
):
    try:
        calc(bad)
        raise AssertionError(f"haette abgelehnt werden muessen: {bad!r}")
    except AssertionError:
        raise
    except Exception:
        pass

try:
    calc("1 / 0")
    raise AssertionError("Division durch 0")
except ZeroDivisionError:
    pass

# ---------- Aufgeraeumt: Test-Ueberreste sind weg ----------
assert not hasattr(tasks, "create_test_task")
registry = TaskRegistry()
tasks.register_all_tasks(registry)
assert registry.get("TEST_TASK") is None
assert registry.get("SEARCH_WEB") is not None

try:
    action_executor.execute_action(Action("print_message", {"message": "x"}))
    raise AssertionError("print_message darf es nicht mehr geben")
except ValueError:
    pass

# ---------- Hintergrund-Ergebnisse ----------
j = object.__new__(jarvis_module.Jarvis)
assert "30 Sekunden" in j.process_background_result(
    {"type": "TIMER_FINISHED", "data": {"seconds": 30}}
)
assert "2 Minuten" in j.process_background_result(
    {"type": "TIMER_FINISHED", "data": {"seconds": 120}}
)
named = j.process_background_result(
    {"type": "TIMER_FINISHED", "data": {"seconds": 300, "name": "Nudeln"}}
)
assert "„Nudeln“" in named and "5 Minuten" in named, named
unnamed = j.process_background_result(
    {"type": "TIMER_FINISHED", "data": {"seconds": 300, "name": "Timer"}}
)
assert "„" not in unnamed, unnamed
assert "„" not in j.process_background_result({"type": "TIMER_FINISHED", "data": {"seconds": 5}})
assert j.process_background_result(
    {"type": "TEST_FINISHED", "data": {"message": "x"}}
) is None

# ---------- Lautstaerke ----------
results = []


class FakeVolume:
    def SetMasterVolumeLevelScalar(self, value, context):
        results.append(value)


fake_pycaw = types.ModuleType("pycaw")
fake_inner = types.ModuleType("pycaw.pycaw")
fake_inner.AudioUtilities = types.SimpleNamespace(
    GetSpeakers=lambda: types.SimpleNamespace(EndpointVolume=FakeVolume())
)

# a) ohne pycaw: normaler Tool-Fehler, kein Absturz beim Import
sys.modules.pop("pycaw", None)
sys.modules.pop("pycaw.pycaw", None)
sys.modules["pycaw"] = None            # erzwingt ImportError
result = volume_tool.set_volume(50)
assert not result.success and result.error

# b) mit (Fake-)pycaw
sys.modules["pycaw"] = fake_pycaw
sys.modules["pycaw.pycaw"] = fake_inner
for value, expected in ((50, 0.5), (0, 0.0), (100, 1.0), ("30", 0.3), (12.5, 0.125)):
    results.clear()
    result = volume_tool.set_volume(value)
    assert result.success and results == [expected], (value, results)

for bad in (-1, 101, 500, "laut", None, float("nan"), [50]):
    results.clear()
    result = volume_tool.set_volume(bad)
    assert not result.success and results == [], bad

# ---------- task_executor: kaputter Task stuerzt nicht ab ----------
broken = Task("KAPUTT", "x")
broken.actions = None                  # simuliert kaputte Daten
task_executor.execute_task(broken)
assert broken.status == "FAILED" and broken.error

empty = Task("LEER", "x")              # leerer Task ist kein Fehler
task_executor.execute_task(empty)
assert empty.status == "COMPLETED"

print("ALL TESTS PASSED")
