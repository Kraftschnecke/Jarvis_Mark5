"""Serien (Mark 5, Step 2.10): wiederkehrende Kalendereintraege und Erinnerungen, mit Fake-Uhr getestet."""

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
import http.client
import json
import tempfile
import threading
import types as _types
from datetime import date, datetime, timedelta

import guest
import jarvis as jarvis_module
import reminders
import server
import widgets
from reminders import ReminderError, ReminderScheduler, ReminderStore, describe_due
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
clock = [datetime(2026, 10, 22, 9, 30, 15)]            # Donnerstag
now = lambda: clock[0]
today = lambda: clock[0].date()
calendar = widgets.WidgetStore(folder / "w.json", today=today)
widgets.set_default_store(calendar)
store = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
reminders.set_default_store(store)
run = action_executor.execute_action
titles = lambda: [(e["date"], e["time"], e["title"]) for e in calendar.get()["events"]]

# ======================= Kalender-Serien =======================
# 1) Das Beispiel: Kurs jeden Dienstag 10 Uhr, die nächsten 8 Wochen
created = calendar.add_series("Kurs Uni", "2026-10-27", "10:00", "weekly", None, 8, None)
assert len(created) == 8 and created[0]["open_ended"] is False
events = calendar.get()["events"]
assert [e["date"] for e in events] == ["2026-10-27", "2026-11-03", "2026-11-10", "2026-11-17", "2026-11-24", "2026-12-01", "2026-12-08", "2026-12-15"]
assert len({e["series"] for e in events}) == 1 and all(e["repeat"] == "jeden Dienstag, 8 Mal" and e["time"] == "10:00" for e in events)
assert calendar.events_on("2026-11-10")[0]["title"] == "Kurs Uni"
assert "open_ended" not in events[0], "nur Antwort-Hinweis, nicht gespeichert"
assert not (folder / "w.json").read_text(encoding="utf-8").count("open_ended")

# 2) Einen Tag löschen: nur dieser Tag fehlt, die Serie bleibt
calendar.delete_event(events[2]["id"])
assert len(calendar.get()["events"]) == 7 and "2026-11-10" not in [e["date"] for e in calendar.get()["events"]]

