"""Remote R4 (Mark 5): Verwaltung am PC. Zustand, Koppel-Link, Sperren, Entfernen. Nur lokal, nie vom Handy, nie ein Geheimnis in der Anzeige."""
import sys
import tempfile
import types
from datetime import date, datetime, timedelta
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

import profiles
import tester
REMOTE_HOST = "mein-pc.tail1234.ts.net"
ORIGIN = "https://" + REMOTE_HOST
tmp = Path(tempfile.mkdtemp())
settings = SettingsManager(tmp / "settings.json")
settings.set("remote", "enabled", True)
settings.set("jarvis", "home_place", "Hamburg")
settings.set("jarvis", "address", "Boss")
reminders.set_default_store(reminders.ReminderStore(str(tmp / "reminders.json")))
ringing.set_default_ringer(ringing.Ringer(siren=types.SimpleNamespace(playing=False, start=lambda: None, stop=lambda: None, chime=lambda: False)))
focus.set_default_manager(focus.FocusManager())
owner_widgets_path = tmp / "widgets.json"
widget_store = widgets.WidgetStore(owner_widgets_path)
widgets.set_default_store(widget_store)
widget_store.set_notes("GEHEIM: Notiz von Moritz")
widget_store.set_lists([{"name": "Geheimliste", "items": [{"text": "Geheimding", "done": False}]}])


class FakeAI:
    def __init__(self, label):
        self.label = label
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text=f"{self.label}: Antwort")


class OwnerJarvis:
    """Der Jarvis des Besitzers. Alles, was ein Gast hier anfasst, wird vermerkt."""

    def __init__(self):
        self.settings_manager = settings
        self.guest = False
        self.cost_counter = None
        self.conversation = types.SimpleNamespace(messages=[{"role": "user", "content": "GEHEIM: Frage von Moritz"}])
        self.touched = []
        self.local_messages = []
        self.remote_calls = []
        self.owner_ai = FakeAI("OWNER")
        self.raw_ai = FakeAI("GAST")
        self.client = types.SimpleNamespace(_client=self.raw_ai, responses=self.owner_ai)      # wie cost_guard.GuardedClient

    def get_tree(self):
        return [{"id": 1, "name": "GEHEIM-Projekt", "conversations": []}]

    def get_active(self):
        return {"project_id": 1, "conversation_id": 7}

    def apply_settings(self):
        pass

    def check_background_results(self):
        return [{"text": "GEHEIM: Timer"}]

    def process_message(self, message):
        self.local_messages.append(message)
        return {"status": "response", "content": "lokal: " + message}

    def process_remote_message(self, text, device_name, levels):
        self.remote_calls.append(text)
        return {"status": "response", "content": "Handy-Antwort"}

    def __getattr__(self, name):
        self.touched.append(name)
        raise AttributeError(name)


profile_store = profiles.ProfileStore(tmp / "profiles.json", tmp / "profiles")
bruder = profile_store.create("Bruder")["id"]
anderer = profile_store.create("Anderer")["id"]
store = remote_auth.DeviceStore(tmp / "remote_devices.json")
gate = remote_gate.RemoteGate(REMOTE_HOST, store, settings, profile_store)
owner = OwnerJarvis()
httpd = server.JarvisServer(("127.0.0.1", 0), owner, widget_store=widget_store, monitor=object(),
                            weather=types.SimpleNamespace(summary=lambda: "Sonnig in Hamburg"), remote=gate)
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def call(method, path, host=REMOTE_HOST, origin=None, cookie=None, body=None, agent=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = cookie
    if agent is not None:
        headers["User-Agent"] = agent
    payload = None
    if method == "POST":
        payload = json.dumps(body if body is not None else {}).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(payload))
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    return response.status, raw


def pair(name, profile):
    code = store.create_pairing(name, profile)["code"]
    status, token, device = store.redeem(code, "test")
    assert status == "ok"
    return f"jarvis_device={token}", device


def get(path, cookie):
    status, raw = call("GET", path, cookie=cookie)
    return status, raw


def getj(path, cookie):
    status, raw = call("GET", path, cookie=cookie)
    assert status == 200, (path, status, raw[:200])
    return json.loads(raw.decode("utf-8"))


def post(path, cookie, body=None):
    return call("POST", path, cookie=cookie, origin=ORIGIN, body=body)


