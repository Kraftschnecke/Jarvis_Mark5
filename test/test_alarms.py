"""Wecker (Mark 5, Step 2.11): Eintragsart alarm, Scheduler mit Klingeln, Aufgaben, Briefing, Jarvis-Verdrahtung."""

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
import background_tasks
import briefing
import guest
import jarvis as jarvis_module
import reminders
import ringing
import risk
import timer
import widgets
from action import Action
from reminders import ReminderError, ReminderScheduler, ReminderStore
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks

folder = Path(tempfile.mkdtemp())
clock = [datetime(2026, 10, 22, 6, 0, 0)]                      # Donnerstag
now = lambda: clock[0]
calendar = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
store = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
reminders.set_default_store(store)
widgets.set_default_store(calendar)


class FakeWinsound:
    SND_FILENAME, SND_ASYNC, SND_LOOP, SND_PURGE = 1, 2, 8, 64

    def __init__(self):
        self.calls = []

    def PlaySound(self, what, flags):
        self.calls.append((what, flags))


def clear():
    for kind in ("alarm", "reminder"):
        if store.list(kind):
            store.cancel("alle", kind=kind)


def fresh_ringer():
    ringer = ringing.Ringer(siren=ringing.Siren(player=FakeWinsound(), folder=folder))
    ringing.set_default_ringer(ringer)
    return ringer


ringer = fresh_ringer()
background_tasks.get_results()

# 1) Wecker anlegen: Standardname, kein Kalendereintrag, Briefing-Wunsch gespeichert
a = store.add("", "", "06:30", kind="alarm")
assert a["text"] == "Wecker" and a["due"] == "2026-10-22T06:30" and a["kind"] == "alarm" and a["event_id"] is None
assert a["briefing"] is False and calendar.events_on("2026-10-22") == []
b = store.add("Zug erwischen", "2026-10-23", "05:15", kind="alarm", briefing=True)
assert b["briefing"] is True and calendar.events_on("2026-10-23") == []
for bad_time in ("", "abc", None):
    try:
        store.add("x", "", bad_time, kind="alarm")
        raise AssertionError("Zeit muss abgelehnt werden")
    except ReminderError as error:
        assert "wecken" in str(error)
try:
    store.add("x" * 91, "", "07:00", kind="alarm")
    raise AssertionError("zu langer Name")
except ReminderError as error:
    assert "höchstens" in str(error)
r = store.add("Wäsche", "", "19:00")                                  # normale Erinnerung daneben
assert r["event_id"] is not None and "kind" not in r and len(calendar.events_on("2026-10-22")) == 1
rolled = store.add("Früh", "", "05:00", kind="alarm")                 # um 6 Uhr gesagt: gemeint ist morgen
assert rolled["rolled"] is True and rolled["due"] == "2026-10-23T05:00"
store.cancel("Früh", kind="alarm")

# 2) Getrennte Listen, Neustart, Anzeige
assert [x["text"] for x in store.list()] == ["Wäsche"]
assert [x["text"] for x in store.list("alarm")] == ["Wecker", "Zug erwischen"]
assert len(store.list(None)) == 3
again = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
assert [(x["text"], x["briefing"]) for x in again.list("alarm")] == [("Wecker", False), ("Zug erwischen", True)]
assert again.list()[0].get("kind") is None
assert ReminderStore.describe(again.list("alarm")).startswith("Gestellt: 1: Wecker (heute um 06:30)")
assert ReminderStore.describe(again.list()).startswith("Offen: 1: Wäsche")

# 3) Löschen wirkt nur auf die eigene Art, Nummern zählen je Art
try:
    store.cancel("5", kind="alarm")
    raise AssertionError
except ReminderError as error:
    assert "Einen Wecker Nummer 5" in str(error) and "Gestellt:" in str(error)
try:
    store.cancel("Wäsche", kind="alarm")                              # gibt es, aber als Erinnerung
    raise AssertionError
except ReminderError as error:
    assert "Kein" in str(error) and "Wecker" in str(error)
