"""Proaktive Hinweise (Mark 5, Step 2.29): Termin bald, Wetter morgen; nur Anzeige, einmal pro Hinweis, alles aus."""
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

import json
import tempfile
from datetime import datetime

import abilities
import hints
import jarvis as jarvis_module
import reminders
import widgets
from settings_manager import SettingsManager
from tools import weather_tool
from tools.tool_result import ToolResult

# 1) Termine
now = datetime(2026, 11, 5, 14, 0)
ev = lambda title, at, date="2026-11-05": {"id": "x", "title": title, "date": date, "time": at}
found = hints.appointment_hints([ev("Zahnarzt", "14:30"), ev("Später", "16:00"), ev("Schon vorbei", "13:50"), ev("Ganztägig", ""),
                                 ev("Morgen", "14:10", "2026-11-06"), ev("⏰ Wäsche", "14:05"), ev("Jetzt", "14:00"), ev("Gleich", "14:01")], now, 30)
assert [h["text"] for h in found] == ["In 1 Minute: Gleich um 14:01 Uhr.", "In 30 Minuten: Zahnarzt um 14:30 Uhr."], found
assert found[1]["id"] == "appt:2026-11-05:14:30:Zahnarzt" and found[1]["kind"] == "appointment"
assert [h["text"] for h in hints.appointment_hints([ev("Zahnarzt", "14:30")], now, 29)] == []
assert hints.appointment_hints([ev("Zahnarzt", "14:30")], now, 30) and hints.appointment_hints([ev("A", "14:30")], datetime(2026, 11, 5, 14, 29, 30), 5)[0]["text"] == "In 1 Minute: A um 14:30 Uhr."
assert hints.appointment_hints([ev("A", "25:99")], now, 600) == [] and hints.appointment_hints(None, now, 30) == [] and hints.appointment_hints([5, None, {}], now, 30) == []
odd = hints.appointment_hints([ev("<b>Chef</b>\n" + "x" * 200 + "​", "14:10")], now, 30)[0]["text"]
assert "\n" not in odd and "<" not in odd and "​" not in odd and len(odd) < 120, odd
assert hints.appointment_hints([ev("   ", "14:10")], now, 30) == []
assert hints.appointment_hints([{"title": "Ohne Datum", "time": "14:10"}, {"date": "2026-11-05", "title": "Ohne Zeit"}], now, 30) == []
late = hints.appointment_hints([ev("Frühstück", "00:10", "2026-11-06")], datetime(2026, 11, 5, 23, 50), 30)
assert [h["text"] for h in late] == ["In 20 Minuten: Frühstück um 00:10 Uhr."], "ueber Mitternacht"
assert hints.appointment_hints([ev("Gestern", "23:50", "2026-11-04")], now, 30) == []

# 2) Wetter
full = hints.weather_hint({"place": "Mannheim, Baden-Württemberg", "condition": "bewölkt", "low": 4, "high": 11, "rain_chance_percent": 60}, "2026-11-06")
assert full == {"id": "weather:2026-11-06", "kind": "weather", "text": "Morgen in Mannheim: bewölkt, 4 bis 11 °C, Regenwahrscheinlichkeit 60 %."}, full
assert hints.weather_hint({"place": "Köln", "high": 9, "rain_chance_percent": 29}, "d")["text"] == "Morgen in Köln: bis 9 °C."
assert hints.weather_hint({"condition": "sonnig"}, "d")["text"] == "Morgen: sonnig."
assert hints.weather_hint({"place": "X"}, "d") is None and hints.weather_hint(None, "d") is None and hints.weather_hint([], "d") is None
assert "Regen" not in hints.weather_hint({"high": 1, "rain_chance_percent": True}, "d")["text"]