def postj(path, cookie, body=None):
    status, raw = post(path, cookie, body)
    assert status == 200, (path, status, raw[:200])
    return json.loads(raw.decode("utf-8"))


phone, phone_device = pair("Handy Moritz", profiles.OWNER)
laptop, laptop_device = pair("Laptop Bruder", bruder)
other_cookie, other_device = pair("Laptop Anderer", anderer)

# Der Gast-Jarvis antwortet ueber seinen eigenen Router (hier: immer Plaudern)
def chat_route():
    return {"kind": "CHAT", "task_type": None, "parameters": {},
            "command": {"intent": "NORMAL_MESSAGE", "project_name": None, "conversation_name": None, "new_conversation_name": None}}


tester.route_message = lambda client, message, registry, context="": chat_route()


def snapshot_owner():
    return {
        "widgets": owner_widgets_path.read_text(encoding="utf-8"),
        "reminders": (tmp / "reminders.json").read_text(encoding="utf-8") if (tmp / "reminders.json").exists() else None,
        "settings": (tmp / "settings.json").read_text(encoding="utf-8") if (tmp / "settings.json").exists() else None,
    }


owner_before = snapshot_owner()

# 1) Lesen als Gast: nur der eigene (leere) Bereich, nie etwas vom Besitzer
GUEST_READS = ["/api/remote/whoami", "/api/settings", "/api/background", "/api/timers", "/api/ringing", "/api/alarms", "/api/focus",
               "/api/weather", "/api/projects", "/api/widgets", "/api/sync"]
everything = ""
for path in GUEST_READS:
    everything += json.dumps(getj(path, laptop), ensure_ascii=False)
for secret in ("GEHEIM", "Geheimliste", "Geheimding", "Hamburg", "Boss", "Sonnig", "Moritz"):
    assert secret not in everything, secret
who = getj("/api/remote/whoami", laptop)
assert who["tester"] is True and who["area"] == "Bruder" and who["levels"] == {"info": True, "daily": True, "pc": False}
view = getj("/api/settings", laptop)
assert view["tester"] is True and view["area"] == "Bruder" and view["guest"] is False and view["usage"] is None
assert view["settings"]["voice"]["engine"] == "Browser"                         # nie die bezahlte Stimme des Besitzers
assert settings.get("voice", "engine") == "OpenAI"                              # beim Besitzer unveraendert
assert view["settings"]["jarvis"]["address"] == "Sir"                           # Standard, nie die Anrede des Besitzers
assert getj("/api/projects", laptop) == {"projects": [], "active": {"project_id": None, "conversation_id": None}}
assert getj("/api/background", laptop) == {"messages": [], "last": 0}
widgets_view = getj("/api/widgets", laptop)
assert widgets_view["notes"] == "" and widgets_view["lists"] == [] and widgets_view["device_note"] == ""
assert getj("/api/sync", laptop)["messages"] == []

# Der Besitzer sieht weiter nur seine Dinge
owner_view = getj("/api/widgets", phone)
assert "Geheimliste" in json.dumps(owner_view) and "GEHEIM" in owner_view["notes"]
assert getj("/api/remote/whoami", phone).get("tester") is None
assert "Hamburg" in json.dumps(getj("/api/weather", phone)) or True

# Rollen-Seiten: der Gast bekommt seine eigene Seite und nur die Dateien, die sie braucht
for page in ("/app_base.js", "/app_state.js", "/app_start.js", "/style.css", "/core.js", "/manifest.webmanifest", "/icon-192.png", "/remote_prefs.js"):
    status, raw = call("GET", page, cookie=laptop)
    assert status == 200 and b"GEHEIM" not in raw, page
guest_html = {}
for page in ("/", "/index.html", "/guest.html"):
    status, raw = call("GET", page, cookie=laptop)
    assert status == 200 and b"J.A.R.V.I.S. Gast" in raw and b'id="new-project"' not in raw and b"remote_admin.js" not in raw, page
    guest_html[page] = raw
