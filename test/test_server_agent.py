"""PC-Agent am Server (S6): Kopplung, Long-Poll, Ping von der Seite, Handy bleibt draussen, Browser kommt nicht an /agent/ heran."""
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

import http.client
import json
import re
import threading
import time

import focus
import reminders
import remote_auth
import remote_gate
import remote_policy
import ringing
import server
import timer
import widgets
from settings_manager import SettingsManager
from tools import news_tool
from tools.tool_result import ToolResult

REMOTE_HOST = "mein-pc.tail1234.ts.net"
tmp = Path(tempfile.mkdtemp())
settings = SettingsManager(tmp / "settings.json")
reminders.set_default_store(reminders.ReminderStore(str(tmp / "reminders.json")))
ringing.set_default_ringer(ringing.Ringer(siren=types.SimpleNamespace(playing=False, start=lambda: None, stop=lambda: None, chime=lambda: False)))
focus.set_default_manager(focus.FocusManager())
widget_store = widgets.WidgetStore(tmp / "widgets.json")
widgets.set_default_store(widget_store)
# Schlagzeilen fuer GET /api/news ohne Netz
news_tool.set_default_service(types.SimpleNamespace(get_news=lambda source, topic, count: ToolResult(
    success=True, data={"items": [{"number": 1, "source": "Test", "title": "Schlagzeile", "summary": "Text", "url": "https://example.org/a", "published": None}], "unavailable_sources": []})))


class SpyJarvis:
    """Merkt sich jeden Zugriff auf etwas, das es nicht ausdruecklich gibt."""

    def __init__(self):
        self.settings_manager = settings
        self.guest = False
        self.cost_counter = None
        self.conversation = types.SimpleNamespace(messages=[])
        self.touched = []
        self.local_messages = []

    def get_tree(self):
        return []

    def daily_briefing(self):
        return "Guten Abend, Sir. Testbriefing."

    def get_active(self):
        return {"project_id": None, "conversation_id": None}

    def check_background_results(self):
        return []

    def process_message(self, message):
        self.local_messages.append(message)
        return {"status": "response", "content": "lokal: " + message}

    def __getattr__(self, name):
        self.touched.append(name)
        raise AttributeError(name)


class RemoteJarvis(SpyJarvis):
    def __init__(self):
        super().__init__()
        self.remote_calls = []
        self.reply = {"status": "response", "content": "Antwort fuers Handy"}

    def process_remote_message(self, text, device_name, levels):
        self.remote_calls.append((text, device_name, dict(levels)))
        return self.reply


store = remote_auth.DeviceStore(tmp / "remote_devices.json")
gate = remote_gate.RemoteGate(REMOTE_HOST, store, settings)
spy = SpyJarvis()
httpd = server.JarvisServer(("127.0.0.1", 0), spy, widget_store=widget_store, monitor=object(),
                            weather=types.SimpleNamespace(summary=lambda: None, week_forecast=lambda place, icons=False: ToolResult(success=True, data={"place": place, "now": None, "days": []})), remote=gate)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
plain_httpd = server.JarvisServer(("127.0.0.1", 0), SpyJarvis(), widget_store=widget_store, monitor=object())   # ohne Remote
threading.Thread(target=plain_httpd.serve_forever, daemon=True).start()
ORIGIN = "https://" + REMOTE_HOST


def call(srv, method, path, host=REMOTE_HOST, origin=None, cookie=None, body=None, content_type="application/json", extra=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = cookie
    headers.update(extra or {})
    payload = None
    if method == "POST":
        payload = body if isinstance(body, (bytes, str)) else json.dumps(body if body is not None else {})
        payload = payload.encode("utf-8") if isinstance(payload, str) else payload
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(payload))
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    result = (response.status, dict((k.lower(), v) for k, v in response.getheaders()), raw)
    conn.close()
    return result


def unlock():
    store.guard._locked_until.clear()
    store.guard._failures.clear()


def jbody(raw):
    return json.loads(raw.decode("utf-8"))


def pair(name="iPhone Moritz"):
    code = store.create_pairing(name)["code"]
    status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})
    assert status == 200, (status, raw)
    cookie = headers["set-cookie"].split(";")[0]
    return cookie, headers, jbody(raw)



settings.set("remote", "enabled", True)
import pc_agent
pc_agent.POLL_WAIT = 1                          # Long-Poll im Test kurz halten
ORIGIN = "https://" + REMOTE_HOST


def agent_call(srv, path, body=None, token=None, host=REMOTE_HOST, origin=None, content_type="application/json", raw=None, method="POST"):
    headers = {"Host": host}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if origin is not None:
        headers["Origin"] = origin
    payload = raw if raw is not None else json.dumps(body if body is not None else {}).encode("utf-8")
    if method == "POST":
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(payload))
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=15)
    conn.request(method, path, body=payload if method == "POST" else None, headers=headers)
    response = conn.getresponse()
    data = response.read()
    result = (response.status, dict((k.lower(), v) for k, v in response.getheaders()), data)
    conn.close()
    return result


