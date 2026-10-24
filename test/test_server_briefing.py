"""Server-Route fuer das Briefing beim ersten Start des Tages (Mark 5, Step 2.12)."""

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

import server
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
calls = []


def auto_briefing():
    calls.append(1)
    return "Guten Morgen, Sir." if len(calls) == 1 else None


jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False, auto_briefing=auto_briefing)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, monitor=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=jarvis.settings_manager, guest=True,
                                                                          auto_briefing=auto_briefing), guest=True)
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()


def request(httpd_, method, path, payload=None, content_type="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", httpd_.server_address[1], timeout=5)
    body = None if payload is None else json.dumps(payload).encode()
    conn.request(method, path, body=body, headers={"Content-Type": content_type} if body is not None else {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# 1) Route liefert den Text, danach null (die Logik "einmal pro Tag" steckt in Jarvis.auto_briefing)
with httpd.message_lock:                                       # braucht den message_lock nicht
    assert request(httpd, "POST", "/api/briefing/auto", {}) == (200, {"text": "Guten Morgen, Sir."})
assert request(httpd, "POST", "/api/briefing/auto", {}) == (200, {"text": None})
assert len(calls) == 2

# 2) Nur POST mit JSON; GET gibt es nicht
assert request(httpd, "GET", "/api/briefing/auto")[0] in (403, 404)
assert request(httpd, "POST", "/api/briefing/auto", {}, content_type="text/plain")[0] == 415

# 3) Gastmodus: gesperrt, auto_briefing wird gar nicht erst gefragt
before = len(calls)
assert request(guest_httpd, "POST", "/api/briefing/auto", {})[0] == 403 and len(calls) == before

httpd.shutdown()
guest_httpd.shutdown()
print("ALL TESTS PASSED")
