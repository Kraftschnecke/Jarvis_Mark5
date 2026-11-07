"""Remote R4 (Mark 5): Verwaltung am PC. Zustand, Koppel-Link, Sperren, Entfernen. Nur lokal, nie vom Handy, nie ein Geheimnis in der Anzeige."""
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

REMOTE_HOST = "mein-pc.tail1234.ts.net"
tmp = Path(tempfile.mkdtemp())
settings = SettingsManager(tmp / "settings.json")
reminders.set_default_store(reminders.ReminderStore(str(tmp / "reminders.json")))
ringing.set_default_ringer(ringing.Ringer(siren=types.SimpleNamespace(playing=False, start=lambda: None, stop=lambda: None, chime=lambda: False)))
focus.set_default_manager(focus.FocusManager())
widget_store = widgets.WidgetStore(tmp / "widgets.json")
widgets.set_default_store(widget_store)


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

    def get_active(self):
        return {"project_id": None, "conversation_id": None}

    def apply_settings(self):
        pass

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
                            weather=types.SimpleNamespace(summary=lambda: None), remote=gate)
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


# ----- Vorbereitung: Remote einschalten -----
def post(path, body=None, host="localhost:8000", cookie=None, origin=None):
    return call(httpd, "POST", path, host=host, cookie=cookie, origin=origin, body=body if body is not None else {})


def state():
    status, _, raw = call(httpd, "GET", "/api/remote/state", host="localhost:8000")
    assert status == 200
    return jbody(raw)


# 1) Zustand am PC: aus, mit Namen aus der .env, ohne Geraete
first = state()
assert first == {"available": True, "host": REMOTE_HOST, "enabled": False, "active": False,
                 "levels": {"info": True, "daily": True, "pc": False}, "devices": [], "pending": 0}
status, headers, _ = call(httpd, "GET", "/api/remote/state", host="localhost:8000")
assert headers["cache-control"] == "no-store"

# Ohne Remote-Pforte (kein Name eingetragen) gibt es keine Verwaltung
status, _, raw = call(plain_httpd, "GET", "/api/remote/state", host="localhost:8000")
assert status == 200 and jbody(raw)["available"] is False and jbody(raw)["devices"] == []
assert call(plain_httpd, "POST", "/api/remote/pair_link", host="localhost:8000", body={"name": "x"})[0] == 404

# 2) Koppel-Link: erst wenn Remote an ist
status, _, raw = post("/api/remote/pair_link", {"name": "iPhone"})
assert status == 400 and "ausgeschaltet" in jbody(raw)["error"] and store.pending_count() == 0
settings.set("remote", "enabled", True)
status, _, raw = post("/api/remote/pair_link", {"name": "  iPhone   Moritz "})
answer = jbody(raw)
assert status == 200 and answer["name"] == "iPhone Moritz" and 290 <= answer["expires_in"] <= 300
assert answer["link"].startswith("https://" + REMOTE_HOST + "/pair#") and len(answer["link"].split("#")[1]) >= 20
assert answer["state"]["pending"] == 1 and answer["state"]["active"] is True
code = answer["link"].split("#")[1]
assert "?" not in answer["link"]                                    # der Code steht im Fragment, nicht in der Adresse

# Der Link funktioniert genau einmal: Handy koppelt, danach steht das Geraet in der Liste
status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})
assert status == 200
cookie = headers["set-cookie"].split(";")[0]
listed = state()
assert listed["pending"] == 0 and [d["name"] for d in listed["devices"]] == ["iPhone Moritz"]
device = listed["devices"][0]
assert set(device) == {"id", "name", "created", "last_seen", "revoked", "expired"}
assert device["revoked"] is False and device["expired"] is False
assert code not in json.dumps(listed) and cookie.split("=", 1)[1] not in json.dumps(listed)       # nie Code oder Token
assert "hash" not in json.dumps(listed).lower()
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})[0] in (400, 401, 403)     # nicht ein zweites Mal
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 200

# Namen: leer, zu lang, kein Text
for bad in ({}, {"name": ""}, {"name": "   "}, {"name": "x" * 41}, {"name": 5}, {"name": ["a"]}, {"name": None}):
    assert post("/api/remote/pair_link", bad)[0] == 400, bad
assert store.pending_count() == 0
settings.set("remote", "enabled", False)
assert post("/api/remote/pair_link", {"name": "X"})[0] == 400
settings.set("remote", "enabled", True)

# 3) Mehrere Geraete: neuestes zuerst (mit Uhr, die wir selbst stellen)
import time as _time
real_clock = store.clock
store.clock = lambda: real_clock() + 1000
second_code = jbody(post("/api/remote/pair_link", {"name": "iPad"})[2])["link"].split("#")[1]
status, headers2, _ = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": second_code})
cookie2 = headers2["set-cookie"].split(";")[0]
store.clock = real_clock
names = [d["name"] for d in state()["devices"]]
assert names == ["iPad", "iPhone Moritz"], names

# Abgelaufene Geraete werden als abgelaufen gemeldet (Token laeuft nach 90 Tagen ab)
later = server.remote_panel_state(gate, now=_time.time() + 200 * 86400)
assert all(d["expired"] for d in later["devices"]) and not any(d["expired"] for d in state()["devices"])