removed = store.cancel("1", kind="alarm")
assert [x["text"] for x in removed] == ["Wecker"] and [x["text"] for x in store.list()] == ["Wäsche"]
assert len(calendar.events_on("2026-10-22")) == 1                     # Kalendereintrag der Erinnerung bleibt
removed = store.cancel("alle wecker", kind="alarm")
assert [x["text"] for x in removed] == ["Zug erwischen"] and store.list("alarm") == []
try:
    store.cancel("1", kind="alarm")
    raise AssertionError
except ReminderError as error:
    assert str(error) == "Es ist kein Wecker gestellt."
store.cancel("1")                                                     # Erinnerung "Wäsche"
assert calendar.events_on("2026-10-22") == []
try:
    store.add("Nur Wecker", "", "07:00", kind="alarm")
    store.cancel("1")
    raise AssertionError
except ReminderError as error:
    assert str(error) == "Es gibt keine offenen Erinnerungen."        # Wecker zählen nicht als Erinnerungen
store.cancel("1", kind="alarm")

# 4) Wiederholung: täglich und werktags ohne Ende (nur für Wecker), mit Ende wie bei Erinnerungen
d = store.add("", "", "06:30", freq="daily", kind="alarm")
assert d["repeat"]["rule"]["freq"] == "daily" and ReminderStore.repeat_info(d) == {"repeat": "täglich", "left": None}
store.cancel("alle", kind="alarm")
for kind, ok in (("alarm", True), ("reminder", False)):                # Erinnerungen bleiben bei "braucht ein Ende"
    try:
        store.add("T", "", "06:30", freq="daily", kind=kind)
        assert ok, "Erinnerung ohne Ende muss abgelehnt werden"
    except ReminderError as error:
        assert not ok and "braucht ein Ende" in str(error)
store.cancel("alle", kind="alarm")
w = store.add("Arbeit", "", "06:30", freq="werktags", until="2026-11-06", kind="alarm")
assert w["due"] == "2026-10-22T06:30" and ReminderStore.repeat_info(w)["repeat"] == "werktags (Mo–Fr), bis 06.11.2026"
store.cancel("alle", kind="alarm")

# Samstagabend gestellt, werktags: der erste Wecker ist der MONTAG, nicht der Sonntag
clock[0] = datetime(2026, 10, 24, 20, 0, 0)
w = store.add("Arbeit", "", "06:30", freq="werktags", kind="alarm")
assert w["due"] == "2026-10-26T06:30" and w["rolled"] is True, w          # Mo 26.10.
store.cancel("alle", kind="alarm")
w = store.add("Arbeit", "2026-10-25", "06:30", freq="werktags", count=3, kind="alarm")      # Sonntag genannt
assert w["due"] == "2026-10-26T06:30"
store.cancel("alle", kind="alarm")
clock[0] = datetime(2026, 10, 22, 6, 0, 0)

# 5) Scheduler: pünktlicher Wecker läutet + meldet, verpasster meldet nur, Erinnerung läutet nie
rings, sent = [], []
sch = ReminderScheduler(store, submit=sent.append, ring=lambda label, brief: rings.append((label, brief)))
store.add("", "", "06:30", kind="alarm", briefing=True)
store.add("Wäsche", "", "06:31")
clock[0] = datetime(2026, 10, 22, 6, 30, 20)
assert sch.check() == 1 and rings == [("Wecker", True)]
assert sent[-1] == {"type": "ALARM_DUE", "data": {"text": "Wecker", "due": "2026-10-22T06:30", "missed": False, "briefing": True}}
assert store.list("alarm") == [] and len(store.list()) == 1           # Wecker weg, Erinnerung offen
clock[0] = datetime(2026, 10, 22, 6, 31, 5)
assert sch.check() == 1 and len(rings) == 1 and sent[-1]["type"] == "REMINDER_DUE" and "briefing" not in sent[-1]["data"]

store.add("Verschlafen", "", "06:40", kind="alarm")
clock[0] = datetime(2026, 10, 22, 7, 0, 0)                            # 20 Minuten zu spät: Jarvis war nicht aktiv
assert sch.check() == 1 and len(rings) == 1                           # kein Läuten mehr
assert sent[-1]["type"] == "ALARM_DUE" and sent[-1]["data"]["missed"] is True and sent[-1]["data"]["briefing"] is False

