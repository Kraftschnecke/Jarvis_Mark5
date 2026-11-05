"""Rechner-Grundfunktionen (Mark 5, Step 2.23): feste Befehle, nur Windows, Helligkeit nur ueber ein festes Skript, immer erst fragen."""
import re
import subprocess
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
import guest
import risk
import tools.system_tool as st
from action import Action
from task_registry import TaskRegistry
from tasks import register_all_tasks

REAL_PLATFORM = sys.platform
keys, locks, scripts = [], [], []
st._press = lambda k: keys.append(tuple(k))
st._lock = lambda: locks.append(1)
brightness = [60]


def fake_powershell(script):
    scripts.append(script)
    if script == st._GET:
        return f"{brightness[0]}\r\n"
    assert script.startswith("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1,") and script.endswith(")"), script
    brightness[0] = int(script.rsplit(",", 1)[1][:-1])
    return ""


real_powershell = st._powershell
st._powershell = fake_powershell
sys.platform = "win32"

# 0) Die echte PowerShell-Huelle: Ausgabe als Bytes, auch mit Zeichen, die cp1252 nicht kennt (Windows-Fehlertexte)
class Done:
    def __init__(self, code, out):
        self.returncode, self.stdout = code, out


calls = []


def fake_run(cmd, **kw):
    calls.append((cmd, kw))
    return fake_run.result


real_run = st.subprocess.run
st.subprocess.run = fake_run
try:
    fake_run.result = Done(0, b"60\r\n\x81\xe4")
    out = real_powershell("SKRIPT")
    assert isinstance(out, str) and out.startswith("60"), out
    assert calls[0][0][-1] == "SKRIPT" and calls[0][0][0] == "powershell" and "shell" not in calls[0][1]
    assert not calls[0][1].get("text") and not calls[0][1].get("universal_newlines") and calls[0][1]["timeout"] == st.POWERSHELL_TIMEOUT
    fake_run.result = Done(0, None)
    assert real_powershell("x") == ""
    fake_run.result = Done(1, b"Zugriff verweigert \x81")
    try:
        real_powershell("x")
        raise SystemExit("Fehlercode ignoriert")
    except OSError:
        pass
finally:
    st.subprocess.run = real_run


# 1) Befehle erkennen
for raw, expected in (("mute", "mute"), ("Stumm", "mute"), ("ton aus", "mute"), ("lock", "lock"), ("Bildschirm sperren", "lock"),
                      ("show_desktop", "show_desktop"), ("Show Desktop", "show_desktop"), ("alle Fenster minimieren", "show_desktop"),
                      ("brightness_set", "brightness_set"), ("Helligkeit", "brightness_set"), ("heller", "brightness_up"),
                      ("brightness_up", "brightness_up"), ("dunkler", "brightness_down"), ("dim", "brightness_down")):
    assert st.normalize_command(raw) == expected, raw
for raw in ("", "  ", None, 5, {"x": 1}, "shutdown", "herunterfahren", "neu starten", "alt f4", "rm -rf", "lock; calc", "mute && del", "lauter"):
    assert st.normalize_command(raw) is None, raw
assert set(st.COMMANDS) == {"mute", "lock", "show_desktop", "brightness_set", "brightness_up", "brightness_down"}

# 2) Tasten und Sperren
r = st.system_control("mute")
assert r.success and keys == [(0xAD,)] and "Umschalter" in r.data["note"] and r.data["command"] == "mute"
keys.clear()
r = st.system_control("show_desktop")
assert r.success and keys == [(0x5B, 0x44)], keys
r = st.system_control("lock")
assert r.success and locks == [1] and r.data["done"] == "Bildschirm gesperrt" and "note" not in r.data
assert keys == [(0x5B, 0x44)], "Sperren drueckt keine Taste"

# 3) Prozentzahlen
for raw, expected in (("50", 50), ("50%", 50), (" 7 Prozent ", 7), (50, 50), (50.0, 50), ("0", 0), ("100", 100), ("50,0", 50)):
    assert st.parse_percent(raw) == expected, raw
for raw in ("", None, True, False, "101", "-5", 101, -1, 50.5, "abc", "50; calc", "5 0", "$(calc)", [], "1e2", "050x"):
    assert st.parse_percent(raw) is None, raw

# 4) Helligkeit
scripts.clear()
r = st.system_control("brightness_set", "80")
assert r.success and brightness[0] == 80 and r.data["brightness"] == 80 and "80 Prozent" in r.data["done"]
r = st.system_control("heller")
assert r.success and brightness[0] == 100 and r.data["brightness"] == 100, "80 + 20, bei 100 gedeckelt"
r = st.system_control("brightness_up")
assert r.data["brightness"] == 100
r = st.system_control("dunkler")
assert brightness[0] == 80
r = st.system_control("brightness_down", "30")
assert brightness[0] == 50, "eigener Schritt"
r = st.system_control("brightness_set", "0")
assert r.success and brightness[0] == st.MIN_BRIGHTNESS and "note" in r.data, "nie ganz schwarz"
brightness[0] = 10
r = st.system_control("dunkler")
assert brightness[0] == st.MIN_BRIGHTNESS and "note" in r.data
before = len(scripts)
for bad in ("", "hoch", "101", "5; calc", None, "$(calc)"):
    r = st.system_control("brightness_set", bad)
    assert not r.success and "Prozent" in r.error and "0 bis 100" in r.error, bad
