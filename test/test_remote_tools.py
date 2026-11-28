"""Weitere PC-Werkzeuge ueber den Agenten (S6, G6): System-Befehle, Programme, Prozesse, Zwischenablage, Bildschirm, Browser."""
import base64
import sys
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

import device_commands as dc
import device_hub
import pc_agent
import remote_files
from tools import browser_tool, clipboard_tool, process_tool, program_tool, screen_tool, system_tool
from tools.tool_result import ToolResult

PNG = base64.b64encode(screen_tool.PNG_SIGNATURE + b"\x00" * 50).decode("ascii")
OK = {"success": True, "error": None, "data": {"x": 1}}


def raises(call):
    try:
        call()
    except dc.CommandError:
        return True
    return False


# 1) Parameter
for value in ("", "50", "50%"):
    assert dc.check_args("system.run", {"command": "brightness_set", "value": value}) == {"command": "brightness_set", "value": value}
for command in dc.SYSTEM_COMMANDS:
    assert dc.check_args("system.run", {"command": command, "value": ""})["command"] == command
for bad in ({"command": "shutdown", "value": ""}, {"command": "lock"}, {"command": "lock", "value": 5}, {"command": "lock", "value": "x" * 11},
            {"command": "lock", "value": "", "extra": 1}, {"command": 5, "value": ""}, None, [], "lock"):
    assert raises(lambda: dc.check_args("system.run", bad)), bad
assert dc.check_args("programs.find", {"program": "spotify"}) == {"program": "spotify"}
assert dc.check_args("programs.launch", {"target": "C:\\x\\a.exe"}) == {"target": "C:\\x\\a.exe"}
for command, key, limit in (("programs.find", "program", 100), ("programs.launch", "target", 500), ("clipboard.read", "question", 300)):
    assert dc.check_args(command, {key: "x" * limit}) and raises(lambda: dc.check_args(command, {key: "x" * (limit + 1)}))
    for bad in ({}, {key: 5}, {key: None}, {key: "a", "extra": 1}, None):
        assert raises(lambda: dc.check_args(command, bad)), (command, bad)
assert dc.check_args("browser.open", {"url": "https://a.de", "query": ""}) == {"url": "https://a.de", "query": ""}
assert raises(lambda: dc.check_args("browser.open", {"url": "x" * 2001, "query": ""})) and raises(lambda: dc.check_args("browser.open", {"url": "", "query": "q" * 201}))
assert raises(lambda: dc.check_args("browser.open", {"url": ""}))
for command in ("processes.list", "screen.capture"):
    assert dc.check_args(command, None) == {} and dc.check_args(command, {}) == {} and raises(lambda: dc.check_args(command, {"x": 1}))

# 2) Ergebnisse
for command in ("system.run", "programs.find", "programs.launch", "clipboard.read", "browser.open"):
    assert dc.check_result(command, dict(OK, evil="x")) == OK
    for bad in (None, {}, {"success": True}, dict(OK, success="ja"), dict(OK, error="e" * 401)):
        assert raises(lambda: dc.check_result(command, bad)), (command, bad)
GOOD = {"success": True, "error": None, "data": ["a.exe", "b.exe"]}
assert dc.check_result("processes.list", dict(GOOD, evil=1)) == GOOD
assert dc.check_result("processes.list", {"success": False, "error": "Nein", "data": None})["data"] is None
for bad in (dict(GOOD, data="x"), dict(GOOD, data=[5]), dict(GOOD, data=["x" * 101]), dict(GOOD, data=["a"] * 301), dict(GOOD, success=1)):
    assert raises(lambda: dc.check_result("processes.list", bad)), bad
assert dc.check_result("processes.list", dict(GOOD, data=["a"] * 300))
shot = {"success": True, "error": None, "data": {"image": PNG}}
assert dc.check_result("screen.capture", dict(shot, evil=1)) == shot
assert dc.check_result("screen.capture", {"success": False, "error": "Nein", "data": None})["data"] is None
for bad in (dict(shot, data={"image": 5}), dict(shot, data={}), dict(shot, data="x")):
    assert raises(lambda: dc.check_result("screen.capture", bad)), bad

# Groessen: nur das Bildschirmfoto darf gross sein; alles andere bleibt bei 64 KB
assert dc.result_limit("screen.capture") > 8_000_000 and dc.result_limit("clipboard.read") == dc.MAX_RESULT_BYTES == dc.result_limit("files.find")
big = {"success": True, "error": None, "data": {"image": "A" * 7_000_000}}
assert dc.check_result("screen.capture", big)["data"]["image"] == "A" * 7_000_000
assert raises(lambda: dc.check_result("screen.capture", {"success": True, "error": None, "data": {"image": "A" * (dc.MAX_IMAGE_CHARS + 1)}}))
assert raises(lambda: dc.check_result("clipboard.read", {"success": True, "error": None, "data": ["x" * 11000] * 8}))      # ueber 64 KB
assert dc.timeout_for("screen.capture") == 40 and dc.timeout_for("system.run") == 20