# 3) Ganze Serie löschen; unbekannte Serie; fremde Termine bleiben
mine = calendar.add_event("Zahnarzt", "2026-10-28", "08:00")
series_id = calendar.get()["events"][0]["series"]
assert calendar.delete_series(series_id) == 7
assert titles() == [("2026-10-28", "08:00", "Zahnarzt")]
for bad in ("gibtsnicht", None, 5):
    try:
        calendar.delete_series(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

# 4) Ohne Wiederholung oder mit Anzahl 1: ein normaler Termin ohne Serien-Merker
single = calendar.add_series("Einmalig", "2026-11-02", "09:00", None, None, None, None)
assert len(single) == 1 and "series" not in calendar.events_on("2026-11-02")[0]
one = calendar.add_series("Nur einer", "2026-11-03", "", "weekly", None, 1, None)
assert len(one) == 1 and "series" not in calendar.events_on("2026-11-03")[0]

# 5) Enddatum, Monatsende
calendar.add_series("Tägliches Training", "2026-11-09", "07:00", "daily", None, None, "2026-11-13")
assert [e["date"] for e in calendar.get()["events"] if e["title"] == "Tägliches Training"] == ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
calendar.add_series("Miete", "2026-12-31", "", "monthly", None, 3, None)
assert [e["date"] for e in calendar.get()["events"] if e["title"] == "Miete"] == ["2026-12-31", "2027-01-31", "2027-02-28"]

# 6) Ungültiges: nichts wird gespeichert
before = titles()
for args, part in (
    (("X", "2026-11-05", "10:00", "daily", None, None, None), "braucht ein Ende"),
    (("X", "2026-11-05", "10:00", "manchmal", None, 3, None), "nicht verstanden"),
    (("X", "2026-11-05", "10:00", "weekly", None, 101, None), "Anzahl"),
    (("X", "2026-11-05", "10:00", "weekly", None, None, "2026-11-01"), "vor dem ersten"),
    (("X", "2026-11-05", "10:00", "daily", None, None, "2027-11-05"), "mehr als 100"),
    (("X", "2026-11-05", "10:00", "yearly", 5, 30, None), "zu weit"),
    (("X", "2026-11-05", "25:00", "weekly", None, 3, None), "Uhrzeit"),
    (("", "2026-11-05", "10:00", "weekly", None, 3, None), "Titel"),
    (("X", "2020-01-01", "10:00", "weekly", None, 3, None), "weit"),
):
    try:
        calendar.add_series(*args)
        raise AssertionError(args)
    except ValueError as error:
        assert part in str(error), (args, str(error))
assert titles() == before

# 7) Serie ohne Ende (Geburtstag): ein Jahr voraus, wächst mit der Zeit nach, gelöschte Tage kommen nicht wieder
calendar.add_series("Training Montag", "2026-10-26", "18:00", "weekly", None, None, None)
mondays = lambda: [e["date"] for e in calendar.get()["events"] if e["title"] == "Training Montag"]
assert len(mondays()) == 52 and mondays()[0] == "2026-10-26" and mondays()[-1] == "2027-10-18"
first_monday = [e for e in calendar.get()["events"] if e["title"] == "Training Montag"][1]
calendar.delete_event(first_monday["id"])                     # 2026-11-02 gelöscht
clock[0] = datetime(2026, 12, 1, 9, 0, 0)
assert mondays()[-1] == "2027-11-29" and "2026-11-02" not in mondays(), "nachgelegt, Gelöschtes bleibt weg"
assert len(mondays()) == 57, len(mondays())      # 26.10.2026 bis 29.11.2027 = 58 Montage, einer gelöscht
assert mondays().count("2026-11-09") == 1, "keine Doppelten"
clock[0] = datetime(2026, 10, 22, 9, 30, 15)
data = json.loads((folder / "w.json").read_text(encoding="utf-8"))
assert len(data["series"]) == 1 and data["series"][0]["rule"]["freq"] == "weekly"
calendar.add_series("Geburtstag Mama", "2026-11-14", "", "yearly", None, None, None)
assert [e["date"] for e in calendar.get()["events"] if e["title"] == "Geburtstag Mama"] == ["2026-11-14"]
clock[0] = datetime(2026, 12, 1, 9, 0, 0)
assert [e["date"] for e in calendar.get()["events"] if e["title"] == "Geburtstag Mama"] == ["2026-11-14", "2027-11-14"]
clock[0] = datetime(2026, 10, 22, 9, 30, 15)
oid = [e["series"] for e in calendar.get()["events"] if e["title"] == "Training Montag"][0]
calendar.delete_series(oid)
assert not [e for e in calendar.get()["events"] if e["title"] == "Training Montag"]
assert all(s["id"] != oid for s in json.loads((folder / "w.json").read_text(encoding="utf-8"))["series"]), "Merker weg"

# 8) Kaputte Datei: Serien-Einträge werden ignoriert, nichts stürzt ab
bad = folder / "bad.json"
bad.write_text(json.dumps({"series": [1, {"id": "a"}, {"id": "a", "title": "T", "time": "", "start": "2026-10-01", "label": "x",
                                                       "generated_until": "2026-10-01", "rule": {"freq": "daily"}}],
                           "events": [{"id": "e", "title": "T", "date": "2026-10-30", "time": "", "series": 7, "repeat": "x"}]}), encoding="utf-8")
w = widgets.WidgetStore(bad, today=today).get()
assert [e["title"] for e in w["events"]] == ["T"] and "series" not in w["events"][0]

# 9) Grenzen: Kalender voll, zu viele offene Serien
full = widgets.WidgetStore(folder / "full.json", today=today)
(folder / "full.json").write_text(json.dumps({"events": [
    {"id": f"i{n}", "title": "x", "date": "2026-11-01", "time": ""} for n in range(widgets.MAX_EVENTS - 3)]}), encoding="utf-8")
try:
    full.add_series("Zu viel", "2026-11-02", "", "weekly", None, 8, None)
    raise AssertionError
except ValueError as error:
    assert "höchstens" in str(error)
many = widgets.WidgetStore(folder / "many.json", today=today)
for n in range(widgets.MAX_SERIES):
    many.add_series(f"S{n}", "2026-11-02", "", "yearly", None, None, None)
try:
    many.add_series("Eine zu viel", "2026-11-02", "", "yearly", None, None, None)
    raise AssertionError
except ValueError as error:
    assert "Serien ohne Ende" in str(error)

# 10) Aufgabe/Executor: Beispielsatz, Antwortdaten, Fehler
out = run(Action("add_calendar_event", {"title": "Kurs", "date": "2026-10-27", "time": "10:00", "repeat": "weekly", "count": "8"}))
assert out.success and out.data["repeat"] == "jeden Dienstag, 8 Mal" and out.data["events_created"] == 8
assert out.data["last_date"].endswith("15.12.2026") and out.data["open_ended"] is False
out = run(Action("add_calendar_event", {"title": "Müll", "date": "2026-10-26", "time": "ganztägig", "repeat": "weekly"}))
assert out.success and out.data["open_ended"] is True and out.data["time"] == "ganztägig"
out = run(Action("add_calendar_event", {"title": "Normal", "date": "2026-11-04", "time": "11:00"}))
assert out.success and "repeat" not in out.data and out.data["title"] == "Normal"
assert not run(Action("add_calendar_event", {"title": "X", "date": "2026-11-04", "time": "11:00", "repeat": "daily"})).success
listing = run(Action("list_calendar_events", {"date": "2026-11-03"})).data["events"]
assert any(e.get("repeat") == "jeden Dienstag, 8 Mal" for e in listing)
assert "repeat" not in run(Action("list_calendar_events", {"date": "2026-11-04"})).data["events"][0]

# 11) Server: ganze Serie über die Schnittstelle löschen
settings = SettingsManager(folder / "s.json")
httpd = server.JarvisServer(("127.0.0.1", 0), _types.SimpleNamespace(settings_manager=settings, guest=False), widget_store=calendar)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def post(path, payload):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    body = json.loads(response.read())
    conn.close()
    return response.status, body


kurs = [e for e in calendar.get()["events"] if e["title"] == "Kurs"]
status, body = post("/api/widgets/events/delete_series", {"series": kurs[0]["series"]})
assert status == 200 and not [e for e in body["events"] if e["title"] == "Kurs"] and any(e["title"] == "Müll" for e in body["events"])
assert post("/api/widgets/events/delete_series", {"series": "gibtsnicht"})[0] == 400
assert post("/api/widgets/events/delete_series", {})[0] == 400
httpd.shutdown()

# ======================= wiederkehrende Erinnerungen =======================
clock[0] = datetime(2026, 10, 22, 9, 30, 15)
reminders_events = lambda: [e["title"] + "@" + e["date"] for e in calendar.get()["events"] if e["title"].startswith("⏰")]

# 12) Anlegen: ein Eintrag, nur der nächste Termin im Kalender; Anzeige-Infos
r = store.add("Kurs Uni", "2026-10-27", "09:30", "weekly", None, 3, None)
assert r["repeat"] == {"rule": {"freq": "weekly", "interval": 1, "count": 3, "until": None}, "start": "2026-10-27", "index": 0}
assert reminders_events() == ["⏰ Kurs Uni@2026-10-27"] and len(store.list()) == 1
assert ReminderStore.repeat_info(r) == {"repeat": "jeden Dienstag, 3 Mal", "left": 3}
assert ReminderStore.repeat_info({"text": "x"}) == {}
plain = store.add("Einzeln", "2026-10-25", "08:00")
assert "repeat" not in plain and "repeat" not in store.add("Count1", "2026-10-26", "08:00", "weekly", None, 1, None)
store.cancel("Einzeln"); store.cancel("Count1")

# 13) Auslösen: Meldung mit next_due, im Kalender wandert der Eintrag zum nächsten Termin
sent = []
sched = ReminderScheduler(store, submit=sent.append)
clock[0] = datetime(2026, 10, 27, 9, 30, 5)
assert sched.check() == 1
assert sent[-1]["data"] == {"text": "Kurs Uni", "due": "2026-10-27T09:30", "missed": False, "next_due": "2026-11-03T09:30"}
assert reminders_events() == ["⏰ Kurs Uni@2026-11-03"] and store.list()[0]["due"] == "2026-11-03T09:30"
assert store.list()[0]["repeat"]["index"] == 1 and ReminderStore.repeat_info(store.list()[0])["left"] == 2
assert sched.check() == 0
clock[0] = datetime(2026, 11, 3, 9, 30, 5)
sched.check()
assert sent[-1]["data"]["next_due"] == "2026-11-10T09:30"
clock[0] = datetime(2026, 11, 10, 9, 30, 5)
sched.check()
assert sent[-1]["data"] == {"text": "Kurs Uni", "due": "2026-11-10T09:30", "missed": False, "last_of_series": True}
assert store.list() == [] and reminders_events() == [], "nach dem dritten Mal ist die Serie weg"

# 14) Verpasst: drei Wochen aus -> EINE Meldung "verpasst", danach der nächste künftige Termin (verpasste zählen mit)
clock[0] = datetime(2026, 11, 11, 8, 0, 0)
store.add("Wöchentlich", "2026-11-16", "09:00", "weekly", None, 6, None)
clock[0] = datetime(2026, 12, 8, 12, 0, 0)               # 16.11., 23.11., 30.11., 07.12. verpasst
sent.clear()
assert sched.check() == 1
d = sent[0]["data"]
assert d["missed"] is True and d["due"] == "2026-11-16T09:00" and d["next_due"] == "2026-12-14T09:00", d
assert store.list()[0]["repeat"]["index"] == 4, "Termin 5 von 6 (die vier verpassten zählen mit)"
clock[0] = datetime(2026, 12, 14, 9, 0, 1)
sched.check()
assert sent[-1]["data"]["next_due"] == "2026-12-21T09:00" and not sent[-1]["data"]["missed"]
clock[0] = datetime(2026, 12, 21, 9, 0, 1)
sched.check()
assert sent[-1]["data"].get("last_of_series") is True and store.list() == []

# 15) Löschen: nur der nächste (Serie läuft weiter) / ganze Serie / bei Einzelnen wie bisher
clock[0] = datetime(2026, 10, 22, 9, 0, 0)
store.add("Serie A", "2026-10-26", "07:00", "weekly", None, 4, None)
removed = store.cancel("Serie A")
assert removed[0]["next_due"] == "2026-11-02T07:00" and store.list()[0]["due"] == "2026-11-02T07:00"
assert reminders_events() == ["⏰ Serie A@2026-11-02"]
removed = store.cancel("Serie A", "series")
assert removed[0]["next_due"] is None and store.list() == [] and reminders_events() == []
store.add("Serie B", "2026-10-26", "07:00", "weekly", None, 2, None)
store.cancel("Serie B"); assert store.list()[0]["due"] == "2026-11-02T07:00"
r = store.cancel("Serie B"); assert r[0]["next_due"] is None and store.list() == [], "letzter Termin: Serie endet"
store.add("Serie C", "2026-10-26", "07:00", "monthly", None, None, None)
store.add("Einzel", "2026-10-27", "07:00")
removed = store.cancel("alle")
assert len(removed) == 2 and all(x["next_due"] is None for x in removed) and store.list() == []
store.add("Offen", "2026-10-26", "07:00", "weekly", None, None, None)
store.cancel("Offen"); assert store.list()[0]["due"] == "2026-11-02T07:00"
store.cancel("Offen", "ganze Serie"); assert store.list() == []

# 16) Ungültiges und Neustart
for args, part in ((("X", "2026-10-26", "07:00", "daily", None, None, None), "braucht ein Ende"),
                   (("X", "2026-10-26", "07:00", "weekly", None, 101, None), "Anzahl"),
                   (("X", "2026-10-26", "07:00", "weekly", None, None, "2026-10-01"), "vor dem ersten"),
                   (("X", "2026-10-26", "07:00", "daily", None, None, "2027-10-26"), "mehr als 100"),
                   (("X", "2026-10-26", "07:00", "bald", None, 3, None), "nicht verstanden")):
    try:
        store.add(*args)
        raise AssertionError(args)
    except ReminderError as error:
        assert part in str(error), (args, str(error))
assert store.list() == [] and reminders_events() == []
store.add("Bleibt", "2026-10-26", "07:00", "weekly", None, 4, None)
again = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
assert again.list()[0]["repeat"]["index"] == 0 and ReminderStore.repeat_info(again.list()[0])["left"] == 4
(folder / "kaputt.json").write_text(json.dumps({"reminders": [
    {"id": "a", "text": "ok", "due": "2026-11-01T10:00", "repeat": {"rule": {"freq": "kaputt"}, "start": "2026-11-01", "index": 0}},
    {"id": "b", "text": "ok2", "due": "2026-11-01T11:00", "repeat": {"rule": {"freq": "weekly", "count": 3}, "start": "2026-11-01", "index": -1}},
    {"id": "c", "text": "ok3", "due": "2026-11-01T12:00", "repeat": {"rule": {"freq": "weekly", "count": 3}, "start": "2026-11-01", "index": 0}}]}), encoding="utf-8")
items = ReminderStore(folder / "kaputt.json", now=now, calendar=lambda: calendar).list()
assert [("repeat" in i) for i in items] == [False, False, True]
store.cancel("alle")

# 17) Executor und Risiko
import risk
out = run(Action("set_reminder", {"text": "Kurs", "date": "2026-10-27", "time": "09:30", "repeat": "weekly", "count": "8"}))
assert out.success and out.data["repeat"] == "jeden Dienstag, 8 Mal" and out.data["left"] == 8
out = run(Action("set_reminder", {"text": "Müll", "date": "2026-10-26", "time": "07:00", "repeat": "weekly"}))
assert out.success and out.data["repeat"] == "jeden Montag" and "left" not in out.data
out = run(Action("list_reminders", {}))
assert [r.get("repeat") for r in out.data["reminders"]] == ["jeden Montag", "jeden Dienstag, 8 Mal"] and out.data["reminders"][1]["left"] == 8
assert not run(Action("set_reminder", {"text": "X", "time": "09:00", "date": "2026-10-27", "repeat": "daily"})).success
out = run(Action("cancel_reminder", {"which": "Kurs"}))
assert out.success and out.data["only_next_removed_series_continues"][0]["text"] == "Kurs" and out.data["cancelled"] == []
out = run(Action("cancel_reminder", {"which": "Kurs", "scope": "series"}))
assert out.data == {"cancelled": ["Kurs"]}
assert run(Action("cancel_reminder", {"which": "Müll", "scope": "next"})).success
assert risk.action_risk(Action("cancel_reminder", {"which": "1"})) == risk.SAFE
assert risk.action_risk(Action("cancel_reminder", {"which": "1", "scope": "next"})) == risk.SAFE
for scope in ("series", "Serie", "ganze Serie", "all", "alle"):
    assert risk.action_risk(Action("cancel_reminder", {"which": "1", "scope": scope})) == risk.CONFIRM, scope
assert risk.action_risk(Action("cancel_reminder", {"which": "alle"})) == risk.CONFIRM

# 18) Chat-Meldungen
j = object.__new__(jarvis_module.Jarvis)
m = j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "Kurs", "due": "2026-10-27T09:30", "missed": False, "next_due": "2026-11-03T09:30"}})
assert m.endswith("Erinnerung: Kurs (die nächste kommt am Dienstag, 03.11. um 09:30)"), m
m = j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "Kurs", "due": "2026-10-27T09:30", "missed": False, "last_of_series": True}})
assert m.endswith("Erinnerung: Kurs (das war die letzte dieser Serie)"), m
m = j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "Kurs", "due": "2026-10-27T09:30", "missed": True, "next_due": "2026-11-03T09:30"}})
assert "nicht aktiv; die nächste kommt" in m, m
assert j.process_background_result({"type": "REMINDER_DUE", "data": {"text": "X", "due": "2026-10-27T09:30", "missed": False}}).endswith("Erinnerung: X")

# 19) Aufgabenbeschreibungen kennen die neuen Angaben, Gäste nicht
registry = TaskRegistry()
register_all_tasks(registry)
for task_name, params in (("ADD_CALENDAR_EVENT", ("repeat", "interval", "count", "until")), ("SET_REMINDER", ("repeat", "interval", "count", "until")),
                          ("CANCEL_REMINDER", ("scope",))):
    action = registry.get(task_name).actions[0]
    assert all(p in action.parameters for p in params), (task_name, params)
assert "ADD_CALENDAR_EVENT" not in guest.GUEST_TASKS

print("ALL TESTS PASSED")
