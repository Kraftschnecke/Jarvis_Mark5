"""Systemanbindung (Mark 5, Step 4B.4): Hotkey-Text, Hotkey-Lauscher, Fenster nach vorn, Benachrichtigungen fuer Wecker/Timer."""
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

import queue
import threading
import time

import desktop_system
import jarvis_app
from desktop_system import (HotkeyListener, RingWatcher, focus_window, is_foreground, notification_for, parse_hotkey,
                            short_label)

# 1) Hotkey-Text lesen
assert parse_hotkey("ctrl+space") == (0x2, 0x20)
assert parse_hotkey("  Strg + Space ") == (0x2, 0x20)
assert parse_hotkey("alt+j") == (0x1, ord("J"))
assert parse_hotkey("ctrl+shift+f9") == (0x2 | 0x4, 0x78)
assert parse_hotkey("win+1") == (0x8, ord("1"))
assert parse_hotkey("ctrl+alt+f12") == (0x3, 0x7B)
for off in ("", "off", "AUS", "none", None):
    assert parse_hotkey(off) is None
for bad in ("space", "j", "ctrl+", "+", "ctrl++x", "foo+x", "ctrl+f13", "ctrl+f0", "ctrl+ä", "ctrl+enter", "ctrl+ab"):
    try:
        parse_hotkey(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"{bad!r} haette abgelehnt werden muessen")


# 2) Hotkey-Lauscher mit Attrappe fuer Windows
class FakeHotkeyApi:
    def __init__(self, register_ok=True):
        self.register_ok = register_ok
        self.events = queue.Queue()
        self.registered_with = None
        self.unregistered = False
    def register(self, mods, code):
        self.registered_with = (mods, code)
        return self.register_ok
    def next_event(self):
        return self.events.get(timeout=5)
    def unregister(self):
        self.unregistered = True
    def stop(self):
        self.events.put(False)


