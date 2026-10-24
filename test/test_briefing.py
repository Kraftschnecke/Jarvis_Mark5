"""Tagesbriefing (Mark 5, Step 2.12): Sätze, Marker, Aufgabe, Jarvis-Verdrahtung, direkte Antwort ohne KI."""

import json
import sys
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

# 1) Ziele
assert briefing.goals_sentence([]) is None
assert briefing.goals_sentence([{"text": "  ", "done": False}, "x"]) is None
assert briefing.goals_sentence([{"text": "Sport", "done": False}]) == "Offenes Ziel für heute: Sport."
assert briefing.goals_sentence([{"text": "Sport", "done": True}]) == "Dein Ziel für heute ist schon erledigt."
assert briefing.goals_sentence([{"text": "A", "done": True}, {"text": "B", "done": True}]) == "Alle Ziele für heute sind schon erledigt."
assert briefing.goals_sentence([{"text": "A", "done": True}, {"text": "B"}, {"text": "C"}]) == "Offene Ziele für heute: B, C (1 von 3 erledigt)."
many = [{"text": f"Z{n}"} for n in range(8)]
assert briefing.goals_sentence(many) == "Offene Ziele für heute: Z0, Z1, Z2, Z3, Z4 und 3 weitere."

# 2) Timer
assert briefing.timers_sentence([]) is None
assert briefing.timers_sentence([{"name": "Nudeln", "remaining": 300}]) == "Ein Timer läuft: Nudeln, noch 5 Minuten."
assert briefing.timers_sentence([{"name": "Timer", "remaining": 45}]) == "Ein Timer läuft: noch 45 Sekunden."
two = briefing.timers_sentence([{"name": "Nudeln", "remaining": 300}, {"name": "Timer", "remaining": 3900}])
assert two == "2 Timer laufen: Nudeln, noch 5 Minuten; noch 1 Stunde 5 Minuten.", two

# 3) Schlagzeilen: bereinigt, höchstens 3, leer -> kein Satz
assert briefing.news_sentence([]) is None and briefing.news_sentence([{"title": "  "}, 5]) is None
items = [{"source": "Tagesschau", "title": "Erste​ Meldung"}, {"source": "heise", "title": "Zweite"},
         {"source": "Spiegel", "title": "Dritte"}, {"source": "BBC", "title": "Vierte"}]
sentence = briefing.news_sentence(items)
assert sentence == "Schlagzeilen: Tagesschau: Erste Meldung; heise: Zweite; Spiegel: Dritte.", sentence
long_title = briefing.news_sentence([{"source": "X", "title": "w" * 500}])
assert len(long_title) < 160

# 4) build_briefing: Reihenfolge, Fehler in einem Teil lassen nur diesen aus
now = datetime(2026, 10, 22, 8, 30)
def boom():
    raise RuntimeError("kaputt")
text = briefing.build_briefing(now, "Sir", events=lambda: [], reminder_items=boom, weather=lambda: "Sonnig.",
                               goals=lambda: [{"text": "Sport"}], timers=boom, news=lambda: [{"source": "A", "title": "B"}])
assert text == ("Guten Morgen, Sir. Es ist 08:30 Uhr, Donnerstag, der 22. Oktober. Heute stehen keine Termine an. Sonnig. "
                "Offenes Ziel für heute: Sport. Schlagzeilen: A: B."), text
only = briefing.build_briefing(now, "Sir")
assert only == "Guten Morgen, Sir. Es ist 08:30 Uhr, Donnerstag, der 22. Oktober."

# 5) Marker: einmal pro Tag, kaputte Datei zählt als "noch nie"
folder = Path(tempfile.mkdtemp())
marker = briefing.DailyMarker(folder / "m.json")
assert marker.last_day() is None and marker.is_due("2026-10-22")
marker.mark("2026-10-22")
assert marker.last_day() == "2026-10-22" and not marker.is_due("2026-10-22") and marker.is_due("2026-10-23")
assert not list(folder.glob("*.tmp"))
(folder / "m.json").write_text("{kaputt", encoding="utf-8")
assert marker.last_day() is None and marker.is_due("2026-10-22")
(folder / "m.json").write_text('["x"]', encoding="utf-8")
assert marker.last_day() is None

# 6) Aktion get_briefing
briefing.set_provider(None)
result = briefing.get_briefing()
assert not result.success and "nicht verfügbar" in result.error
briefing.set_provider(lambda: "Fertig.")
assert briefing.get_briefing().data == {"briefing": "Fertig."}
briefing.set_provider(boom)
failed = briefing.get_briefing()
assert not failed.success and "RuntimeError" in failed.error and "kaputt" not in failed.error
briefing.set_provider(lambda: "Aus dem Executor.")
done = action_executor.execute_action(Action("get_briefing"))
assert done.success and done.data["briefing"] == "Aus dem Executor."

# 7) Aufgabe, Risiko, Fähigkeit
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("GET_BRIEFING")
assert task is not None and [a.name for a in task.actions] == ["get_briefing"] and task.actions[0].parameters == {}
assert risk.task_risk(task) == risk.SAFE
ability = [a for a in abilities.ABILITIES if a.id == "briefing"][0]
assert ability.tasks == ("GET_BRIEFING",) and ability.default is True
assert "GET_BRIEFING" not in abilities.CORE_TASKS

# 8) Jarvis: daily_briefing mit Fähigkeiten, auto_briefing, direkte Antwort
clock = [datetime(2026, 10, 22, 8, 30)]
calendar = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
store = ReminderStore(folder / "r.json", now=lambda: clock[0], calendar=lambda: calendar)
reminders.set_default_store(store)
widgets.set_default_store(calendar)
calendar.add_event("Kurs Uni", "2026-10-22", "09:00")
calendar.set_goals([{"text": "Sport", "done": False, "daily": False}, {"text": "Lesen", "done": True, "daily": False}])
store.add("Wäsche", "", "19:00")
timer.start_timer(300, "Nudeln")


