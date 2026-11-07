"""Remote R2 (Mark 5): Server-Pforte fuer das Handy. Jede Adresse einzeln, mit und ohne Anmeldung, Kopplung, Origin, Sperren, Schalter."""
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


def pair(name="iPhone Moritz"):
    code = store.create_pairing(name)["code"]
    status, headers, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})
    assert status == 200, (status, raw)
    cookie = headers["set-cookie"].split(";")[0]
    return cookie, headers, jbody(raw)


routes = set(re.findall(r'"(/api/[a-z_/]+)"', (PROJECT_DIR / "server.py").read_text(encoding="utf-8")))
routes |= {"/api/remote/pair", "/api/remote/whoami", "/api/sync"}
assert "/api/message" in routes and "/api/settings" in routes and len(routes) > 40


# 1) Remote ist aus (Voreinstellung): der Remote-Name wird abgelehnt, localhost geht wie immer
assert settings.get("remote", "enabled") is False and gate.active() is False
for method, path in (("GET", "/"), ("GET", "/pair"), ("GET", "/api/settings"), ("POST", "/api/remote/pair"), ("POST", "/api/message")):
    status, _, _ = call(httpd, method, path, origin=ORIGIN, body={"message": "x"})
    assert status == 403, (method, path, status)
assert call(httpd, "GET", "/api/timers", host="localhost:8000")[0] == 200
assert call(httpd, "GET", "/api/timers", host="127.0.0.1")[0] == 200

# 2) Ohne eingetragenen Namen gibt es Remote gar nicht (keine Pforte)
assert call(plain_httpd, "GET", "/pair")[0] == 403 and call(plain_httpd, "GET", "/api/timers")[0] == 403
assert call(plain_httpd, "GET", "/api/timers", host="localhost")[0] == 200

settings.set("remote", "enabled", True)
assert gate.active() is True

# 3) Fremde Namen bleiben draussen, auch mit Remote an
for host in ("evil.example", REMOTE_HOST + ".evil.example", "x" + REMOTE_HOST, "", "localhost.evil.example"):
    assert call(httpd, "GET", "/pair", host=host)[0] == 403, host
assert call(httpd, "GET", "/pair", host=REMOTE_HOST.upper())[0] == 200          # Gross-/Kleinschreibung egal
assert call(httpd, "GET", "/pair", host=REMOTE_HOST + ":443")[0] == 200

# 4) Ohne Anmeldung: nur Kopplungsseite und Dateien ohne Geheimnisse
status, headers, raw = call(httpd, "GET", "/pair")
assert status == 200 and "J.A.R.V.I.S." in raw.decode("utf-8") and "/api/remote/pair" in raw.decode("utf-8")
assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"
for path in ("/", "/index.html", "/app.js", "/style.css", "/voice.js", "/nirgends"):
    status, _, raw = call(httpd, "GET", path)
    assert status == 401 and b"koppeln" in raw.lower() or b"gekoppelt" in raw.lower(), path
    assert b"const input" not in raw                                      # die App selbst wird nicht ausgeliefert
for path in sorted(remote_policy.PUBLIC_STATIC):
    assert call(httpd, "GET", path)[0] == 200, path
assert call(httpd, "GET", "/api/timers")[0] == 401 and jbody(call(httpd, "GET", "/api/settings")[2])["pair"] is True

# 5) Kopplung: Cookie mit allen Schutz-Merkmalen, Token nie im Text der Antwort
cookie, headers, answer = pair()
set_cookie = headers["set-cookie"]
for part in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/", "Max-Age=7776000"):
    assert part in set_cookie, part
token = cookie.split("=", 1)[1]
assert answer == {"ok": True, "name": "iPhone Moritz"} and token not in json.dumps(answer)
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": "falsch"})[0] == 400
code = store.create_pairing("Zweitgeraet")["code"]
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})[0] == 200
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": code})[0] == 400          # nur einmal
unlock()
for bad in ({}, {"code": 5}, {"code": None}, {"code": ["a"]}, {"code": ""}):
    assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body=bad)[0] == 400, bad
