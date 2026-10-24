"""Erinnerungen (Mark 5, Step 2.9): Fake-Uhr, Neustart, Kalender-Kopplung, ohne Wartezeiten getestet."""

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
import json
import tempfile
import time
from datetime import date, datetime, timedelta

import background_tasks
import guest
import jarvis as jarvis_module
import reminders
import widgets
from reminders import ReminderError, ReminderScheduler, ReminderStore, parse_time, describe_due

folder = Path(tempfile.mkdtemp())
clock = [datetime(2026, 10, 22, 9, 30, 15)]
now = lambda: clock[0]
calendar = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
store = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
reminders.set_default_store(store)

# 1) Uhrzeit-Parser: alle Schreibweisen aus Sprache und Text
for raw, expected in (("19:00", "19:00"), ("1900", "19:00"), ("19.30", "19:30"), ("19", "19:00"), ("7", "07:00"),
                      ("730", "07:30"), ("0730", "07:30"), ("19 Uhr", "19:00"), ("19:30 Uhr", "19:30"), ("19 Uhr 30", "19:30"),
                      ("7pm", "19:00"), ("7:30 PM", "19:30"), ("12am", "00:00"), ("12 pm", "12:00"), (" 00:00 ", "00:00"),
                      ("23:59", "23:59")):
    assert parse_time(raw) == expected, (raw, parse_time(raw))
for bad in ("", "abc", "24:00", "19:60", "2500", "13pm", "0pm", "19:5", "1:2:3", None, 19, "ganztägig", "19:00; DROP"):
    assert parse_time(bad) is None, bad

# 2) Anlegen: gespeichert, im Kalender als "⏰ Text" mit Uhrzeit
e = store.add("Wäsche aufhängen", "2026-10-22", "1900")
assert e["due"] == "2026-10-22T19:00" and not e["rolled"] and e["event_id"]
events = calendar.get()["events"]
assert [(x["title"], x["date"], x["time"]) for x in events] == [("⏰ Wäsche aufhängen", "2026-10-22", "19:00")]
assert json.loads((folder / "r.json").read_text(encoding="utf-8"))["reminders"][0]["text"] == "Wäsche aufhängen"
assert describe_due(e["due"], clock[0]) == "heute um 19:00"

# 3) Kein Datum: heute, wenn die Zeit noch kommt, sonst morgen (mit Hinweis)
assert store.add("A", "", "10:00")["due"] == "2026-10-22T10:00"
r = store.add("B", None, "08:00")
assert r["due"] == "2026-10-23T08:00" and r["rolled"] and describe_due(r["due"], clock[0]) == "morgen um 08:00"
assert store.add("C", "heute", "09:30")["due"] == "2026-10-23T09:30", "genau jetzt gilt als vorbei"

# 4) Ungültiges wird abgelehnt, mit verständlichem Satz, ohne etwas zu speichern
before = (len(store.list()), len(calendar.get()["events"]))
for args, part in ((("", "2026-10-22", "19:00"), "Woran"), (("   ", "2026-10-22", "19:00"), "Woran"), ((None, "2026-10-22", "19:00"), "Woran"),
                   (("x" * 91, "2026-10-22", "19:00"), "höchstens"), (("X", "2026-10-22", ""), "Um wie viel Uhr"),
                   (("X", "2026-10-22", "25:00"), "Um wie viel Uhr"), (("X", "morgen", "19:00"), "Datum"),
                   (("X", "2026-02-30", "19:00"), "Datum"), (("X", "2026-10-22", "09:00"), "vorbei"),
                   (("X", "2026-10-21", "19:00"), "vorbei"), (("X", "2028-10-22", "19:00"), "Tage im Voraus")):
    try:
        store.add(*args)
        raise AssertionError(args)
    except ReminderError as error:
        assert part in str(error), (args, str(error))
assert (len(store.list()), len(calendar.get()["events"])) == before

# 5) Text wird gesäubert, Steuerzeichen und Zeilenumbrüche raus
r = store.add("Ruf\nMama\x00 an‮", "2026-10-24", "18:00")
assert r["text"] == "Ruf Mama an" and "\x00" not in calendar.get()["events"][-1]["title"]

# 6) Liste: nach Zeit sortiert, Nummer 1 = die nächste
texts = [x["text"] for x in store.list()]
assert texts == ["A", "Wäsche aufhängen", "B", "C", "Ruf Mama an"], texts

# 7) Normale Termine bleiben unberührt: Kalender-Termin des Nutzers überlebt Fälligkeit und Löschen
mine = calendar.add_event("Zahnarzt", "2026-10-22", "10:00")

