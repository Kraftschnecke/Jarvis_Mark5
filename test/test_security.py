import json
import os
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


class FakeTimeout(Exception):
    pass


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing(
    "requests",
    get=None,
    exceptions=types.SimpleNamespace(Timeout=FakeTimeout)
)
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

import requests
from tools import file_tool, program_tool, web_search_tool
import task_executor
from task_registry import TaskRegistry
from tasks import register_all_tasks

# Nichts davon darf wirklich etwas starten
started = []
os.startfile = lambda target: started.append(target)
program_tool.platform.system = lambda: "Windows"

tmp = Path(tempfile.mkdtemp())


# =====================================================================
# open_file: Dokumente ja, Programme nein
# =====================================================================

def make(name, content="x"):
    path = tmp / name
    path.write_text(content)
    return str(path)


# Harmlose Dateien und Ordner werden geoeffnet
for name in ("notiz.txt", "bericht.pdf", "bild.PNG"):
    started.clear()
    result = file_tool.open_file(make(name))
    assert result.success and started == [str(tmp / name)], name

started.clear()
assert file_tool.open_file(str(tmp)).success  # Ordner -> Explorer

# Ausfuehrbares wird blockiert, in jeder Schreibweise
for name in (
    "spiel.exe", "SPIEL.EXE", "run.bat", "run.CMD", "setup.msi",
    "skript.ps1", "x.vbs", "x.js", "link.lnk", "x.url", "x.jar",
    "tool.exe.",      # Windows ignoriert den Punkt am Ende
):
    started.clear()
    result = file_tool.open_file(make(name))
    assert not result.success, name
    assert started == [], name
    assert "programs.json" in result.error

# Leerzeichen am Ende ("x.exe ") umgehen die Sperre nicht
started.clear()
exe = make("leer.exe")
for variant in (exe + " ", " " + exe, exe + "  "):
    result = file_tool.open_file(variant)
    assert not result.success and "programs.json" in result.error, repr(variant)
assert started == []

# Verknuepfung auf eine exe: das Ziel zaehlt
target = make("boese.exe")
started.clear()
link = tmp / "harmlos.txt"
try:
    os.symlink(target, link)   # sieht aus wie .txt, zeigt auf eine .exe
except OSError:
    # Windows erlaubt Symlinks ohne Admin-Recht / Entwicklermodus nicht.
    print("Hinweis: Symlink-Test uebersprungen (fehlendes Windows-Recht).")
else:
    assert not file_tool.open_file(str(link)).success
    assert started == []

# Web-Adressen, Netzwerkpfade, leere und fehlende Pfade
for bad in (
    "https://evil.example/x.pdf", "file:///C:/x.txt", "ms-msdt://x",
    "\\\\server\\share\\x.txt", "//server/share/x.txt",
    "", "   ", None, str(tmp / "gibtsnicht.txt")
):
    started.clear()
    assert not file_tool.open_file(bad).success, bad
    assert started == [], bad


# =====================================================================
# Programme: nur Freigabeliste
# =====================================================================

programs_file = tmp / "programs.json"
program_tool.PROGRAMS_FILE = programs_file


def write_programs(data):
    programs_file.write_text(
        data if isinstance(data, str) else json.dumps(data)
    )


write_programs({
    "Rainbow Six Siege": "C:/Games/R6/RainbowSix.exe",
    "steam": "C:/Steam/steam.exe",
    "counter strike": "steam://rungameid/730",
    "counter strike 2": "steam://rungameid/9999",
})
program_tool.shutil.which = lambda exe: {"notepad.exe": "C:/Windows/notepad.exe"}.get(exe)


def found(name):
    result = program_tool.find_program(name)
    return result.data if result.success else None


# Name genau, Gross-/Kleinschreibung egal, Leerzeichen egal
assert found("rainbow six siege") == "C:/Games/R6/RainbowSix.exe"
assert found("  RAINBOW SIX SIEGE ") == "C:/Games/R6/RainbowSix.exe"
assert found("counter strike") == "steam://rungameid/730"      # exakt gewinnt
# Teilname, wenn eindeutig
assert found("rainbow") == "C:/Games/R6/RainbowSix.exe"
# Mehrdeutig: Fehler mit Auswahl statt Raten
result = program_tool.find_program("counter")
assert not result.success and "counter strike 2" in result.error
# Zu kurz fuer Teiltreffer
assert found("st") is None and found("s") is None
# Eingebaute Programme
assert found("notepad") == "C:/Windows/notepad.exe"
assert found("editor") == "C:/Windows/notepad.exe"
# Unbekannt, leer, und vor allem: freie Pfade werden NICHT gesucht
for unknown in ("chrome", "", "C:/Users/x/Downloads/boese.exe", "cmd", "powershell"):
    result = program_tool.find_program(unknown)
    assert not result.success, unknown
assert "programs.json" in program_tool.find_program("chrome").error