# 3) Merkliste
folder = Path(tempfile.mkdtemp())
log = hints.HintLog(folder / "h.json")
assert not log.seen("a", "2026-11-05")
log.mark("a", "2026-11-05"); log.mark("a", "2026-11-05"); log.mark("b", "2026-11-05")
assert json.loads((folder / "h.json").read_text(encoding="utf-8")) == {"day": "2026-11-05", "shown": ["a", "b"]}
assert log.seen("a", "2026-11-05") and not log.seen("a", "2026-11-06"), "neuer Tag beginnt leer"
log.mark("c", "2026-11-06")
assert json.loads((folder / "h.json").read_text(encoding="utf-8"))["shown"] == ["c"]
for bad in ("{kaputt", "[1]", '{"day": "2026-11-06", "shown": "x"}', '{"day": "2026-11-06", "shown": [1, "z"]}'):
    (folder / "b.json").write_text(bad, encoding="utf-8")
    assert hints.HintLog(folder / "b.json").seen("z", "2026-11-06") == (bad.endswith('[1, "z"]}')), bad
for n in range(300):
    log.mark(f"id{n}", "2026-11-06")
assert len(json.loads((folder / "h.json").read_text(encoding="utf-8"))["shown"]) == 200
assert not list(folder.glob("*.tmp"))

# 4) Jarvis.proactive_hints
clock = [datetime(2026, 11, 5, 14, 0)]
cal = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
widgets.set_default_store(cal)
reminders.set_default_store(reminders.ReminderStore(folder / "r.json", now=lambda: clock[0], calendar=lambda: cal))
hints.set_default_log(hints.HintLog(folder / "state.json"))
cal.add_event("Zahnarzt", "2026-11-05", "14:20")


class FakeWeather:
    calls = 0
    fail = False

    def get_weather(self, place, day="heute"):
        FakeWeather.calls += 1
        assert (place, day) == ("heimat", "morgen")
        if FakeWeather.fail:
            return ToolResult(success=False, error="kein Netz")
        return ToolResult(success=True, data={"place": "Mannheim", "condition": "Regen", "low": 3, "high": 8, "rain_chance_percent": 80})


weather_tool.set_default_service(FakeWeather())
j = object.__new__(jarvis_module.Jarvis)
j.settings_manager = SettingsManager(folder / "j.json")
m = j.settings_manager
assert m.get_all()["hints"] == {"appointments": False, "appointment_minutes": 30, "weather": False, "weather_hour": 19, "pc": False}
assert j.proactive_hints() == [] and FakeWeather.calls == 0, "alles aus per Voreinstellung"

m.set("hints", "appointments", True)
assert j.proactive_hints() == [{"kind": "appointment", "text": "In 20 Minuten: Zahnarzt um 14:20 Uhr."}]
assert j.proactive_hints() == [], "jeder Hinweis nur einmal"
cal.add_event("Training", "2026-11-05", "14:45")
assert j.proactive_hints() == []
clock[0] = datetime(2026, 11, 5, 14, 20)
assert j.proactive_hints() == [{"kind": "appointment", "text": "In 25 Minuten: Training um 14:45 Uhr."}]
m.set("hints", "appointment_minutes", 5)
cal.add_event("Kurz", "2026-11-05", "15:00")
clock[0] = datetime(2026, 11, 5, 14, 50)
assert j.proactive_hints() == [], "10 Minuten sind mehr als das Fenster von 5"
clock[0] = datetime(2026, 11, 5, 14, 56)
assert j.proactive_hints() == [{"kind": "appointment", "text": "In 4 Minuten: Kurz um 15:00 Uhr."}]
assert j.proactive_hints() == []

# Wetter: erst ab der Stunde, einmal pro Tag, Fehler -> spaeter noch einmal
m.set("hints", "weather", True)
assert j.proactive_hints() == [] and FakeWeather.calls == 0, "vor 19 Uhr nichts"
clock[0] = datetime(2026, 11, 5, 19, 0)
FakeWeather.fail = True
assert j.proactive_hints() == [] and FakeWeather.calls == 1
clock[0] = datetime(2026, 11, 5, 19, 5)
assert j.proactive_hints() == [] and FakeWeather.calls == 1, "nach Fehler 10 Minuten Pause"
FakeWeather.fail = False
clock[0] = datetime(2026, 11, 5, 19, 10)
assert j.proactive_hints() == [{"kind": "weather", "text": "Morgen in Mannheim: Regen, 3 bis 8 °C, Regenwahrscheinlichkeit 80 %."}]
assert j.proactive_hints() == [] and FakeWeather.calls == 2, "einmal pro Tag, auch nicht noch einmal abgerufen"
clock[0] = datetime(2026, 11, 6, 19, 30)
assert len(j.proactive_hints()) == 1 and FakeWeather.calls == 3, "naechster Tag wieder"

