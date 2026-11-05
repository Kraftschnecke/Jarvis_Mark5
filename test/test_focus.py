"""Fokus-Timer / Pomodoro (Mark 5, Step 2.13): Phasenwechsel, Meldungen, Ton, Aufgaben, Jarvis-Verdrahtung."""

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

import threading
import time

import abilities
import action_executor
import focus
import jarvis as jarvis_module
import ringing
import risk
from action import Action
from focus import FocusError, FocusManager
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks


def expect_error(fn, part):
    try:
        fn()
    except FocusError as error:
        assert part in str(error), (part, str(error))
        return
    raise AssertionError("FocusError erwartet: " + part)


# 1) Zahlen: Standard, Text, Grenzen
pn = focus.parse_number
assert pn(None, 25, "work", "Fokusphase") == 25 and pn("standard", 25, "work", "x") == 25 and pn(" Ohne ", 5, "break", "x") == 5
assert pn("40", 25, "work", "x") == 40 and pn(40, 25, "work", "x") == 40 and pn("40,0", 25, "work", "x") == 40 and pn(12.0, 5, "break", "x") == 12
expect_error(lambda: pn("0", 25, "work", "Fokusphase"), "Fokusphase: erlaubt sind 1 bis 120")
expect_error(lambda: pn("121", 25, "work", "Fokusphase"), "1 bis 120")
expect_error(lambda: pn("61", 5, "break", "Pause"), "Pause: erlaubt sind 1 bis 60")
expect_error(lambda: pn("13", 4, "rounds", "Runden"), "Runden: erlaubt sind 1 bis 12")
expect_error(lambda: pn("25,5", 25, "work", "Fokusphase"), "ganze Zahl")
expect_error(lambda: pn("abc", 25, "work", "Fokusphase"), "„abc“ habe ich nicht als Zahl verstanden")
expect_error(lambda: pn(True, 25, "work", "Fokusphase"), "nicht als Zahl")
expect_error(lambda: pn("-5", 25, "work", "Fokusphase"), "erlaubt sind")
assert focus.clean_label("  Lernen\n für  Mathe ") == "Lernen für Mathe" and focus.clean_label("ohne") == "" and focus.clean_label(None) == ""
assert focus.clean_label("x" * 80) == "x" * 40 and "​" not in focus.clean_label("a​b")

# 2) Sitzung mit Phasenwechseln (falsche Uhr, kein Thread)
clock = [1000.0]
events, chimes = [], []
manager = FocusManager(clock=lambda: clock[0], submit=events.append, chime=lambda: chimes.append(1), auto_thread=False)
assert manager.state() == {"active": False} and manager.tick() is None and manager.stop() is None
state = manager.start(label="Lernen", rounds=3)
assert state["active"] and state["phase"] == "work" and state["phase_name"] == "Fokus" and state["round"] == 1 and state["rounds"] == 3
assert state["remaining"] == 25 * 60 and state["label"] == "Lernen" and state["work_minutes"] == 25 and state["break_minutes"] == 5
expect_error(lambda: manager.start(), "Es läuft schon eine Fokus-Sitzung (Runde 1 von 3)")
clock[0] += 25 * 60 - 1
assert manager.tick() is None and events == [] and manager.state()["remaining"] == 1
clock[0] += 1
ev = manager.tick()
assert ev == {"label": "Lernen", "rounds": 3, "done": "work", "round": 1, "next": "break", "minutes": 5, "finished": False}, ev
assert events == [{"type": "FOCUS_PHASE", "data": ev}] and len(chimes) == 1
st = manager.state()
assert st["phase"] == "break" and st["phase_name"] == "Pause" and st["round"] == 1 and st["remaining"] == 300
assert manager.tick() is None                                                         # zweimal tickt nicht doppelt
clock[0] += 300
ev = manager.tick()
assert ev["done"] == "break" and ev["next"] == "work" and ev["round"] == 2 and ev["minutes"] == 25 and ev["finished"] is False
assert manager.state()["phase"] == "work" and manager.state()["round"] == 2
clock[0] += 25 * 60
assert manager.tick()["next"] == "break"
clock[0] += 300
assert manager.tick()["round"] == 3
clock[0] += 25 * 60
ev = manager.tick()                                                                   # letzte Runde: fertig
assert ev == {"label": "Lernen", "rounds": 3, "done": "work", "round": 3, "next": None, "minutes": 0, "finished": True}, ev
assert manager.state() == {"active": False} and len(events) == 5 and len(chimes) == 5
assert manager.tick() is None
assert manager.start(rounds=1)["rounds"] == 1                                         # danach geht eine neue Sitzung
assert manager.stop() == {"label": "", "completed_rounds": 0, "rounds": 1}

