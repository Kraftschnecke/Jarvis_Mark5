"""Programme aus dem Startmenue (Get-StartApps): "Apple Music" geht ohne programs.json; Shells und Fremdes bleiben draussen."""
import json
import sys
import tempfile
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

try:
    import psutil  # noqa: F401
except ImportError:
    stub = types.ModuleType("psutil")
    stub.NoSuchProcess = stub.AccessDenied = Exception
    sys.modules["psutil"] = stub

import pc_agent  # noqa: F401  (Agent-Handler unten)
from tools import program_tool

tmp = Path(tempfile.mkdtemp())
program_tool.PROGRAMS_FILE = tmp / "programs.json"
program_tool.platform.system = lambda: "Windows"
program_tool.shutil.which = lambda exe: {"notepad.exe": "C:/Windows/notepad.exe"}.get(exe)
started = []
program_tool.os.startfile = lambda target: started.append(target)

APPS = [
    ("Apple Music", "AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"),
    ("Spotify", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
    ("Apple TV", "AppleInc.AppleTVWin_nzyj5cx40ttqa!App"),
    ("Groove  Musik", "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"),
    ("Steam", "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}\\Steam\\steam.exe"),
    ("Windows PowerShell", "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"),
    ("Eingabeaufforderung", "Microsoft.WindowsCommandPrompt"),
    ("Windows Terminal", "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"),
    ("Registrierungs-Editor", "{F38BF404-1D43-42F2-9305-67DE0B28FC23}\\regedit.exe"),
    ("Uninstall Steam", "{7C5A40EF}\\Steam\\uninstall.exe"),
    ("Boese", "x;y&calc"),
    ("", "Leer.App"),
    ("Kein Text", None),
]
reads = []
now = [1000.0]
clock = lambda: now[0]


def reader():
    reads.append(1)
    return list(APPS)


program_tool._read_start_apps = reader


def reset():
    program_tool._start_apps_cache.update({"time": None, "apps": {}})
    reads.clear()
    started.clear()


def find(name):
    result = program_tool.find_program(name)
    return result.data if result.success else result.error


# 1) Namen: genau, Gross/Klein egal, Leerzeichen zusammengefasst, eindeutiger Teilname; Auswahl bei Mehrdeutigem
reset()
assert find("apple music") == "shell:AppsFolder\\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"
assert find("  APPLE   Music ") == "shell:AppsFolder\\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"
assert find("spotify") == "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
assert find("groove") == "shell:AppsFolder\\Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"          # eindeutiger Teilname
assert find("steam") == "shell:AppsFolder\\{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}\\Steam\\steam.exe"
error = find("apple")
assert error.startswith("Mehrere Programme passen zu 'apple': ") and "apple music" in error and "apple tv" in error
assert find("music") == "shell:AppsFolder\\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"                           # nur ein Name enthaelt "music"
assert find("zz")[:7] == "Program" and find("s")[:7] == "Program"                                           # zu kurz fuer Teiltreffer
assert len(reads) == 1, reads                                                                                # Liste nur einmal gelesen (gemerkt)

# 2) Nicht dabei: Shells, Terminal, Registry, Deinstallation, ungueltige IDs und Namen
for name in ("powershell", "windows powershell", "eingabeaufforderung", "terminal", "windows terminal", "registrierungs-editor", "regedit", "uninstall steam",
             "boese", "kein text"):
    assert find(name)[:7] in ("Program", "Mehrere"), (name, find(name))
    assert not find(name).startswith("shell:"), name
apps = program_tool.start_apps()
assert set(apps) == {"apple music", "spotify", "apple tv", "groove musik", "steam"}, set(apps)
assert all(target.startswith("shell:AppsFolder\\") for target in apps.values())

# 3) Vorrang: programs.json und eingebaute Programme vor dem Startmenue
(tmp / "programs.json").write_text(json.dumps({"spotify": "C:/Spotify/Spotify.exe"}))
assert find("spotify") == "C:/Spotify/Spotify.exe"
assert find("notepad") == "C:/Windows/notepad.exe"
assert find("apple music").startswith("shell:")
(tmp / "programs.json").unlink()

# 4) Start: Startmenue-Programme ja, alles andere weiter nur mit Freigabe
reset()
target = find("apple music")
assert program_tool.launch_program(target).success and started == [target]
started.clear()
for evil in ("shell:AppsFolder\\Microsoft.WindowsTerminal_8wekyb3d8bbwe!App", "shell:AppsFolder\\x", "shell:AppsFolder\\", "powershell.exe", "cmd.exe",
             "shell:Startup", "C:/Users/x/Downloads/boese.exe", "", None, ["x"]):
    assert not program_tool.launch_program(evil).success, evil
assert started == []
assert program_tool.launch_program("C:/Windows/notepad.exe").success

# 5) Merken und Nachlesen: Treffer aus dem Speicher; Fehltreffer liest erst nach 20 s neu (z. B. nach einer Installation)
reset()
find("spotify")
assert len(reads) == 1
now[0] += 5
find("spotify")
assert len(reads) == 1
orig = program_tool.time.monotonic
program_tool.time.monotonic = clock
program_tool._start_apps_cache["time"] = None
program_tool.start_apps(clock=clock)
n = len(reads)
assert program_tool._from_start_apps("nichtda", clock=clock) is None and len(reads) == n                      # gerade gelesen: kein zweiter Versuch
now[0] += program_tool.START_APPS_RETRY + 1
assert program_tool._from_start_apps("nichtda", clock=clock) is None and len(reads) == n + 1                  # spaeter: einmal neu gelesen
APPS.append(("Neues Spiel", "Studio.Neu!App"))
now[0] += program_tool.START_APPS_RETRY + 1
assert program_tool._from_start_apps("neues spiel", clock=clock) == "shell:AppsFolder\\Studio.Neu!App"         # neu installiert: gefunden
APPS.pop()
now[0] += program_tool.START_APPS_TTL + 1
reads.clear()
program_tool.start_apps(clock=clock)
assert len(reads) == 1                                                                                          # nach 5 Minuten neu
program_tool.time.monotonic = orig

# 6) Lesefehler: kein Absturz, Meldung wie vorher
reset()
program_tool._read_start_apps = lambda: (_ for _ in ()).throw(OSError("PowerShell fehlt"))
assert find("spotify")[:7] == "Program" and program_tool.start_apps() == {}
program_tool._read_start_apps = lambda: [("A" * 150, "A.B"), ("Gut", "G" * 301), ("Okay", "Ok.App!x")] * 400
reset()
assert set(program_tool.start_apps()) == {"okay"}
program_tool._read_start_apps = reader

# 6b) Erster Lookup mit leerem Speicher liest nur einmal, auch bei Fehltreffer; Duplikate: der erste Name gilt; Obergrenze; Teilname am Anfang gewinnt
reset()
assert find("nichtda")[:7] == "Program" and len(reads) == 1, reads
program_tool._read_start_apps = lambda: [("Doppelt", "A.One!App"), ("doppelt", "B.Two!App"), ("Apple Music", "Apple.Music!App"), ("Pineapple", "Pine.Apple!App")]
reset()
assert find("doppelt") == "shell:AppsFolder\\A.One!App"
assert find("apple") == "shell:AppsFolder\\Apple.Music!App"                                                   # zwei Treffer, nur einer beginnt damit
program_tool._read_start_apps = lambda: [(f"App {i}", f"Pub.App{i}!App") for i in range(program_tool.MAX_START_APPS + 100)]
reset()
assert len(program_tool.start_apps()) == program_tool.MAX_START_APPS
program_tool._read_start_apps = reader

# 7) Echter Lesefehler-Pfad ausserhalb von Windows: leer
import importlib
fresh = importlib.reload(program_tool)
assert fresh._read_start_apps() == [] or sys.platform.startswith("win")

print("ALL TESTS PASSED")

# Kommandozeilen werden nie ueber den Namen gefunden, auch nicht als Teiltreffer
program_tool._read_start_apps = lambda: [("Cmd Helper", "Pub.Cmd!App"), ("Gut", "Pub.Gut!App")]
program_tool.start_apps(force=True)
for shell in ("cmd", "powershell", "terminal", "regedit"):
    assert program_tool._from_start_apps(shell) is None, shell
assert program_tool._from_start_apps("gut") == "shell:AppsFolder\\Pub.Gut!App"
print("ALL TESTS PASSED")
