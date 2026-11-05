"""Server-Routen des Fokus-Timers (Mark 5, Step 2.13): Anzeige und Abbrechen."""

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

import focus
import server
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
clock = [100.0]
manager = focus.FocusManager(clock=lambda: clock[0], submit=lambda item: None, chime=lambda: None, auto_thread=False)
focus.set_default_manager(manager)
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, monitor=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=jarvis.settings_manager, guest=True), guest=True)
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()


def request(httpd_, method, path, payload=None, content_type="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", httpd_.server_address[1], timeout=5)
    body = None if payload is None else json.dumps(payload).encode()
    conn.request(method, path, body=body, headers={"Content-Type": content_type} if body is not None else {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# 1) Keine Sitzung
assert request(httpd, "GET", "/api/focus") == (200, {"active": False})
assert request(httpd, "POST", "/api/focus/stop", {}) == (200, {"stopped": False, "summary": None, "state": {"active": False}})

# 2) Laufende Sitzung sichtbar
manager.start(label="Lernen", rounds=3)
clock[0] += 60
status, data = request(httpd, "GET", "/api/focus")
assert status == 200 and data["active"] and data["phase"] == "work" and data["round"] == 1 and data["rounds"] == 3
assert data["remaining"] == 24 * 60 and data["label"] == "Lernen"

# 3) Abbrechen geht auch, während Jarvis antwortet (kein message_lock)
with httpd.message_lock:
    status, data = request(httpd, "POST", "/api/focus/stop", {})
assert status == 200 and data["stopped"] is True and data["summary"] == {"label": "Lernen", "completed_rounds": 0, "rounds": 3}
assert data["state"] == {"active": False} and manager.state() == {"active": False}

# 4) Nur POST mit JSON zum Abbrechen
assert request(httpd, "POST", "/api/focus/stop", {}, content_type="text/plain")[0] == 415
assert request(httpd, "GET", "/api/focus/stop")[0] in (403, 404)

# 5) Gastmodus: beides gesperrt, und eine laufende Sitzung bleibt unberührt
manager.start(rounds=2)
assert request(guest_httpd, "GET", "/api/focus")[0] == 403
assert request(guest_httpd, "POST", "/api/focus/stop", {})[0] == 403
assert manager.state()["active"] is True
manager.stop()

httpd.shutdown()
guest_httpd.shutdown()
print("ALL TESTS PASSED")