# Täglicher Wecker läutet jeden Tag; nach dem Läuten steht der nächste schon da
clock[0] = datetime(2026, 10, 22, 7, 30, 0)
store.add("Aufstehen", "", "07:45", freq="daily", kind="alarm")
for day in (22, 23, 24):
    clock[0] = datetime(2026, 10, day, 7, 45, 1)
    assert sch.check() == 1, day
assert [x[0] for x in rings] == ["Wecker", "Aufstehen", "Aufstehen", "Aufstehen"]
assert [x["due"] for x in store.list("alarm")] == ["2026-10-25T07:45"]
assert sent[-1]["data"]["next_due"] == "2026-10-25T07:45" and "last_of_series" not in sent[-1]["data"]
clear()
clock[0] = datetime(2026, 10, 22, 6, 0, 0)

# Standard-Klingeln: ohne eigenes ring geht es an den Standard-Ringer
ringer = fresh_ringer()
default_sch = ReminderScheduler(store, submit=lambda m: None)
store.add("Echt", "", "06:10", kind="alarm", briefing=True)
clock[0] = datetime(2026, 10, 22, 6, 10, 30)
assert default_sch.check() == 1
rows = ringer.active()
assert len(rows) == 1 and rows[0]["kind"] == "alarm" and rows[0]["label"] == "Echt" and rows[0]["briefing"] is True
ringer.stop()
clock[0] = datetime(2026, 10, 22, 6, 0, 0)

# 6) Aufgaben (Executor): stellen, zeigen, löschen, ausschalten
run = action_executor.execute_action
clear()
ringer = fresh_ringer()
out = run(Action("set_alarm", {"time": "630", "date": "", "label": "", "repeat": "", "briefing": ""}))
assert out.success and out.data["label"] == "Wecker" and out.data["when"] == "heute um 06:30" and out.data["time"] == "06:30"
assert out.data["reads_briefing_when_stopped"] is True and "repeat" not in out.data and "note" not in out.data      # Voreinstellung: an
out = run(Action("set_alarm", {"time": "7:00", "label": "Zug", "briefing": "nein"}))
assert out.success and out.data["reads_briefing_when_stopped"] is False and out.data["label"] == "Zug"
out = run(Action("set_alarm", {"time": "05:00", "briefing": "ja", "repeat": "weekdays"}))
assert out.success and out.data["when"] == "morgen um 05:00" and out.data["repeat"] == "werktags (Mo–Fr)" and "morgen" in out.data["note"]
assert "left" not in out.data                                                         # offenes Ende: keine Restzahl
out = run(Action("set_alarm", {"time": "", "label": "x"}))
assert not out.success and "wecken" in out.error
out = run(Action("set_alarm", {"time": "08:00", "repeat": "yearly", "count": "9999"}))
assert not out.success
ringer.configure(briefing=False)
out = run(Action("set_alarm", {"time": "09:00", "briefing": "vielleicht"}))
assert out.success and out.data["reads_briefing_when_stopped"] is False              # Unklares -> Voreinstellung aus den Einstellungen
ringer.configure(briefing=True)

out = run(Action("list_alarms", {}))
rows = out.data["alarms"]
assert [x["number"] for x in rows] == [1, 2, 3, 4] and [x["label"] for x in rows] == ["Wecker", "Zug", "Wecker", "Wecker"]
assert [x["when"] for x in rows] == ["heute um 06:30", "heute um 07:00", "heute um 09:00", "morgen um 05:00"]
assert [x["reads_briefing_when_stopped"] for x in rows] == [True, False, False, True]
assert rows[3]["repeat"] == "werktags (Mo–Fr)" and "repeat" not in rows[0]
assert run(Action("list_reminders", {})).data["reminders"] == []                      # Wecker tauchen dort nicht auf
store.cancel("alle", kind="alarm")
out = run(Action("list_alarms", {}))
assert out.success and out.data == {"alarms": [], "info": "Es ist kein Wecker gestellt."}
assert not run(Action("cancel_alarm", {"which": "1"})).success
run(Action("set_alarm", {"time": "10:00", "label": "Eins"}))
run(Action("set_alarm", {"time": "11:00", "label": "Zwei", "repeat": "daily"}))
out = run(Action("cancel_alarm", {"which": "Zwei"}))                                   # nur das nächste Klingeln
assert out.data["cancelled"] == [] and out.data["only_next_removed_series_continues"][0]["label"] == "Zwei"
out = run(Action("cancel_alarm", {"which": "Zwei", "scope": "series"}))
assert out.data == {"cancelled": ["Zwei"]}
out = run(Action("cancel_alarm", {"which": "1"}))
assert out.data == {"cancelled": ["Eins"]}

