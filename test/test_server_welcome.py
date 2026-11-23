"""Server-Routen fuer die Willkommensseite: Erinnerungen, Schlagzeilen, Briefing lesen; Medientaste und Lautstaerke (nur am PC)."""

import http.client
import json
import sys
import tempfile
import threading
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
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
stub_if_missing("requests")
project_stub = types.ModuleType("project")
for fn in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
           "save_message", "get_conversation", "rename_conversation", "create_project",
           "reset_conversation", "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, fn, lambda *a, **k: None)
sys.modules["project"] = project_stub

import reminders
import remote_policy
import server
from settings_manager import SettingsManager
from tools import media_tool, news_tool, volume_tool
from tools.tool_result import ToolResult

folder = Path(tempfile.mkdtemp())
settings = SettingsManager(folder / "s.json")
store = reminders.ReminderStore(str(folder / "reminders.json"), now=lambda: datetime(2026, 11, 22, 10, 0))
reminders.set_default_store(store)

calls = {"news": [], "briefing": 0, "press": [], "volume": []}


def fake_news(source, topic, count):
    calls["news"].append((source, topic, count))
    return ToolResult(success=True, data={"items": [
        {"number": 1, "source": "Tagesschau", "title": "Schlagzeile <b>eins</b>", "summary": "x" * 500, "url": "https://example.org/a", "published": "22.11.2026 08:00 UTC"}],
        "unavailable_sources": []})


news_tool.set_default_service(types.SimpleNamespace(get_news=fake_news))
media_tool._press = lambda key: calls["press"].append(key)
volume_tool.set_volume = lambda percent: (calls["volume"].append(percent), ToolResult(success=percent != 13, data=percent, error="kaputt"))[1]


class FakeJarvis:
    guest = False
    settings_manager = settings

    def daily_briefing(self):
        calls["briefing"] += 1
        return "Guten Abend, Sir. Heute: nichts Besonderes."


forecast_calls = []


def fake_week(place, icons=False):
    forecast_calls.append((place, icons))
    if place == "Nirgendwo":
        return ToolResult(success=False, error="Den Ort „Nirgendwo“ habe ich nicht gefunden.")
    if place == "kaputt":
        raise RuntimeError("geheime Einzelheit")
    return ToolResult(success=True, data={"place": "Ort " + place, "now": None, "days": []})


httpd = server.JarvisServer(("127.0.0.1", 0), FakeJarvis(), monitor=object(), weather=types.SimpleNamespace(week_forecast=fake_week))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=settings, guest=True), guest=True)
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()