# Origin muss genau die eigene https-Adresse sein
unlock()
code = store.create_pairing("Origin-Test")["code"]
for origin in (None, "https://evil.example", "http://" + REMOTE_HOST, "https://" + REMOTE_HOST + ":8443", "http://localhost:8000", "null", "https://" + REMOTE_HOST + ".evil.example"):
    assert call(httpd, "POST", "/api/remote/pair", origin=origin, body={"code": code})[0] == 403, origin
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN + ":443", body={"code": code})[0] == 200
unlock()
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body="kein json")[0] == 400
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body="[1]")[0] == 400
assert call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": "x"}, content_type="text/plain")[0] == 415
# Der Server nimmt keinen Remote-Origin an, wenn die Anfrage an localhost ging, und umgekehrt
assert call(httpd, "POST", "/api/timer/cancel", host="localhost", origin=ORIGIN, body={"id": 1})[0] == 403
assert call(httpd, "POST", "/api/remote/pair", origin="http://localhost:8000", body={"code": "x"})[0] == 403

# 6) Zu viele falsche Codes: Kopplung ist gesperrt, auch fuer den richtigen Code
for _ in range(6):
    call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": "falsch"})
locked_code = store.create_pairing("Gesperrt")["code"]
status, _, raw = call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": locked_code})
assert status == 429 and "set-cookie" not in call(httpd, "POST", "/api/remote/pair", origin=ORIGIN, body={"code": locked_code})[1]
unlock()

# 7) Angemeldet: Dateien der App kommen, Adressen nur aus der Liste
cookie, _, _ = pair("iPhone Moritz")
for path in ("/", "/app.js", "/style.css", "/core.js", "/manifest.webmanifest"):
    status, headers, raw = call(httpd, "GET", path, cookie=cookie)
    assert status == 200 and headers["x-content-type-options"] == "nosniff", path
assert b"const input" in call(httpd, "GET", "/app.js", cookie=cookie)[2]
assert call(httpd, "GET", "/pair", cookie=cookie)[0] == 200
assert call(httpd, "GET", "/../server.py", cookie=cookie)[0] in (403, 404)
assert call(httpd, "GET", "/%2e%2e/server.py", cookie=cookie)[0] in (403, 404)

allowed_get = sorted(remote_policy.GET_API)
for path in allowed_get:
    status, headers, raw = call(httpd, "GET", path, cookie=cookie)
    assert status == 200, (path, status, raw[:200])
    assert headers["cache-control"] == "no-store"
assert call(httpd, "GET", "/api/sync", host="localhost:8000")[0] == 200
assert call(httpd, "GET", "/api/sync")[0] == 401                                      # ohne Cookie am Remote-Namen

who = jbody(call(httpd, "GET", "/api/remote/whoami", cookie=cookie)[2])
assert who == {"remote": True, "device": "iPhone Moritz", "levels": {"info": True, "daily": True, "pc": False}}

# Einstellungen: nur die gefilterte Sicht
shown = jbody(call(httpd, "GET", "/api/settings", cookie=cookie)[2])
assert shown["remote"] is True and shown["guest"] is False and shown["abilities"] == [] and shown["usage"] is None
assert shown["settings"]["jarvis"] == {"address": "Sir"}
assert set(shown["settings"]) <= set(remote_gate.SETTINGS_FOR_REMOTE) | {"jarvis"}
assert "remote" not in shown["settings"]                                  # die Remote-Einstellungen sieht nur der PC
for hidden in ("home_place", "limits", "memory", "abilities", "ai_calls_per_day", "max_messages", "token"):
    assert hidden not in json.dumps(shown["settings"]), hidden
assert jbody(call(httpd, "GET", "/api/settings", host="localhost")[2])["settings"]["jarvis"]["home_place"] == "Mannheim"   # am PC unveraendert

# 8) Alles andere: auch mit gueltigem Cookie verboten, und Jarvis wird nie beruehrt
spy.touched.clear()
for path in sorted(routes - remote_policy.GET_API - remote_policy.POST_API - {"/api/remote/pair"}):
    assert call(httpd, "GET", path, cookie=cookie)[0] == 403, ("GET", path)
    if path in remote_policy.DAILY_POST_API:
        continue                                                          # mit der Stufe "Alltag" erlaubt, siehe unten
    assert call(httpd, "POST", path, cookie=cookie, origin=ORIGIN, body={"id": 1})[0] == 403, ("POST", path)