# Ausschalten per Aufgabe
out = run(Action("stop_ringing", {}))
assert out.success and out.data == {"info": "Es läutet gerade nichts."}
ringer.briefing_provider = lambda: "Heute: nichts."
ringer.start("alarm", "Wecker", briefing=True)
ringer.start("timer", "Ei")
out = run(Action("stop_ringing", {"what": "Timer"}))
assert out.data == {"stopped": ["Ei"]} and ringer.is_ringing()
out = run(Action("stop_ringing", {"what": "wecker"}))
assert out.data == {"stopped": ["Wecker"], "briefing_to_read_aloud": "Heute: nichts."} and not ringer.is_ringing()
ringer.start("alarm", "Wecker", briefing=False)
assert "briefing_to_read_aloud" not in run(Action("stop_ringing", {"what": ""})).data
plans = []
ringer.snooze_handler = lambda ring, minutes: plans.append((ring["label"], minutes))
ringer.start("alarm", "Wecker")
out = run(Action("stop_ringing", {"snooze_minutes": "10"}))
assert out.data == {"stopped": ["Wecker"], "rings_again_in_minutes": 10} and plans == [("Wecker", 10)]
ringer.start("alarm", "Wecker")
out = run(Action("stop_ringing", {"snooze_minutes": "bald"}))                        # kein Zahlenwert: normal ausschalten
assert out.data == {"stopped": ["Wecker"]} and plans == [("Wecker", 10)]

# 7) Risiko, Fähigkeit, Gast, Schalter
registry = TaskRegistry()
register_all_tasks(registry)
for task_type in ("SET_ALARM", "LIST_ALARMS", "CANCEL_ALARM", "STOP_RINGING"):
    assert registry.get(task_type) is not None and task_type not in guest.GUEST_TASKS
assert risk.action_risk(Action("set_alarm", {"time": "07:00"})) == risk.SAFE
assert risk.action_risk(Action("stop_ringing", {})) == risk.SAFE
assert risk.action_risk(Action("cancel_alarm", {"which": "1"})) == risk.SAFE
assert risk.action_risk(Action("cancel_alarm", {"which": "Alle"})) == risk.CONFIRM
assert risk.action_risk(Action("cancel_alarm", {"which": "alle Wecker"})) == risk.CONFIRM
assert risk.action_risk(Action("cancel_alarm", {"which": "1", "scope": "series"})) == risk.CONFIRM
assert "STOP_RINGING" in abilities.CORE_TASKS
assert any(x.id == "alarm" and set(x.tasks) == {"SET_ALARM", "LIST_ALARMS", "CANCEL_ALARM"} for x in abilities.ABILITIES)
settings = SettingsManager(folder / "s.json")
settings.set("abilities", "alarm", False)
off = TaskRegistry(is_enabled=lambda t: abilities.task_enabled(t, settings))
register_all_tasks(off)
assert off.is_disabled("SET_ALARM") and off.is_disabled("CANCEL_ALARM") and not off.is_disabled("STOP_RINGING")   # Ausschalten geht immer

# 8) Briefing-Text
assert [briefing.greeting(h) for h in (0, 6, 10, 11, 17, 18, 23)] == [
    "Guten Morgen", "Guten Morgen", "Guten Morgen", "Guten Tag", "Guten Tag", "Guten Abend", "Guten Abend"]