# 3) Lange Pause nach jeder 4. Runde, wenn noch etwas folgt
events.clear()
manager.start(work=1, brk=2, long=7, rounds=5)
kinds = []
for _ in range(9):                                                                    # 5 Fokusphasen + 4 Pausen
    clock[0] += 3600
    ev = manager.tick()
    kinds.append((ev["done"], ev["round"], ev["next"], ev["minutes"]))
assert kinds == [("work", 1, "break", 2), ("break", 2, "work", 1), ("work", 2, "break", 2), ("break", 3, "work", 1),
                 ("work", 3, "break", 2), ("break", 4, "work", 1), ("work", 4, "long_break", 7), ("break", 5, "work", 1),
                 ("work", 5, None, 0)], kinds
assert manager.state() == {"active": False}
manager.start(work=1, rounds=4)                                                       # genau 4 Runden: nach der letzten keine lange Pause
for _ in range(7):
    clock[0] += 3600
    last = manager.tick()
assert last["finished"] is True and last["next"] is None and manager.state() == {"active": False}

# 4) Abbrechen: wie viele Runden geschafft
manager.start(rounds=4)
assert manager.stop() == {"label": "", "completed_rounds": 0, "rounds": 4}
manager.start(rounds=4)
clock[0] += 3600; manager.tick(); clock[0] += 3600; manager.tick()                    # Runde 2, Fokusphase
assert manager.stop()["completed_rounds"] == 1
manager.start(rounds=4)
clock[0] += 3600; manager.tick()                                                      # Pause nach Runde 1
assert manager.stop()["completed_rounds"] == 1 and manager.state() == {"active": False}

# 5) Voreinstellungen
manager.configure(work=50, brk=10, long=20, rounds=2)
s = manager.start()
assert (s["work_minutes"], s["break_minutes"], s["long_break_minutes"], s["rounds"]) == (50, 10, 20, 2)
manager.stop()
manager.configure(work=0, brk=True, long="x", rounds=99)                              # Ungültiges wird ignoriert
assert manager.defaults == {"work": 50, "break": 10, "long": 20, "rounds": 2}
s = manager.start(work="30", brk=3)
assert s["work_minutes"] == 30 and s["break_minutes"] == 3 and s["rounds"] == 2
manager.stop()
expect_error(lambda: manager.start(work="500"), "Fokusphase")
assert manager.state() == {"active": False}                                           # ein Fehler startet nichts

# 6) Lange Pause des Rechners (Schlaf): nur ein Wechsel, danach läuft die neue Phase ab jetzt
manager.configure(work=25, brk=5, long=15, rounds=4)
events.clear(); chimes.clear()
manager.start()
clock[0] += 10 * 3600
ev = manager.tick()
assert ev["next"] == "break" and manager.state()["remaining"] == 300 and manager.tick() is None and len(events) == 1
manager.stop()

# 7) Ein Fehler beim Melden hält die Sitzung nicht an; der Ton kommt trotzdem
def bad_submit(item):
    raise RuntimeError("kaputt")
m2 = FocusManager(clock=lambda: clock[0], submit=bad_submit, chime=lambda: chimes.append("m2"), auto_thread=False)
m2.start(rounds=2)
chimes.clear()
clock[0] += 3600
try:
    m2.tick()
except RuntimeError:
    pass
assert chimes == ["m2"] and m2.state()["phase"] == "break"
def bad_chime():
    raise OSError("kein Ton")
m3 = FocusManager(clock=lambda: clock[0], submit=events.append, chime=bad_chime, auto_thread=False)
m3.start(rounds=2)
clock[0] += 3600
assert m3.tick()["next"] == "break"

# 8) Hintergrund-Thread: tickt von selbst, nur ein Thread, shutdown beendet ihn
tclock = [5000.0]
got = []
live = FocusManager(clock=lambda: tclock[0], submit=got.append, chime=lambda: None)
live.ensure_thread(interval=0.02)
first = live._thread
live.ensure_thread(interval=0.02)
assert live._thread is first and first.is_alive()
live.start(work=1, rounds=2)
tclock[0] += 61
for _ in range(100):
    if got:
        break
    time.sleep(0.02)