for path in sorted(remote_policy.GET_API):
    if path not in remote_policy.POST_API:
        assert call(httpd, "POST", path, cookie=cookie, origin=ORIGIN, body={})[0] == 403, ("POST", path)
for path in sorted(remote_policy.POST_API):
    if path not in remote_policy.GET_API:
        assert call(httpd, "GET", path, cookie=cookie)[0] == 403, ("GET", path)
for method in ("PUT", "DELETE", "PATCH"):
    assert call(httpd, method, "/api/message", cookie=cookie, origin=ORIGIN)[0] in (501, 405, 403), method
assert spy.touched == [], spy.touched
assert spy.local_messages == []

# 8b) Ziele abhaken und Listen pflegen: nur mit der Stufe "Alltag", Notizen und Termine nie
assert remote_policy.DAILY_POST_API == {"/api/widgets/goals", "/api/widgets/lists", "/api/widgets/notes", "/api/widgets/device_note"}
goal_body = {"items": [{"text": "Sport", "done": True, "daily": False}]}
list_body = {"lists": [{"name": "Einkaufen", "items": [{"text": "Milch", "done": True}]}]}
settings.set("remote", "daily", True)
status, _, raw = call(httpd, "POST", "/api/widgets/goals", cookie=cookie, origin=ORIGIN, body=goal_body)
assert status == 200
assert widget_store.get()["goals"][0]["text"] == "Sport" and widget_store.get()["goals"][0]["done"] is True
status, _, raw = call(httpd, "POST", "/api/widgets/lists", cookie=cookie, origin=ORIGIN, body=list_body)
assert status == 200 and widget_store.get()["lists"] == list_body["lists"]
# strenge Pruefung gilt auch von hier
assert call(httpd, "POST", "/api/widgets/goals", cookie=cookie, origin=ORIGIN, body={"items": "x"})[0] == 400
assert call(httpd, "POST", "/api/widgets/lists", cookie=cookie, origin=ORIGIN, body={"lists": [{"name": "", "items": []}]})[0] == 400
assert call(httpd, "POST", "/api/widgets/goals", cookie=cookie, origin=ORIGIN, body=goal_body, content_type="text/plain")[0] == 415
# ohne gueltigen Ursprung oder ohne Anmeldung: zu
assert call(httpd, "POST", "/api/widgets/goals", cookie=cookie, origin="https://evil.example", body=goal_body)[0] == 403
assert call(httpd, "POST", "/api/widgets/goals", origin=ORIGIN, body=goal_body)[0] == 401
# Notizen, Termine, Abend-Ziele: nie
for path, body in (("/api/widgets/events", {"title": "x", "date": "2030-01-01"}),
                   ("/api/widgets/events/delete", {"id": "x"}), ("/api/widgets/events/delete_series", {"series": "x"}), ("/api/goals/evening", {})):
    before_widgets = json.dumps(widget_store.get(), sort_keys=True)
    assert call(httpd, "POST", path, cookie=cookie, origin=ORIGIN, body=body)[0] == 403, path
    assert json.dumps(widget_store.get(), sort_keys=True) == before_widgets
# Stufe "Alltag" aus: auch Ziele und Listen zu, nichts aendert sich
settings.set("remote", "daily", False)
before_widgets = json.dumps(widget_store.get(), sort_keys=True)
for path, body in (("/api/widgets/goals", {"items": []}), ("/api/widgets/lists", {"lists": []}),
                   ("/api/widgets/notes", {"text": "x"}), ("/api/widgets/device_note", {"text": "x"})):
    assert call(httpd, "POST", path, cookie=cookie, origin=ORIGIN, body=body)[0] == 403, path
assert json.dumps(widget_store.get(), sort_keys=True) == before_widgets
settings.set("remote", "daily", True)

