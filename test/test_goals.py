"""Ziele und Gewohnheiten (Mark 5, Step 2.28): Serien, Wochenleiste, Chat-Aufgabe, Abendfrage."""
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

import json
import tempfile
from datetime import date, datetime, timedelta

import abilities
import action_executor
import briefing
import guest
import jarvis as jarvis_module
import reminders
import risk
import widgets
import tools.goals_tool as goals_tool
from action import Action
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks
from widgets import WidgetStore

folder = Path(tempfile.mkdtemp())
day = [date(2026, 11, 1)]
store = WidgetStore(folder / "w.json", today=lambda: day[0])
GYM = {"text": "Gym", "done": True, "daily": True}


def goals(s=None):
    return {g["text"]: g for g in (s or store).get()["goals"]}


# 1) Serie: Tag fuer Tag abhaken
for n in range(1, 4):
    day[0] = date(2026, 11, n)
    store.set_goals([dict(GYM)])
    assert goals()["Gym"]["streak"] == n, (n, goals())
# Heute noch offen: Serie lebt (zaehlt bis gestern)
day[0] = date(2026, 11, 4)
assert goals()["Gym"] == {"text": "Gym", "done": False, "daily": True, "streak": 3}
store.set_goals([dict(GYM, done=False)])
assert goals()["Gym"]["streak"] == 3
store.set_goals([dict(GYM)])
assert goals()["Gym"]["streak"] == 4
store.set_goals([dict(GYM, done=False)])                       # Haken wieder weg: 4 -> 3
assert goals()["Gym"]["streak"] == 3
# Ein ausgelassener Tag (5. und 6. nie geoeffnet) bricht die Serie
day[0] = date(2026, 11, 7)
assert goals()["Gym"]["streak"] == 0
store.set_goals([dict(GYM)])
assert goals()["Gym"]["streak"] == 1
# Nur ein Tag Pause (gestern nicht erledigt, heute offen) -> 0
day[0] = date(2026, 11, 9)
assert goals()["Gym"]["streak"] == 0

# 2) Nur taegliche Ziele haben eine Serie; Gross/Klein und Leerzeichen sind dasselbe Ziel
day[0] = date(2026, 12, 1)
store = WidgetStore(folder / "w2.json", today=lambda: day[0])
store.set_goals([{"text": "Gym", "done": True, "daily": True}, {"text": "Steuer", "done": True, "daily": False}])
g = goals(store)
assert g["Gym"]["streak"] == 1 and "streak" not in g["Steuer"]
day[0] = date(2026, 12, 2)
store.set_goals([{"text": "  gym ", "done": True, "daily": True}])
assert goals(store)["gym"]["streak"] == 2, "gleiches Ziel trotz anderer Schreibweise"
assert WidgetStore.goal_key("  GyM   Training ") == "gym training"
# Ziel einmalig machen: keine Serie mehr angezeigt
store.set_goals([{"text": "gym", "done": True, "daily": False}])
assert "streak" not in goals(store)["gym"]
store.set_goals([{"text": "gym", "done": True, "daily": True}])
assert goals(store)["gym"]["streak"] == 2, "Verlauf bleibt erhalten"
# Doppelte Eintraege: erledigt zaehlt, wenn eines erledigt ist
store.set_goals([{"text": "Lesen", "done": False, "daily": True}, {"text": "lesen", "done": True, "daily": True}])
assert goals(store)["lesen"]["streak"] == 1
# Der Zustand von der Seite (inklusive streak-Feld) wird zurueckgeschickt: das Feld wird ignoriert, nicht gespeichert
store.set_goals(store.get()["goals"])
raw = json.loads((folder / "w2.json").read_text(encoding="utf-8"))
assert all("streak" not in i for i in raw["goals"]["items"]), raw["goals"]

# 3) Wochenleiste
day[0] = date(2026, 12, 10)
store = WidgetStore(folder / "w3.json", today=lambda: day[0])
assert store.get()["week"] == [{"date": f"2026-12-{d:02d}", "done": 0, "total": 0} for d in range(4, 11)]
for d, done in ((8, True), (9, False), (10, True)):
    day[0] = date(2026, 12, d)
    store.set_goals([{"text": "Gym", "done": done, "daily": True}, {"text": "Lesen", "done": True, "daily": True},
                     {"text": "Einmalig", "done": True, "daily": False}])
