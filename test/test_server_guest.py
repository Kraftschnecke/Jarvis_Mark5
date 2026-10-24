"""Server im Gastmodus: nur drei Adressen, alles andere ist verboten und erreicht Jarvis nie."""

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

import background_tasks
import guest
import server
import timer
from guest import GuestJarvis


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text="Gerne, Sir.")


guest.route_message = lambda client, message, registry: {
    "kind": "CHAT", "task_type": None, "parameters": {},
    "command": {"intent": "NORMAL_MESSAGE", "project_name": None,
                "conversation_name": None, "new_conversation_name": None}}

client = FakeClient()
gj = GuestJarvis(client)
httpd = server.JarvisServer(("127.0.0.1", 0), gj, guest=True)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def request(method, path, body=None, headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = dict(headers or {})
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    for key, value in headers.items():
        conn.putheader(key, value)
    if body is not None:
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders(body)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def post(path, payload, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    return request("POST", path, json.dumps(payload).encode(), h)


# Der Besitzer hat gerade einen Timer laufen und eine Meldung wartet: der Gast sieht nichts davon
owner_timer = timer.start_timer(600, "Geheim")
background_tasks.submit_result({"type": "TIMER_FINISHED", "data": {"seconds": 5, "name": "Geheim"}})

# 1) Seite und Dateien gibt es
status, body = request("GET", "/")
assert status == 200 and b"J.A.R.V.I.S." in body
assert request("GET", "/app.js")[0] == 200 and request("GET", "/style.css")[0] == 200

# 2) Erlaubt: Einstellungen (Standardwerte, mit Gast-Kennzeichen) und leere Hintergrundliste
status, body = request("GET", "/api/settings")
data = json.loads(body)
assert status == 200 and data["guest"] is True
assert data["settings"]["voice"]["output"] is False and data["settings"]["memory"]["enabled"] is True
assert request("GET", "/api/background") == (200, b'{"messages": [], "last": 0}')
assert request("GET", "/api/background?after=0") == (200, b'{"messages": [], "last": 0}')
assert background_tasks.result_queue.qsize() == 1, "Meldungen des Besitzers duerfen nicht abgeholt werden"

# 3) Alle anderen Adressen sind verboten
for path in ("/api/projects", "/api/timers", "/api/memories", "/api/actions", "/api/speak", "/api/message",
             "/api/confirm", "/api/plan/abort", "/api/unbekannt", "/api/conversation/open",
             "/api/widgets", "/api/hockey", "/api/weather", "/api/system", "/api/performance"):
    status, body = request("GET", path)
    assert status == 403 and "Gastmodus" in json.loads(body)["error"], (path, status)

for path, payload in (
    ("/api/settings", {"category": "voice", "key": "output", "value": True}),
    ("/api/speak", {"text": "Hallo"}),
    ("/api/timer/cancel", {"id": owner_timer.id}),
    ("/api/confirm", {"id": "x", "approve": True}),
    ("/api/plan/confirm", {"id": "x", "approve": True}),
    ("/api/plan/abort", {}),
    ("/api/memory/update", {"key": "a", "value": "b", "type": "fact"}),
    ("/api/memory/delete", {"key": "a"}),
    ("/api/memory/delete_all", {"phrase": "ALLE ERINNERUNGEN LÖSCHEN", "count": 1}),
    ("/api/project/open", {"id": 1}),
    ("/api/project/new", {"name": "x"}),
    ("/api/project/delete", {"id": 1}),
    ("/api/conversation/open", {"id": 1}),
    ("/api/conversation/reset", {}),
    ("/api/conversation/delete", {"id": 1}),
    ("/api/widgets/notes", {"text": "x"}),
    ("/api/widgets/goals", {"items": []}),
    ("/api/unbekannt", {}),
):
    status, body = post(path, payload)
    assert status == 403 and "Gastmodus" in json.loads(body)["error"], (path, status)

assert len(timer.list_timers()) == 1, "der Gast darf deinen Timer nicht abbrechen"
assert client.calls == [], "verbotene Anfragen duerfen nichts kosten"

# 4) Nachrichten gehen an den Gast-Jarvis
status, body = post("/api/message", {"message": "Hallo"})
data = json.loads(body)
assert status == 200 and data == {"status": "response", "content": "Gerne, Sir."}, data
assert len(client.calls) == 1
# Zusaetzliche Felder aendern nichts (kein Befehl, kein Sonderstatus)
status, body = post("/api/message", {"message": "Hallo", "status": "exit", "confirmation": {"id": 1}})
assert json.loads(body) == {"status": "response", "content": "Gerne, Sir."}
assert post("/api/message", {"message": 5})[0] == 400
assert post("/api/message", {})[0] == 400

# 5) Schutz wie im Normalbetrieb
assert post("/api/message", {"message": "Hallo"}, {"Origin": "https://evil.example"})[0] == 403
assert request("GET", "/api/settings", host="evil.example")[0] == 403
assert request("POST", "/api/message", b'{"message": "x"}', {"Content-Type": "text/plain"})[0] == 415

# Aufraeumen
timer.cancel_timer_by_id(owner_timer.id)
background_tasks.get_results()

# 6) Start nur ueber --guest: ohne Schalter ist der Server nicht im Gastmodus
assert server.JarvisServer.__init__.__defaults__ == (False, None, None, None, None)
assert "--guest" in open(PROJECT_DIR / "server.py", encoding="utf-8").read()
settings_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read().split("EDITABLE_SETTINGS = {")[1].split("}")[0]
assert "guest" not in settings_source, "der Gastmodus darf nicht ueber Einstellungen schaltbar sein"

print("ALL TESTS PASSED")