# 8) Fällig werden: Uhr vorstellen -> genau eine Meldung, aus Datei UND Kalender entfernt
sent = []
scheduler = ReminderScheduler(store, submit=sent.append)
assert scheduler.check() == 0 and sent == []
clock[0] = datetime(2026, 10, 22, 10, 0, 5)
assert scheduler.check() == 1
assert sent == [{"type": "REMINDER_DUE", "data": {"text": "A", "due": "2026-10-22T10:00", "missed": False}}]
assert scheduler.check() == 0, "nur einmal"
assert "A" not in [x["text"] for x in store.list()]
titles = [x["title"] for x in calendar.get()["events"]]
assert "⏰ A" not in titles and "Zahnarzt" in titles and "⏰ Wäsche aufhängen" in titles

# 9) Neustart: neue Objekte lesen dieselbe Datei; eine verpasste Erinnerung kommt mit "missed"
store2 = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
assert [x["text"] for x in store2.list()] == ["Wäsche aufhängen", "B", "C", "Ruf Mama an"]
clock[0] = datetime(2026, 10, 22, 21, 0, 0)       # Jarvis war zwischen 19:00 und 21:00 aus
sent2 = []
ReminderScheduler(store2, submit=sent2.append).check()
assert sent2 == [{"type": "REMINDER_DUE", "data": {"text": "Wäsche aufhängen", "due": "2026-10-22T19:00", "missed": True}}]
assert "⏰ Wäsche aufhängen" not in [x["title"] for x in calendar.get()["events"]]
# eine Minute zu spät ist noch nicht "verpasst"
clock[0] = datetime(2026, 10, 23, 8, 1, 0)
sent3 = []
ReminderScheduler(store2, submit=sent3.append).check()
assert sent3[0]["data"]["text"] == "B" and sent3[0]["data"]["missed"] is False

# 10) Löschen: Nummer, Stichwort, mehrdeutig, unbekannt, alle; Kalender wird mitgeräumt
clock[0] = datetime(2026, 10, 22, 8, 0, 0)
store.add("Müll rausbringen", "2026-10-25", "07:00")
store.add("Müll sortieren", "2026-10-26", "07:00")
store.add("Pizza bestellen", "2026-10-27", "19:00")
for which, part in (("", "Welche"), ("7", "Nummer 7"), ("0", "Nummer 0"), ("Müll", "mehrere"), ("Auto", "Keine Erinnerung passt")):
    try:
        store.cancel(which)
        raise AssertionError(which)
    except ReminderError as error:
        assert part in str(error), (which, str(error))
        assert "Offen:" in str(error) or which == ""
removed = store.cancel("pizza")
assert [x["text"] for x in removed] == ["Pizza bestellen"]
assert "⏰ Pizza bestellen" not in [x["title"] for x in calendar.get()["events"]]
first = store.list()[0]["text"]
assert [x["text"] for x in store.cancel("Nummer 1")] == [first] and [x["text"] for x in store.cancel("#1")] != [first]
assert reminders.is_all("Alle") and reminders.is_all("alle Erinnerungen.") and not reminders.is_all("1") and not reminders.is_all(None)
store.cancel("alle")
assert store.list() == [] and [x["title"] for x in calendar.get()["events"] if x["title"].startswith("⏰")] == []
assert "Zahnarzt" in [x["title"] for x in calendar.get()["events"]], "normale Termine bleiben"
try:
    store.cancel("1")
    raise AssertionError
except ReminderError as error:
    assert "keine offenen" in str(error)

# 11) Der Nutzer löscht den Kalendereintrag selbst: Erinnerung kommt trotzdem, ohne Fehler
r = store.add("Selbst gelöscht", "2026-10-22", "09:00")
calendar.delete_event(r["event_id"])
clock[0] = datetime(2026, 10, 22, 9, 0, 30)
sent4 = []
assert ReminderScheduler(store, submit=sent4.append).check() == 1 and sent4[0]["data"]["text"] == "Selbst gelöscht"

# 12) Kaputte oder fremde Datei: wird ignoriert, nie ein Absturz
bad = folder / "bad.json"
for content in ("", "{", "[]", '{"reminders": "x"}', '{"reminders": [1, {"id": 1}, {"id": "a", "text": "t", "due": "2026-13-45T99:99"}, {"id": "b", "text": "ok", "due": "2026-11-01T10:00"}]}'):
    bad.write_text(content, encoding="utf-8")
    items = ReminderStore(bad, now=now, calendar=lambda: calendar).list()
    assert items == ([{"id": "b", "text": "ok", "due": "2026-11-01T10:00", "event_id": None}] if "ok" in content else []), content

# 13) Grenzen: höchstens 50 offene; Kalender voll -> Erinnerung gilt trotzdem
limited = ReminderStore(folder / "lim.json", now=now, calendar=lambda: calendar)
clock[0] = datetime(2026, 10, 22, 8, 0, 0)
class FullCalendar:
    def add_event(self, *a): raise ValueError("voll")
    def delete_event(self, *a): raise ValueError("weg")
nocal = ReminderStore(folder / "nocal.json", now=now, calendar=lambda: FullCalendar())
assert nocal.add("Ohne Kalender", "2026-10-22", "12:00")["event_id"] is None
clock[0] = datetime(2026, 10, 22, 12, 0, 1)
assert len(nocal.pop_due()) == 1
clock[0] = datetime(2026, 10, 22, 8, 0, 0)
for i in range(reminders.MAX_OPEN):
    limited.add(f"R{i}", "2026-10-23", f"{i % 24:02d}:{i % 60:02d}")