ev = lambda title, time="": {"title": title, "time": time}
assert briefing.events_sentence([]) == "Heute stehen keine Termine an."
assert briefing.events_sentence([ev("⏰ Wäsche", "19:00")]) == "Heute stehen keine Termine an."          # Erinnerungen zählen hier nicht
assert briefing.events_sentence([ev("Zahnarzt", "14:00")]) == "Heute steht ein Termin an: um 14:00 Zahnarzt."
assert briefing.events_sentence([ev("Zahnarzt", "14:00"), ev("Kurs Uni", "09:00"), ev("Geburtstag")]) == \
    "Heute stehen 3 Termine an: ganztägig Geburtstag, um 09:00 Kurs Uni, um 14:00 Zahnarzt."      # ganztägig zuerst
many = [ev(f"T{i}", f"{8 + i:02d}:00") for i in range(7)]
assert briefing.events_sentence(many) == ("Heute stehen 7 Termine an: um 08:00 T0, um 09:00 T1, um 10:00 T2, "
                                          "um 11:00 T3, um 12:00 T4 und 2 weitere.")
assert len(briefing.events_sentence([ev("x" * 300, "08:00")])) < 120
items = [{"text": "Wäsche", "due": "2026-10-22T19:00"}, {"text": "Morgen", "due": "2026-10-23T08:00"},
         {"text": "Früh", "due": "2026-10-22T07:00"}]
assert briefing.reminders_sentence(items, "2026-10-22") == "Erinnerungen für heute: um 07:00 Früh, um 19:00 Wäsche."
assert briefing.reminders_sentence(items[1:2], "2026-10-22") is None
moment = datetime(2026, 10, 22, 6, 5)
text = briefing.build_briefing(moment, "Sir", events=lambda: [ev("Kurs Uni", "09:00")], reminder_items=lambda: items,
                               weather=lambda: "In Mannheim sind es 9 °C.")
assert text == ("Guten Morgen, Sir. Es ist 06:05 Uhr, Donnerstag, der 22. Oktober. Heute steht ein Termin an: um 09:00 Kurs Uni. "
                "Erinnerungen für heute: um 07:00 Früh, um 19:00 Wäsche. In Mannheim sind es 9 °C."), text
text = briefing.build_briefing(moment, "Sir", events=lambda: 1 / 0, reminder_items=None, weather=lambda: None)
assert text == "Guten Morgen, Sir. Es ist 06:05 Uhr, Donnerstag, der 22. Oktober."            # kaputte/leere Teile fallen weg
assert briefing.build_briefing(datetime(2026, 12, 31, 21, 0), "Chef").startswith("Guten Abend, Chef. Es ist 21:00 Uhr, Donnerstag, der 31. Dezember.")

# 9) Jarvis: Meldungstexte, Verdrahtung, Briefing, Schlummern, Schnellweg
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
j.apply_settings()
text = j.process_background_result({"type": "ALARM_DUE", "data": {"text": "Wecker", "due": "2026-10-22T06:30", "missed": False, "briefing": True}})
assert text == "Sir, Wecker: es ist 06:30 Uhr."
text = j.process_background_result({"type": "ALARM_DUE", "data": {"text": "Zug", "due": "2026-10-22T06:30", "missed": True,
                                                                 "next_due": "2026-10-23T06:30"}})
assert text.startswith("Sir, Wecker „Zug“: es ist 06:30 Uhr.") and "ich war nicht aktiv" in text and "morgen um 06:30" in text
text = j.process_background_result({"type": "ALARM_DUE", "data": {"text": "Wecker", "due": "2026-10-22T06:30", "missed": False, "last_of_series": True}})
assert "das war der letzte dieser Serie" in text
text = j.process_background_result({"type": "RINGING_EXPIRED", "data": {"label": "Ei", "kind": "timer", "minutes": 10}})
assert text == "Sir, ich habe den Timer „Ei“ nach 10 Minuten von selbst ausgeschaltet."
assert "Wecker „Wecker“" in j.process_background_result({"type": "RINGING_EXPIRED", "data": {"label": "Wecker", "kind": "alarm", "minutes": 5}})

