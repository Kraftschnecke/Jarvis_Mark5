"""Schutz gegen Selbstsperre: Das Geraet mit Vollzugriff kann sich in der Remote-Verwaltung nicht selbst sperren, entfernen oder mit \"Alle Geraete sperren\" aussperren."""
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


routes = set(re.findall(r'"(/api/[a-z_/]+)"', (PROJECT_DIR / "server.py").read_text(encoding="utf-8")))
routes |= {"/api/remote/pair", "/api/remote/whoami", "/api/sync"}
assert "/api/message" in routes and "/api/settings" in routes and len(routes) > 40



settings.set("remote", "enabled", True)
FULL_PENDING = tmp / remote_auth.FULL_PENDING_NAME


def pair_full(name="PC Moritz"):
    """Wie im Server-Terminal: ein ANDERER Store (eigener Prozess) legt den Code in die Datei, der Server loest ihn ein."""
    terminal = remote_auth.DeviceStore(tmp / "remote_devices.json")
    code = terminal.create_pairing(name, full=True)["code"]
    status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})
    assert status == 200, (status, raw)
    return headers["set-cookie"].split(";")[0], headers


full_cookie, full_headers = pair_full()
phone_cookie, _, _ = pair("iPhone Moritz")
assert [d["full"] for d in store.devices()] == [True, False] and not FULL_PENDING.exists()


own_id = store.devices()[0]["id"]
phone_id = store.devices()[1]["id"]
assert store.devices()[0]["full"] is True and store.devices()[1]["full"] is False


def admin(path, **body):
    status, _, raw = call(httpd, "POST", path, origin=ORIGIN, cookie=full_cookie, body=body)
    return status, jbody(raw)


def flags():
    return {d["id"]: d["revoked"] for d in store.devices()}


# 1) Das eigene Geraet sperren oder entfernen: abgelehnt, nichts passiert
status, body = admin("/api/remote/revoke", id=own_id)
assert status == 400 and "dieses Gerät" in body["error"], (status, body)
status, body = admin("/api/remote/forget", id=own_id)
assert status == 400 and "dieses Gerät" in body["error"], (status, body)
assert flags() == {own_id: False, phone_id: False}
assert call(httpd, "GET", "/api/settings", cookie=full_cookie)[0] == 200          # weiter angemeldet

# 2) Das Handy sperren, entsperren, entfernen: geht wie vorher
status, body = admin("/api/remote/revoke", id=phone_id)
assert status == 200 and flags()[phone_id] is True
status, body = admin("/api/remote/restore", id=phone_id)
assert status == 200 and flags()[phone_id] is False

# 3) "Alle Geraete sperren": das Handy wird gesperrt, das eigene Geraet bleibt (Zaehler = 1)
status, body = admin("/api/remote/revoke_all")
assert status == 200 and body["revoked"] == 1, (status, body)
assert flags() == {own_id: False, phone_id: True}
assert call(httpd, "GET", "/api/settings", cookie=full_cookie)[0] == 200
assert call(httpd, "GET", "/api/settings", cookie=phone_cookie)[0] == 401          # gesperrtes Handy ist draussen

# 4) Das Handy kann diese Adressen nie erreichen (unveraendert)
store.restore(phone_id)
assert call(httpd, "POST", "/api/remote/revoke_all", origin=ORIGIN, cookie=phone_cookie, body={})[0] == 403
assert flags() == {own_id: False, phone_id: False}

# 5) Entfernen des Handys klappt weiter
status, body = admin("/api/remote/forget", id=phone_id)
assert status == 200 and [d["id"] for d in store.devices()] == [own_id]

# 6) Ohne Vollzugriff-Geraet (echter PC, lokal): alles wie bisher, auch revoke_all sperrt alle
local_store_count = store.revoke_all()
assert local_store_count == 1 and flags() == {own_id: True}

print("ALL TESTS PASSED")
