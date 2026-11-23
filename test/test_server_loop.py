"""Server-Betrieb: der Hintergrund-Takt (server_loop.py) sammelt Meldungen und Hinweise ohne offene Seite und schickt sie per Push."""

import http.client
import io
import json
import sys
import threading
import types
from contextlib import redirect_stdout
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
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing("requests")
project_stub = types.ModuleType("project")
for fn in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
           "save_message", "get_conversation", "rename_conversation", "create_project",
           "reset_conversation", "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, fn, lambda *a, **k: None)
sys.modules["project"] = project_stub

import notify
import server
import server_loop
import server_main

TOPIC = "jarvis-geheim-12345678"


class Clock:
    now = 100.0
    def __call__(self):
        return self.now


class FakeJarvis:
    guest = False
    settings_manager = None

    def __init__(self):
        self.results = []          # was der Hintergrund gerade meldet
        self.hints = []            # faellige Hinweise
        self.hint_calls = 0
        self.fail_feed = False
        self.fail_hints = False

    def check_background_results(self):
        if self.fail_feed:
            raise RuntimeError("geheim-feed")
        found, self.results = self.results, []
        return found

    def proactive_hints(self):
        self.hint_calls += 1
        if self.fail_hints:
            raise RuntimeError("geheim-hints")
        found, self.hints = self.hints, []
        return found


def make(sent):
    jarvis = FakeJarvis()
    httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, monitor=object(), weather=object(), health=object())
    notifier = notify.Notifier(TOPIC, post=lambda url, body, headers: (sent.append(json.loads(body)), 200)[1])
    return httpd, jarvis, notifier


