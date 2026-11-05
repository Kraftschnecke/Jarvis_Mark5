"""Server-Routen fuer freigegebene Ordner (Mark 5, Step 2.14): anzeigen, hinzufuegen, entfernen."""

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

import os
import tempfile

import folders
import server
from settings_manager import SettingsManager

base = Path(tempfile.mkdtemp()).resolve()
home = base / "home"
docs = home / "Dokumente"
docs.mkdir(parents=True)
(base / "project").mkdir()
(base / "sys").mkdir()
fl = folders.FolderList(base / "f.json", project_dir=base / "project", home=home, system_dirs=[base / "sys"])
folders.set_default_list(fl)
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(base / "s.json"), guest=False)
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


# 1) Leer, hinzufügen, anzeigen (auch während Jarvis antwortet: kein message_lock)
assert request(httpd, "GET", "/api/folders") == (200, {"folders": [], "max": 10})
with httpd.message_lock:
    status, data = request(httpd, "POST", "/api/folders/add", {"path": str(docs)})
assert status == 200 and data == {"folders": [{"path": str(docs), "exists": True}], "max": 10}
assert request(httpd, "GET", "/api/folders")[1]["folders"] == [{"path": str(docs), "exists": True}]
assert fl.roots() == [str(docs)]

# 2) Fehler kommen als 400 mit lesbarem Satz, und es ändert sich nichts
for payload, part in (({"path": str(docs)}, "schon freigegeben"), ({"path": str(home)}, "Benutzerordner"),
                      ({"path": str(base / "project")}, "geschützt"), ({"path": str(base / "gibtsnicht")}, "gibt es nicht"),
                      ({"path": "https://x.de"}, "Web- oder Netzwerk"), ({"path": ""}, "kein Ordner"), ({"path": "relativ"}, "vollständigen Pfad")):
    status, data = request(httpd, "POST", "/api/folders/add", payload)
    assert status == 400 and part in data["error"], (payload, status, data)
for payload in ({"path": 5}, {"path": None}, {"path": ["x"]}, {}):
    status, data = request(httpd, "POST", "/api/folders/add", payload)
    assert status == 400 and "kein Ordner" in data["error"], payload
    assert request(httpd, "POST", "/api/folders/remove", payload)[0] == 400
assert [f["path"] for f in fl.list()] == [str(docs)]

# 3) Entfernen
status, data = request(httpd, "POST", "/api/folders/remove", {"path": "/nicht/in/der/liste"})
assert status == 400 and "nicht in der Liste" in data["error"]
assert request(httpd, "POST", "/api/folders/remove", {"path": str(docs)}) == (200, {"folders": [], "max": 10})
assert fl.roots() == []

# 4) Nur POST mit JSON
assert request(httpd, "POST", "/api/folders/add", {"path": str(docs)}, content_type="text/plain")[0] == 415
assert request(httpd, "GET", "/api/folders/add")[0] in (403, 404)
assert fl.list() == []

# 5) Gastmodus: alles gesperrt, nichts ändert sich
assert request(guest_httpd, "GET", "/api/folders")[0] == 403
assert request(guest_httpd, "POST", "/api/folders/add", {"path": str(docs)})[0] == 403
fl.add(str(docs))
assert request(guest_httpd, "POST", "/api/folders/remove", {"path": str(docs)})[0] == 403
assert [f["path"] for f in fl.list()] == [str(docs)]

# 6) Quelltext: die Routen stehen vor dem message_lock und nach der Gast-Sperre; Oberfläche
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
post = server_source.split("def do_POST")[1]
assert post.index("self.server.guest and path") < post.index("/api/folders/add") < post.rindex("with self.server.message_lock:")
app_js = open(PROJECT_DIR / "web" / "app.js", encoding="utf-8").read()
assert 'type: "folder-list"' in app_js and '"/api/folders/add"' in app_js and '"/api/folders/remove"' in app_js and "function buildFolderList" in app_js
assert "innerHTML" not in app_js.split("function buildFolderList")[1].split("function buildMemoryList")[0]       # Pfade nie als HTML

httpd.shutdown()
guest_httpd.shutdown()
print("ALL TESTS PASSED")