# 3) Server-Seite: Werkzeuge schicken Auftraege
class FakeHub:
    def __init__(self):
        self.calls, self.reply, self.error = [], dict(OK), None

    def request(self, command, args=None, **kw):
        self.calls.append((command, args))
        if self.error:
            raise self.error
        return self.reply


hub = FakeHub()
remote = remote_files._Remote(hub)
for module in (system_tool, program_tool, process_tool, clipboard_tool, screen_tool, browser_tool):
    module.set_remote(remote)

# System-Befehle: der Server prueft den Namen, der PC fuehrt aus (kein "nur unter Windows" mehr)
r = system_tool.system_control("sperren")
assert r.success and hub.calls[-1] == ("system.run", {"command": "lock", "value": ""})
r = system_tool.system_control("Helligkeit", 40)
assert hub.calls[-1] == ("system.run", {"command": "brightness_set", "value": "40"})
system_tool.system_control("brightness_set", "50%")
assert hub.calls[-1][1]["value"] == "50%"
system_tool.system_control("mute", True)
assert hub.calls[-1][1]["value"] == ""
system_tool.system_control("heller", "x" * 50)
assert hub.calls[-1][1]["value"] == "x" * 10
n = len(hub.calls)
r = system_tool.system_control("herunterfahren")
assert not r.success and "Rechnerbefehl" in r.error and len(hub.calls) == n                 # unbekannt: erreicht den PC nie

# Programme
r = program_tool.find_program("spotify")
assert r.success and hub.calls[-1] == ("programs.find", {"program": "spotify"})
program_tool.find_program(None)
assert hub.calls[-1] == ("programs.find", {"program": ""})
program_tool.find_program("x" * 500)
assert len(hub.calls[-1][1]["program"]) == 100
r = program_tool.launch_program("C:\\Programme\\a.exe")
assert r.success and hub.calls[-1] == ("programs.launch", {"target": "C:\\Programme\\a.exe"})
program_tool.launch_program(["x"])
assert hub.calls[-1] == ("programs.launch", {"target": ""})
assert len(hub.calls) > 0

# Prozesse, Zwischenablage, Browser
hub.reply = {"success": True, "error": None, "data": ["chrome.exe", "a\u200bb.exe"]}
r = process_tool.get_running_programs()
assert r.success and r.data == ["chrome.exe", "ab.exe"] and hub.calls[-1] == ("processes.list", {})
hub.reply = {"success": True, "error": None, "data": {"characters": 5, "text": "Hal\u200blo"}}
r = clipboard_tool.read_clipboard("Was ist das?")
assert r.data == {"characters": 5, "text": "Hallo"} and hub.calls[-1] == ("clipboard.read", {"question": "Was ist das?"})
clipboard_tool.read_clipboard(None)
assert hub.calls[-1] == ("clipboard.read", {"question": ""})
hub.reply = dict(OK)
n = len(hub.calls)
r = browser_tool.open_website("localhost")
assert not r.success and len(hub.calls) == n                                             # ungueltige Adresse: Server lehnt ab, PC wird nicht gefragt
n = len(hub.calls)
assert not browser_tool.open_website(query="x" * 500).success and len(hub.calls) == n          # zu lang: schon der Server lehnt ab
r = browser_tool.open_website(query="wetter berlin")
assert r.success and hub.calls[-1] == ("browser.open", {"url": "", "query": "wetter berlin"})
r = browser_tool.open_website("https://example.org/a")
assert r.success and hub.calls[-1] == ("browser.open", {"url": "https://example.org/a", "query": ""})

# Bildschirm: das Bild wird NICHT als Text bereinigt/gekuerzt, aber als PNG geprueft; Frage wird bereinigt
hub.reply = {"success": True, "error": None, "data": {"image": PNG}}
r = screen_tool.describe_screen("Was siehst du?")
assert r.success and r.data[screen_tool.IMAGE_KEY] == PNG and r.data["question"] == "Was siehst du?" and hub.calls[-1] == ("screen.capture", {})
long_png = base64.b64encode(screen_tool.PNG_SIGNATURE + b"\x01" * 3_000_000).decode("ascii")
hub.reply = {"success": True, "error": None, "data": {"image": long_png}}
assert screen_tool.describe_screen().data[screen_tool.IMAGE_KEY] == long_png               # nichts abgeschnitten
for bad in ({"image": "kein png"}, {"image": base64.b64encode(b"GIF89a....").decode()}, {"image": 5}, {}, None):
    hub.reply = {"success": True, "error": None, "data": bad}
    r = screen_tool.describe_screen()
    assert not r.success and "brauchbares Bild" in r.error, bad
hub.reply = {"success": False, "error": "Die Bild\u200bschirmaufnahme hat nicht geklappt.", "data": None}
assert screen_tool.describe_screen().error == "Die Bildschirmaufnahme hat nicht geklappt."