assert got and got[0]["data"]["done"] == "work" and got[0]["data"]["next"] == "break", got
live.shutdown()
first.join(2)
assert not first.is_alive()

# 9) Ton: einmal, ohne Schleife; nicht bei Sirene, nicht bei Ton "Aus"/"Browser"
class FakePlayer:
    SND_FILENAME, SND_ASYNC, SND_LOOP, SND_PURGE = 1, 2, 8, 64
    def __init__(self): self.calls = []
    def PlaySound(self, what, flags): self.calls.append((what, flags))
player = FakePlayer()
folder = Path(tempfile.mkdtemp())
ringer = ringing.Ringer(siren=ringing.Siren(player=player, folder=folder))
assert ringer.chime() is True and len(player.calls) == 1
assert player.calls[0][1] == 1 | 2 and not player.calls[0][1] & 8 and Path(player.calls[0][0]).exists()
ringer.configure(sound="Browser")
assert ringer.chime() is False and len(player.calls) == 1
ringer.configure(sound="Aus")
assert ringer.chime() is False
ringer.configure(sound="Computer")
ringer.start("timer", "Ei")                                                           # läutet: kein Ton dazwischen
calls_before = len(player.calls)
assert ringer.chime() is False and len(player.calls) == calls_before
ringer.stop()
class RecordingSiren(ringing.Siren):
    def __init__(self):
        super().__init__(player=FakePlayer(), folder=folder)
        self.chimes = 0
    def start(self):                                                                  # läutet "leise": playing bleibt False
        return True
    def chime(self):
        self.chimes += 1
        return True
quiet = ringing.Ringer(siren=RecordingSiren())
assert quiet.chime() is True and quiet.siren.chimes == 1
quiet.start("alarm", "Wecker")
assert quiet.is_ringing() and quiet.chime() is False and quiet.siren.chimes == 1      # Ringer-Sperre unabhängig von der Sirene
no_player = ringing.Siren(player=FakePlayer(), folder=folder)
no_player.player = None                                                               # "kein winsound" (Siren(player=None) würde es unter Windows laden)
assert no_player.chime() is False
class BadPlayer(FakePlayer):
    def PlaySound(self, what, flags): raise OSError("x")
assert ringing.Siren(player=BadPlayer(), folder=folder).chime() is False
ringing.set_default_ringer(ringer)
assert ringing.chime() is True

# 10) Aufgaben, Risiko, Fähigkeit
registry = TaskRegistry()
register_all_tasks(registry)
for name, actions in (("START_FOCUS", ["start_focus"]), ("FOCUS_STATUS", ["focus_status"]), ("STOP_FOCUS", ["stop_focus"])):
    task = registry.get(name)
    assert task is not None and [a.name for a in task.actions] == actions and risk.task_risk(task) == risk.SAFE, name
assert set(registry.get("START_FOCUS").actions[0].parameters) == {"work_minutes", "break_minutes", "rounds", "label"}
ability = [a for a in abilities.ABILITIES if a.id == "focus"][0]
assert ability.tasks == ("START_FOCUS", "FOCUS_STATUS", "STOP_FOCUS") and ability.default is True

# 11) Aktionen mit dem Standard-Manager
em = FocusManager(clock=lambda: clock[0], submit=events.append, chime=lambda: None, auto_thread=False)
focus.set_default_manager(em)
def run(name, **params):
    return action_executor.execute_action(Action(name, params))
r = run("start_focus", work_minutes="standard", break_minutes="standard", rounds="standard", label="ohne")
assert r.success and r.data == {"work_minutes": 25, "break_minutes": 5, "rounds": 4, "first_break_in_minutes": 25,
                                "note": "Die Sitzung liegt im Speicher: Startet Jarvis neu, ist sie weg."}, r.data