# Notizen: die gemeinsame Notiz gilt fuer alle Geraete, die eigene Notiz gehoert nur diesem Handy und der PC zeigt sie an
status, _, raw = call(httpd, "POST", "/api/widgets/notes", cookie=cookie, origin=ORIGIN, body={"text": "fuer alle"})
assert status == 200 and jbody(raw)["notes"] == "fuer alle" and widget_store.get()["notes"] == "fuer alle"
assert jbody(raw)["device_note"] == ""                                              # das Handy bekommt nur seine eigene
status, _, raw = call(httpd, "POST", "/api/widgets/device_note", cookie=cookie, origin=ORIGIN, body={"text": "nur ich"})
assert status == 200 and jbody(raw)["device_note"] == "nur ich" and jbody(raw)["notes"] == "fuer alle"
assert widget_store.get()["notes"] == "fuer alle"                                    # die gemeinsame Notiz bleibt unberuehrt
phone_view = jbody(call(httpd, "GET", "/api/widgets", cookie=cookie)[2])
assert phone_view["device_note"] == "nur ich" and "device_notes" not in phone_view
pc_view = jbody(call(httpd, "GET", "/api/widgets", host="localhost")[2])
assert pc_view["notes"] == "fuer alle" and "device_note" not in pc_view
assert [(n["name"], n["text"]) for n in pc_view["device_notes"]] == [("iPhone Moritz", "nur ich")]
# zweites Handy: sieht die Notiz des ersten nie, schreibt nur seine
token2 = store.redeem(store.create_pairing("iPad")["code"], "test")[1]
cookie_ipad = "jarvis_device=" + token2
assert jbody(call(httpd, "GET", "/api/widgets", cookie=cookie_ipad)[2])["device_note"] == ""
assert call(httpd, "POST", "/api/widgets/device_note", cookie=cookie_ipad, origin=ORIGIN, body={"text": "iPad-Notiz"})[0] == 200
assert jbody(call(httpd, "GET", "/api/widgets", cookie=cookie)[2])["device_note"] == "nur ich"
assert sorted((n["name"], n["text"]) for n in jbody(call(httpd, "GET", "/api/widgets", host="localhost")[2])["device_notes"]) == [("iPad", "iPad-Notiz"), ("iPhone Moritz", "nur ich")]
# strenge Pruefung, Ursprung, Anmeldung
assert call(httpd, "POST", "/api/widgets/device_note", cookie=cookie, origin=ORIGIN, body={"text": "x" * 5001})[0] == 400
assert call(httpd, "POST", "/api/widgets/device_note", cookie=cookie, origin=ORIGIN, body={"text": 5})[0] == 400
assert call(httpd, "POST", "/api/widgets/device_note", cookie=cookie, origin="https://evil.example", body={"text": "x"})[0] == 403
assert call(httpd, "POST", "/api/widgets/device_note", origin=ORIGIN, body={"text": "x"})[0] == 401
assert call(httpd, "POST", "/api/widgets/notes", cookie=cookie, origin=ORIGIN, body={"text": "x" * 5001})[0] == 400
# am PC gibt es keine eigene Notiz
assert call(httpd, "POST", "/api/widgets/device_note", host="localhost", body={"text": "x"})[0] == 400
assert widget_store.get()["notes"] == "fuer alle"
# ein gesperrtes Handy verschwindet beim PC aus der Anzeige
ipad_id = token2.split(".", 1)[0]
store.revoke(ipad_id)
assert [n["name"] for n in jbody(call(httpd, "GET", "/api/widgets", host="localhost")[2])["device_notes"]] == ["iPhone Moritz"]
assert call(httpd, "GET", "/api/widgets", cookie=cookie_ipad)[0] == 401
# Am PC (ohne Remote-Namen) bleibt alles wie vorher
assert call(httpd, "POST", "/api/widgets/notes", host="localhost", body={"text": "am PC"})[0] == 200
assert spy.touched == []

# 9) Ohne Anmeldung ist jede Adresse zu, mit Ausnahme der Kopplung
for path in sorted(routes - {"/api/remote/pair"}):
    assert call(httpd, "GET", path)[0] == 401, ("GET", path)
    assert call(httpd, "POST", path, origin=ORIGIN, body={"message": "x"})[0] == 401, ("POST", path)