def wait_for(condition, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False

api = FakeHotkeyApi()
pressed, logs = [], []
def action():
    pressed.append(1)
    if len(pressed) == 1:
        raise RuntimeError("Fenster kaputt")            # darf den Hotkey nicht beenden

listener = HotkeyListener("ctrl+space", action, api_factory=lambda: api, log=logs.append)
assert listener.start() is True and api.registered_with == (0x2, 0x20)
api.events.put(True); api.events.put(True)
assert wait_for(lambda: len(pressed) == 2)               # zweiter Druck funktioniert trotz Fehler beim ersten
assert any("fehlgeschlagen" in line for line in logs)
listener.stop()
assert api.unregistered and not listener._thread.is_alive() and listener.registered is False

busy = FakeHotkeyApi(register_ok=False)
busy_listener = HotkeyListener("ctrl+space", action, api_factory=lambda: busy)
assert busy_listener.start() is False and not busy.unregistered
busy_listener.stop()                                     # harmlos

def broken_factory():
    raise OSError("kein Windows")
broken = HotkeyListener("ctrl+space", action, api_factory=broken_factory)
assert broken.start() is False and isinstance(broken.error, OSError)

off_listener = HotkeyListener("off", action, api_factory=broken_factory)
assert off_listener.parsed is None and off_listener.start() is False and off_listener.error is None
try:
    HotkeyListener("quatsch", action)
except ValueError:
    pass
else:
    raise AssertionError("ungueltiger Hotkey")


# 3) Fenster nach vorn
class FakeWindows:
    def __init__(self, hwnd=None, foreground=""):
        self.hwnd, self.foreground, self.fronted, self.searched = hwnd, foreground, [], []
    def find(self, title):
        self.searched.append(title)
        return self.hwnd
    def bring_to_front(self, hwnd):
        self.fronted.append(hwnd)
    def foreground_title(self):
        return self.foreground

windows = FakeWindows(hwnd=42)
assert focus_window(windows=windows) is True and windows.fronted == [42] and windows.searched == ["J.A.R.V.I.S."]
windows = FakeWindows(hwnd=None)
assert focus_window(windows=windows) is False and windows.fronted == []
assert is_foreground(windows=FakeWindows(foreground="J.A.R.V.I.S.")) is True
assert is_foreground(windows=FakeWindows(foreground="J.A.R.V.I.S. - Edge")) is False
assert is_foreground(windows=FakeWindows(foreground="")) is False


# 4) Benachrichtigungstexte: nur der kurze Name
assert short_label("  Pizza \n  fertig ") == "Pizza fertig"
assert short_label(None) == "" and len(short_label("x" * 200)) == 60 and short_label("x" * 200).endswith("…")
assert notification_for({"kind": "timer", "label": "Pizza"}) == ("Timer", "Timer abgelaufen: Pizza")
assert notification_for({"kind": "timer", "label": ""}) == ("Timer", "Timer abgelaufen")
assert notification_for({"kind": "alarm", "label": "Aufstehen"}) == ("Wecker", "Aufstehen")
assert notification_for({"kind": "alarm"}) == ("Wecker", "Wecker")
assert notification_for({"kind": "alarm", "label": "x", "briefing": True, "secret": "Passwort"}) == ("Wecker", "x")

# 5) Beobachter fuer laeutende Wecker/Timer
data = {"ringing": []}
notes, foreground = [], [False]
watcher = RingWatcher(lambda: data, lambda title, text: notes.append((title, text)), lambda: foreground[0])
assert watcher.check() == [] and notes == []
data["ringing"] = [{"id": 1, "kind": "timer", "label": "Pizza"}]
assert len(watcher.check()) == 1 and notes == [("Timer", "Timer abgelaufen: Pizza")]
watcher.check(); watcher.check()
assert len(notes) == 1                                   # läutet weiter: nicht noch einmal melden
data["ringing"].append({"id": 2, "kind": "alarm", "label": "Aufstehen"})
watcher.check()
assert notes[-1] == ("Wecker", "Aufstehen") and len(notes) == 2
data["ringing"] = []
watcher.check()
assert watcher.seen == set()                             # beendete werden vergessen
data["ringing"] = [{"id": 3, "kind": "timer", "label": "Tee"}]
foreground[0] = True                                     # Fenster vorn: Seite zeigt es selbst, keine Meldung
watcher.check()
assert len(notes) == 2
foreground[0] = False
watcher.check()
assert len(notes) == 2                                   # und danach nicht nachtraeglich
for odd in (None, {}, {"ringing": None}, {"ringing": ["x", {"label": "ohne id"}]}):
    odd_watcher = RingWatcher(lambda odd=odd: odd, lambda *a: notes.append(a))
    assert odd_watcher.check() == []
assert len(notes) == 2

# Der Hintergrundthread ueberlebt Fehler und stoppt
results = iter([OSError("Server weg"), {"ringing": [{"id": 9, "kind": "timer", "label": "Ei"}]}])
def flaky_fetch():
    value = next(results, {"ringing": []})
    if isinstance(value, Exception):
        raise value
    return value
threaded_notes = []
threaded = RingWatcher(flaky_fetch, lambda t, x: threaded_notes.append((t, x)), interval=0.01)
threaded.start()
assert wait_for(lambda: threaded_notes == [("Timer", "Timer abgelaufen: Ei")])
threaded.stop()
assert wait_for(lambda: not threaded._thread.is_alive())

# 6) Server-Antwort wirklich lesbar: fetch_ringing gegen den echten Server
import server
import ringing
httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace())
serve = threading.Thread(target=httpd.serve_forever, daemon=True)
serve.start()
ringer = ringing.Ringer(siren=types.SimpleNamespace(playing=False, start=lambda: None, stop=lambda: None, chime=lambda: False))
ringing.set_default_ringer(ringer)
try:
    base = f"http://localhost:{httpd.server_address[1]}"
    fetch = desktop_system.fetch_ringing(base)
    assert fetch()["ringing"] == []
    ringer.start("timer", "Pizza")
    live_notes = []
    live = RingWatcher(fetch, lambda title, text: live_notes.append((title, text)))
    live.check(); live.check()
    assert live_notes == [("Timer", "Timer abgelaufen: Pizza")]      # Server -> Beobachter -> genau eine Meldung
