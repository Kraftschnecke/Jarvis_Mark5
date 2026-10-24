"""Rechner (Mark 5, Step 2.3): exakte Dezimalrechnung, Prozent, Potenzen."""

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
for name in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
             "save_message", "get_conversation", "rename_conversation", "create_project", "reset_conversation",
             "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub

import abilities
import action_executor
import risk
import router
import server
from action import Action
from net_fetch import NetError
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools import calc_tool, convert_tool


calc = calc_tool.calculate

# 1) Exakt, nicht Fliesskomma
assert calc("0.1 + 0.2") == 0.3 and calc("0.1*3") == 0.3 and calc("1.1*1.1") == 1.21
assert calc("10/3*3") == 10 and isinstance(calc("10/3*3"), int)
assert calc("1/3") == 0.333333333333333 and calc("2/3") == 0.666666666666667
assert calc("100*1.19") == 119 and calc("19.99*3") == 59.97
assert calc("2**100") == 2 ** 100 and isinstance(calc("2**100"), int), "grosse ganze Zahlen bleiben exakt"
assert calc("123456789*987654321") == 123456789 * 987654321

# 2) Grundrechenarten, Klammern, Vorzeichen (wie bisher)
for expression, expected in (("2 + 3 * 4", 14), ("(1 + 2) * 3", 9), ("10 / 4", 2.5), ("-5 + 3", -2), ("2 * -3", -6),
                             ("--2", 2), ("+4", 4), ("-(2 + 3)", -5), ("7/2", 3.5), ("  42  ", 42)):
    assert calc(expression) == expected, expression

# 3) Neu: Potenzen, Prozent, Dezimalkomma, Zeichen aus Sprache/Text
assert calc("2 ** 3") == 8 and calc("2^10") == 1024 and calc("9**0.5") == 3 and calc("2**-2") == 0.25
assert calc("80*15%") == 12 and calc("15% * 80") == 12 and calc("80*(1+19%)") == 95.2 and calc("200 - 200*12.5%") == 175
assert calc("50%") == 0.5 and calc("100 * 7 %") == 7
assert calc("1,5 * 2") == 3 and calc("3,14*2") == 6.28
assert calc("6 × 7") == 42 and calc("84 ÷ 2") == 42 and calc("5 − 3") == 2

# 4) Fehler: klare Saetze, keine fremden Ausdruecke
for bad in ("__import__('os')", "abs(-1)", "x + 1", "True + 1", "1j", "'a' * 3", "[1, 2]", "", "   ", "2 +", "10 % 3",
            "(-8)**0.5", "0**0", "2**5000", "2**3**4**5", "9" * 300, "1e999", "lambda: 1", "(1).real", "1 if 1 else 2",
            "[x for x in range(9)]", "((((((((((1))))))))))" * 40, None, 5, 1.5, ["1+1"]):
    try:
        calc(bad)
        raise AssertionError(f"haette abgelehnt werden muessen: {bad!r}")
    except AssertionError:
        raise
    except ValueError as error:
        assert str(error) and "Traceback" not in str(error), error
try:
    calc("1 / 0")
    raise AssertionError
except ZeroDivisionError:
    pass
try:
    calc("0 / 0")
    raise AssertionError
except (ValueError, ZeroDivisionError):
    pass

# 5) Einbindung: Aufgabe, Executor, Beschreibung
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("CALCULATE")
parameter = task.actions[0].parameters["expression"]
assert isinstance(parameter, dict) and "%" in parameter["description"] and "Potenz" in parameter["description"]
assert action_executor.execute_action(Action("calculate", {"expression": "80*15%"})) == 12
assert risk.task_risk(task) == "safe" and abilities.ability_of("CALCULATE") is None, "Rechnen bleibt eine Grundfaehigkeit"
assert not hasattr(action_executor, "calculate_expression"), "alter Rechner ist ersetzt"

print("ALL TESTS PASSED")