m.set("hints", "appointment_minutes", 30)
# Wetter-Hinweis aus: kein Abruf, Termine kommen trotzdem
m.set("hints", "weather", False)
clock[0] = datetime(2026, 11, 12, 19, 30)
cal.add_event("Nur Termin", "2026-11-12", "19:50")
before = FakeWeather.calls
assert j.proactive_hints() == [{"kind": "appointment", "text": "In 20 Minuten: Nur Termin um 19:50 Uhr."}] and FakeWeather.calls == before
m.set("hints", "weather", True)

# Fehler in einer Art stoert die andere nicht; Faehigkeiten aus; Gast
clock[0] = datetime(2026, 11, 7, 19, 30)
cal.add_event("Bald", "2026-11-07", "19:45")
class Boom:
    def get_weather(self, *a):
        raise RuntimeError("kaputt")
weather_tool.set_default_service(Boom())
res = j.proactive_hints()
assert res == [{"kind": "appointment", "text": "In 15 Minuten: Bald um 19:45 Uhr."}], res
weather_tool.set_default_service(FakeWeather())
clock[0] = datetime(2026, 11, 8, 19, 30)
cal.add_event("Bald2", "2026-11-08", "19:40")
m.set("abilities", "calendar", False)
assert [h["kind"] for h in j.proactive_hints()] == ["weather"], "Kalender-Faehigkeit aus: keine Termine"
m.set("abilities", "calendar", True)
m.set("abilities", "weather", False)
clock[0] = datetime(2026, 11, 9, 19, 30)
cal.add_event("Bald3", "2026-11-09", "19:40")
assert [h["kind"] for h in j.proactive_hints()] == ["appointment"], "Wetter-Faehigkeit aus: kein Wetter"
m.set("abilities", "weather", True)
clock[0] = datetime(2026, 11, 10, 19, 30)
cal.add_event("Bald4", "2026-11-10", "19:40")
j.guest = True
assert j.proactive_hints() == []
del j.guest
assert len(j.proactive_hints()) == 2
cal.get = lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))
clock[0] = datetime(2026, 11, 11, 19, 30)
assert [h["kind"] for h in j.proactive_hints()] == ["weather"], "kaputter Kalender: Wetter kommt trotzdem"


# 4b) Kritische PC-Probleme (reine Funktion pc_hints): nur "bad", bei Dauer erst nach der Wartezeit, Luecken starten neu
from datetime import timedelta
from tools import pc_health


def bad(fid, sustained=False, text="Text", tip="Tipp", level="bad"):
    return {"id": fid, "level": level, "sustained": sustained, "short": "kurz", "text": text, "tip": tip}


t0 = datetime(2026, 11, 20, 12, 0)
state = {}
assessment = {"level": "bad", "findings": [bad("health:D", text="Das Laufwerk D: meldet „Warning“.", tip="Mach ein Backup."), bad("ram", True), bad("cpu", True),
                                          bad("battery", level="warn"), bad("uptime", level="tip")]}
res = hints.pc_hints(assessment, state, t0)
assert res == [{"id": "pc:health:D", "kind": "pc", "text": "PC-Warnung: Das Laufwerk D: meldet „Warning“. Mach ein Backup."}], res
assert hints.pc_hints(assessment, state, t0 + timedelta(minutes=1)) == [res[0]], "ohne HintLog kommt es jedes Mal: das 'nur einmal' merkt sich das HintLog"
for minute in (2, 3, 4):                                                                          # alle 1-2 Minuten geprueft (kleiner als die Luecke)
    now = t0 + timedelta(minutes=minute)
    assert [h["id"] for h in hints.pc_hints(assessment, state, now)] == ["pc:health:D"], minute
now = t0 + timedelta(minutes=5)
assert [h["id"] for h in hints.pc_hints(assessment, state, now)] == ["pc:health:D", "pc:ram"], "RAM nach 5 Minuten"
for minute in (6, 7, 8, 9):
    assert "pc:cpu" not in [h["id"] for h in hints.pc_hints(assessment, state, t0 + timedelta(minutes=minute))], minute
