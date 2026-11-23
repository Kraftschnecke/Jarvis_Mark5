"""Server-Betrieb S4: Geraet mit Vollzugriff (nur im Server-Terminal gekoppelt) arbeitet wie am PC, Handys bleiben eingeschraenkt."""
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

# 1) Das Handy bleibt eingeschraenkt (so wie bisher): lokale Adressen sind 403, Nachrichten laufen ueber Remote
assert call(httpd, "GET", "/api/folders", cookie=phone_cookie)[0] == 403
assert call(httpd, "GET", "/api/remote/state", cookie=phone_cookie)[0] == 403
shown = jbody(call(httpd, "GET", "/api/settings", cookie=phone_cookie)[2])
assert shown["remote"] is True

# 2) Vollzugriff: wie am PC. Volle Einstellungen, lokale Adressen, Nachrichten ohne Remote-Beschraenkung
status, headers, raw = call(httpd, "GET", "/api/settings", cookie=full_cookie)
full_shown = jbody(raw)
assert status == 200 and full_shown.get("remote") is not True and "remote" in full_shown["settings"] and "abilities" in full_shown
assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"      # Schutz-Kopfzeilen des Remote-Namens bleiben
assert call(httpd, "GET", "/api/folders", cookie=full_cookie)[0] == 200
assert call(httpd, "GET", "/api/remote/state", cookie=full_cookie)[0] == 200
status, headers, raw = call(httpd, "GET", "/", cookie=full_cookie)
assert status == 200 and b"koppeln" not in raw.lower()                                                       # die normale Seite, nicht die Kopplungsseite
spy.local_messages.clear()
status, headers, raw = call(httpd, "POST", "/api/message", origin=ORIGIN, cookie=full_cookie, body={"message": "hallo vom server"})
assert status == 200 and spy.local_messages == ["hallo vom server"] and headers["x-content-type-options"] == "nosniff", (status, raw)
assert call(httpd, "POST", "/api/settings", origin=ORIGIN, cookie=phone_cookie, body={"category": "appearance", "key": "theme", "value": "dark"})[0] == 403

# 3) Schutz bleibt: ohne Cookie, falscher Origin, falscher Name, Remote aus
assert call(httpd, "GET", "/api/folders")[0] == 401
assert call(httpd, "POST", "/api/message", origin="https://evil.example", cookie=full_cookie, body={"message": "x"})[0] == 403
assert call(httpd, "POST", "/api/message", cookie=full_cookie, body={"message": "x"})[0] == 403                    # ohne Origin
assert call(httpd, "GET", "/api/folders", host="evil.example", cookie=full_cookie)[0] == 403
settings.set("remote", "enabled", False)
assert call(httpd, "GET", "/api/folders", cookie=full_cookie)[0] == 403
settings.set("remote", "enabled", True)
assert spy.local_messages == ["hallo vom server"]                                                  # keiner der abgelehnten Aufrufe kam an

# 4) Eine Verbindung, zwei Anfragen nacheinander: der Vollzugriff haengt nie an der Verbindung
conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
for cookie, expected in ((full_cookie, 200), (phone_cookie, 403), (full_cookie, 200), (phone_cookie, 403)):
    conn.request("GET", "/api/folders", headers={"Host": REMOTE_HOST, "Cookie": cookie})
    answer = conn.getresponse()
    answer.read()
    assert answer.status == expected, (cookie, answer.status)
conn.close()
conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
for cookie, expected_local in ((full_cookie, True), (phone_cookie, False), (full_cookie, True)):
    before = len(spy.local_messages)
    payload = json.dumps({"message": "x"}).encode()
    conn.request("POST", "/api/message", body=payload, headers={"Host": REMOTE_HOST, "Origin": ORIGIN, "Cookie": cookie,
                                                                  "Content-Type": "application/json", "Content-Length": str(len(payload))})
    answer = conn.getresponse()
    answer.read()
    assert (len(spy.local_messages) == before + 1) == expected_local, (cookie, answer.status)
conn.close()
assert spy.local_messages == ["hallo vom server", "x", "x"]

# 5) Vollzugriff entsteht NIE ueber die Weboberflaeche
status, _, raw = call(httpd, "POST", "/api/remote/pair_link", origin=ORIGIN, cookie=full_cookie, body={"name": "Neues Handy", "full": True})
assert status == 200, raw
web_code = jbody(raw)["code"]
assert not FULL_PENDING.exists()
status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": web_code})
assert status == 200
web_cookie = headers["set-cookie"].split(";")[0]
assert [d["full"] for d in store.devices()][-1] is False and call(httpd, "GET", "/api/folders", cookie=web_cookie)[0] == 403
for extra in ({"full": True}, {"full": "true"}, {"owner": True}, {"profile": "owner", "full": True}):
    status, _, raw = call(httpd, "POST", "/api/remote/pair_link", origin=ORIGIN, cookie=phone_cookie, body={"name": "x", **extra})
    assert status == 403                                                                           # das Handy hat die Verwaltung gar nicht
assert all(d["full"] is False for d in store.devices()[2:])

# 6) Gesperrt, abgemeldet, vergessen: kein Vollzugriff mehr
full_id = store.devices()[0]["id"]
assert store.revoke(full_id)
assert call(httpd, "GET", "/api/folders", cookie=full_cookie)[0] == 401
assert store.restore(full_id)
assert call(httpd, "GET", "/api/folders", cookie=full_cookie)[0] == 200
status, headers, _ = call(httpd, "POST", "/api/remote/logout", origin=ORIGIN, cookie=full_cookie, body={})
assert status == 200 and call(httpd, "GET", "/api/folders", cookie=full_cookie)[0] == 401

# 6b) become_owner: aus "remote" wird "local" (wie am PC), ohne Handy-Geraet, mit Schutz-Kopfzeilen des Remote-Namens
handler = server.JarvisHandler.__new__(server.JarvisHandler)
handler.kind, handler.device, handler.via_remote = "remote", {"full": True, "id": "x"}, False
assert handler.become_owner() is False and handler.kind == "local" and handler.device is None and handler.via_remote is True

# 7) Aus der Datei zaehlt "full" nur fuer Geraete des Besitzers (und nur als echtes True)
file = tmp / "remote_devices_check.json"
def entry(device_id, **extra):
    return {"id": device_id, "name": device_id, "token_hash": "x" * 64, "created": 1, "last_seen": 1, "expires": 9e9, "revoked": False, **extra}
file.write_text(json.dumps({"devices": [entry("a", profile="owner", full=True), entry("b", profile="owner", full="ja"),
                                        entry("c", profile="owner", full=1), entry("d", profile="owner"),
                                        entry("e", profile="a1b2c3d4", full=True)]}), encoding="utf-8")
loaded = {d["id"]: d["full"] for d in remote_auth.DeviceStore(file).devices()}
assert loaded == {"a": True, "b": False, "c": False, "d": False, "e": False}, loaded

print("ALL TESTS PASSED")
