"""Remote R2b (Mark 5): Live-Abgleich /api/sync. Fingerabdruck, Verlauf nur bei Aenderung, PC und Handy, kein message_lock."""
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
import threading
import types

import server

tmp = Path(tempfile.mkdtemp())


class FakeJarvis:
    def __init__(self):
        self.conversation = types.SimpleNamespace(messages=[])
        self.active = {"project_id": 1, "conversation_id": 7}
        self.tree_calls = 0

    def get_active(self):
        return dict(self.active)

    def get_tree(self):
        self.tree_calls += 1
        return [{"id": 1, "name": "Alltag", "conversations": [{"id": 7, "title": "Test"}]}]


def get(httpd, path):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    conn.request("GET", path, headers={"Host": "localhost:%d" % httpd.server_address[1]})
    response = conn.getresponse()
    raw = response.read()
    headers = dict((k.lower(), v) for k, v in response.getheaders())
    conn.close()
    return response.status, headers, json.loads(raw.decode("utf-8"))


jarvis = FakeJarvis()
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, widget_store=None, monitor=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()

# 1) Ohne bekannte Version kommt alles: Version, aktive Konversation, Verlauf, Seitenleiste
status, headers, first = get(httpd, "/api/sync")
assert status == 200 and headers["cache-control"] == "no-store"
assert set(first) == {"version", "active", "messages", "projects"}, set(first)
assert first["active"] == {"project_id": 1, "conversation_id": 7} and first["messages"] == []
assert isinstance(first["version"], str) and len(first["version"]) == 16
assert first["projects"][0]["name"] == "Alltag"

# 2) Gleiche Version: nur Version und active, kein Verlauf, keine Baumabfrage
jarvis.tree_calls = 0
_, _, same = get(httpd, "/api/sync?known=" + first["version"])
assert same == {"version": first["version"], "active": first["active"]}
assert jarvis.tree_calls == 0

# 3) Neue Nachricht (egal ob vom PC oder vom Handy): Version aendert sich, Verlauf kommt mit
jarvis.conversation.messages.append({"role": "user", "content": "Hallo"})
_, _, second = get(httpd, "/api/sync?known=" + first["version"])
assert second["version"] != first["version"]
assert second["messages"] == [{"role": "user", "content": "Hallo"}] and "projects" in second
_, _, quiet = get(httpd, "/api/sync?known=" + second["version"])
assert "messages" not in quiet and quiet["version"] == second["version"]

# 4) Jede Aenderung zaehlt: Antwort angehaengt, Text geaendert, andere Konversation
jarvis.conversation.messages.append({"role": "assistant", "content": "Guten Tag"})
v3 = get(httpd, "/api/sync")[2]["version"]
assert v3 != second["version"]
jarvis.conversation.messages[-1]["content"] = "Guten Abend"
v4 = get(httpd, "/api/sync")[2]["version"]
assert v4 not in (v3, second["version"])
jarvis.active = {"project_id": 1, "conversation_id": 8}
v5 = get(httpd, "/api/sync")[2]
assert v5["version"] != v4 and v5["active"]["conversation_id"] == 8
jarvis.conversation.messages.clear()
v6 = get(httpd, "/api/sync")[2]
assert v6["version"] != v5["version"] and v6["messages"] == []

# 5) Stabil: gleicher Stand, gleiche Version (auch ueber mehrere Aufrufe)
assert get(httpd, "/api/sync")[2]["version"] == get(httpd, "/api/sync")[2]["version"] == v6["version"]

# 6) Falsche oder uebergrosse known-Werte stoeren nicht: es kommt einfach der volle Stand
for junk in ("", "x", "A" * 5000, "%00", "../../etc"):
    status, _, data = get(httpd, "/api/sync?known=" + junk)
    assert status == 200 and "messages" in data, junk

# 7) Die Antwort enthaelt den Verlauf als Kopien: Aendern der Antwort aendert Jarvis nicht
jarvis.conversation.messages.append({"role": "user", "content": "A"})
data = get(httpd, "/api/sync")[2]
data["messages"][0]["content"] = "veraendert"
assert jarvis.conversation.messages[0]["content"] == "A"

# 8) Ein Absturz in Jarvis wird zu einer sauberen 500 ohne Details
class Broken(FakeJarvis):
    def get_active(self):
        raise RuntimeError("geheimer Pfad C:/x")

broken = server.JarvisServer(("127.0.0.1", 0), Broken(), widget_store=None, monitor=object())
threading.Thread(target=broken.serve_forever, daemon=True).start()
import contextlib, io
with contextlib.redirect_stderr(io.StringIO()):
    status, _, data = get(broken, "/api/sync")
assert status == 500 and data == {"error": "Abgleich nicht moeglich."} and "geheim" not in json.dumps(data)

# 9) Der Abgleich nimmt den message_lock nicht (sonst blockiert er waehrend einer langen Antwort)
httpd.message_lock.acquire()
try:
    status, _, data = get(httpd, "/api/sync")
    assert status == 200
finally:
    httpd.message_lock.release()

print("ALL TESTS PASSED")