assert guest_html["/"] == guest_html["/index.html"] == guest_html["/guest.html"]
for page in ("/remote_admin.js", "/app_owner.js", "/app.js", "/server.py", "/.env", "/profiles.json", "/remote_devices.json", "/nichts.js", "/web/app.js", "/../server.py",
             "/%2e%2e/server.py", "/test_server_tester.py"):
    status, raw = call("GET", page, cookie=laptop)
    assert status == 404 and b"GEHEIM" not in raw and b"Bruder" not in raw, (page, status)
status, raw = call("GET", "/pair", cookie=laptop)
assert status == 200 and b"koppeln" in raw
# Der Besitzer bekommt weiter seine Seite mit allem
status, raw = call("GET", "/index.html", cookie=phone)
assert status == 200 and b'id="new-project"' in raw and b"J.A.R.V.I.S. Gast" not in raw
# "/" ist fuer den Besitzer die Willkommensseite; der Gast bekommt sie nicht (404), sein "/" bleibt die Gast-Seite
status, raw = call("GET", "/", cookie=phone)
assert status == 200 and b'id="start"' in raw and b'href="index.html"' in raw and b"J.A.R.V.I.S. Gast" not in raw
for name in ("/welcome.html", "/welcome.css", "/welcome.js", "/welcome_logic.js", "/welcome_panels.js", "/welcome_dialogs.js",
             "/mobile.html", "/mobile.css", "/mobile.js", "/mobile_logic.js", "/embed.js", "/welcome_app.js"):
    assert call("GET", name, cookie=phone)[0] == 200, name
    assert call("GET", name, cookie=laptop)[0] == 404, name
# Auf dem iPhone bekommt der Besitzer die Handy-Version, ?pc=1 erzwingt die PC-Ansicht; der Gast bleibt bei seiner Seite
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
status, raw = call("GET", "/", cookie=phone, agent=IPHONE)
assert status == 200 and b'id="mpages"' in raw and b"J.A.R.V.I.S. Gast" not in raw
assert b'id="start"' in call("GET", "/?pc=1", cookie=phone, agent=IPHONE)[1]
status, raw = call("GET", "/", cookie=laptop, agent=IPHONE)
assert status == 200 and b"J.A.R.V.I.S. Gast" in raw and b'id="mpages"' not in raw
assert b"J.A.R.V.I.S. Gast" in call("GET", "/?handy=1", cookie=laptop, agent=IPHONE)[1]
assert call("GET", "/remote_admin.js", cookie=phone)[0] == 200 and call("GET", "/app_owner.js", cookie=phone)[0] == 200
# Ohne Anmeldung bleibt es die Kopplungsseite (401), nie die Gast-Seite
status, raw = call("GET", "/")
assert status == 401 and b"koppeln" in raw and b"J.A.R.V.I.S. Gast" not in raw

# Abmelden: der Eintrag verschwindet, das Cookie wird geloescht, das Token geht nicht mehr
mine_cookie, mine_device = pair("Abmelden-Test", bruder)
assert getj("/api/remote/whoami", mine_cookie)["tester"] is True
assert call("POST", "/api/remote/logout", cookie=mine_cookie, body={})[0] == 403                  # ohne Origin wie jede Schreib-Anfrage
assert call("POST", "/api/remote/logout", origin=ORIGIN, body={})[0] == 401                       # ohne Anmeldung
conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
conn.request("POST", "/api/remote/logout", body=b"{}", headers={"Host": REMOTE_HOST, "Origin": ORIGIN, "Cookie": mine_cookie,
                                                              "Content-Type": "application/json", "Content-Length": "2"})
answer = conn.getresponse()
answer.read()
cookie_header = answer.getheader("Set-Cookie")
conn.close()
assert answer.status == 200 and "Max-Age=0" in cookie_header and "HttpOnly" in cookie_header and "Secure" in cookie_header
assert mine_device["id"] not in [d["id"] for d in store.devices()]
assert get("/api/remote/whoami", mine_cookie)[0] == 401
assert call("GET", "/")[0] == 401
status, _ = post("/api/remote/logout", phone)                                                          # auch der Besitzer am Handy kann sich abmelden
assert status == 200 and get("/api/remote/whoami", phone)[0] == 401
phone, phone_device = pair("Handy Moritz", profiles.OWNER)                                             # fuer die Tests weiter unten