# 4) Sperren: das Geraet kommt sofort nicht mehr rein, das andere schon
first_id = next(d["id"] for d in state()["devices"] if d["name"] == "iPhone Moritz")
status, _, raw = post("/api/remote/revoke", {"id": first_id})
assert status == 200 and [d for d in jbody(raw)["state"]["devices"] if d["id"] == first_id][0]["revoked"] is True
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 401
assert call(httpd, "GET", "/api/timers", cookie=cookie2)[0] == 200
assert post("/api/remote/revoke", {"id": first_id})[0] == 404              # schon gesperrt
assert post("/api/remote/revoke", {"id": "gibt-es-nicht"})[0] == 404
for bad in ({}, {"id": 5}, {"id": ""}, {"id": "x" * 65}, {"id": ["a"]}, {"id": None}):
    assert post("/api/remote/revoke", bad)[0] == 400, bad
    assert post("/api/remote/forget", bad)[0] == 400, bad

# 4b) Entsperren: derselbe Token geht wieder, ohne neuen Koppel-Link; nur Gesperrte lassen sich entsperren
assert post("/api/remote/restore", {"id": first_id})[0] == 200
assert [d for d in state()["devices"] if d["id"] == first_id][0]["revoked"] is False
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 200
assert post("/api/remote/restore", {"id": first_id})[0] == 404             # ist nicht gesperrt
assert post("/api/remote/restore", {"id": "gibt-es-nicht"})[0] == 404
for bad in ({}, {"id": 5}, {"id": ""}, {"id": "x" * 65}, {"id": ["a"]}, {"id": None}):
    assert post("/api/remote/restore", bad)[0] == 400, bad
assert post("/api/remote/revoke", {"id": first_id})[0] == 200               # wieder sperren fuer die naechsten Schritte
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 401

# 5) Entfernen: weg aus der Liste
status, _, raw = post("/api/remote/forget", {"id": first_id})
assert status == 200 and first_id not in [d["id"] for d in jbody(raw)["state"]["devices"]]
assert post("/api/remote/forget", {"id": first_id})[0] == 404

# 6) Alle sperren: auch offene Koppel-Links werden ungueltig
open_code = jbody(post("/api/remote/pair_link", {"name": "Offen"})[2])["link"].split("#")[1]
assert state()["pending"] == 1
status, _, raw = post("/api/remote/revoke_all")
answer = jbody(raw)
assert status == 200 and answer["revoked"] == 1 and answer["state"]["pending"] == 0
assert all(d["revoked"] for d in answer["state"]["devices"])
assert call(httpd, "GET", "/api/timers", cookie=cookie2)[0] == 401
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": open_code})[0] in (400, 401, 403)
assert jbody(post("/api/remote/revoke_all")[2])["revoked"] == 0

# 7) Vom Handy aus gibt es die Verwaltung nicht (auch nicht mit gueltigem Cookie), und nichts aendert sich
settings.set("remote", "enabled", True)
phone_code = jbody(post("/api/remote/pair_link", {"name": "Handy"})[2])["link"].split("#")[1]
status, headers3, _ = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": phone_code})
phone = headers3["set-cookie"].split(";")[0]
before = json.dumps(state(), sort_keys=True)
for path in ("/api/remote/state",):
    assert call(httpd, "GET", path, cookie=phone)[0] == 403 and call(httpd, "GET", path)[0] == 401
for path in ("/api/remote/pair_link", "/api/remote/revoke", "/api/remote/restore", "/api/remote/revoke_all", "/api/remote/forget"):
    body = {"name": "Boese", "id": "x"}
    assert call(httpd, "POST", path, cookie=phone, origin=ORIGIN, body=body)[0] == 403, path
    assert call(httpd, "POST", path, origin=ORIGIN, body=body)[0] == 401, path
assert json.dumps(state(), sort_keys=True) == before
assert call(httpd, "GET", "/api/timers", cookie=phone)[0] == 200

# 8) Schalter und Stufen: ueber die normalen Einstellungen am PC, mit Pruefung
def setting(key, value):
    return call(httpd, "POST", "/api/settings", host="localhost:8000", body={"category": "remote", "key": key, "value": value})[0]

assert setting("pc", True) == 200 and state()["levels"]["pc"] is True
assert setting("pc", "ja") == 400 and state()["levels"]["pc"] is True
assert setting("max_messages", 5) == 200 and setting("max_messages", -1) == 400 and setting("max_ai_per_day", 100001) == 400
assert setting("enabled", False) == 200 and state()["active"] is False and state()["enabled"] is False
assert call(httpd, "GET", "/api/timers", cookie=phone)[0] == 403         # Remote aus: auch ein gekoppeltes Geraet kommt nicht rein
assert setting("enabled", True) == 200 and call(httpd, "GET", "/api/timers", cookie=phone)[0] == 200
assert call(httpd, "POST", "/api/settings", cookie=phone, origin=ORIGIN, body={"category": "remote", "key": "pc", "value": True})[0] == 403

# 9) Zustand ohne Schwaetzer: nichts an Jarvis
assert spy.touched == [], spy.touched

print("ALL TESTS PASSED")
