"""Server: Seitenleisten-Widgets (Notizen, Ziele, Spielplan) ueber HTTP."""

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
from datetime import date

import server
import widgets
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False)


class FakeHockey:
    fail = False
    calls = []

    def get(self, team):
        FakeHockey.calls.append(team)
        if FakeHockey.fail:
            raise widgets.HockeyError("Der Spielplan ist gerade nicht erreichbar.")
        return {"team": team, "current": None, "next": [], "stale": False}


store = widgets.WidgetStore(folder / "w.json", today=lambda: date(2026, 10, 21))
class FakeMonitor:
    fail = False

    def sample(self):
        if FakeMonitor.fail:
            raise RuntimeError("psutil kaputt")
        return {"cpu_percent": 12.5, "ram_percent": 40.0}


httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, widget_store=store, hockey=FakeHockey(), monitor=FakeMonitor())
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def request(method, path, payload=None, content_type="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": content_type} if body is not None else {}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# Standard: leer
assert request("GET", "/api/widgets") == (200, {"notes": "", "goals": [], "date": "2026-10-21", "events": []})

# Speichern und wieder lesen (auch waehrend Jarvis eine Nachricht bearbeitet)
with httpd.message_lock:
    assert request("POST", "/api/widgets/notes", {"text": "Hallo Welt"})[1]["notes"] == "Hallo Welt"
    status, data = request("POST", "/api/widgets/goals", {"items": [{"text": "Sport", "done": True}]})
    assert status == 200 and data["goals"] == [{"text": "Sport", "done": True, "daily": False}]
    assert request("GET", "/api/widgets")[1]["notes"] == "Hallo Welt"

# Taegliche Ziele und Termine
status, data = request("POST", "/api/widgets/goals", {"items": [{"text": "Gym", "done": False, "daily": True}]})
assert status == 200 and data["goals"] == [{"text": "Gym", "done": False, "daily": True}]
status, data = request("POST", "/api/widgets/events", {"title": "Zahnarzt", "date": "2026-10-23", "time": "14:30"})
assert status == 200 and data["events"][0]["title"] == "Zahnarzt" and data["events"][0]["time"] == "14:30"
event_id = data["events"][0]["id"]
status, data = request("POST", "/api/widgets/events", {"title": "Ganztags", "date": "2026-10-24"})
assert status == 200 and len(data["events"]) == 2
assert request("GET", "/api/widgets")[1]["events"][1]["time"] == ""
for payload in ({"title": "", "date": "2026-10-23"}, {"title": "A", "date": "kaputt"}, {"title": "A"}, {"date": "2026-10-23"},
                {"title": "A", "date": "2026-10-23", "time": "99:99"}, {"title": 5, "date": "2026-10-23"}):
    assert request("POST", "/api/widgets/events", payload)[0] == 400, payload
assert request("POST", "/api/widgets/events/delete", {"id": "gibtsnicht"})[0] == 400
assert request("POST", "/api/widgets/events/delete", {})[0] == 400
status, data = request("POST", "/api/widgets/events/delete", {"id": event_id})
assert status == 200 and [e["title"] for e in data["events"]] == ["Ganztags"]
assert request("POST", "/api/widgets/goals", {"items": [{"text": "a", "done": False, "daily": "ja"}]})[0] == 400

# Ungueltiges wird abgelehnt und aendert nichts
for path, payload in (("/api/widgets/notes", {"text": 5}), ("/api/widgets/notes", {}),
                      ("/api/widgets/notes", {"text": "x" * 6000}),
                      ("/api/widgets/goals", {"items": "x"}), ("/api/widgets/goals", {"items": [{"text": ""}]}),
                      ("/api/widgets/goals", {})):
    status, data = request("POST", path, payload)
    assert status == 400 and "error" in data, (path, payload, status)
assert request("GET", "/api/widgets")[1]["goals"] == [{"text": "Gym", "done": False, "daily": True}], "Fehlversuche aendern nichts"
assert request("POST", "/api/widgets/notes", {"text": "x"}, content_type="text/plain")[0] == 415

# Einstellungen fuer die Seitenleiste werden geprueft
for key, bad in (("top", "Weather"), ("top", True), ("middle", "Calendar"), ("bottom", "Eisbaeren Berlin"), ("bottom", None)):
    assert request("POST", "/api/settings", {"category": "widgets", "key": key, "value": bad})[0] == 400, (key, bad)

# jarvis.apply_settings existiert in diesem Test nicht: Einstellungen direkt pruefen
for key, good in (("top", "Calendar"), ("top", "Off"), ("middle", "Goals"), ("middle", "Off"), ("bottom", "Edmonton Oilers"), ("bottom", "Adler Mannheim")):
    assert key in jarvis.settings_manager.get_category("widgets")
    assert server.EDITABLE_SETTINGS[("widgets", key)](good)

# Spielplan: aus -> kein Abruf; an -> Abruf; Fehler -> 502 mit Meldung
jarvis.settings_manager.set("widgets", "bottom", "Off")
assert request("GET", "/api/hockey") == (200, {"team": None}) and FakeHockey.calls == []
jarvis.settings_manager.set("widgets", "bottom", "Edmonton Oilers")
status, data = request("GET", "/api/hockey")
assert status == 200 and data["team"] == "Edmonton Oilers" and FakeHockey.calls == ["Edmonton Oilers"]
jarvis.settings_manager.set("widgets", "bottom", "Adler Mannheim")
assert request("GET", "/api/hockey")[1]["team"] == "Adler Mannheim" and FakeHockey.calls[-1] == "Adler Mannheim"
jarvis.settings_manager.set("widgets", "bottom", "Edmonton Oilers")
FakeHockey.fail = True
status, data = request("GET", "/api/hockey")
assert status == 502 and "nicht erreichbar" in data["error"]
# Ein manipulierter Wert in settings.json fuehrt nie zu einem Abruf
jarvis.settings_manager.set("widgets", "bottom", "http://evil.example")
assert request("GET", "/api/hockey") == (200, {"team": None})

# PC Facts und Performance: lokal gelesen, ohne Parameter, Fehler ohne Einzelheiten nach aussen
status, data = request("GET", "/api/performance")
assert status == 200 and data == {"cpu_percent": 12.5, "ram_percent": 40.0}
status, data = request("GET", "/api/system")
assert status == 200 and "cpu_name" in data and "ram_total_gb" in data and isinstance(data["drives"], list)
FakeMonitor.fail = True
status, data = request("GET", "/api/performance")
assert status == 502 and "psutil" not in data["error"]
assert request("POST", "/api/performance", {})[0] in (404, 405)
# Neue Felder: der Server akzeptiert nur die erlaubten Werte
check = server.EDITABLE_SETTINGS
for slot in ("fourth", "fifth"):
    assert check[("widgets", slot)]("Performance") and check[("widgets", slot)]("PC Facts") and check[("widgets", slot)]("Off")
    assert not check[("widgets", slot)]("Edmonton Oilers") and not check[("widgets", slot)]("<b>x</b>")

print("ALL TESTS PASSED")