try:
    limited.add("zu viel", "2026-10-23", "12:00")
    raise AssertionError
except ReminderError as error:
    assert "höchstens 50" in str(error)

# 14) Scheduler-Thread: läuft wirklich, meldet, stoppt, übersteht Fehler
real_now = datetime.now()
threaded = ReminderStore(folder / "t.json", now=datetime.now, calendar=lambda: calendar)
box = []
sch = ReminderScheduler(threaded, submit=box.append, interval=0.05)
soon = (real_now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
threaded.path.write_text(json.dumps({"reminders": [{"id": "z", "text": "Jetzt", "due": "2020-01-01T10:00", "event_id": None}]}), encoding="utf-8")
sch.start(); sch.start()
deadline = time.time() + 3
while not box and time.time() < deadline:
    time.sleep(0.02)
assert len(box) == 1 and box[0]["data"]["missed"] is True
class Boom:
    def pop_due(self): raise RuntimeError("kaputt")
boom = ReminderScheduler(Boom(), submit=box.append, interval=0.02)
boom.start(); time.sleep(0.15)
assert boom._thread.is_alive(), "Fehler beenden den Thread nicht"
boom.stop(); sch.stop(); time.sleep(0.2)
assert not boom._thread.is_alive() and not sch._thread.is_alive()

# 15) Meldungstext für den Chat
j = object.__new__(jarvis_module.Jarvis)
text = j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "Wäsche aufhängen", "due": "2026-10-22T19:00", "missed": False}})
assert text.endswith("Erinnerung: Wäsche aufhängen") and "nicht aktiv" not in text
text = j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "Wäsche", "due": "2026-10-22T19:00", "missed": True}})
assert "nicht aktiv" in text and "19:00" in text

# 16) Verdrahtung: Aufgaben, Risiko, Fähigkeit, Ausführung, Gast, Schalter
registry = TaskRegistry()
register_all_tasks(registry)
for name in ("SET_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER"):
    assert registry.get(name) is not None and name not in guest.GUEST_TASKS
assert risk.action_risk(Action("set_reminder", {"text": "x", "time": "19:00"})) == risk.SAFE
assert risk.action_risk(Action("list_reminders", {})) == risk.SAFE
assert risk.action_risk(Action("cancel_reminder", {"which": "1"})) == risk.SAFE
assert risk.action_risk(Action("cancel_reminder", {"which": "Alle"})) == risk.CONFIRM
assert risk.action_risk(Action("cancel_reminder", {"which": "alle Erinnerungen"})) == risk.CONFIRM
assert any(a.id == "reminders" and set(a.tasks) == {"SET_REMINDER", "LIST_REMINDERS", "CANCEL_REMINDER"} for a in abilities.ABILITIES)
clock[0] = datetime(2026, 10, 22, 8, 0, 0)
reminders.set_default_store(ReminderStore(folder / "e.json", now=now, calendar=lambda: calendar))
run = action_executor.execute_action
out = run(Action("set_reminder", {"text": "Wäsche", "date": "", "time": "1900"}))
assert out.success and out.data["when"] == "heute um 19:00" and out.data["in_calendar"] is True and "note" not in out.data
out = run(Action("set_reminder", {"text": "Früh", "date": "", "time": "07:00"}))
assert out.success and out.data["when"] == "morgen um 07:00" and "morgen" in out.data["note"]
assert not run(Action("set_reminder", {"text": "", "time": "19:00"})).success
out = run(Action("list_reminders", {}))
assert [r["number"] for r in out.data["reminders"]] == [1, 2] and out.data["reminders"][0]["text"] == "Wäsche"
assert not run(Action("cancel_reminder", {"which": "9"})).success
assert run(Action("cancel_reminder", {"which": "Früh"})).data == {"cancelled": ["Früh"]}
run(Action("cancel_reminder", {"which": "alle"}))
assert run(Action("list_reminders", {})).data["reminders"] == [] and "Keine" in run(Action("list_reminders", {})).data["info"]
off = TaskRegistry(is_enabled=lambda t: t not in ("SET_REMINDER",))
register_all_tasks(off)
assert off.is_disabled("SET_REMINDER") and not off.is_disabled("LIST_REMINDERS")
reminders.set_default_store(None)

# 17) Server startet den Prüfer nur im normalen Modus, nie im Gastmodus
source = open(PROJECT_DIR / "server.py", encoding="utf-8").read().split("def main(")[1]
assert source.index("reminders.start_scheduler()") > source.index("jarvis = Jarvis()") > source.index("if args.guest:")
assert "start_scheduler" not in source.split("else:")[0]
assert "reminders.json" in open(PROJECT_DIR / ".gitignore", encoding="utf-8").read()

print("ALL TESTS PASSED")