class HttpTestTransport:
    """Wie pc_agent.HttpTransport, aber gegen den Test-Server und mit dem Remote-Namen im Host-Kopf."""

    def post(self, path, body, token=None):
        status, _, raw = agent_call(httpd, path, body, token)
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError:
            return status, None


# 1) Kopplung: Code aus dem Server-Terminal (anderer Store), Agent loest ihn ein
terminal = remote_auth.DeviceStore(tmp / "remote_devices.json")
code = terminal.create_pairing("PC Moritz", agent=True)["code"]
status, headers, raw = agent_call(httpd, "/agent/pair", {"code": code})
assert status == 200 and "set-cookie" not in headers, (status, raw)
answer = jbody(raw)
token = answer["token"]
assert answer["name"] == "PC Moritz" and "." in token
assert agent_call(httpd, "/agent/pair", {"code": code})[0] == 400                 # nur einmal
assert agent_call(httpd, "/agent/pair", {"code": 5})[0] == 400
assert agent_call(httpd, "/agent/pair", {})[0] == 400
unlock()
# Ein Browser-Code geht hier nicht (und ein Agent-Code nicht an /api/remote/pair)
browser_code = store.create_pairing("Handy")["code"]
assert agent_call(httpd, "/agent/pair", {"code": browser_code})[0] == 400
unlock()
agent_code2 = terminal.create_pairing("Zweiter", agent=True)["code"]
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": agent_code2})[0] == 400
unlock()
agent_id = [d for d in store.devices() if d["agent"]][0]["id"]
assert [d["agent"] for d in store.devices()].count(True) == 1

# 2) Abgewiesen: Browser (Origin), falscher Inhaltstyp, GET, unbekannte Adresse, kein/falsches Token, Quatsch im Body
assert agent_call(httpd, "/agent/next", {}, token, origin=ORIGIN)[0] == 403
assert agent_call(httpd, "/agent/next", {}, token, origin="https://boese.example")[0] == 403
assert agent_call(httpd, "/agent/next", {}, token, content_type="text/plain")[0] == 415
assert agent_call(httpd, "/agent/next", token=token, method="GET")[0] == 405
assert agent_call(httpd, "/agent/gibtsnicht", {}, token)[0] == 404
assert agent_call(httpd, "/agent/", {}, token)[0] == 404
assert agent_call(httpd, "/agent/next", {})[0] == 401
assert agent_call(httpd, "/agent/next", {}, "falsch.token")[0] == 401
assert agent_call(httpd, "/agent/next", raw=b"{kaputt", token=token)[0] == 400
assert agent_call(httpd, "/agent/next", raw=b"[1]", token=token)[0] == 400
assert agent_call(httpd, "/agent/next", raw=b"", token=token)[0] == 400
assert agent_call(httpd, "/agent/next", raw=b"{" + b" " * (70 * 1024) + b"}", token=token)[0] == 400
assert agent_call(httpd, "/agent/next", {"wait": "viel"}, token)[0] == 400
assert agent_call(httpd, "/agent/next", {"wait": True}, token)[0] == 400
assert agent_call(httpd, "/agent/next", {"wait": 0}, token)[0] == 200
assert jbody(agent_call(httpd, "/agent/next", {"wait": 0}, token)[2]) == {"job": None}
# fremder Host-Name oder Remote ausgeschaltet: nicht erlaubt; Server ohne Remote: es gibt keinen Agent
assert agent_call(httpd, "/agent/next", {}, token, host="boese.example")[0] == 403
assert agent_call(plain_httpd, "/agent/pair", {"code": "AAAA-BBBB"}, host="localhost:8000")[0] == 404
assert jbody(call(plain_httpd, "GET", "/api/agent/status", host="localhost:8000")[2]) == {"online": False, "name": ""}
settings.set("remote", "enabled", False)
assert agent_call(httpd, "/agent/next", {"wait": 0}, token)[0] == 403
settings.set("remote", "enabled", True)

# 3) Das Agent-Token oeffnet nichts anderes: keine API, kein Browser-Cookie
for path in ("/api/settings", "/api/widgets", "/api/agent/status"):
    assert call(httpd, "GET", path, extra={"Authorization": "Bearer " + token})[0] in (401, 403), path
    assert call(httpd, "GET", path, cookie="jarvis_device=" + token)[0] in (401, 403), path
assert call(httpd, "POST", "/api/agent/ping", origin=ORIGIN, cookie="jarvis_device=" + token, body={})[0] in (401, 403)
assert call(httpd, "POST", "/api/message", origin=ORIGIN, cookie="jarvis_device=" + token, body={"message": "hi"})[0] in (401, 403)