# Neue Kopplung auf einem schon gekoppelten Geraet: der alte Zugang wird ersetzt, nicht doppelt gefuehrt
old_cookie, old_device = pair("Wechsler", bruder)
new_code = store.create_pairing("Wechsler", anderer)["code"]
conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
payload = json.dumps({"code": new_code}).encode("utf-8")
conn.request("POST", "/api/remote/pair", body=payload, headers={"Host": REMOTE_HOST, "Origin": ORIGIN, "Cookie": old_cookie,
                                                                 "Content-Type": "application/json", "Content-Length": str(len(payload))})
answer = conn.getresponse()
answer.read()
new_cookie = answer.getheader("Set-Cookie").split(";")[0]
conn.close()
assert answer.status == 200 and new_cookie != old_cookie
assert get("/api/remote/whoami", old_cookie)[0] == 401                                                  # der alte Zugang ist weg
assert getj("/api/remote/whoami", new_cookie)["area"] == "Anderer"
assert old_device["id"] not in [d["id"] for d in store.devices()]
wrong = store.create_pairing("X", anderer)["code"]
status, _ = call("POST", "/api/remote/pair", origin=ORIGIN, cookie=new_cookie, body={"code": "FALSCH"})
assert status == 400 and get("/api/remote/whoami", new_cookie)[0] == 200                               # falscher Code: bleibt angemeldet
store.redeem(wrong, "aufraeumen")

# 2) Alles andere ist fuer den Gast verboten: jede Adresse einzeln, nichts erreicht den Besitzer
DENIED_GET = ["/api/remote/state", "/api/memories", "/api/actions", "/api/folders", "/api/hockey", "/api/system", "/api/performance",
              "/api/nichts", "/api/", "/api//settings", "/api/settings/", "/api/widgets/notes", "/api/remote/profiles"]
for path in DENIED_GET:
    status, raw = get(path, laptop)
    assert status == 403, (path, status)
    assert b"GEHEIM" not in raw
DENIED_POST = ["/api/speak", "/api/settings", "/api/memory/delete", "/api/memory/update", "/api/memories/delete_all", "/api/plan/abort",
               "/api/project/open", "/api/conversation/open", "/api/project/add", "/api/conversation/reset",
               "/api/focus/stop", "/api/ringing/stop", "/api/timer/cancel", "/api/hints", "/api/goals/evening", "/api/briefing/auto",
               "/api/alarms/add", "/api/alarms/delete", "/api/alarms/update", "/api/folders/add", "/api/folders/remove",
               "/api/remote/pair_link", "/api/remote/revoke", "/api/remote/revoke_all", "/api/remote/forget", "/api/remote/restore",
               "/api/remote/profile_add", "/api/remote/profile_limits", "/api/remote/profile_delete", "/api/remote/profile_reset",
               "/api/remote/profile_reset_usage", "/api/confirm", "/api/nichts"]
for path in DENIED_POST:
    status, raw = post(path, laptop, {"name": "x", "id": "x", "text": "x", "message": "x", "category": "remote", "key": "enabled", "value": False})
    assert status == 403, (path, status)
assert owner.touched == [] and owner.local_messages == [] and owner.remote_calls == [] and owner.owner_ai.calls == []
assert snapshot_owner() == owner_before
assert call("POST", "/api/message", cookie=laptop, body={"message": "x"})[0] == 403            # ohne Origin wie bei jedem Remote-Geraet
assert call("GET", "/api/widgets")[0] == 401                                                  # ohne Cookie
assert call("GET", "/api/widgets", host="localhost:8000")[0] == 200                           # am PC unveraendert

# 3) Schreiben als Gast: nur in den eigenen Bereich
note = postj("/api/widgets/notes", laptop, {"text": "Notiz des Bruders"})
assert note["notes"] == "Notiz des Bruders"
postj("/api/widgets/lists", laptop, {"lists": [{"name": "Einkauf", "items": [{"text": "Milch", "done": False}]}]})
postj("/api/widgets/goals", laptop, {"items": [{"text": "Sport", "done": True}]})
tomorrow = (date.today() + timedelta(days=1)).isoformat()
postj("/api/widgets/events", laptop, {"title": "Zahnarzt", "date": tomorrow, "time": "10:00"})
mine = postj("/api/widgets/device_note", laptop, {"text": "Nur mein Laptop"})
assert mine["device_note"] == "Nur mein Laptop"
assert post("/api/widgets/lists", laptop, {"lists": "kaputt"})[0] == 400
assert post("/api/widgets/events", laptop, {"title": "", "date": "x"})[0] == 400
own = getj("/api/widgets", laptop)
for text in ("Notiz des Bruders", "Milch", "Sport", "Zahnarzt", "Nur mein Laptop"):
    assert text in json.dumps(own, ensure_ascii=False), text