assert [h["id"] for h in hints.pc_hints(assessment, state, t0 + timedelta(minutes=10))] == ["pc:health:D", "pc:ram", "pc:cpu"], "CPU nach 10 Minuten"
# verschwindet das Problem, beginnt die Zeit neu
calm = {"level": "ok", "findings": []}
assert hints.pc_hints(calm, state, t0 + timedelta(minutes=11)) == [] and state["since"] == {}
assert [h["id"] for h in hints.pc_hints(assessment, state, t0 + timedelta(minutes=12))] == ["pc:health:D"], "RAM beginnt wieder bei null"
# Luecke groesser als drei Minuten (Seite war zu): auch ein altes Dauerproblem beginnt neu
state2 = {}
ram_only = {"findings": [bad("ram", True)]}
assert hints.pc_hints(ram_only, state2, t0) == []
assert hints.pc_hints(ram_only, state2, t0 + timedelta(minutes=2)) == []
assert [h["id"] for h in hints.pc_hints(ram_only, state2, t0 + timedelta(minutes=5))] == ["pc:ram"], "genau drei Minuten Luecke ist noch erlaubt"
state2b = {}
assert hints.pc_hints(ram_only, state2b, t0) == [] and hints.pc_hints(ram_only, state2b, t0 + timedelta(minutes=2)) == []
assert hints.pc_hints(ram_only, state2b, t0 + timedelta(minutes=5, seconds=1)) == [], "drei Minuten und eine Sekunde Luecke: neu beginnen"
state3 = {}
assert hints.pc_hints({"findings": [bad("ram", True)]}, state3, t0) == []
assert hints.pc_hints({"findings": [bad("ram", True)]}, state3, t0 + timedelta(hours=3)) == [], "nach langer Pause nicht sofort melden"
assert [h["id"] for h in hints.pc_hints({"findings": [bad("ram", True)]}, state3, t0 + timedelta(hours=3, minutes=2))] == []
assert [h["id"] for h in hints.pc_hints({"findings": [bad("ram", True)]}, state3, t0 + timedelta(hours=3, minutes=5))] == ["pc:ram"]
# unbekannte Dauerprobleme warten fuenf Minuten; Unsinn stoert nicht; Text wird bereinigt und gekuerzt
state4 = {}
assert hints.pc_hints({"findings": [bad("busy:D", True)]}, state4, t0) == []
assert [h["id"] for h in hints.pc_hints({"findings": [bad("busy:D", True)]}, state4, t0 + timedelta(minutes=2))] == []
assert [h["id"] for h in hints.pc_hints({"findings": [bad("busy:D", True)]}, state4, t0 + timedelta(minutes=4))] == []
assert [h["id"] for h in hints.pc_hints({"findings": [bad("busy:D", True)]}, state4, t0 + timedelta(minutes=5))] == ["pc:busy:D"]
for junk in (None, [], "x", {}, {"findings": None}, {"findings": [None, 5, "x", {"level": "bad"}, {"level": "bad", "id": 5}, {"level": "bad", "id": "x", "text": "", "tip": ""}]}):
    assert hints.pc_hints(junk, {}, t0) == [], junk
long_one = hints.pc_hints({"findings": [bad("health:C", text="A" * 500 + "\x00\x1b", tip="B")]}, {}, t0)[0]["text"]
assert len(long_one) < 400 and "\x00" not in long_one and "\x1b" not in long_one

# 4c) Jarvis.proactive_hints mit PC-Warnungen: aus per Voreinstellung, einmal pro Tag und Art, Fehler stoert nichts
class FakeHealth:
    findings = [bad("full:C", text="C: ist fast voll.", tip="Aufraeumen."), bad("ram", True, text="RAM voll.", tip="Programm schliessen.")]
    calls = 0
    fail = False

    def report(self):
        FakeHealth.calls += 1
        if FakeHealth.fail:
            raise RuntimeError("kaputt")
        return {"assessment": {"level": "bad", "findings": FakeHealth.findings}}


