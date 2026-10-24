"""Kalender per Jarvis (Etappe C): Aufgaben ADD_CALENDAR_EVENT und LIST_CALENDAR_EVENTS."""

import sys
import tempfile
import types
from datetime import date, datetime
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

import action_executor
import risk
import router
import widgets
from action import Action
from task_registry import TaskRegistry
from tasks import register_all_tasks

store = widgets.WidgetStore(Path(tempfile.mkdtemp()) / "w.json", today=lambda: date(2026, 10, 21))
widgets.set_default_store(store)
run = action_executor.execute_action

registry = TaskRegistry()
register_all_tasks(registry)
add_task = registry.get("ADD_CALENDAR_EVENT")
list_task = registry.get("LIST_CALENDAR_EVENTS")
assert add_task is not None and list_task is not None
assert risk.task_risk(add_task) == risk.SAFE and risk.task_risk(list_task) == risk.SAFE

# Eintragen: mit Uhrzeit, ganztaegig (verschiedene Schreibweisen), Datum wird lesbar zurueckgegeben
result = run(Action("add_calendar_event", {"title": "Zahnarzt", "date": "2026-10-23", "time": "14:30"}))
assert result.success and result.data == {"title": "Zahnarzt", "date": "Freitag, 23.10.2026", "time": "14:30"}
for word in ("ganztägig", "ganztaegig", "none", ""):
    result = run(Action("add_calendar_event", {"title": "Tag " + word, "date": "2026-10-24", "time": word}))
    assert result.success and result.data["time"] == "ganztägig" and result.data["date"] == "Samstag, 24.10.2026", word
assert run(Action("add_calendar_event", {"title": "Ohne Zeit", "date": "2026-10-25", "time": None})).success
assert [e["time"] for e in store.events_on("2026-10-24")] == ["", "", "", ""]

# Fehler kommen als Ergebnis zurueck (kein Absturz), und es wird nichts gespeichert
count = len(store.get()["events"])
for params in ({"title": "A", "date": "morgen", "time": "10:00"}, {"title": "", "date": "2026-10-23", "time": ""},
               {"title": "A", "date": "2026-10-23", "time": "halb drei"}, {"title": "A", "date": "2099-01-01", "time": ""},
               {"title": 5, "date": "2026-10-23", "time": ""}, {"date": "2026-10-23", "time": ""}):
    result = run(Action("add_calendar_event", params))
    assert result.success is False and result.error, params
assert len(store.get()["events"]) == count

# Anzeigen: ein Tag, die naechsten, unverstandenes Datum
result = run(Action("list_calendar_events", {"date": "2026-10-23"}))
assert result.success and result.data == {"events": [{"date": "Freitag, 23.10.2026", "time": "14:30", "title": "Zahnarzt"}]}
result = run(Action("list_calendar_events", {"date": "2026-11-30"}))
assert result.success and result.data["events"] == [] and result.data["info"] == "Keine Termine."
result = run(Action("list_calendar_events", {"date": "naechste"}))
assert result.success and result.data["events"][0]["title"] == "Zahnarzt" and len(result.data["events"]) == 6
for bad in ("bald", "", None, 5):
    assert run(Action("list_calendar_events", {"date": bad})).success is False, bad

# Auswertung fuer Plan-Pruefung: alle Parameter sind benannt (Plan verlangt jeden Wert)
params = [name for a in add_task.actions for name in a.parameters]
assert params == ["title", "date", "time", "repeat", "interval", "count", "until"]

# Der Router kennt beide Aufgaben und weiss, welcher Tag heute ist
prompt = router.build_prompt("Trag morgen Zahnarzt ein", registry, today=datetime(2026, 10, 21, 7, 0))
assert "ADD_CALENDAR_EVENT" in prompt and "LIST_CALENDAR_EVENTS" in prompt
assert "2026-10-21 (Wednesday)" in prompt
assert "YYYY-MM-DD" in prompt
assert "Today's date is" in router.build_prompt("x", registry)
route = router.normalize_route({"kind": "TASK", "task_type": "ADD_CALENDAR_EVENT",
                                "parameters": {"title": "Zahnarzt", "date": "2026-10-22", "time": "ganztaegig"}}, registry)
assert route["kind"] == "TASK" and route["parameters"]["date"] == "2026-10-22"

# Die Gast-Version kennt den Kalender nicht
import guest
assert "ADD_CALENDAR_EVENT" not in guest.GUEST_TASKS and "LIST_CALENDAR_EVENTS" not in guest.GUEST_TASKS

# Jeder Name im Executor ist eingestuft (test_risk prueft das auch); hier: nichts Unbekanntes
assert risk.action_risk(Action("add_calendar_event")) == risk.SAFE
assert risk.action_risk(Action("delete_calendar_event")) == risk.FORBIDDEN

print("ALL TESTS PASSED")