week = store.get()["week"]
assert len(week) == 7 and week[0]["date"] == "2026-12-04" and week[-1]["date"] == "2026-12-10"
assert [(w["done"], w["total"]) for w in week] == [(0, 0), (0, 0), (0, 0), (0, 0), (2, 2), (1, 2), (2, 2)]
day[0] = date(2026, 12, 11)                                    # neuer Tag: heute zaehlt aus der aktuellen Liste (alles offen)
week = store.get()["week"]
assert week[-1] == {"date": "2026-12-11", "done": 0, "total": 2} and week[-2] == {"date": "2026-12-10", "done": 2, "total": 2}
assert week[0]["date"] == "2026-12-05"

# 4) Verlauf wird begrenzt, kaputter Verlauf stoert nicht
day[0] = date(2026, 1, 1)
store = WidgetStore(folder / "w4.json", today=lambda: day[0])
for n in range(widgets.HISTORY_DAYS + 30):
    day[0] = date(2026, 1, 1) + timedelta(days=n)
    store.set_goals([dict(GYM)])
hist = json.loads((folder / "w4.json").read_text(encoding="utf-8"))["history"]
assert len(hist) == widgets.HISTORY_DAYS and day[0].isoformat() in hist and "2026-01-01" not in hist
assert store.get()["goals"][0]["streak"] == widgets.HISTORY_DAYS, "Serie hoechstens so lang wie der Verlauf"
(folder / "w5.json").write_text(json.dumps({"history": {"kaputt": {"a": True}, "2026-01-01": "x", "2026-01-02": {"a": "ja", 5: True}, "2026-01-03": {"a": True}},
                                            "goals": {"date": "2026-01-04", "items": [{"text": "A", "done": False, "daily": True}]}}), encoding="utf-8")
s5 = WidgetStore(folder / "w5.json", today=lambda: date(2026, 1, 4))
assert s5.get()["goals"] == [{"text": "A", "done": False, "daily": True, "streak": 1}]
(folder / "w6.json").write_text('{"history": [1, 2]}', encoding="utf-8")
assert WidgetStore(folder / "w6.json", today=lambda: date(2026, 1, 4)).get()["week"][-1]["total"] == 0
# Ziele und Verlauf: Notizen speichern loescht den Verlauf nicht
store.set_notes("x")
assert "history" in json.loads((folder / "w4.json").read_text(encoding="utf-8"))
# Alle Ziele loeschen: heutiger Verlauf weg, frueherer bleibt
day[0] = date(2026, 6, 1)
store = WidgetStore(folder / "w7.json", today=lambda: day[0])
store.set_goals([dict(GYM)])
store.set_goals([])
assert json.loads((folder / "w7.json").read_text(encoding="utf-8"))["history"] == {}

# 7) Chat-Aufgabe goal_overview
day[0] = date(2026, 12, 11)
store = WidgetStore(folder / "w8.json", today=lambda: day[0])
for d in (9, 10):
    day[0] = date(2026, 12, d)
    store.set_goals([{"text": "Gym", "done": True, "daily": True}, {"text": "Steuer", "done": False, "daily": False}])
day[0] = date(2026, 12, 11)
res = goals_tool.goal_overview(store)
assert res.success and res.data["date"] == "2026-12-11" and res.data["open"] == 1
assert res.data["goals"] == [{"text": "Gym", "daily": True, "done": False, "streak": 2}]
assert res.data["week"][-1] == {"date": "2026-12-11", "weekday": "Freitag", "done": 0, "total": 1}
assert res.data["week"][-2]["weekday"] == "Donnerstag" and res.data["week"][-2]["done"] == 1
store.set_goals([{"text": "Gym", "done": True, "daily": True}, {"text": "Steuer", "done": False, "daily": False},
                 {"text": "Lesen", "done": False, "daily": False}])
both = goals_tool.goal_overview(store).data
assert len(both["goals"]) == 3 and both["open"] == 2, "offen zaehlt nur nicht erledigte"
store.set_goals([{"text": "Gym", "done": False, "daily": True}])
class Broken:
    def get(self):
        raise OSError("weg")
res = goals_tool.goal_overview(Broken())
assert not res.success and "OSError" in res.error and "weg" not in res.error
widgets.set_default_store(store)
assert action_executor.execute_action(Action("goal_overview", {})).data["goals"][0]["streak"] == 2
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("GOAL_OVERVIEW")
assert [a.name for a in task.actions] == ["goal_overview"] and task.actions[0].parameters == {}
assert risk.task_risk(task) == risk.SAFE and risk.ACTION_RISK["goal_overview"] == risk.SAFE
ab = next(a for a in abilities.ABILITIES if a.id == "goals")
assert ab.tasks == ("GOAL_OVERVIEW",) and ab.default is True and "GOAL_OVERVIEW" not in guest.GUEST_TASKS
src = open(PROJECT_DIR / "tools" / "goals_tool.py", encoding="utf-8").read().split('"""', 2)[2]
assert "set_goals" not in src and "_save" not in src and "write" not in src

