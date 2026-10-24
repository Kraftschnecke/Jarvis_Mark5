"""Server: Wecker/Timer ausschalten ueber HTTP (Step 2.11): Zustand, Stopp, Schlummern, Gastmodus."""

import http.client
import json
import sys
import threading
import types
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

import tempfile

import ringing
import server
import timer
import background_tasks
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())


class FakeWinsound:
    SND_FILENAME, SND_ASYNC, SND_LOOP, SND_PURGE = 1, 2, 8, 64

    def __init__(self):
        self.calls = []

    def PlaySound(self, what, flags):
        self.calls.append((what, flags))


fake = FakeWinsound()
ringer = ringing.Ringer(siren=ringing.Siren(player=fake, folder=folder))
ringing.set_default_ringer(ringer)
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, monitor=object())
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def request(method, path, payload=None, content_type="application/json", host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": content_type} if body is not None else {}
    if host:
        headers["Host"] = host
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# 1) Nichts laeutet
status, data = request("GET", "/api/ringing")
assert status == 200 and data["ringing"] == [] and data["sound"] == "Computer" and data["server_sound"] is False
assert request("POST", "/api/ringing/stop", {}) == (200, {"stopped": [], "reply": "", "state": data})

# 2) Wecker + Timer laeuten: Zustand sichtbar
ringer.briefing_provider = lambda: "Heute: nichts."
a = ringer.start("alarm", "Wecker", briefing=True)
t = ringer.start("timer", "Nudeln")
status, data = request("GET", "/api/ringing")
assert [(r["id"], r["kind"], r["label"]) for r in data["ringing"]] == [(1, "alarm", "Wecker"), (2, "timer", "Nudeln")]
assert data["server_sound"] is True and data["snooze_minutes"] == 5 and data["version"] == ringer.version

# 3) Einen ausschalten (Timer) - auch waehrend Jarvis eine Nachricht bearbeitet (kein message_lock)
with httpd.message_lock:
    status, data = request("POST", "/api/ringing/stop", {"id": 2})
assert status == 200 and data["stopped"] == ["Nudeln"] and data["reply"] == "Sir, Timer aus (Nudeln)."
assert [r["id"] for r in data["state"]["ringing"]] == [1] and ringer.siren.playing

# 4) Wecker ausschalten: Antwort mit Briefing zum Vorlesen
status, data = request("POST", "/api/ringing/stop", {"id": 1})
assert data["stopped"] == ["Wecker"] and data["reply"].endswith("Wecker aus. Heute: nichts.") and data["state"]["ringing"] == []
assert fake.calls[-1] == (None, fake.SND_PURGE)

# 5) Alles auf einmal (ohne id) und unbekannte Nummer
ringer.start("alarm", "Wecker")
ringer.start("timer", "Ei")
assert request("POST", "/api/ringing/stop", {"id": 99})[1]["stopped"] == [] and ringer.is_ringing()
status, data = request("POST", "/api/ringing/stop", {})
assert sorted(data["stopped"]) == ["Ei", "Wecker"] and not ringer.is_ringing()

# 6) Schlummern: Handler plant neu, Antwort nennt die Minuten
plans = []
ringer.snooze_handler = lambda ring, minutes: plans.append((ring["kind"], ring["label"], minutes))
ringer.start("alarm", "Wecker")
status, data = request("POST", "/api/ringing/stop", {"snooze": True})
assert data["reply"] == "Sir, ich wecke dich in 5 Minuten wieder." and plans == [("alarm", "Wecker", 5)] and not ringer.is_ringing()
ringer.start("alarm", "Wecker")
status, data = request("POST", "/api/ringing/stop", {"snooze": True, "minutes": 15})
assert data["reply"] == "Sir, ich wecke dich in 15 Minuten wieder." and plans[-1] == ("alarm", "Wecker", 15)
ringer.start("alarm", "Wecker")
assert request("POST", "/api/ringing/stop", {"snooze": True, "minutes": 9999})[1]["reply"].startswith("Sir, ich wecke dich in 60 Minuten")
assert request("POST", "/api/ringing/stop", {"snooze": True})[1]["reply"] == ""          # nichts da: nichts melden
ringer.snooze_handler = None

# 7) Ungueltige Eingaben
for bad in ({"id": "1"}, {"id": True}, {"id": 1.5}, {"id": [1]}):
    status, data = request("POST", "/api/ringing/stop", bad)
    assert status == 400, bad
assert request("POST", "/api/ringing/stop", {}, content_type="text/plain")[0] == 415
assert request("GET", "/api/ringing", host="evil.example")[0] == 403                    # fremder Host: abgelehnt
assert request("POST", "/api/ringing/stop", {}, host="evil.example")[0] == 403

# 8) Gastmodus kennt beide Adressen nicht
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=jarvis.settings_manager, guest=True), guest=True)
guest_port = guest_httpd.server_address[1]
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()
ringer.start("alarm", "Wecker")
conn = http.client.HTTPConnection("127.0.0.1", guest_port, timeout=5)
conn.request("GET", "/api/ringing")
assert conn.getresponse().status == 403
conn.close()
conn = http.client.HTTPConnection("127.0.0.1", guest_port, timeout=5)
conn.request("POST", "/api/ringing/stop", body=b"{}", headers={"Content-Type": "application/json"})
assert conn.getresponse().status == 403 and ringer.is_ringing()                          # Gast schaltet nichts aus
conn.close()
guest_httpd.shutdown()
ringer.stop()
httpd.shutdown()

print("ALL TESTS PASSED")