def request(srv, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    body = None if payload is None else json.dumps(payload).encode()
    conn.request(method, path, body=body, headers={"Content-Type": "application/json"} if body is not None else {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# 1) BackgroundFeed.add: fortlaufende Nummer, die Seiten holen es mit ab, hoechstens 100 bleiben
feed = server.BackgroundFeed()
feed.add("eins")
feed.add("zwei")
assert feed.since(0) == (2, [{"id": 1, "text": "eins"}, {"id": 2, "text": "zwei"}]) and feed.since(1) == (2, [{"id": 2, "text": "zwei"}])
for i in range(150):
    feed.add(f"n{i}")
last, items = feed.since(0)
assert last == 152 and len(items) == server.BackgroundFeed.MAX_KEPT and items[0]["id"] == 53 and items[-1]["text"] == "n149"

# 2) Meldungen: neue werden gepusht (hohe Prioritaet), alte vom Start nicht, jede nur einmal
sent = []
httpd, jarvis, notifier = make(sent)
jarvis.results = ["alt vor dem Start"]
httpd.feed.collect(jarvis)                                          # liegt schon im Topf, als der Takt startet
clock = Clock()
loop = server_loop.ServerLoop(httpd, notifier, clock=clock)
assert loop.tick_feed() == 0 and sent == []
jarvis.results = ["Sir, Erinnerung: Zahnarzt", "Sir, der Timer ist abgelaufen."]
assert loop.tick_feed() == 2
assert [(m["title"], m["message"], m["priority"], m["topic"]) for m in sent] == [
    ("Jarvis", "Sir, Erinnerung: Zahnarzt", 4, TOPIC), ("Jarvis", "Sir, der Timer ist abgelaufen.", 4, TOPIC)], sent
assert loop.tick_feed() == 0 and len(sent) == 2
# was eine offene Seite schon abgeholt hat (collect), wird trotzdem gepusht - und der Seite bleibt es erhalten
jarvis.results = ["Sir, Wecker: es ist 07:00 Uhr."]
httpd.feed.collect(jarvis)
assert loop.tick_feed() == 1 and sent[-1]["message"] == "Sir, Wecker: es ist 07:00 Uhr." and loop.tick_feed() == 0
assert httpd.feed.since(0)[1][-1]["text"] == "Sir, Wecker: es ist 07:00 Uhr."

# 3) Hinweise: abgeholt, in den Topf gelegt (die Seite sieht sie), gepusht (ueber tick_feed)
sent.clear()
jarvis.hints = [{"kind": "weather", "text": "Morgen regnet es."}, {"kind": "appointment", "text": "In 30 Minuten: Zahnarzt."}]
assert loop.tick_hints() == 2 and [i["text"] for i in httpd.feed.since(0)[1][-2:]] == ["Morgen regnet es.", "In 30 Minuten: Zahnarzt."]
assert loop.tick_feed() == 2 and [m["message"] for m in sent] == ["Morgen regnet es.", "In 30 Minuten: Zahnarzt."]

# 4) tick(): Hinweise nur alle 60 Sekunden, die Meldungen jedes Mal; frisch abgeholte Hinweise gehen sofort raus
sent.clear()
jarvis.hint_calls = 0
clock.now = 1000.0
loop = server_loop.ServerLoop(httpd, notifier, clock=clock)
jarvis.hints = [{"kind": "weather", "text": "Hinweis A"}]
assert loop.tick() == 1 and jarvis.hint_calls == 1 and [m["message"] for m in sent] == ["Hinweis A"]
jarvis.results = ["Meldung B"]
clock.now += 59
assert loop.tick() == 1 and jarvis.hint_calls == 1 and sent[-1]["message"] == "Meldung B"       # zu frueh fuer Hinweise
jarvis.hints = [{"kind": "weather", "text": "Hinweis C"}]
clock.now += 1
assert loop.tick() == 1 and jarvis.hint_calls == 2 and sent[-1]["message"] == "Hinweis C"
clock.now += 59.9
loop.tick()
assert jarvis.hint_calls == 2

# 5) Fehler halten den Takt nie an und stehen ohne Einzelheiten im Terminal
for flag in ("fail_feed", "fail_hints"):
    setattr(jarvis, flag, True)
    clock.now += 100
    out = io.StringIO()
    with redirect_stdout(out):
        loop.tick()
    assert "geheim" not in out.getvalue() and "RuntimeError" in out.getvalue(), out.getvalue()
    setattr(jarvis, flag, False)
jarvis.results = ["nach dem Fehler"]
clock.now += 100
loop.tick()
assert sent[-1]["message"] == "nach dem Fehler"
# ein Hinweis-Fehler laesst die Meldungen derselben Runde nicht ausfallen
jarvis.fail_hints = True
jarvis.results = ["trotzdem da"]
clock.now += 100
with redirect_stdout(io.StringIO()):
    assert loop.tick() == 1
assert sent[-1]["message"] == "trotzdem da"
jarvis.fail_hints = False

# 6) Push aus (kein Themenname): Takt laeuft, nichts geht ins Netz, Meldungen bleiben fuer die Seite
off = server_loop.ServerLoop(httpd, notify.Notifier(""), clock=clock)
jarvis.results = ["still"]
assert off.tick_feed() == 1 and httpd.feed.since(0)[1][-1]["text"] == "still"

# 7) Thread: start/stop, hints_by_loop, nur ein Thread
sent.clear()
httpd2, jarvis2, notifier2 = make(sent)
assert httpd2.hints_by_loop is False
real = server_loop.ServerLoop(httpd2, notifier2, feed_seconds=0.01, hints_seconds=0.02)
real.start()
first = real._thread
real.start()
assert real._thread is first and httpd2.hints_by_loop is True
jarvis2.results = ["vom Thread"]
done = threading.Event()
for _ in range(300):
    if sent:
        done.set()
        break
    threading.Event().wait(0.01)
assert done.is_set() and sent[0]["message"] == "vom Thread" and jarvis2.hint_calls >= 1
real.stop()
first.join(2)
assert not first.is_alive() and httpd2.hints_by_loop is False
real.start()
assert real._thread is not first and real._thread.is_alive()
real.stop()

# 8) Route /api/hints: im Server-Betrieb holt die Seite nichts ab (sonst wuerde sie dem Push die Hinweise wegnehmen)
threading.Thread(target=httpd2.serve_forever, daemon=True).start()
jarvis2.hints = [{"kind": "weather", "text": "gehoert dem Takt"}]
jarvis2.hint_calls = 0
assert request(httpd2, "POST", "/api/hints", {}) == (200, {"hints": [{"kind": "weather", "text": "gehoert dem Takt"}]})    # Takt aus: wie bisher
httpd2.hints_by_loop = True
jarvis2.hints = [{"kind": "weather", "text": "bleibt liegen"}]
before = jarvis2.hint_calls
assert request(httpd2, "POST", "/api/hints", {}) == (200, {"hints": []}) and jarvis2.hint_calls == before and jarvis2.hints

HTTPD = types.SimpleNamespace(remote=None, hub=object(), monitor=None, health=None)

# 9) server_main: startet den Takt, wenn der Server bereit ist, und stoppt ihn am Ende; kein Browser
started = {}
class FakeLoop:
    def __init__(self, httpd, notifier_):
        started["args"] = (httpd, notifier_)
    def start(self):
        started["start"] = True
    def stop(self):
        started["stop"] = True
real_loop, real_main = server_main.ServerLoop, server.main
server_main.ServerLoop = FakeLoop
def fake_main(argv=None, on_ready=None, open_browser=True):
    started["argv"], started["browser"] = argv, open_browser
    on_ready(HTTPD)
server.main = fake_main
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.run(["--port", "8123"], notifier=notifier) == 0
assert started == {"args": (HTTPD, notifier), "start": True, "stop": True, "argv": ["--port", "8123"], "browser": False}, started
assert "Push AN" in out.getvalue() and TOPIC not in out.getvalue()
# Im Server-Betrieb kommen die PC-Daten vom PC-Agent (S6): Fenster, Chat und Warnungen fragen nicht den Server selbst
from tools import pc_health as _pc_health, system_status_tool as _sst
assert _sst._remote is not None and _sst._remote.hub is HTTPD.hub
assert HTTPD.monitor is _sst.default_monitor() and HTTPD.health is _pc_health.default_health() and HTTPD.monitor is not None
_sst.set_remote(None)
_sst.set_default_monitor(None)
_pc_health.set_default_health(None)
started.clear()
out = io.StringIO()
with redirect_stdout(out):
    server_main.run([], notifier=notify.Notifier(""))
assert "Push AUS" in out.getvalue() and "NTFY_TOPIC" in out.getvalue()
def broken_main(argv=None, on_ready=None, open_browser=True):
    on_ready(HTTPD)
    raise KeyboardInterrupt()
server.main = broken_main
started.clear()
try:
    with redirect_stdout(io.StringIO()):
        server_main.run([], notifier=notifier)
except KeyboardInterrupt:
    pass
assert started.get("stop") is True                                  # auch bei Abbruch wird der Takt gestoppt
def early_fail(argv=None, on_ready=None, open_browser=True):
    raise RuntimeError("Start fehlgeschlagen")
server.main = early_fail
try:
    with redirect_stdout(io.StringIO()):
        server_main.run([], notifier=notifier)
    raise SystemExit("Fehler muss weitergereicht werden")
except RuntimeError:
    pass
server_main.ServerLoop, server.main = real_loop, real_main

# 9b) --test-push: schickt genau eine Nachricht, startet keinen Server
sent.clear()
started.clear()
server.main = lambda *a, **k: started.setdefault("server", True)
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.run(["--test-push"], notifier=notifier) == 0
assert len(sent) == 1 and sent[0]["priority"] == 4 and "Test" in sent[0]["message"] and "server" not in started and "gesendet" in out.getvalue()
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.run(["--test-push"], notifier=notify.Notifier("")) == 1
assert "NTFY_TOPIC" in out.getvalue() and len(sent) == 1
bad = notify.Notifier(TOPIC, post=lambda *a: 500)
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.run(["--test-push"], notifier=bad) == 1
assert "ging nicht raus" in out.getvalue() and TOPIC not in out.getvalue()
# ohne argv gelten die Argumente der Eingabeaufforderung (so ruft "py server_main.py --test-push" es auf)
sent.clear()
real_argv = sys.argv
sys.argv = ["server_main.py", "--test-push"]
try:
    with redirect_stdout(io.StringIO()):
        assert server_main.run(notifier=notifier) == 0
finally:
    sys.argv = real_argv
assert len(sent) == 1 and "server" not in started
sys.argv = ["server_main.py", "--port", "8124"]
started.clear()
server.main = fake_main
server_main.ServerLoop = FakeLoop
try:
    with redirect_stdout(io.StringIO()):
        server_main.run(notifier=notifier)
finally:
    sys.argv = real_argv
assert started["argv"] == ["--port", "8124"] and len(sent) == 1, started        # sonst wuerde server.main die Zeile selbst lesen
server_main.ServerLoop = real_loop
server.main = real_main

# 9c) --pair-owner: Link mit Vollzugriff, nur im Terminal; ohne Remote-Namen geht es nicht
import tempfile
import remote_auth
pair_store = remote_auth.DeviceStore(Path(tempfile.mkdtemp()) / "remote_devices.json")
server.main = lambda *a, **k: started.setdefault("server", True)
started.clear()
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.pair_owner(["--pair-owner", "PC Moritz"], store=pair_store, host="jarvis.tail1.ts.net") == 0
match = __import__("re").search(r"https://jarvis\.tail1\.ts\.net/pair#([A-Z0-9]{4}-[A-Z0-9]{4})", out.getvalue())
assert match and "PC Moritz" in out.getvalue() and "5 Minuten" in out.getvalue(), out.getvalue()
status, token, device = pair_store.redeem(match.group(1))
assert status == "ok" and device["full"] is True and device["name"] == "PC Moritz"
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.pair_owner(["--pair-owner"], store=pair_store, host="h.ts.net") == 0
assert "Besitzer-Gerät" in out.getvalue()
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.pair_owner(["--pair-owner", "--port", "1"], store=pair_store, host="h.ts.net") == 0       # ein Schalter ist kein Name
assert "Besitzer-Gerät" in out.getvalue() and "--port" not in out.getvalue()
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.pair_owner(["--pair-owner", "X"], store=pair_store, host="") == 1
assert "JARVIS_REMOTE_HOST" in out.getvalue()
class BrokenStore:
    def create_pairing(self, name, full=False):
        raise OSError("Platte voll")
out = io.StringIO()
with redirect_stdout(out):
    assert server_main.pair_owner(["--pair-owner", "X"], store=BrokenStore(), host="h.ts.net") == 1
assert "OSError" in out.getvalue() and "Platte voll" not in out.getvalue()
# ueber run(): kein Server wird gestartet, der Notifier nicht gebraucht
out = io.StringIO()
real_pair = server_main.pair_owner
server_main.pair_owner = lambda argv, **k: (started.setdefault("pair_argv", argv), 0)[1]
with redirect_stdout(out):
    assert server_main.run(["--pair-owner", "Laptop"], notifier=notify.Notifier("")) == 0
server_main.pair_owner = real_pair
assert started["pair_argv"] == ["--pair-owner", "Laptop"] and "server" not in started

# 9d) Server-Betrieb schaltet Remote ein, wenn der Name eingetragen ist (sonst kommt man nie an die Oberflaeche)
class FakeSettings:
    def __init__(self, enabled):
        self.values = {("remote", "enabled"): enabled}
    def set(self, category, key, value):
        self.values[(category, key)] = value
class FakeGate:
    def __init__(self, host, enabled):
        self.host = host
        self.settings = FakeSettings(enabled)
    def active(self):
        return bool(self.host) and self.settings.values[("remote", "enabled")] is True
for host, enabled, expected, said in (("h.ts.net", False, True, True), ("h.ts.net", True, True, False), ("", False, False, False)):
    gate_ = FakeGate(host, enabled)
    out = io.StringIO()
    with redirect_stdout(out):
        server_main.enable_remote(types.SimpleNamespace(remote=gate_))
    assert gate_.settings.values[("remote", "enabled")] is expected and ("eingeschaltet" in out.getvalue()) is said, (host, enabled)
with redirect_stdout(io.StringIO()):
    server_main.enable_remote(types.SimpleNamespace(remote=None))                   # kein Remote-Name: nichts zu tun
started.clear()
holder_httpd = []
class FakeLoop2(FakeLoop):
    pass
server_main.ServerLoop = FakeLoop2
gate_ = FakeGate("h.ts.net", False)
def main_with_gate(argv=None, on_ready=None, open_browser=True):
    on_ready(types.SimpleNamespace(remote=gate_, hub=object(), monitor=None, health=None))
server.main = main_with_gate
with redirect_stdout(io.StringIO()):
    server_main.run([], notifier=notifier)
assert gate_.active() is True and started.get("start") is True                       # run() schaltet ein, bevor der Takt startet
_sst.set_remote(None)
_sst.set_default_monitor(None)
_pc_health.set_default_health(None)
server_main.ServerLoop = real_loop
server.main = real_main

# 10) Windows-Pakete nur unter Windows; Server-Start laedt kein Fenster-Modul
req = (PROJECT_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
for pkg in ("pycaw", "pystray"):
    line = next(l for l in req if l.startswith(pkg))
    assert 'sys_platform == "win32"' in line, line
assert not any("sys_platform" in l for l in req if l.startswith(("openai", "psycopg", "psutil", "python-dotenv", "tzdata")))
text = (PROJECT_DIR / "server_main.py").read_text(encoding="utf-8")
assert "jarvis_app" not in text and "pystray" not in text and "winsound" not in text and "open_browser=False" in text

print("ALL TESTS PASSED")