# 4) Ohne verbundenen Agent: Status "offline", Ping meldet den Grund (Besitzer am PC = localhost)
fresh_hub = server.JarvisServer(("127.0.0.1", 0), SpyJarvis(), widget_store=widget_store, monitor=object(), remote=gate, hub=None)
threading.Thread(target=fresh_hub.serve_forever, daemon=True).start()
assert jbody(call(fresh_hub, "GET", "/api/agent/status", host="localhost:8000")[2]) == {"online": False, "name": ""}
out = jbody(call(fresh_hub, "POST", "/api/agent/ping", host="localhost:8000", body={})[2])
assert out["ok"] is False and "nicht erreichbar" in out["error"]
fresh_hub.shutdown()

# 5) Der echte Agent (pc_agent.Agent) verbindet sich: Status online, Ping von der Seite kommt an
logs = []
stop = threading.Event()
agent = pc_agent.Agent(HttpTestTransport(), token, log=logs.append, sleep=lambda s: time.sleep(0.05))
runner = threading.Thread(target=lambda: box.update(code=agent.run(should_stop=stop.is_set)), daemon=True)
box = {}
runner.start()
deadline = time.time() + 10
while time.time() < deadline and not jbody(call(httpd, "GET", "/api/agent/status", host="localhost:8000")[2])["online"]:
    time.sleep(0.1)
assert jbody(call(httpd, "GET", "/api/agent/status", host="localhost:8000")[2]) == {"online": True, "name": "PC Moritz"}
out = jbody(call(httpd, "POST", "/api/agent/ping", host="localhost:8000", body={})[2])
assert out["ok"] is True and set(out["result"]) == {"name", "time", "version"} and out["result"]["version"] == 1, out
deadline = time.time() + 5
while time.time() < deadline and not ("Verbunden mit dem Jarvis-Server." in logs and "Auftrag ping: ok" in logs):
    time.sleep(0.05)                                      # der Agent schreibt sein Log erst nach dem Abschicken des Ergebnisses
assert "Verbunden mit dem Jarvis-Server." in logs and "Auftrag ping: ok" in logs, logs

# 6) Handy (eingeschraenkt) und Gast kommen an Status und Ping nicht heran; Besitzer mit Vollzugriff schon
phone_cookie, _, _ = pair("iPhone Moritz")
assert call(httpd, "GET", "/api/agent/status", cookie=phone_cookie)[0] == 403
assert call(httpd, "POST", "/api/agent/ping", origin=ORIGIN, cookie=phone_cookie, body={})[0] == 403
assert call(httpd, "GET", "/api/agent/status")[0] in (401, 403)                   # Remote-Name ohne Cookie
code = terminal.create_pairing("PC Browser", full=True)["code"]
status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})
assert status == 200
full_cookie = headers["set-cookie"].split(";")[0]
unlock()
assert jbody(call(httpd, "GET", "/api/agent/status", cookie=full_cookie)[2]) == {"online": True, "name": "PC Moritz"}
status, _, raw = call(httpd, "POST", "/api/agent/ping", origin=ORIGIN, cookie=full_cookie, body={})
assert status == 200 and jbody(raw)["ok"] is True

# 7) Zwei Pings kurz hintereinander laufen sauber durch
results = []
threads = [threading.Thread(target=lambda: results.append(jbody(call(httpd, "POST", "/api/agent/ping", host="localhost:8000", body={})[2])["ok"])) for _ in range(3)]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert results == [True, True, True], results

# 8) Gesperrt: der Agent bekommt 401, beendet sich mit Meldung und ist nicht mehr zu erreichen
store.revoke(agent_id)
runner.join(timeout=10)
assert not runner.is_alive() and box["code"] == 1 and any("neu koppeln" in line for line in logs)
assert agent_call(httpd, "/agent/next", {"wait": 0}, token)[0] == 401
store.restore(agent_id)

# 9) Ergebnis in falscher Form (kaputter oder boeswilliger Agent): Ping meldet Fehler, kein Absturz
bad_agent = pc_agent.Agent(HttpTestTransport(), token, handlers={"ping": lambda args: {"name": "x"}}, log=lambda line: None, sleep=lambda s: time.sleep(0.05))
stop2 = threading.Event()
runner2 = threading.Thread(target=lambda: bad_agent.run(should_stop=stop2.is_set), daemon=True)
runner2.start()
deadline = time.time() + 10
while time.time() < deadline and not jbody(call(httpd, "GET", "/api/agent/status", host="localhost:8000")[2])["online"]:
    time.sleep(0.1)
out = jbody(call(httpd, "POST", "/api/agent/ping", host="localhost:8000", body={})[2])
assert out["ok"] is False and "passt nicht" in out["error"], out
# Ergebnis fuer einen erfundenen Auftrag wird abgelehnt
status, _, raw = agent_call(httpd, "/agent/result", {"id": "erfunden", "ok": True, "data": {}}, token)
assert status == 404 and jbody(raw) == {"ok": False}
stop2.set()
runner2.join(timeout=10)
stop.set()

print("ALL TESTS PASSED")