assert spy.touched == [] and spy.local_messages == []

# 10) Falsche, fremde und kaputte Cookies
for bad_cookie in ("jarvis_device=falsch", "jarvis_device=", "jarvis_device=abc.def", "anderes=1", "jarvis_device", ";;;", "x" * 3000,
                   "jarvis_device=" + token + "x", "jarvis_device=" + token.upper(), "jarvis_device=\"" + token + "\"x"):
    assert call(httpd, "GET", "/api/timers", cookie=bad_cookie)[0] == 401, bad_cookie[:40]
assert call(httpd, "GET", "/api/timers", cookie="a=1; " + cookie + "; b=2")[0] == 200
assert call(httpd, "GET", "/api/timers", cookie="pad=" + "x" * 2100 + "; " + cookie)[0] == 401      # absurd lange Cookie-Zeile
assert call(httpd, "GET", "/api/timers", host="localhost", cookie="jarvis_device=falsch")[0] == 200      # am PC zaehlt ein Cookie nicht

# 11) Nachrichten: ohne Remote-Weg in Jarvis nichts, mit ihm nur das Erlaubte
status, _, raw = call(httpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "Hallo"})
assert status == 503 and spy.local_messages == []                          # nie ueber den normalen Weg
assert call(httpd, "POST", "/api/message", cookie=cookie, body={"message": "Hallo"})[0] == 403    # Origin fehlt
assert call(httpd, "POST", "/api/message", cookie=cookie, origin="https://evil.example", body={"message": "Hallo"})[0] == 403
assert call(httpd, "POST", "/api/message", cookie=cookie, origin="http://localhost", body={"message": "Hallo"})[0] == 403

remote_jarvis = RemoteJarvis()
rhttpd = server.JarvisServer(("127.0.0.1", 0), remote_jarvis, widget_store=widget_store, monitor=object(), remote=gate)
threading.Thread(target=rhttpd.serve_forever, daemon=True).start()
status, _, raw = call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "  Wie spaet ist es?  "})
assert status == 200 and jbody(raw) == {"status": "response", "content": "Antwort fuers Handy"}
assert remote_jarvis.remote_calls == [("Wie spaet ist es?", "iPhone Moritz", {"info": True, "daily": True, "pc": False})]
assert remote_jarvis.local_messages == []
for bad in ({}, {"message": ""}, {"message": "   "}, {"message": 5}, {"message": None}, {"message": ["a"]}, {"message": "x" * 1001}):
    assert call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body=bad)[0] == 400, bad
assert len(remote_jarvis.remote_calls) == 1
assert call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "x" * 1000})[0] == 200
for status_text in ("confirmation", "plan", "exit", "error"):
    remote_jarvis.reply = {"status": status_text, "content": "geheim: Programm oeffnen?", "confirmation": {"x": 1}}
    status, _, raw = call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "Oeffne Notepad"})
    assert status == 200 and jbody(raw) == {"status": "response", "content": "Das geht nur am PC."}, status_text
remote_jarvis.reply = {"status": "response", "content": "ok"}
# Rueckfragen und Plaene kann das Handy nicht beantworten
for path in ("/api/confirm", "/api/plan/confirm", "/api/plan/abort"):
    assert call(rhttpd, "POST", path, cookie=cookie, origin=ORIGIN, body={"approve": True})[0] == 403, path
# Stufen kommen live aus den Einstellungen
settings.set("remote", "pc", True)
call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "Leiser"})
assert remote_jarvis.remote_calls[-1][2] == {"info": True, "daily": True, "pc": True}
settings.set("remote", "pc", False)
# Grenzen (0 = unbegrenzt ist die Voreinstellung; mit Wert gilt er sofort)
before = len(remote_jarvis.remote_calls)
for _ in range(30):
    assert call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "x"})[0] == 200
settings.set("remote", "max_messages", 2)
results = [call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "y"})[0] for _ in range(4)]
assert results.count(200) == 2 and results.count(429) == 2, results
settings.set("remote", "max_messages", 0)
gate.refresh_limits()
assert call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "z"})[0] == 200
settings.set("remote", "max_ai_per_day", 1)
results = [call(rhttpd, "POST", "/api/message", cookie=cookie, origin=ORIGIN, body={"message": "d"})[0] for _ in range(3)]
assert results.count(429) >= 2, results
settings.set("remote", "max_ai_per_day", 0)
rhttpd.shutdown(); rhttpd.server_close()