# PC aus / Zeitueberschreitung / ungueltiger Auftrag: klare Meldung, nie eine Ausnahme
hub.reply = dict(OK)
for error, text in ((device_hub.DeviceOffline("Der PC ist gerade nicht erreichbar."), "nicht erreichbar"),
                    (device_hub.DeviceTimeout("Der PC hat nicht rechtzeitig geantwortet."), "rechtzeitig"),
                    (device_hub.DeviceFailed("Das Gerät konnte den Auftrag nicht ausführen."), "nicht ausführen"),
                    (dc.CommandError("Falsche Parameter."), "Falsche Parameter")):
    hub.error = error
    for result in (system_tool.system_control("lock"), program_tool.find_program("a"), program_tool.launch_program("a"), process_tool.get_running_programs(),
                   clipboard_tool.read_clipboard(), screen_tool.describe_screen(), browser_tool.open_website("https://example.org")):
        assert not result.success and text in result.error, (text, result.error)
hub.error = None

# Ohne Verbindung zum Agenten (set_remote(None)) bleibt alles lokal wie vorher
for module in (system_tool, program_tool, process_tool, clipboard_tool, screen_tool, browser_tool):
    module.set_remote(None)
n = len(hub.calls)
if not sys.platform.startswith("win"):
    assert system_tool.system_control("lock").error == "Diese Befehle funktionieren nur unter Windows."
    assert clipboard_tool.read_clipboard().error == "Die Zwischenablage kann Jarvis nur unter Windows lesen."
    assert screen_tool.describe_screen().error == "Den Bildschirm kann Jarvis nur unter Windows ansehen."
assert len(hub.calls) == n

# 4) Agent-Seite: die echten Werkzeuge laufen dort (hier ersetzt), Umschlag/Antwort passen zur Liste
handlers = pc_agent.default_handlers()
for command in ("system.run", "programs.find", "programs.launch", "processes.list", "clipboard.read", "screen.capture", "browser.open"):
    assert command in handlers and command in dc.COMMANDS, command
seen = {}


def fake(module, name, result):
    def run(*args):
        seen[name] = args
        return result
    setattr(module, name, run)


fake(system_tool, "system_control", ToolResult(success=True, data={"command": "lock", "done": "Bildschirm gesperrt"}))
out = handlers["system.run"]({"command": "lock", "value": ""})
assert out == {"success": True, "error": None, "data": {"command": "lock", "done": "Bildschirm gesperrt"}} and seen["system_control"] == ("lock", "")
assert dc.check_result("system.run", out)
fake(system_tool, "system_control", ToolResult(success=False, error="Der Befehl ließ sich nicht ausführen: x"))
out = handlers["system.run"]({"command": "lock", "value": ""})
assert out["success"] is False and out["data"] is None and "nicht ausführen" in out["error"] and dc.check_result("system.run", out)
fake(program_tool, "find_program", ToolResult(success=True, data="C:\\Spotify.exe"))
assert handlers["programs.find"]({"program": "spotify"})["data"] == "C:\\Spotify.exe" and seen["find_program"] == ("spotify",)
fake(program_tool, "launch_program", ToolResult(success=False, error="Dieses Programm ist nicht freigegeben. Trage es in programs.json ein, wenn ich es starten soll."))
out = handlers["programs.launch"]({"target": "C:\\evil.exe"})
assert out["success"] is False and "nicht freigegeben" in out["error"] and dc.check_result("programs.launch", out)
fake(process_tool, "get_running_programs", ToolResult(success=True, data=["a.exe", "b" * 300] + [f"p{i}.exe" for i in range(400)]))
out = handlers["processes.list"]({})
assert len(out["data"]) == 300 and len(out["data"][1]) == 100 and dc.check_result("processes.list", out)
fake(process_tool, "get_running_programs", ToolResult(success=False, error="C:\\geheim\\pfad"))
out = handlers["processes.list"]({})
assert out["success"] is False and "geheim" not in out["error"] and out["data"] is None and dc.check_result("processes.list", out)
fake(clipboard_tool, "read_clipboard", ToolResult(success=True, data={"characters": 3, "text": "abc"}))
assert handlers["clipboard.read"]({"question": "was?"})["data"]["text"] == "abc" and seen["read_clipboard"] == ("was?",)
fake(screen_tool, "describe_screen", ToolResult(success=True, data={screen_tool.IMAGE_KEY: PNG, "image": "Text", "question": "x"}))
out = handlers["screen.capture"]({})
assert out == {"success": True, "error": None, "data": {"image": PNG}} and seen["describe_screen"] == ("",) and dc.check_result("screen.capture", out)
fake(screen_tool, "describe_screen", ToolResult(success=False, error="Die Bildschirmaufnahme hat nicht geklappt."))
out = handlers["screen.capture"]({})
assert out["success"] is False and out["data"] is None and dc.check_result("screen.capture", out)
fake(browser_tool, "open_website", ToolResult(success=True, data={"kind": "website", "host": "example.org", "url": "https://example.org/", "done": "ok"}))
assert handlers["browser.open"]({"url": "https://example.org", "query": ""})["success"] and seen["open_website"] == ("https://example.org", "")

# 5) Alle Befehle des Agents stehen in der Liste und umgekehrt (nichts Verstecktes)
assert set(handlers) == set(dc.COMMANDS), set(handlers) ^ set(dc.COMMANDS)
print("ALL TESTS PASSED")
