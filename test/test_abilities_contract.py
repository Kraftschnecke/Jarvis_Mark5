"""Vertrag fuer Faehigkeiten (Mark 5, Step 1.1): was jede Aufgabe/Action haben MUSS.
Siehe DESIGN_ABILITIES.md. Schlaegt an, wenn jemand eine Faehigkeit halb baut."""

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


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

import risk
from task_registry import TaskRegistry
from tasks import register_all_tasks

registry = TaskRegistry()
register_all_tasks(registry)
tasks = list(registry.get_all())
executor_source = (PROJECT_DIR / "action_executor.py").read_text(encoding="utf-8")

# Aeltere Actions haben Parameter ohne Beschreibung (``{"query": None}``); die Liste wird nie laenger.
LEGACY_PLAIN_PARAMETERS = {"search_web", "calculate", "open_file", "set_volume", "find_program"}

used_actions = set()
goals = set()
for task in tasks:
    # Aufgabe: Grossbuchstaben_mit_Unterstrich, ein lesbares Ziel, jedes Ziel nur einmal
    assert re.fullmatch(r"[A-Z][A-Z0-9_]+", task.task_type), task.task_type
    assert len(task.goal.strip()) >= 10, task.task_type
    assert task.goal not in goals, f"Ziel doppelt: {task.goal}"
    goals.add(task.goal)
    assert task.actions, f"{task.task_type} hat keine Action"

    for action in task.actions:
        used_actions.add(action.name)

        # 1) Jede Action ist bewusst eingestuft (unbekannt waere automatisch verboten, also unbrauchbar)
        assert action.name in risk.ACTION_RISK, f"{action.name}: Risikostufe in risk.py fehlt"
        assert risk.ACTION_RISK[action.name] in (risk.SAFE, risk.CONFIRM), f"{action.name} ist verboten"

        # 2) Jede Action hat einen Zweig im Executor
        assert f'action.name == "{action.name}"' in executor_source, f"{action.name}: kein Zweig in action_executor.py"

        # 3) Parameter, die das Sprachmodell fuellt, sind beschrieben (Beschreibung + Typ)
        for name, spec in action.parameters.items():
            if spec is None:
                assert action.name in LEGACY_PLAIN_PARAMETERS, f"{action.name}.{name}: Beschreibung fehlt"
            elif spec.get("source") == "previous_result":
                pass
            else:
                assert isinstance(spec.get("description"), str) and len(spec["description"]) >= 10, f"{action.name}.{name}: Beschreibung"
                assert spec.get("type") in ("string", "number", "boolean"), f"{action.name}.{name}: Typ"

# 4) Keine toten Eintraege in risk.py: jede eingestufte Action gehoert zu einer Aufgabe
dead = set(risk.ACTION_RISK) - used_actions
assert not dead, f"risk.py kennt Actions ohne Aufgabe: {dead}"

# 5) Der Executor kennt keine Action, die nirgends eingestuft ist
for name in set(re.findall(r'action\.name == "([a-z_]+)"', executor_source)):
    assert name in risk.ACTION_RISK, f"{name} im Executor, aber nicht in risk.py"

# 6) Jede Aufgabe gehoert zu den Grundfaehigkeiten ODER zu genau einer schaltbaren Faehigkeit
import abilities
registered = {t.task_type for t in tasks}
claimed = [t for a in abilities.ABILITIES for t in a.tasks]
assert len(claimed) == len(set(claimed)), "Eine Aufgabe gehoert zu zwei Faehigkeiten"
assert not set(claimed) & set(abilities.CORE_TASKS)
assert registered == set(claimed) | set(abilities.CORE_TASKS), (
    "Aufgabe ohne Schalter-Zuordnung (abilities.py) oder Zuordnung ohne Aufgabe: "
    f"{registered ^ (set(claimed) | set(abilities.CORE_TASKS))}")
assert len({a.id for a in abilities.ABILITIES}) == len(abilities.ABILITIES)
for a in abilities.ABILITIES:
    assert a.label and len(a.description) >= 15, a.id

print("ALL TESTS PASSED")