assert len(scripts) == before, "ungueltiger Wert startet nichts"
# Nur gepruefte Zahlen im Skript
for script in scripts:
    assert script == st._GET or re.fullmatch(r"\(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods\)\.WmiSetBrightness\(1,\d{1,3}\)", script), script

# Die letzte Sicherung: _set_brightness lehnt alles ausser einer ganzen Zahl 5 bis 100 selbst ab
for bad in (0, 4, 101, -3, "5; calc", "abc", None, [50]):
    try:
        st._set_brightness(bad)
        raise SystemExit(f"Wert akzeptiert: {bad!r}")
    except (ValueError, TypeError):
        pass
assert len(scripts) == before, "abgelehnte Werte erreichen PowerShell nie"

# Bildschirm ohne Helligkeitssteuerung / PowerShell kaputt: klarer Satz
def broken(script):
    raise OSError("kein Monitor")


st._powershell = broken
for cmd, val in (("brightness_set", "50"), ("heller", ""), ("dunkler", "")):
    r = st.system_control(cmd, val)
    assert not r.success and "nicht von Windows" in r.error and "kein Monitor" not in r.error, cmd
st._powershell = lambda script: "kaputt"
r = st.system_control("heller")
assert not r.success and "nicht von Windows" in r.error, "Muell als Helligkeit"
st._powershell = lambda script: (_ for _ in ()).throw(subprocess.TimeoutExpired("powershell", 15))
assert not st.system_control("heller").success and not st.system_control("brightness_set", "40").success
st._powershell = fake_powershell

# 5) Ungueltig, nicht Windows, Fehler
keys.clear(); locks.clear(); scripts.clear()
for bad in ("", None, "shutdown", "lauter", {"description": "x", "type": "string"}, "lock; calc.exe"):
    r = st.system_control(bad)
    assert not r.success and "Rechnerbefehl" in r.error, bad
assert keys == [] and locks == [] and scripts == []
sys.platform = "linux"
for cmd in ("mute", "lock", "show_desktop", "heller"):
    r = st.system_control(cmd)
    assert not r.success and "Windows" in r.error
assert keys == [] and locks == [] and scripts == []
sys.platform = "win32"


def boom(_):
    raise OSError("kaputt")


good = st._press
st._press = boom
r = st.system_control("mute")
assert not r.success and "kaputt" in r.error
st._press = good
good_lock = st._lock
st._lock = lambda: boom(None)
assert not st.system_control("lock").success
st._lock = good_lock

# 6) Rueckfrage
assert st.describe("mute")[0].startswith("Ton stumm")
assert "Passwort" in st.describe("lock")[0] and "minimieren" in st.describe("show_desktop")[0]
assert st.describe("brightness_set", "40")[0] == "Helligkeit auf 40 Prozent" and st.describe("brightness_set", "x")[0] == "Helligkeit ändern"
assert "heller" in st.describe("heller")[0] and "dunkler" in st.describe("brightness_down")[0]
assert st.describe("???")[0] == "Rechnerbefehl" and all("gelöscht" in st.describe(c)[1] for c in st.COMMANDS)

# 7) Einbindung: Risiko, Rueckfrage, Executor, Fähigkeit, Gast
registry = TaskRegistry()
register_all_tasks(registry)
task = next(t for t in registry.get_all() if t.task_type == "SYSTEM_CONTROL")
assert [a.name for a in task.actions] == ["system_control"] and risk.task_risk(task) == risk.SAFE
assert risk.ACTION_RISK["system_control"] == risk.SAFE
# Nur das Sperren fragt vorher; alles andere (auch Unbekanntes, das ohnehin nichts tut) laeuft direkt
for command, expected in (("lock", risk.CONFIRM), ("Bildschirm sperren", risk.CONFIRM), ("sperren", risk.CONFIRM), ("LOCK", risk.CONFIRM),
                          ("mute", risk.SAFE), ("show_desktop", risk.SAFE), ("brightness_set", risk.SAFE), ("heller", risk.SAFE),
                          ("dunkler", risk.SAFE), ("", risk.SAFE), (None, risk.SAFE), ({"description": "x", "type": "string"}, risk.SAFE)):
    task.actions[0].parameters = {"command": command, "value": ""}
    assert risk.task_risk(task) == expected, command
task.actions[0].parameters = {"command": "lock", "value": ""}
goal, details = risk.describe_task(task)
assert goal == "Rechnerbefehl ausführen" and "Passwort" in " ".join(details) and "Stell den Ton" not in " ".join(details)
keys.clear()
res = action_executor.execute_action(Action("system_control", {"command": "mute", "value": ""}))
assert res.success and keys == [(0xAD,)]
res = action_executor.execute_action(Action("system_control", {"command": "brightness_set", "value": "70"}))
assert res.success and brightness[0] == 70
system = next(a for a in abilities.ABILITIES if a.id == "system")
assert system.default is True and system.tasks == ("SYSTEM_CONTROL",)
assert "SYSTEM_CONTROL" not in guest.GUEST_TASKS

# Das Modul kann nichts anderes: kein Herunterfahren, keine beliebige Taste, keine Shell
source = open(PROJECT_DIR / "tools" / "system_tool.py", encoding="utf-8").read()
code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
for forbidden in ("shell=True", "os.system", "shutdown", "Stop-Computer", "Restart-Computer", "ExitWindows", "eval(", "exec("):
    assert forbidden not in code.split('"""', 2)[2], forbidden

sys.platform = REAL_PLATFORM
print("ALL TESTS PASSED")