bad = run("start_focus", work_minutes="10")
assert not bad.success and "Es läuft schon eine Fokus-Sitzung" in bad.error
s = run("focus_status")
assert s.success and s.data == {"active": True, "phase": "Fokus", "round": 1, "rounds": 4, "remaining": "25 Minuten"}, s.data
clock[0] += 25 * 60
em.tick()
s = run("focus_status")
assert s.data["phase"] == "Pause" and s.data["remaining"] == "5 Minuten"
t = run("stop_focus")
assert t.data == {"stopped": True, "completed_rounds": 1, "rounds": 4}, t.data
assert run("stop_focus").data == {"stopped": False, "info": "Es lief keine Fokus-Sitzung."}
assert run("focus_status").data == {"active": False, "info": "Es läuft keine Fokus-Sitzung."}
r = run("start_focus", work_minutes="50", break_minutes="10", rounds="6", label="Mathe lernen")
assert r.data["label"] == "Mathe lernen" and r.data["long_break_minutes"] == 15 and r.data["long_break_after_round"] == 4 and r.data["rounds"] == 6
em.stop()
for params in ({"work_minutes": "0"}, {"rounds": "abc"}, {"break_minutes": "99"}):
    failed = run("start_focus", **params)
    assert not failed.success and em.state() == {"active": False}, params
focus.set_default_manager(None)

# 12) Jarvis: Meldungstexte, Einstellungen
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
focus.set_default_manager(FocusManager(auto_thread=False))
j.apply_settings()
assert focus.default_manager().defaults == {"work": 25, "break": 5, "long": 15, "rounds": 4}
j.settings_manager.set("focus", "work_minutes", 50)
j.settings_manager.set("focus", "break_minutes", 10)
j.settings_manager.set("focus", "long_break_minutes", 30)
j.settings_manager.set("focus", "rounds", 3)
j.apply_settings()
assert focus.default_manager().defaults == {"work": 50, "break": 10, "long": 30, "rounds": 3}
msg = lambda **d: j.process_background_result({"type": "FOCUS_PHASE", "data": d})
assert msg(label="Lernen", rounds=2, done="work", round=2, next=None, minutes=0, finished=True) == \
    "Sir, alle 2 Fokusphasen sind geschafft (Lernen). Gut gemacht, die Sitzung ist beendet."
base = {"label": "", "rounds": 4}
assert msg(**base, done="work", round=1, next="break", minutes=5, finished=False) == "Sir, Fokusphase 1 von 4 geschafft. Zeit für eine Pause: 5 Minuten."
assert msg(**dict(base, label="Lernen"), done="work", round=1, next="break", minutes=1, finished=False) == \
    "Sir, Fokusphase 1 von 4 (Lernen) geschafft. Zeit für eine Pause: 1 Minute."
assert msg(**base, done="work", round=4, next="long_break", minutes=15, finished=False).endswith("Zeit für eine lange Pause: 15 Minuten.")
assert msg(**base, done="break", round=2, next="work", minutes=25, finished=False) == "Sir, die Pause ist vorbei. Fokusphase 2 von 4 beginnt: 25 Minuten."
assert msg(**dict(base, label="Lernen"), done="break", round=3, next="work", minutes=25, finished=False) == \
    "Sir, die Pause ist vorbei. Fokusphase 3 von 4 (Lernen) beginnt: 25 Minuten."
assert msg(**base, done="work", round=4, next=None, minutes=0, finished=True) == \
    "Sir, alle 4 Fokusphasen sind geschafft. Gut gemacht, die Sitzung ist beendet."
assert msg(**dict(base, rounds=1, label="Lesen"), done="work", round=1, next=None, minutes=0, finished=True) == \
    "Sir, die Fokusphase (Lesen) ist geschafft. Gut gemacht, die Sitzung ist beendet."
focus.set_default_manager(None)

# 13) Server und Oberfläche (Quelltext; die Routen testet test_server_focus.py)
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
post = server_source.split("def do_POST")[1]
assert post.index("self.server.guest and path") < post.index("/api/focus/stop") < post.rindex("with self.server.message_lock:")
for key, low, high in (("work_minutes", 1, 120), ("break_minutes", 1, 60), ("long_break_minutes", 1, 60), ("rounds", 1, 12)):
    assert f'EDITABLE_SETTINGS[("focus", "{key}")] = lambda v: _is_int(v, {low}, {high})' in server_source, key
app_js = open(PROJECT_DIR / "web" / "app.js", encoding="utf-8").read()
assert '"/api/focus/stop"' in app_js and '"/api/focus"' in app_js and "setInterval(refreshFocus, 1000)" in app_js
for key in ("work_minutes", "break_minutes", "long_break_minutes", "rounds"):
    assert f'category: "focus", key: "{key}"' in app_js, key
assert 'id="focus"' in open(PROJECT_DIR / "web" / "index.html", encoding="utf-8").read()
import guest
assert not {"START_FOCUS", "FOCUS_STATUS", "STOP_FOCUS"} & set(guest.GUEST_TASKS)
print("ALL TESTS PASSED")