del cal.get                                                                                   # der Kalender aus dem Fehlertest oben ist wieder heil
pc_health.set_default_health(FakeHealth())
clock[0] = datetime(2026, 12, 1, 10, 0)
assert j.proactive_hints() == [] and FakeHealth.calls == 0, "PC-Warnungen sind per Voreinstellung aus"
m.set("hints", "pc", True)
res = j.proactive_hints()
assert res == [{"kind": "pc", "text": "PC-Warnung: C: ist fast voll. Aufraeumen."}], res
clock[0] = datetime(2026, 12, 1, 10, 1)
assert j.proactive_hints() == [], "einmal pro Tag"
for minute in (2, 3, 4):                                                                       # die Seite fragt jede Minute
    clock[0] = datetime(2026, 12, 1, 10, minute)
    assert j.proactive_hints() == [], minute
clock[0] = datetime(2026, 12, 1, 10, 5)
res = j.proactive_hints()
assert res == [{"kind": "pc", "text": "PC-Warnung: RAM voll. Programm schliessen."}], "RAM nach fuenf Minuten Dauer"
clock[0] = datetime(2026, 12, 1, 10, 6)
assert j.proactive_hints() == []
clock[0] = datetime(2026, 12, 2, 10, 0)                                                        # naechster Tag: die Laufwerks-Warnung kommt wieder, RAM erst nach der Wartezeit
assert [h["text"] for h in j.proactive_hints()] == ["PC-Warnung: C: ist fast voll. Aufraeumen."]
FakeHealth.fail = True
clock[0] = datetime(2026, 12, 3, 10, 0)
cal.add_event("Mit kaputtem PC-Check", "2026-12-03", "10:20")
assert [h["kind"] for h in j.proactive_hints()] == ["appointment"], "kaputte PC-Pruefung stoert den Termin nicht"
FakeHealth.fail = False
import abilities
real_enabled = abilities.task_enabled                                                         # GET_SYSTEM_INFO ist eine Kernaufgabe: nur so laesst sich "aus" nachstellen
abilities.task_enabled = lambda task, manager: False if task == "GET_SYSTEM_INFO" else real_enabled(task, manager)
FakeHealth.calls = 0
clock[0] = datetime(2026, 12, 4, 10, 0)
assert j.proactive_hints() == [] and FakeHealth.calls == 0, "Faehigkeit aus: keine Pruefung"
abilities.task_enabled = real_enabled
j.guest = True
calls_before = FakeHealth.calls
clock[0] = datetime(2026, 12, 5, 10, 0)
assert j.proactive_hints() == [] and FakeHealth.calls == calls_before, "Gast: nie"
del j.guest
m.set("hints", "pc", False)
calls_before = FakeHealth.calls
clock[0] = datetime(2026, 12, 6, 10, 0)
assert j.proactive_hints() == [] and FakeHealth.calls == calls_before
pc_health.set_default_health(None)

# 5) Einstellungen, Server, Oberflaeche, Quelltext
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
for key, rule in (("appointments", "isinstance(v, bool)"), ("appointment_minutes", "_is_int(v, 5, 120)"), ("weather", "isinstance(v, bool)"), ("weather_hour", "_is_int(v, 15, 23)"), ("pc", "isinstance(v, bool)")):
    assert f'EDITABLE_SETTINGS[("hints", "{key}")] = lambda v: {rule}' in server_source, key
post = server_source.split("def do_POST")[1]
assert post.index("self.server.guest and path") < post.index("/api/hints") < post.rindex("with self.server.message_lock:")
app_js = webapp.app_text()
assert '"/api/hints"' in app_js and "setInterval(checkHints, 60 * 1000)" in app_js and 'category: "hints", key: "appointments"' in app_js
assert 'category: "hints", key: "weather_hour"' in app_js and 'category: "hints", key: "pc"' in app_js and 'addMessage("background", hint.text, "HINWEIS")' in app_js
code = open(PROJECT_DIR / "hints.py", encoding="utf-8").read().split('"""', 2)[2]
for forbidden in ("subprocess", "os.system", "eval(", "exec(", "webbrowser", "requests", "execute_task", "run_task"):
    assert forbidden not in code, forbidden

print("ALL TESTS PASSED")
