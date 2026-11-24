"""PC-Daten ueber den Agent (S6, G2): die Fenster PC-Status, PC-Lage und Laufwerke zeigen den PC, nicht den Server; PC aus = klare Meldung."""
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


import remote_pc
from tools import pc_health, system_status_tool

PC_FACTS = {"os": "Windows 11", "os_version": "10.0.26100", "architecture": "AMD64", "cpu_name": "Test-CPU", "cpu_cores": 8, "cpu_threads": 16,
            "cpu_max_mhz": 3800, "ram_total_gb": 32.0, "drives": [{"name": "C:\\", "total_gb": 931.5, "free_gb": 400.0, "used_percent": 57.0}],
            "computer_name": "GOTT-DESKTOP", "python_version": "3.12.3", "has_battery": False}
PC_NOW = {"cpu_percent": 12.5, "ram_percent": 96.0, "ram_used_gb": 30.7, "ram_total_gb": 32.0, "disk_percent": 55.5, "disk_used_gb": 500.0,
          "disk_total_gb": 931.5, "battery": None, "network": {"down_kb_s": 1.5, "up_kb_s": 0.0}, "uptime_seconds": 3600}
PC_SNAPSHOT = {"now": PC_NOW, "drives": [], "programs": {"ram": [{"name": "chrome.exe", "mb": 25000, "count": 30}], "cpu": [], "disk": []},
               "autostart": ["Steam"], "assessment": {"level": "ok", "headline": "Alles super", "findings": []}}
seen = []
handlers = {
    "pc.facts": lambda args: seen.append("pc.facts") or PC_FACTS,
    "pc.performance": lambda args: seen.append(("pc.performance", args["fresh"])) or PC_NOW,
    "pc.top": lambda args: seen.append("pc.top") or [{"name": "chrome.exe", "ram_mb": 25000, "count": 30}],
    "pc.snapshot": lambda args: seen.append("pc.snapshot") or PC_SNAPSHOT,
    "folders.list": lambda args: seen.append("folders.list") or {"folders": [{"path": "C:\\Users\\Test\\Dokumente", "exists": True}]},
}

# 2) Ohne Agent: die drei Fenster bekommen 503 mit klarer Meldung (und nicht die Werte des Servers)
remote_pc.install(httpd)
try:
    for path in ("/api/system", "/api/performance", "/api/pc_lage"):
        status, _, raw = call(httpd, "GET", path, host="localhost:8000")
        assert status == 503 and "nicht erreichbar" in jbody(raw)["error"], (path, status, raw)

    # 2b) Freigegebene Ordner: ohne PC 503; freigeben/entfernen geht ueber den Server nie (nur am PC)
    status, _, raw = call(httpd, "GET", "/api/folders", host="localhost:8000")
    assert status == 503 and "nicht erreichbar" in jbody(raw)["error"], (status, raw)
    for path in ("/api/folders/add", "/api/folders/remove"):
        status, _, raw = call(httpd, "POST", path, host="localhost:8000", body={"path": "C:\\Users\\Test"})
        assert status == 400 and "am PC" in jbody(raw)["error"] and "--folders" in jbody(raw)["error"], (path, status, raw)

    # 3) Agent verbindet sich (mit eigenen Auftraegen aus der Liste), Fenster zeigen den PC
    stop = threading.Event()
    agent = pc_agent.Agent(HttpTestTransport(), token, handlers=handlers, log=lambda line: None, sleep=lambda s: time.sleep(0.05))
    runner = threading.Thread(target=lambda: agent.run(should_stop=stop.is_set), daemon=True)
    runner.start()
    deadline = time.time() + 10
    while time.time() < deadline and not jbody(call(httpd, "GET", "/api/agent/status", host="localhost:8000")[2])["online"]:
        time.sleep(0.1)
    status, _, raw = call(httpd, "GET", "/api/system", host="localhost:8000")
    assert status == 200 and jbody(raw) == PC_FACTS
    status, _, raw = call(httpd, "GET", "/api/performance", host="localhost:8000")
    assert status == 200 and jbody(raw) == PC_NOW
    status, _, raw = call(httpd, "GET", "/api/pc_lage", host="localhost:8000")
    lage = jbody(raw)["pc_lage"]
    assert status == 200 and lage["now"] == PC_NOW and lage["autostart"] == ["Steam"]
    # die Bewertung kommt vom Server: RAM 96 % ist eine Warnung, auch wenn der Agent "Alles super" behauptet
    assert lage["assessment"]["level"] in ("warn", "bad") and any(f["id"] == "ram" for f in lage["assessment"]["findings"])
    assert "Alles super" not in json.dumps(lage["assessment"])
    assert "pc.facts" in seen and ("pc.performance", False) in seen and "pc.snapshot" in seen

    status, _, raw = call(httpd, "GET", "/api/folders", host="localhost:8000")
    assert status == 200 and jbody(raw)["folders"] == [{"path": "C:\\Users\\Test\\Dokumente", "exists": True}] and "folders.list" in seen

    # 4) Der Chat bekommt ebenfalls die Werte des PCs
    info = system_status_tool.get_system_info()
    assert info.success and info.data["computer_name"] == "GOTT-DESKTOP" and ("pc.performance", True) in seen

    # 5) Handy (eingeschraenkt) kommt weiter nicht an die PC-Daten heran
    phone_cookie, _, _ = pair("iPhone Moritz")
    for path in ("/api/system", "/api/performance", "/api/pc_lage"):
        assert call(httpd, "GET", path, cookie=phone_cookie)[0] == 403, path

    # 6) Agent beendet: nach dem letzten Auftrag meldet sich der PC nicht mehr; der Server wartet nicht ewig
    stop.set()
    runner.join(timeout=10)
    httpd.hub.forget(agent_id)
    status, _, raw = call(httpd, "GET", "/api/performance", host="localhost:8000")
    assert status == 503 and "nicht erreichbar" in jbody(raw)["error"]
finally:
    import folders as folders_module
    from tools import document_tool, file_search_tool, media_tool, note_tool, volume_tool
    folders_module.set_default_list(None)
    file_search_tool.set_default_search(None)
    document_tool.set_default_reader(None)
    note_tool.set_default_writer(None)
    volume_tool.set_remote(None)
    media_tool.set_remote(None)
    system_status_tool.set_remote(None)
    system_status_tool.set_default_monitor(None)
    pc_health.set_default_health(None)

print("ALL TESTS PASSED")