class FakeWeather:
    calls = 0
    def summary(self):
        FakeWeather.calls += 1
        return "In Mannheim sind es 9 °C."


class FakeNews:
    calls = []
    def get_news(self, source="alle", topic="", count=3):
        FakeNews.calls.append((source, topic, count))
        return ToolResult(success=True, data={"items": [{"source": "Tagesschau", "title": "Etwas passiert <b>heute</b>"}]})


weather_tool.set_default_service(FakeWeather())
news_tool.set_default_service(FakeNews())
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
j.client = None                                    # ein Modellaufruf wäre hier ein Fehler
j.apply_settings()
assert briefing._provider == j.daily_briefing

full = j.daily_briefing()
assert full.startswith("Guten Morgen, Sir. Es ist 08:30 Uhr, Donnerstag, der 22. Oktober. Heute steht ein Termin an: um 09:00 Kurs Uni. "
                       "Erinnerungen für heute: um 19:00 Wäsche. In Mannheim sind es 9 °C. Offenes Ziel für heute: Sport (1 von 2 erledigt). "
                       "Ein Timer läuft: Nudeln, noch "), full
assert full.endswith("Schlagzeilen: Tagesschau: Etwas passiert heute."), full
assert FakeNews.calls == [("alle", "", 3)]
assert "<b>" not in full

# Fähigkeiten einzeln aus: der Teil fehlt und es wird nichts abgerufen
FakeWeather.calls = 0
FakeNews.calls.clear()
for ability_id, absent in (("weather", "Mannheim"), ("news", "Schlagzeilen"), ("calendar", "Kurs Uni"),
                           ("reminders", "Wäsche"), ("timers", "Nudeln")):
    j.settings_manager.set("abilities", ability_id, False)
    out = j.daily_briefing()
    assert absent not in out, (ability_id, out)
    j.settings_manager.set("abilities", ability_id, True)
assert FakeWeather.calls == 4 and len(FakeNews.calls) == 4                       # nur bei den Läufen, in denen sie an waren
j.settings_manager.set("briefing", "news", False)
FakeNews.calls.clear()
assert "Schlagzeilen" not in j.daily_briefing() and FakeNews.calls == []
j.settings_manager.set("briefing", "news", True)

# Nachrichtenfehler: nur der Satz fehlt
class BrokenNews:
    def get_news(self, *a, **k):
        return ToolResult(success=False, error="nicht erreichbar")
news_tool.set_default_service(BrokenNews())
assert "Schlagzeilen" not in j.daily_briefing() and "Sport" in j.daily_briefing()
news_tool.set_default_service(FakeNews())

# Schnellweg ohne KI: Antwort ist der fertige Text
route = {"kind": "TASK", "task_type": "GET_BRIEFING", "parameters": {}}
j.task_registry = registry
reply = j.run_task("Briefing", route)
assert reply["status"] == "response" and reply["content"].startswith("Guten Morgen, Sir.") and "Schlagzeilen" in reply["content"]
briefing.set_provider(boom)
reply = j.run_task("Briefing", route)
assert reply["content"].startswith("Sir: Das Briefing konnte nicht erstellt werden"), reply
briefing.set_provider(j.daily_briefing)

# auto_briefing: standardmäßig aus, dann genau einmal pro Tag
briefing.set_default_marker(briefing.DailyMarker(folder / "state.json"))
assert j.auto_briefing() is None                                                  # Voreinstellung aus
j.settings_manager.set("briefing", "auto", True)
first = j.auto_briefing()
assert first and first.startswith("Guten Morgen, Sir.")
assert j.auto_briefing() is None                                                  # am selben Tag nicht noch einmal
clock[0] = datetime(2026, 10, 23, 7, 0)
assert j.auto_briefing().startswith("Guten Morgen, Sir.")                         # nächster Tag wieder
assert j.auto_briefing() is None
clock[0] = datetime(2026, 10, 24, 7, 0)
j.settings_manager.set("abilities", "briefing", False)
assert j.auto_briefing() is None and briefing.default_marker().last_day() == "2026-10-23"   # Fähigkeit aus: nichts, nicht markiert
j.settings_manager.set("abilities", "briefing", True)
briefing.set_provider(boom)
j.daily_briefing = boom                                                            # Aufbau scheitert: kein Text, Tag bleibt offen
assert j.auto_briefing() is None and briefing.default_marker().last_day() == "2026-10-23"
del j.daily_briefing
j.guest = True
assert j.auto_briefing() is None
del j.guest

# 9) Einstellungen, Server, Gast
assert j.settings_manager.get_all()["briefing"] == {"auto": True, "news": True}
fresh = SettingsManager(folder / "fresh.json")
assert fresh.get_all()["briefing"] == {"auto": False, "news": True}
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
assert 'EDITABLE_SETTINGS[("briefing", "auto")]' in server_source and 'EDITABLE_SETTINGS[("briefing", "news")]' in server_source
post = server_source.split("def do_POST")[1]
assert post.index("self.server.guest and path") < post.index("/api/briefing/auto") < post.rindex("with self.server.message_lock:")
app_js = open(PROJECT_DIR / "web" / "app.js", encoding="utf-8").read()
assert '"/api/briefing/auto"' in app_js and 'category: "briefing", key: "auto"' in app_js
assert "briefing_state.json" in open(PROJECT_DIR / ".gitignore", encoding="utf-8").read()
import guest
assert "GET_BRIEFING" not in guest.GUEST_TASKS

for left in timer.list_timers():
    timer.cancel_timer_by_id(left["id"])
print("ALL TESTS PASSED")