default = ringing.default_ringer()
assert default.briefing_provider == j.wakeup_briefing and default.snooze_handler == j.snooze_ring
j.settings_manager.set("alarm", "sound", "Browser")
j.settings_manager.set("alarm", "max_minutes", 3)
j.settings_manager.set("alarm", "snooze_minutes", 7)
j.settings_manager.set("alarm", "ring_timers", False)
j.settings_manager.set("alarm", "briefing", False)
j.apply_settings()
assert (default.sound, default.max_minutes, default.snooze_minutes, default.ring_timers, default.briefing_default) == ("Browser", 3, 7, False, False)
j.settings_manager.set("alarm", "sound", "Computer")
j.settings_manager.set("alarm", "ring_timers", True)
j.settings_manager.set("alarm", "briefing", True)
j.apply_settings()

# Briefing: Termine von heute, Erinnerungen, Wetter nur mit eingeschalteter Fähigkeit
clear()
calendar.add_event("Kurs Uni", "2026-10-22", "09:00")
store.add("Wäsche", "", "19:00")
from tools import weather_tool


class FakeWeather:
    calls = 0

    def summary(self):
        FakeWeather.calls += 1
        return "In Mannheim sind es 9 °C."


weather_tool.set_default_service(FakeWeather())
brief = j.wakeup_briefing()
assert brief == ("Guten Morgen, Sir. Es ist 06:00 Uhr, Donnerstag, der 22. Oktober. Heute steht ein Termin an: um 09:00 Kurs Uni. "
                 "Erinnerungen für heute: um 19:00 Wäsche. In Mannheim sind es 9 °C."), brief
j.settings_manager.set("abilities", "weather", False)
FakeWeather.calls = 0
assert "Mannheim" not in j.wakeup_briefing() and FakeWeather.calls == 0                   # Wetter aus: kein Abruf
j.settings_manager.set("abilities", "weather", True)

# Schlummern: Wecker kommt später wieder, Timer ebenso
clear()
j.snooze_ring({"kind": "alarm", "label": "Zug", "briefing": True}, 5)
snoozed = store.list("alarm")
assert len(snoozed) == 1 and snoozed[0]["text"] == "Zug" and snoozed[0]["due"] == "2026-10-22T06:05" and snoozed[0]["briefing"] is True
store.cancel("alle", kind="alarm")
clock[0] = datetime(2026, 10, 22, 23, 58, 30)
j.snooze_ring({"kind": "alarm", "label": "Spät", "briefing": False}, 5)                  # über Mitternacht
assert store.list("alarm")[0]["due"] == "2026-10-23T00:03"
store.cancel("alle", kind="alarm")
clock[0] = datetime(2026, 10, 22, 6, 0, 0)
before = len(timer.list_timers())
j.snooze_ring({"kind": "timer", "label": "Ei", "briefing": False}, 2)
mine = [t for t in timer.list_timers() if t["name"] == "Ei"]
assert len(timer.list_timers()) == before + 1 and 115 <= mine[0]["remaining"] <= 120
timer.cancel_timer_by_id(mine[0]["id"])

# Schnellweg in _process_message: vor Router und KI
ringer = fresh_ringer()
ringer.briefing_provider = j.wakeup_briefing
ringer.start("alarm", "Wecker", briefing=True)
reply = j._process_message("Jarvis, Wecker aus!")
assert reply["status"] == "response" and reply["content"].startswith("Sir, Wecker aus. Guten Morgen, Sir.") and not ringer.is_ringing()
ringer.start("timer", "Ei")
reply = j._process_message("noch 3 Minuten")
assert reply["content"] == "Sir, ich wecke dich in 3 Minuten wieder." and not ringer.is_ringing()
ringer.configure(sound="Computer")
for left in timer.list_timers():
    timer.cancel_timer_by_id(left["id"])
src = open(PROJECT_DIR / "jarvis.py", encoding="utf-8").read().split("def _process_message")[1]
assert src.index("ringing.handle_message") < src.index("answer_timer_choice") < src.index("route_message")

# 10) Server: Takt wird nur im normalen Modus gestartet und beim Beenden gestoppt
source = open(PROJECT_DIR / "server.py", encoding="utf-8").read().split("def main(")[1]
assert source.index("ringing.start_ticker()") > source.index("jarvis = Jarvis()") > source.index("if args.guest:")
assert "start_ticker" not in source.split("else:")[0] and "ringing.stop_ticker()" in source.split("finally:")[1]

print("ALL TESTS PASSED")