# 12) Der normale Weg am PC ist unveraendert
status, _, raw = call(httpd, "POST", "/api/message", host="localhost:8000", body={"message": "Hallo"})
assert status == 200 and jbody(raw)["content"] == "lokal: Hallo" and spy.local_messages == ["Hallo"]
assert call(httpd, "POST", "/api/message", host="localhost", origin="https://evil.example", body={"message": "x"})[0] == 403
assert call(httpd, "GET", "/api/folders", host="localhost")[0] == 200 and call(httpd, "GET", "/api/folders", cookie=cookie)[0] == 403   # PC-Seiten bleiben PC-Seiten

# 13) Sperren wirkt sofort, ebenso der Schalter
revoked_cookie, _, _ = pair("Verlorenes Handy")
assert call(httpd, "GET", "/api/timers", cookie=revoked_cookie)[0] == 200
device_id = [d for d in store.devices() if d["name"] == "Verlorenes Handy"][0]["id"]
assert store.revoke(device_id)
assert call(httpd, "GET", "/api/timers", cookie=revoked_cookie)[0] == 401
assert call(httpd, "POST", "/api/ringing/stop", cookie=revoked_cookie, origin=ORIGIN, body={})[0] == 401
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 200                    # andere Geraete bleiben
settings.set("remote", "enabled", False)
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 403                    # Schalter aus: sofort alles zu
assert call(httpd, "GET", "/pair")[0] == 403
settings.set("remote", "enabled", True)
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 200
store.revoke_all()
assert call(httpd, "GET", "/api/timers", cookie=cookie)[0] == 401

# 14) Pforte einzeln: Peer, Origin, Cookie
assert gate.request_kind(REMOTE_HOST, "127.0.0.1") == "remote" and gate.request_kind(REMOTE_HOST, "::1") == "remote"
assert gate.request_kind(REMOTE_HOST, "192.168.1.5") is None and gate.request_kind(REMOTE_HOST, "100.64.0.7") is None
assert gate.request_kind("localhost:8000", "192.168.1.5") == "local"
assert gate.request_kind(None, "127.0.0.1") is None
assert gate.origin_ok("local", None) is True and gate.origin_ok("local", "http://localhost:8000") is True
assert gate.origin_ok("local", "https://" + REMOTE_HOST) is False and gate.origin_ok("local", "http://[::1") is False
assert gate.origin_ok("remote", None) is False and gate.origin_ok("remote", "http://[::1") is False
assert remote_gate.RemoteGate("", store, settings).request_kind("", "127.0.0.1") is None
assert remote_gate.RemoteGate("", store, settings).active() is False

# 15) Einbindung und Quelltext
import config
assert config._clean_host("Mein-PC.tail1.ts.net") == "mein-pc.tail1.ts.net"
for bad in ("", "localhost", "127.0.0.1", "evil host.com", "a.b/c", "http://x.y", "a..", "-a.b", ".a.b", "x.y:8000"):
    assert config._clean_host(bad) == "" or bad in ("a..", ), bad
assert config.REMOTE_HOST == "" or "." in config.REMOTE_HOST
assert 'SERVER_HOST = "127.0.0.1"' in (PROJECT_DIR / "config.py").read_text(encoding="utf-8")       # weiterhin nur lokal
pair_page = (PROJECT_DIR / "web" / "pair.html").read_text(encoding="utf-8")
assert "location.hash" in pair_page and "history.replaceState" in pair_page and "innerHTML" not in pair_page
assert 'name="referrer" content="no-referrer"' in pair_page
for name in ("remote_gate.py",):
    source = (PROJECT_DIR / name).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "eval(", "exec(", "print(", "0.0.0.0"):
        assert forbidden not in source, (name, forbidden)

httpd.shutdown(); plain_httpd.shutdown()
print("ALL TESTS PASSED")