def request(srv, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    body = None if payload is None else json.dumps(payload).encode()
    conn.request(method, path, body=body, headers={"Content-Type": "application/json"} if body is not None else {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


# 1) Erinnerungen: nach Zeit sortiert, hoechstens zehn, mit Wiederholung
assert request(httpd, "GET", "/api/reminders") == (200, {"reminders": []})
store.add("Zahnarzt anrufen", "2026-11-25", "09:00")
store.add("Muell raus", "2026-11-23", "20:00", freq="weekly")
status, data = request(httpd, "GET", "/api/reminders")
assert status == 200 and [r["text"] for r in data["reminders"]] == ["Muell raus", "Zahnarzt anrufen"], data
assert data["reminders"][0]["repeat"] and data["reminders"][1]["repeat"] is None and set(data["reminders"][0]) == {"id", "text", "due", "repeat"}
for n in range(12):
    store.add(f"Aufgabe {n}", "2026-12-01", f"{8 + n // 2:02d}:{(n % 2) * 30:02d}")
assert len(request(httpd, "GET", "/api/reminders")[1]["reminders"]) == 10
store.add("Wecker nicht dabei", "2026-11-24", "06:30", kind="alarm")
assert "Wecker nicht dabei" not in json.dumps(request(httpd, "GET", "/api/reminders")[1])
settings.set("abilities", "reminders", False)
assert request(httpd, "GET", "/api/reminders") == (200, {"reminders": [], "disabled": True})
settings.set("abilities", "reminders", True)

# 2) Schlagzeilen: acht, Text gekuerzt, aus -> "disabled", Fehler -> 502
status, data = request(httpd, "GET", "/api/news")
assert status == 200 and calls["news"] == [("alle", "", 8)]
item = data["items"][0]
assert set(item) == {"title", "source", "summary", "url", "published"} and item["title"] == "Schlagzeile <b>eins</b>" and len(item["summary"]) == 300
settings.set("abilities", "news", False)
assert request(httpd, "GET", "/api/news") == (200, {"items": [], "disabled": True}) and len(calls["news"]) == 1
settings.set("abilities", "news", True)
news_tool.set_default_service(types.SimpleNamespace(get_news=lambda *a: ToolResult(success=False, error="Die News sind gerade nicht abrufbar.")))
status, data = request(httpd, "GET", "/api/news")
assert status == 502 and "nicht abrufbar" in data["error"]

# 3) Briefing: nur lesen, ohne den Tagesmerker
status, data = request(httpd, "GET", "/api/briefing")
assert status == 200 and data == {"text": "Guten Abend, Sir. Heute: nichts Besonderes."} and calls["briefing"] == 1
settings.set("abilities", "briefing", False)
assert request(httpd, "GET", "/api/briefing") == (200, {"text": None, "disabled": True}) and calls["briefing"] == 1
settings.set("abilities", "briefing", True)

# 4) Medientaste: feste Befehle, ungueltig -> 400, aus -> 403
status, data = request(httpd, "POST", "/api/media", {"action": "play_pause"})
if sys.platform.startswith("win"):
    assert status == 200 and data["command"] == "play_pause" and calls["press"] == [media_tool.VK_MEDIA_PLAY_PAUSE]
else:
    assert status == 400 and "nur unter Windows" in data["error"]       # ohne Windows nur die Meldung
assert request(httpd, "POST", "/api/media", {"action": "Programm starten"})[0] == 400
assert request(httpd, "POST", "/api/media", {})[0] == 400
settings.set("abilities", "music", False)
assert request(httpd, "POST", "/api/media", {"action": "next"})[0] == 403
settings.set("abilities", "music", True)

# 5) Lautstaerke: ganze Zahl 0..100
assert request(httpd, "POST", "/api/volume", {"percent": 40}) == (200, {"percent": 40}) and calls["volume"] == [40]
for bad in ("40", 40.5, True, None, [40]):
    assert request(httpd, "POST", "/api/volume", {"percent": bad})[0] == 400, bad
assert calls["volume"] == [40]                                              # nichts davon erreichte die Lautstaerke
status, data = request(httpd, "POST", "/api/volume", {"percent": 13})        # das Werkzeug meldet einen Fehler
assert status == 400 and data["error"] == "kaputt"
settings.set("abilities", "volume", False)
assert request(httpd, "POST", "/api/volume", {"percent": 50})[0] == 403 and calls["volume"] == [40, 13]
settings.set("abilities", "volume", True)

# 5b) Wochenvorhersage: Heimatort ohne Angabe, gesuchter Ort ueber ?place=, aus -> "disabled", Fehler -> 502 ohne Einzelheiten
assert request(httpd, "GET", "/api/forecast") == (200, {"forecast": {"place": "Ort heimat", "now": None, "days": []}})
assert request(httpd, "GET", "/api/forecast?place=Lissabon")[1]["forecast"]["place"] == "Ort Lissabon"
assert request(httpd, "GET", "/api/forecast?place=Bad%20Homburg%20v.%20d.%20H.")[1]["forecast"]["place"] == "Ort Bad Homburg v. d. H."
assert request(httpd, "GET", "/api/forecast?place=")[1]["forecast"]["place"] == "Ort heimat"
assert forecast_calls == [("heimat", True), ("Lissabon", True), ("Bad Homburg v. d. H.", True), ("heimat", True)], forecast_calls
status, data = request(httpd, "GET", "/api/forecast?place=Nirgendwo")
assert status == 502 and "nicht gefunden" in data["error"]
status, data = request(httpd, "GET", "/api/forecast?place=kaputt")
assert status == 502 and "geheime" not in json.dumps(data) and "nicht abrufbar" in data["error"]
n_calls = len(forecast_calls)
settings.set("abilities", "weather", False)
assert request(httpd, "GET", "/api/forecast?place=Lissabon") == (200, {"disabled": True}) and len(forecast_calls) == n_calls
settings.set("abilities", "weather", True)

# 5c) PC-Lage: der Bericht der Auswertung, aus -> "disabled", Fehler -> 502 ohne Einzelheiten
class FakeHealth:
    broken = False

    def report(self):
        if self.broken:
            raise RuntimeError("geheime Einzelheit")
        return {"now": {}, "drives": [{"letter": "C", "media": "SSD"}], "programs": {"ram": [], "cpu": [], "disk": []}, "autostart": [],
                "assessment": {"level": "ok", "headline": "Alles ruhig.", "findings": []}}


health = FakeHealth()
health_httpd = server.JarvisServer(("127.0.0.1", 0), FakeJarvis(), monitor=object(), health=health)
threading.Thread(target=health_httpd.serve_forever, daemon=True).start()
status, data = request(health_httpd, "GET", "/api/pc_lage")
assert status == 200 and data["pc_lage"]["assessment"]["headline"] == "Alles ruhig." and data["pc_lage"]["drives"][0]["media"] == "SSD", data
health.broken = True
status, data = request(health_httpd, "GET", "/api/pc_lage")
assert status == 502 and "geheime" not in json.dumps(data) and "PC-Lage" in data["error"]
health.broken = False
import abilities
real_enabled = abilities.task_enabled
abilities.task_enabled = lambda task, manager: False if task == "GET_SYSTEM_INFO" else real_enabled(task, manager)
assert request(health_httpd, "GET", "/api/pc_lage") == (200, {"disabled": True})
abilities.task_enabled = real_enabled

# 6) Gastmodus: keine dieser Adressen
for method, path, payload in (("GET", "/api/pc_lage", None), ("GET", "/api/forecast?place=Rom", None), ("GET", "/api/reminders", None), ("GET", "/api/news", None), ("GET", "/api/briefing", None),
                              ("POST", "/api/media", {"action": "next"}), ("POST", "/api/volume", {"percent": 10})):
    status, data = request(guest_httpd, method, path, payload)
    assert status in (403, 404), (path, status)
assert calls["volume"] == [40, 13] and len(calls["press"]) <= 1

# 7) Remote: lesen ja (Anzeige), Medientaste und Lautstaerke nie
for path in ("/api/reminders", "/api/news", "/api/briefing", "/api/forecast"):
    assert remote_policy.api_allowed("GET", path), path
assert not remote_policy.api_allowed("GET", "/api/pc_lage"), "PC-Lage nur am PC"
for path in ("/api/media", "/api/volume"):
    assert not remote_policy.api_allowed("POST", path, {"info": True, "daily": True, "pc": True}), path
    assert not remote_policy.api_allowed("GET", path), path

print("ALL TESTS PASSED")
