"""Desktop-App (Mark 5, Step 4B.3): Browsersuche, Fensterbefehl, Autostart, Tray-Menue, sauberes Beenden des Servers."""
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
import types as _types
import urllib.request

import jarvis_app
from jarvis_app import Autostart, DesktopApp, autostart_command, find_browser, port_in_use, wait_until_up, window_command

# 1) Browser finden: Edge zuerst, dann Chrome, sonst None
env = {"ProgramFiles(x86)": "C:/PF86", "ProgramFiles": "C:/PF"}
edge = str(Path("C:/PF86") / "Microsoft/Edge/Application/msedge.exe")
chrome = str(Path("C:/PF") / "Google/Chrome/Application/chrome.exe")
assert find_browser(env, lambda p: p in (edge, chrome)) == edge
assert find_browser(env, lambda p: p == chrome) == chrome
assert find_browser(env, lambda p: False) is None
assert find_browser({}, lambda p: True) is None

# 2) Fensterbefehl: App-Modus, eigenes Profil, nur die lokale Adresse
cmd = window_command("edge.exe", "http://localhost:8000", Path("prof"))
assert cmd[0] == "edge.exe" and "--app=http://localhost:8000" in cmd
assert any(part.startswith("--user-data-dir=") and part.endswith("prof") for part in cmd)

# 3) Port-Pruefung und Warten auf den Server
class Conn:
    closed = False
    def close(self):
        Conn.closed = True

def refuse(addr, timeout):
    raise OSError("zu")

assert port_in_use("127.0.0.1", 8000, lambda addr, timeout: Conn()) is True and Conn.closed
assert port_in_use("127.0.0.1", 8000, refuse) is False

calls = []
def flaky(url):
    calls.append(url)
    if len(calls) < 3:
        raise OSError("noch nicht")

assert wait_until_up("http://x", fetch=flaky, sleep=lambda s: None) is True and len(calls) == 3
now = [0.0]
def tick():
    now[0] += 10
    return now[0]
assert wait_until_up("http://x", timeout=25, fetch=lambda u: 1 / 0, sleep=lambda s: None, clock=tick) is False

# 4) Autostart: Eintrag im Registry-Ersatz anlegen, erkennen, entfernen
class FakeRegistry:
    def __init__(self):
        self.values = {}
    def get(self, name):
        return self.values.get(name)
    def set(self, name, value):
        self.values[name] = value
    def delete(self, name):
        self.values.pop(name, None)

registry = FakeRegistry()
auto = Autostart(registry, '"py.exe" "app.py" --background')
assert auto.is_enabled() is False
assert auto.toggle() is True and registry.values == {"JARVIS": '"py.exe" "app.py" --background'}
assert auto.toggle() is False and registry.values == {}
registry.values["JARVIS"] = "etwas anderes"
assert auto.is_enabled() is False                      # fremder Eintrag zaehlt nicht als "an"
auto.disable(); auto.disable()                         # doppeltes Entfernen ist harmlos
assert autostart_command("C:/Py/python.exe", "C:/J/jarvis_app.py", exists=lambda p: True) == '"' + str(Path("C:/Py/pythonw.exe")) + '" "C:/J/jarvis_app.py" --background'
assert autostart_command("C:/Py/python.exe", "C:/J/jarvis_app.py", exists=lambda p: False).startswith('"C:/Py/python.exe"')

# 5) App-Logik: Fenster oeffnen (nur eines), Beenden (nur einmal), Menue
class FakeProcess:
    def __init__(self):
        self.alive = True
    def poll(self):
        return None if self.alive else 0

spawned, stops, quits = [], [], []
def spawn(command):
    process = FakeProcess()
    spawned.append((command, process))
    return process

app = DesktopApp("http://localhost:8000", "edge.exe", spawn, lambda: stops.append(1), auto)
app.on_quit = lambda: quits.append(1)
assert app.open_window() is True and len(spawned) == 1 and app.window_open()
assert app.open_window() is False and len(spawned) == 1   # schon offen: kein zweites Fenster
spawned[0][1].alive = False
assert not app.window_open()
assert app.open_window() is True and len(spawned) == 2     # nach dem Schliessen geht es wieder auf
assert [item[0] for item in app.menu()] == ["Jarvis öffnen", "Mit Windows starten", "Beenden"]
assert app.menu()[1][2]() is False
app.menu()[1][1]()
assert app.menu()[1][2]() is True
app.quit(); app.quit()
assert stops == [1] and quits == [1] and app.quit_event.is_set()
assert [item[0] for item in DesktopApp("u", "b", spawn, lambda: None).menu()] == ["Jarvis öffnen", "Beenden"]   # ohne Autostart (nicht Windows)

# ohne Tray: Fenster zu = Beenden-Signal wird abgewartet
waiter = DesktopApp("u", "b", spawn, lambda: None)
waiter.open_window()
polls = []
def sleep_and_close(seconds):
    polls.append(seconds)
    waiter.window.alive = False
waiter.wait_for_window_close(sleep=sleep_and_close)
assert polls == [0.5] and not waiter.window_open()

# ohne gefundenen Browser: Notausgang ueber den Standardbrowser, kein Absturz
import webbrowser
opened = []
real_open = webbrowser.open
webbrowser.open = lambda u: opened.append(u)
try:
    assert DesktopApp("http://localhost:8000", None, spawn, lambda: None).open_window() is True