# Datei fehlt -> nur eingebaute Programme, kein Absturz
programs_file.unlink()
assert found("notepad") == "C:/Windows/notepad.exe"
assert found("rainbow six siege") is None

# Kaputte Datei -> verstaendliche Meldung, kein Absturz
for broken in ("{kaputt", "[1, 2]", '{"a": "C:\\Games\\x.exe"}'):
    write_programs(broken)
    result = program_tool.find_program("steam")
    assert not result.success and "programs.json" in result.error, broken

# Start: nur Freigegebenes
write_programs({"steam": "C:/Steam/steam.exe", "cs": "steam://rungameid/730"})
started.clear()
assert program_tool.launch_program("C:/Steam/steam.exe").success
assert program_tool.launch_program("steam://rungameid/730").success
assert program_tool.launch_program("C:/Windows/notepad.exe").success
assert started == ["C:/Steam/steam.exe", "steam://rungameid/730", "C:/Windows/notepad.exe"]

started.clear()
for evil in ("C:/Users/x/Downloads/boese.exe", "cmd.exe", "steam://evil", "", None, ["x"]):
    result = program_tool.launch_program(evil)
    assert not result.success, evil
assert started == []

# Kaputte Freigabeliste: nichts startet
write_programs("{kaputt")
assert not program_tool.launch_program("C:/Steam/steam.exe").success
assert started == []


# =====================================================================
# Ganze Tasks: kein Umweg ueber einen eigenen Programmpfad
# =====================================================================

write_programs({"rainbow six siege": "C:/Games/R6/RainbowSix.exe"})
registry = TaskRegistry()
register_all_tasks(registry)

started.clear()
task = task_executor.execute_registered_task(
    registry, "START_PROGRAM", {"program": "rainbow six"}, confirmed=True
)
assert task.status == "COMPLETED", task.error
assert started == ["C:/Games/R6/RainbowSix.exe"]

# OPEN_PROGRAM gibt es nicht mehr: ein Task mit eigenem Pfad ist nicht moeglich
started.clear()
assert registry.get("OPEN_PROGRAM") is None
assert task_executor.execute_registered_task(
    registry, "OPEN_PROGRAM", {"path": "C:/Users/x/Downloads/boese.exe"}
) is None
assert started == []

# ... oder ueber START_PROGRAM mit einem Pfad als "Programmname"
task = task_executor.execute_registered_task(
    registry, "START_PROGRAM", {"program": "C:/Users/x/Downloads/boese.exe"},
    confirmed=True
)
assert task.status == "FAILED" and started == []

# OPEN_FILE mit einer exe
task = task_executor.execute_registered_task(
    registry, "OPEN_FILE", {"path": make("trojaner.exe")}, confirmed=True
)
# Programmdateien sind forbidden: sie laufen auch mit Bestaetigung nicht
assert task.status == "BLOCKED" and started == []


# =====================================================================
# Websuche: Timeout, fehlender Key, leere Ergebnisse
# =====================================================================

calls = []


def fake_fetch_json(url, hosts, **kwargs):
    calls.append({"url": url, "hosts": hosts, **kwargs})
    return {"web": {"results": [
        {"title": "T", "url": "https://a.example", "description": "D"},
        {"url": "https://b.example"}          # Felder fehlen
    ]}}


web_search_tool.fetch_json = fake_fetch_json

# Ohne Key: klare Meldung, keine Anfrage
web_search_tool.BRAVE_API_KEY = None
result = web_search_tool.search_web("wetter")
assert not result.success and "BRAVE_API_KEY" in result.error and calls == []

# Mit Key: Timeout gesetzt, Key im Header, nur der Brave-Host, fehlende Felder crashen nicht
web_search_tool.BRAVE_API_KEY = "geheim"
result = web_search_tool.search_web("wetter")
assert result.success and len(result.data) == 2
assert result.data[1] == {"title": "", "url": "https://b.example", "description": ""}
assert calls[0]["timeout"] == web_search_tool.REQUEST_TIMEOUT_SECONDS
assert calls[0]["headers"]["X-Subscription-Token"] == "geheim"
assert calls[0]["hosts"] == ("api.search.brave.com",) and calls[0]["params"] == {"q": "wetter"}

# Keine Treffer ("web" fehlt): leere Liste statt KeyError
web_search_tool.fetch_json = lambda url, hosts, **k: {}
result = web_search_tool.search_web("xyz")
assert result.success and result.data == []

# Netzfehler (Timeout, kein Netz, Fehlercode): freundliche Meldung mit dem Grund
def failing(url, hosts, **kwargs):
    raise web_search_tool.NetError("Der Dienst hat nicht rechtzeitig geantwortet.")

web_search_tool.fetch_json = failing
result = web_search_tool.search_web("wetter")
assert not result.success and "nicht rechtzeitig" in result.error

print("ALL TESTS PASSED")