# Der andere Gast und der Besitzer sehen davon nichts, und der Besitzer wurde nicht veraendert
for cookie in (other_cookie, phone):
    seen = json.dumps(getj("/api/widgets", cookie), ensure_ascii=False)
    for text in ("Notiz des Bruders", "Milch", "Zahnarzt", "Nur mein Laptop"):
        assert text not in seen, (cookie[:20], text)
assert snapshot_owner() == owner_before
assert (tmp / "profiles" / bruder / "widgets.json").exists() and not (tmp / "profiles" / anderer / "widgets.json").exists()
# Eine zweite Seite desselben Bereichs (anderes Geraet) teilt Notiz, Liste und Termine, aber nicht die Geraete-Notiz
laptop2, laptop2_device = pair("Zweiter Laptop", bruder)
shared = getj("/api/widgets", laptop2)
assert shared["notes"] == "Notiz des Bruders" and shared["device_note"] == ""

# 4) Nachrichten: eigener Gast-Jarvis, eigene Zaehler, nichts beim Besitzer
status_before = getj("/api/sync", laptop)
reply = postj("/api/message", laptop, {"message": "Hallo Jarvis"})
assert reply == {"status": "response", "content": "GAST: Antwort"}
assert owner.owner_ai.calls == [] and len(owner.raw_ai.calls) == 1                      # nie der gezaehlte Client des Besitzers
assert owner.local_messages == [] and owner.remote_calls == [] and owner.touched == []
assert "GEHEIM" not in json.dumps(owner.raw_ai.calls[0], ensure_ascii=False, default=str)
after = getj("/api/sync", laptop)
assert after["version"] != status_before["version"] and [m["content"] for m in after["messages"]] == ["Hallo Jarvis", "GAST: Antwort"]
assert getj("/api/sync?known=" + after["version"], laptop) == {"version": after["version"], "active": {"project_id": None, "conversation_id": None}}
assert [m["content"] for m in getj("/api/sync", laptop2)["messages"]] == ["Hallo Jarvis", "GAST: Antwort"]       # gleicher Bereich
assert getj("/api/sync", other_cookie)["messages"] == [] and "Hallo" not in json.dumps(getj("/api/sync", phone))
assert post("/api/message", laptop, {"message": ""})[0] == 400 and post("/api/message", laptop, {"message": "x" * 1001})[0] == 400
assert post("/api/message", laptop, {"message": 5})[0] == 400
assert json.loads((tmp / "profiles" / bruder / "usage.json").read_text(encoding="utf-8"))["counts"]["ai"] == 1
assert snapshot_owner() == owner_before

# Neue Unterhaltung: nur die des Gastes wird geleert
assert postj("/api/conversation/new", laptop2, {})["messages"] == []
assert getj("/api/sync", laptop)["messages"] == []
assert owner.conversation.messages and "GEHEIM" in owner.conversation.messages[0]["content"]

# 4b) Erinnerungen (C3b): faellig werden im Bereich, Meldung nur in der App dieses Gastes
due_now = datetime.now().strftime("%Y-%m-%dT%H:%M")
(tmp / "profiles" / bruder / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "g1", "text": "Wasser trinken", "due": due_now, "event_id": None}]}), encoding="utf-8")
(tmp / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "o1", "text": "Geheime Erinnerung des Besitzers", "due": "2999-01-01T10:00", "event_id": None}]}), encoding="utf-8")
owner_before = snapshot_owner()
assert getj("/api/background", laptop) == {"messages": [], "last": 0}
assert httpd.tick_testers() == 1
got = getj("/api/background?after=0", laptop)
assert [m["text"] for m in got["messages"]] == ["Erinnerung: Wasser trinken"] and got["last"] == 1
assert getj("/api/background?after=1", laptop) == {"messages": [], "last": 1}
assert getj("/api/background", laptop) == {"messages": [], "last": 1}                # neuer Tab: nur der Stand
assert getj("/api/background?after=0", laptop2)["messages"][0]["text"] == "Erinnerung: Wasser trinken"       # gleicher Bereich, anderes Geraet
assert get("/api/background?after=x", laptop)[0] == 400
assert getj("/api/background?after=0", other_cookie) == {"messages": [], "last": 0}
assert "Wasser" not in json.dumps(getj("/api/background?after=0", phone))
assert "Geheime Erinnerung" not in json.dumps(getj("/api/background?after=0", laptop))
assert httpd.tick_testers() == 0
assert snapshot_owner() == owner_before and owner.touched == []