finally:
    webbrowser.open = real_open
assert opened == ["http://localhost:8000"]

# 6) Tray ohne pystray/Pillow: kein Absturz, einfach None
saved = {name: sys.modules.get(name) for name in ("pystray", "PIL")}
sys.modules["pystray"] = None
try:
    assert jarvis_app.make_tray(app) is None
finally:
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module

# 6b) Tray mit einem Ersatz fuer pystray, der wie das echte die Parameterzahl der Funktionen prueft
class FakeMenuItem:
    def __init__(self, text, action, checked=None, default=False):
        count = action.__code__.co_argcount
        if count != 2:
            raise ValueError(action)           # echtes pystray lehnt z. B. Default-Argumente ab
        if checked is not None and checked.__code__.co_argcount != 1:
            raise ValueError(checked)
        self.text, self.action, self.checked, self.default = text, action, checked, default

class FakeIcon:
    def __init__(self, name, image, title, menu):
        self.menu, self.stopped = menu, False
    def stop(self):
        self.stopped = True

fake_pystray = _types.ModuleType("pystray")
fake_pystray.MenuItem = FakeMenuItem
fake_pystray.Menu = lambda *items: list(items)
fake_pystray.Icon = FakeIcon
fake_pil = _types.ModuleType("PIL")
fake_pil.Image = _types.SimpleNamespace(open=lambda path: ("bild", str(path)))
saved = {name: sys.modules.get(name) for name in ("pystray", "PIL")}
sys.modules["pystray"], sys.modules["PIL"] = fake_pystray, fake_pil
try:
    tray_app = DesktopApp("u", "b", spawn, lambda: stops.append("tray"), auto)
    icon = jarvis_app.make_tray(tray_app)
    items = icon.menu
    assert [item.text for item in items] == ["Jarvis öffnen", "Mit Windows starten", "Beenden"]
    assert items[0].default is True and items[1].default is False
    before = len(spawned)
    items[0].action(icon, items[0])                    # Klick auf "Jarvis öffnen"
    assert len(spawned) == before + 1
    state = items[1].checked(items[1])
    items[1].action(icon, items[1])                    # Haken umschalten
    assert items[1].checked(items[1]) is (not state)
    tray_app.on_quit = icon.stop
    items[2].action(icon, items[2])                    # Beenden
    assert icon.stopped and stops[-1] == "tray"
finally:
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module

# 6c) Strg+C in der Konsole beendet sauber; "Beenden" im Tray beendet die Warteschleife
ctrl_app = DesktopApp("u", "b", spawn, lambda: stops.append("ctrl"))
def interrupted():
    raise KeyboardInterrupt
jarvis_app.wait_for_quit(ctrl_app, wait=interrupted)
assert ctrl_app.quit_event.is_set() and stops[-1] == "ctrl"
quit_app = DesktopApp("u", "b", spawn, lambda: None)
answers = iter([False, False, True])
jarvis_app.wait_for_quit(quit_app, wait=lambda: next(answers))      # endet, sobald wait() True liefert
assert next(answers, "leer") == "leer"
real_quit = DesktopApp("u", "b", spawn, lambda: None)
real_quit.quit()
jarvis_app.wait_for_quit(real_quit)                                 # schon beendet: kehrt sofort zurueck

# 7) Echter Serverstart wie in der App: main() mit on_ready, ohne Browser, sauber beendbar
import server, webbrowser as wb

class FakeJarvis:
    def handle(self, *a, **k):
        return ""

fake_module = _types.ModuleType("jarvis")
fake_module.Jarvis = FakeJarvis
sys.modules["jarvis"] = fake_module
opened.clear()
wb.open = lambda u: opened.append(u)
server.REMOTE_HOST = ""                                 # unabhaengig von der .env des Rechners (dort kann ein Remote-Name stehen)
handle = jarvis_app.ServerHandle()
handle.stop()                                           # vor dem Start: harmlos
thread = threading.Thread(target=server.main, kwargs={"argv": ["--port", "0"], "on_ready": handle.on_ready, "open_browser": False})
thread.start()
try:
    assert handle.ready.wait(20), "Server nicht gestartet"
    port = handle.httpd.server_address[1]
    assert wait_until_up(f"http://localhost:{port}/", timeout=10)
    assert opened == []                                 # open_browser=False: kein Browser aus dem Server heraus
    assert port_in_use("127.0.0.1", port)
finally:
    handle.stop()
    thread.join(20)
    wb.open = real_open
assert not thread.is_alive()                            # main() hat aufgeraeumt und ist zurueckgekehrt
assert not port_in_use("127.0.0.1", port)               # Port wieder frei

# 8) Sicherheit/Einbindung: Server bleibt lokal, Quelltext ohne Fernsteuerung
source = (PROJECT_DIR / "jarvis_app.py").read_text(encoding="utf-8")
for forbidden in ("0.0.0.0", "shell=True", "os.system", "eval(", "exec("):
    assert forbidden not in source, forbidden
assert "SERVER_HOST = \"127.0.0.1\"" in (PROJECT_DIR / "config.py").read_text(encoding="utf-8")
assert ".jarvis_app_profile" in (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")
assert "pystray" in (PROJECT_DIR / "requirements.txt").read_text(encoding="utf-8")
assert "jarvis_app.py" in (PROJECT_DIR / "start_jarvis_app.bat").read_text(encoding="utf-8")

print("ALL TESTS PASSED")