# 8) Abendtext
now = datetime(2026, 12, 11, 20, 5)
sample = [{"text": "Gym", "done": False, "daily": True, "streak": 5}, {"text": "Lesen", "done": True, "daily": True, "streak": 1},
          {"text": "Steuer", "done": False, "daily": False}]
text = briefing.evening_text(sample, "Sir", now)
assert text == ("Sir, es ist 20:05 Uhr. Noch offen: Gym, Steuer (1 von 3 erledigt). "
                "Diese Serie reißt, wenn sie heute offen bleibt: Gym (5 Tage). Soll ich dir dabei helfen?"), text
assert briefing.evening_text([{"text": "A", "done": False, "daily": True, "streak": 1}], "Sir", now) == \
    "Sir, es ist 20:05 Uhr. Noch offen: A. Soll ich dir dabei helfen?", "Serie 1 reisst nichts (kaum etwas zu verlieren)"
assert briefing.evening_text([{"text": "A", "done": True}], "Sir", now) is None and briefing.evening_text([], "Sir", now) is None
assert briefing.evening_text([5, None, {"text": " "}], "Sir", now) is None

# 9) Jarvis.evening_goals: aus per Voreinstellung, ab Stunde, einmal am Tag, nur mit offenen Zielen
clock = [datetime(2026, 12, 11, 19, 0)]
cal = WidgetStore(folder / "w9.json", today=lambda: clock[0].date())
widgets.set_default_store(cal)
reminders.set_default_store(reminders.ReminderStore(folder / "r.json", now=lambda: clock[0], calendar=lambda: cal))
briefing.set_evening_marker(briefing.DailyMarker(folder / "g_state.json"))
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
cal.set_goals([{"text": "Gym", "done": False, "daily": True}])
clock[0] = datetime(2026, 12, 11, 21, 0)
assert j.settings_manager.get("goals", "evening", None) is False and j.evening_goals() is None, "Voreinstellung aus"
j.settings_manager.set("goals", "evening", True)
j.settings_manager.set("goals", "evening_hour", 22)
assert j.evening_goals() is None, "noch vor der Stunde"
j.settings_manager.set("goals", "evening_hour", 20)
first = j.evening_goals()
assert first and first.startswith("Sir, es ist 21:00 Uhr. Noch offen: Gym"), first
assert j.evening_goals() is None, "einmal am Tag"
clock[0] = datetime(2026, 12, 12, 21, 0)
cal.set_goals([{"text": "Gym", "done": True, "daily": True}])
assert j.evening_goals() is None and briefing.evening_marker().last_day() == "2026-12-11", "alles erledigt: nichts, nicht markiert"
cal.set_goals([{"text": "Gym", "done": False, "daily": True}])
assert j.evening_goals().startswith("Sir, es ist 21:00 Uhr")
clock[0] = datetime(2026, 12, 13, 21, 0)
j.settings_manager.set("abilities", "goals", False)
assert j.evening_goals() is None and briefing.evening_marker().last_day() == "2026-12-12", "Faehigkeit aus"
j.settings_manager.set("abilities", "goals", True)
j.guest = True
assert j.evening_goals() is None
del j.guest
assert j.evening_goals() is not None
cal.get = lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))
clock[0] = datetime(2026, 12, 14, 21, 0)
assert j.evening_goals() is None and briefing.evening_marker().last_day() == "2026-12-13", "Fehler: kein Text, Tag bleibt offen"

# 10) Einstellungen, Server, Oberflaeche
fresh = SettingsManager(folder / "fresh.json")
assert fresh.get_all()["goals"] == {"evening": False, "evening_hour": 20}
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
assert 'EDITABLE_SETTINGS[("goals", "evening")]' in server_source and 'EDITABLE_SETTINGS[("goals", "evening_hour")] = lambda v: _is_int(v, 17, 23)' in server_source
post = server_source.split("def do_POST")[1]
assert post.index("self.server.guest and path") < post.index("/api/goals/evening") < post.rindex("with self.server.message_lock:")
app_js = open(PROJECT_DIR / "web" / "app.js", encoding="utf-8").read()
assert '"/api/goals/evening"' in app_js and 'category: "goals", key: "evening"' in app_js and 'key: "evening_hour"' in app_js
assert "w-streak" in app_js and "w-week" in app_js and "setInterval(checkEvening" in app_js and "setTimeout(checkEvening, 4000)" in app_js
assert ".w-streak" in open(PROJECT_DIR / "web" / "style.css", encoding="utf-8").read()

print("ALL TESTS PASSED")