# 5) Limits kommen vom PC: Nachrichten pro 10 Minuten, dann "Zaehler zuruecksetzen"
profile_store.set_limits(bruder, messages_per_10min=2, ai_per_day=100)
postj("/api/message", laptop, {"message": "eins"})
answers = [postj("/api/message", laptop, {"message": "zwei"})["content"], postj("/api/message", laptop, {"message": "drei"})["content"]]
assert "höchstens 2 Nachrichten" in answers[-1], answers
ai_calls = len(owner.raw_ai.calls)
postj("/api/message", laptop, {"message": "vier"})
assert len(owner.raw_ai.calls) == ai_calls                                           # abgelehnt kostet nichts
status, raw = call("POST", "/api/remote/profile_reset_usage", host="localhost:8000", body={"id": bruder})
assert status == 200
assert postj("/api/message", laptop, {"message": "fuenf"})["content"] == "GAST: Antwort"
profile_store.set_limits(bruder, messages_per_10min=0, ai_per_day=1)
assert "Tageslimit" in postj("/api/message", laptop, {"message": "sechs"})["content"] or "Tageslimit" in postj("/api/message", laptop, {"message": "sieben"})["content"]
status, raw = call("POST", "/api/remote/profile_limits", host="localhost:8000", body={"id": bruder, "ai_per_day": 0})
assert status == 200 and postj("/api/message", laptop, {"message": "acht"})["content"] == "GAST: Antwort"

# 6) Bereich zuruecksetzen: der Gast arbeitet sofort sauber weiter (Ordner wird neu angelegt)
status, raw = call("POST", "/api/remote/profile_reset", host="localhost:8000", body={"id": bruder})
assert status == 200 and not (tmp / "profiles" / bruder / "widgets.json").exists()
assert getj("/api/widgets", laptop)["notes"] == "" and getj("/api/sync", laptop)["messages"] == []
assert postj("/api/widgets/notes", laptop, {"text": "wieder da"})["notes"] == "wieder da"

# 7) Sperren und Loeschen schliessen den Gast sofort aus
store.revoke(laptop_device["id"])
assert call("GET", "/api/widgets", cookie=laptop)[0] == 401 and post("/api/message", laptop, {"message": "x"})[0] == 401
assert getj("/api/widgets", laptop2)["notes"] == "wieder da"                         # das andere Geraet des Bereichs geht weiter
status, raw = call("POST", "/api/remote/profile_delete", host="localhost:8000", body={"id": bruder})
assert status == 200
assert call("GET", "/api/widgets", cookie=laptop2)[0] == 401 and post("/api/message", laptop2, {"message": "x"})[0] == 401
assert not (tmp / "profiles" / bruder).exists() and getj("/api/widgets", phone) and call("GET", "/api/timers", cookie=phone)[0] == 200

# 8) Fehlt der Bereich, obwohl das Geraet noch da waere (Datei von Hand geloescht), gibt es nichts
other_profile_file = tmp / "profiles.json"
data = json.loads(other_profile_file.read_text(encoding="utf-8"))
data["profiles"] = [p for p in data["profiles"] if p["id"] != anderer]
other_profile_file.write_text(json.dumps(data), encoding="utf-8")
gate.profiles = profiles.ProfileStore(other_profile_file, tmp / "profiles")
httpd._testers.clear()
assert get("/api/widgets", other_cookie)[0] == 403 and post("/api/message", other_cookie, {"message": "x"})[0] == 403
assert owner.touched == [] and owner.local_messages == []

# 9) Ungekoppelte Seiten
assert call("GET", "/manifest.webmanifest")[0] == 200

print("ALL TESTS PASSED")