finally:
    ringing.set_default_ringer(None)
    httpd.shutdown(); httpd.server_close()


# 7) Verdrahtung in der App
spawns = []
def spawn(cmd):
    spawns.append(cmd)
    return types.SimpleNamespace(poll=lambda: None)

focused = [True]
app = jarvis_app.DesktopApp("http://localhost:8000", "edge.exe", spawn, lambda: None, focus=lambda: focused[0])
assert app.open_window() is False and spawns == []       # Fenster da: nur nach vorn, kein zweites
focused[0] = False
assert app.open_window() is True and len(spawns) == 1    # kein Fenster: neues
assert jarvis_app.DesktopApp("u", "b", spawn, lambda: None).focus is None

class FakeListener:
    def __init__(self, hotkey, callback, start_result=True):
        self.hotkey, self.callback, self.parsed, self.result, self.stopped = hotkey, callback, parse_hotkey(hotkey), start_result, False
    def start(self):
        return self.result
    def stop(self):
        self.stopped = True

class FakeWatcher:
    def __init__(self, fetch, notify, is_fg):
        self.args, self.started, self.stopped = (fetch, notify, is_fg), False, False
    def start(self):
        self.started = True
    def stop(self):
        self.stopped = True

made = {}
def make_listener(hotkey, callback):
    made["listener"] = FakeListener(hotkey, callback)
    return made["listener"]
def make_watcher(*args):
    made["watcher"] = FakeWatcher(*args)
    return made["watcher"]

lines = []
stoppers = jarvis_app.start_system_features(app, "ctrl+space", "N", "F", "H", make_listener, make_watcher, lines.append)
assert len(stoppers) == 2 and made["watcher"].started and made["watcher"].args == ("H", "N", "F")
assert made["listener"].callback == app.open_window      # der Hotkey tut genau eins: Fenster oeffnen
assert any("aktiv" in line for line in lines)
for stopper in stoppers:
    stopper()
assert made["listener"].stopped and made["watcher"].stopped

lines.clear()
stoppers = jarvis_app.start_system_features(app, "quatsch", "N", "F", "H", make_listener, make_watcher, lines.append)
assert len(stoppers) == 1 and any("ungueltig" in line for line in lines)      # kein Hotkey, aber Benachrichtigungen laufen

lines.clear()
stoppers = jarvis_app.start_system_features(app, "off", "N", "F", "H", make_listener, make_watcher, lines.append)
assert len(stoppers) == 1 and lines == []                # ausgeschaltet: keine Meldung noetig

lines.clear()
def busy_listener_factory(hotkey, callback):
    return FakeListener(hotkey, callback, start_result=False)
stoppers = jarvis_app.start_system_features(app, "ctrl+space", "N", "F", "H", busy_listener_factory, make_watcher, lines.append)
assert len(stoppers) == 1 and any("belegt" in line for line in lines)

# 8) Einbindung und Sicherheit
source = (PROJECT_DIR / "desktop_system.py").read_text(encoding="utf-8")
for forbidden in ("SetWindowsHookEx", "pynput", "import keyboard", "GetAsyncKeyState", "GetKeyState", "shell=True",
                  "0.0.0.0", "eval(", "exec(", "os.system", "subprocess"):
    assert forbidden not in source, forbidden             # kein Tastatur-Mitlesen, nur RegisterHotKey
assert "RegisterHotKey" in source
config_text = (PROJECT_DIR / "config.py").read_text(encoding="utf-8")
assert 'HOTKEY = os.getenv("JARVIS_HOTKEY", "ctrl+space")' in config_text
import config
assert parse_hotkey(config.HOTKEY) is not None
app_js = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
assert 'window.addEventListener("focus", () => {\n  const active = document.activeElement;\n  if (!active || active === document.body) input.focus();\n});' in app_js
assert "Abnahme 4B.4" in (PROJECT_DIR / "DESIGN_APP.md").read_text(encoding="utf-8")

print("ALL TESTS PASSED")
