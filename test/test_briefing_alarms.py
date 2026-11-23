"""Tagesbriefing nennt auch die Wecker von heute; die allgemeine Frage nach dem Tag geht zum Briefing, Ziele nur auf ausdrueckliche Frage."""

import json
import sys
import webapp
import tempfile
import types
from datetime import datetime
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
import briefing
import jarvis as jarvis_module
import reminders
import risk
import timer
import widgets
from action import Action
from reminders import ReminderStore
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools import news_tool, weather_tool
from tools.tool_result import ToolResult


now = datetime(2026, 11, 23, 8, 30)
TODAY = "2026-11-23"

# 1) Satz: ein Wecker, mehrere, Beschriftung "Wecker" wird nicht wiederholt, andere Tage fehlen, Reihenfolge nach Uhrzeit
assert briefing.alarms_sentence([], TODAY) is None
assert briefing.alarms_sentence([{"text": "Wecker", "due": "2026-11-24T06:30"}], TODAY) is None
assert briefing.alarms_sentence([{"text": "Müll raus", "due": "2026-11-23T20:00"}], TODAY) == "Ein Wecker klingelt heute: um 20:00 Müll raus."
assert briefing.alarms_sentence([{"text": "Wecker", "due": "2026-11-23T20:00"}], TODAY) == "Ein Wecker klingelt heute: um 20:00."
two = [{"text": "Sport", "due": "2026-11-23T18:00"}, {"text": "Wecker", "due": "2026-11-23T07:00"}, {"text": "Morgen", "due": "2026-11-24T07:00"}]
assert briefing.alarms_sentence(two, TODAY) == "Wecker für heute: um 07:00, um 18:00 Sport."
many = [{"text": f"W{n}", "due": f"2026-11-23T1{n}:00"} for n in range(7)]
assert briefing.alarms_sentence(many, TODAY).endswith("und 2 weitere.")

# 2) build_briefing: Wecker stehen hinter den Erinnerungen und vor dem Wetter; ohne Quelle fehlt der Satz; Fehler lassen nur ihn aus
alarm = [{"text": "Müll raus", "due": "2026-11-23T20:00"}]
text = briefing.build_briefing(now, "Sir", reminder_items=lambda: [{"text": "Wäsche", "due": "2026-11-23T19:00"}],
                               alarm_items=lambda: alarm, weather=lambda: "Sonnig.")
assert text.index("Wäsche") < text.index("Ein Wecker klingelt heute: um 20:00 Müll raus.") < text.index("Sonnig."), text
assert "Wecker" not in briefing.build_briefing(now, "Sir", weather=lambda: "Sonnig.")
assert briefing.build_briefing(now, "Sir", alarm_items=lambda: 1 / 0, weather=lambda: "Sonnig.").endswith("Sonnig.")

# 3) Jarvis: das volle Briefing nennt den Wecker, mit ausgeschalteter Wecker-Faehigkeit nicht; das kurze Weckerbriefing bleibt wie es war
folder = Path(tempfile.mkdtemp())
clock = [now]
calendar = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
store = ReminderStore(folder / "r.json", now=lambda: clock[0], calendar=lambda: calendar)
reminders.set_default_store(store)
widgets.set_default_store(calendar)
store.add("Müll raus", "", "20:00", kind="alarm")
weather_tool.set_default_service(types.SimpleNamespace(summary=lambda: None))
news_tool.set_default_service(types.SimpleNamespace(get_news=lambda *a, **k: ToolResult(success=True, data={"items": []})))
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
j.client = None
j.apply_settings()
assert "Ein Wecker klingelt heute: um 20:00 Müll raus." in j.daily_briefing(), j.daily_briefing()
assert "Wecker" not in j.wakeup_briefing()                 # das kurze Weckerbriefing bleibt wie es war
j.settings_manager.set("abilities", "alarm", False)
assert "Müll raus" not in j.daily_briefing()
j.settings_manager.set("abilities", "alarm", True)

# 4) Beschreibungen: die allgemeine Frage nach dem Tag gehoert zum Briefing, Ziele nur auf ausdrueckliche Frage
registry = TaskRegistry()
register_all_tasks(registry)
brief = registry.get("GET_BRIEFING").goal
goals = registry.get("GOAL_OVERVIEW").goal
for phrase in ("Was steht heute an?", "Was steht bei mir an?", "Was habe ich heute vor?", "allgemein nach seinem Tag"):
    assert phrase in brief, phrase
assert "ausdrücklich nach Zielen" in goals and "nicht bei der allgemeinen Frage nach dem Tag" in goals

print("ALL TESTS PASSED")
