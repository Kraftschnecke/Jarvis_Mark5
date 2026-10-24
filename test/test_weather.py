"""Wetter (Mark 5, Step 2.1): Open-Meteo, ohne Internet getestet."""

import sys
import tempfile
import types
from datetime import date
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

import abilities
import action_executor
import risk
import router
import server
from action import Action
from net_fetch import NetError
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools import weather_tool
from tools.weather_tool import WeatherService

TODAY = date(2026, 10, 22)
calls = []
state = {"fail": None, "places": None, "forecast": None}


def geocode_answer(name):
    return {"results": [{"name": name.title(), "latitude": 56.88, "longitude": 14.81,
                         "country": "Schweden", "admin1": "Kronobergs län"}]}


def forecast_answer():
    return {
        "current": {"temperature_2m": 11.6, "apparent_temperature": 9.2, "relative_humidity_2m": 81,
                    "weather_code": 3, "wind_speed_10m": 14.4},
        "daily": {
            "time": [f"2026-10-{22 + i}" for i in range(7)],
            "weather_code": [3, 61, 95, 0, 1, 2, 71],
            "temperature_2m_max": [13.2, 10.4, 9.0, 8.8, 9.1, 10.0, 2.0],
            "temperature_2m_min": [6.1, 5.5, 4.0, 1.2, 0.5, 2.0, -1.0],
            "precipitation_probability_max": [20, 85, 90, 5, 0, 10, 60],
            "precipitation_sum": [0.0, 5.4, 12.0, 0.0, 0.0, 0.1, 3.0],
        },
    }


def fetch(url, hosts, **kwargs):
    calls.append((url, hosts, kwargs))
    if state["fail"]:
        raise state["fail"]
    if "geocoding" in url:
        return state["places"] if state["places"] is not None else geocode_answer(kwargs["params"]["name"])
    return state["forecast"] if state["forecast"] is not None else forecast_answer()


now = [1000.0]
home = ["Mannheim"]
svc = WeatherService(fetch=fetch, clock=lambda: now[0], today=lambda: TODAY, home=lambda: home[0])

# 1) Heute: aktuelles Wetter + Tageswerte, gerundet, mit festen Woertern
r = svc.get_weather("Vaxjo", "heute")
assert r.success, r.error
assert r.data == {
    "place": "Vaxjo, Kronobergs län, Schweden", "day": "Donnerstag, 22.10.2026", "condition": "bedeckt",
    "high": 13, "low": 6, "rain_chance_percent": 20, "rain_mm": 0.0,
    "now": {"condition": "bedeckt", "temperature": 12, "feels_like": 9, "humidity_percent": 81, "wind_kmh": 14},
}, r.data
assert calls[0][1] == weather_tool.HOSTS and calls[0][0].startswith("https://geocoding-api.open-meteo.com/")
assert calls[1][0].startswith("https://api.open-meteo.com/v1/forecast")
assert calls[1][2]["params"]["forecast_days"] == 7 and calls[1][2]["params"]["timezone"] == "auto"

# 2) Zwischenspeicher: gleicher Ort und Tag = keine neuen Abrufe; nach 10 Minuten neue Vorhersage, Ort bleibt
n = len(calls)
svc.get_weather("vaxjo", "morgen")
assert len(calls) == n, "Ort und Vorhersage kommen aus dem Speicher"
now[0] += 601
svc.get_weather("Vaxjo", "heute")
assert len(calls) == n + 1 and "forecast" in calls[-1][0], "nach 10 Minuten nur die Vorhersage neu"

# 3) Andere Tage: kein 'now', Wort oder Datum
r = svc.get_weather("Vaxjo", "morgen")
assert r.success and "now" not in r.data and r.data["day"] == "Freitag, 23.10.2026"
assert r.data["condition"] == "leichter Regen" and r.data["rain_chance_percent"] == 85 and r.data["rain_mm"] == 5.4
assert svc.get_weather("Vaxjo", "Übermorgen").data["condition"] == "Gewitter"
assert svc.get_weather("Vaxjo", "2026-10-28").data["condition"] == "leichter Schneefall"
assert svc.get_weather("Vaxjo", "2026-10-22").data["now"]["temperature"] == 12
for word in ("", "heute", "today", None):
    assert svc.get_weather("Vaxjo", word).success, word

# 4) Falsche Tage: verstaendliche Meldung, kein Abruf
n = len(calls)
for bad, part in (("2026-10-29", "7 Tage"), ("2026-10-21", "vergangene"), ("irgendwann", "nicht verstanden"),
                  ("2026-13-45", "nicht verstanden"), (5, "nicht verstanden")):
    r = svc.get_weather("Vaxjo", bad)
    assert not r.success and part in r.error, (bad, r.error)
assert len(calls) == n

# 5) Heimatort: "heimat", leer, None -> Einstellung; ohne Heimatort eine Rueckfrage
for word in ("heimat", "Home", "", None, "  lokal "):
    r = svc.get_weather(word, "heute")
    assert r.success and r.data["place"].startswith("Mannheim"), (word, r.data)
home[0] = ""
r = svc.get_weather("heimat", "heute")
assert not r.success and "Für welchen Ort" in r.error and "Einstellungen" in r.error
home[0] = "Mannheim"

# 6) Ortsname wird gesaeubert und gekuerzt, Unsinn abgelehnt
n = len(calls)
svc.get_weather("Köln\x00​  Mitte\n", "heute")
sent = [c[2]["params"]["name"] for c in calls[n:] if "geocoding" in c[0]]
assert sent == ["Köln Mitte"], sent
svc.get_weather("x" * 500, "heute")
assert len([c for c in calls if "geocoding" in c[0]][-1][2]["params"]["name"]) <= weather_tool.MAX_PLACE_CHARS
assert weather_tool.clean_place(5) is None and weather_tool.clean_place("   ") is None

# 7) Ort nicht gefunden / kaputte Antworten
for answer in ({}, {"results": []}, {"results": ["x"]}, {"results": [{"name": "X"}]}, {"results": None}, [], "text",
               {"results": [{"name": "X", "latitude": 999, "longitude": 10}]},
               {"results": [{"name": "X", "latitude": "56", "longitude": 14}]},
               {"results": [{"name": "X", "latitude": float("nan"), "longitude": 14}]},
               {"results": [{"name": "X", "latitude": True, "longitude": 14}]}):
    state["places"] = answer
    r = svc.get_weather("Nirgendwo-" + str(id(answer)), "heute")
    assert not r.success and "nicht gefunden" in r.error, (answer, r.error)
state["places"] = None

# 8) Netzfehler: freundliche Meldung mit Grund, kein Absturz; nichts Falsches im Speicher
state["fail"] = NetError("Keine Verbindung zum Dienst.")
r = svc.get_weather("Neuort", "heute")
assert not r.success and "nicht abrufbar" in r.error and "Keine Verbindung" in r.error
state["fail"] = None
assert svc.get_weather("Neuort", "heute").success

# 9) Kaputte oder verrueckte Vorhersage: fehlende Werte werden None, nichts bricht
state["forecast"] = {"current": {"temperature_2m": "heiss", "weather_code": 999, "wind_speed_10m": -5},
                     "daily": {"time": ["2026-10-22"], "weather_code": [None], "temperature_2m_max": [500],
                               "temperature_2m_min": [], "precipitation_probability_max": [150]}}
now[0] += 1000
r = svc.get_weather("Verrueckt", "heute")
assert r.success and r.data["high"] is None and r.data["low"] is None and r.data["rain_chance_percent"] is None
assert r.data["condition"] is None and r.data["now"]["temperature"] is None and r.data["now"]["wind_kmh"] is None
state["forecast"] = {"daily": {"time": ["2026-10-30"]}}
now[0] += 1000
assert "keine Vorhersage" in svc.get_weather("Verrueckt", "heute").error
state["forecast"] = "kein dict"
now[0] += 1000
assert not svc.get_weather("Verrueckt", "heute").success
state["forecast"] = None
now[0] += 1000

# 10) Wettercodes: alle Texte vorhanden und nur feste Woerter
assert weather_tool.WEATHER_CODES[0] == "klar" and weather_tool.WEATHER_CODES[95] == "Gewitter"
assert weather_tool._condition("klar") is None and weather_tool._condition(True) is None and weather_tool._condition(4) is None

# 11) Startbericht: ein Satz; Regen erst ab 30 %; ohne Wetter None
text = svc.summary()
assert text == "In Mannheim sind es 12 °C, bedeckt. Heute bis 13 °C.", text
state["forecast"] = forecast_answer()
state["forecast"]["daily"]["precipitation_probability_max"][0] = 55
now[0] += 1000
assert svc.summary().endswith("Regenwahrscheinlichkeit 55 %."), svc.summary()
state["forecast"] = None
state["fail"] = NetError("x")
now[0] += 1000
svc2 = WeatherService(fetch=fetch, today=lambda: TODAY, home=lambda: "Neu")
assert svc2.summary() is None
state["fail"] = None
home[0] = ""
assert svc.summary() is None
home[0] = "Mannheim"

# 12) Aufgabe: Parameter beschrieben, Stufe safe, Executor ruft den Dienst, Fehler kommen als Ergebnis
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("GET_WEATHER")
assert task is not None and risk.task_risk(task) == risk.SAFE
assert [n for a in task.actions for n in a.parameters] == ["place", "day"]
weather_tool.set_default_service(svc)
result = action_executor.execute_action(Action("get_weather", {"place": "Vaxjo", "day": "morgen"}))
assert result.success and result.data["day"] == "Freitag, 23.10.2026"
assert not action_executor.execute_action(Action("get_weather", {"place": "Vaxjo", "day": "bald"})).success
prompt = router.build_prompt("Wie wird das Wetter morgen?", registry)
assert "GET_WEATHER" in prompt and "heimat" in prompt and "YYYY-MM-DD" in prompt

# 13) Fähigkeit schaltbar, Heimatort in den Einstellungen
assert abilities.ability_of("GET_WEATHER").id == "weather"
settings = SettingsManager(Path(tempfile.mkdtemp()) / "s.json")
assert settings.get("jarvis", "home_place") == "Mannheim"
check = server.EDITABLE_SETTINGS[("jarvis", "home_place")]
assert check("Växjö") and check("") and check("a" * 60)
assert not check("a" * 61) and not check(" Köln") and not check("Köln\n") and not check(5) and not check(None)

# 14) Server: /api/weather liefert den Satz, aber nur wenn die Fähigkeit an ist; Fehler zerstoeren den Start nicht
import json
import threading
import urllib.request


class FakeService:
    mode = "ok"

    def summary(self):
        if FakeService.mode == "boom":
            raise RuntimeError("kaputt")
        return "In Mannheim sind es 12 °C."


jarvis = types.SimpleNamespace(settings_manager=settings, guest=False)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, weather=FakeService())
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def get(path):
    with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=5) as response:
        return json.loads(response.read())


assert get("/api/weather") == {"summary": "In Mannheim sind es 12 °C."}
FakeService.mode = "boom"
assert get("/api/weather") == {"summary": None}
FakeService.mode = "ok"
settings.set("abilities", "weather", False)
assert get("/api/weather") == {"summary": None}, "ausgeschaltet: kein Abruf, kein Satz"
settings.set("abilities", "weather", True)
httpd.shutdown()

# 15) Gastmodus: kein Wetter
import guest
assert "GET_WEATHER" not in guest.GUEST_TASKS

# 16) Ortssuche: deutsche Namen und Sprach-Rueckfall (Kalkutta -> Kolkata; leere Antwort auf Deutsch -> Englisch versuchen)
searches = []
KOLKATA = {"results": [{"name": "Kolkata", "admin1": "West Bengal", "country": "Indien", "latitude": 22.57, "longitude": 88.36, "timezone": "Asia/Kolkata"}]}


def geo_fetch(url, hosts, params=None, **kwargs):
    searches.append((params["name"], params["language"]))
    if params["name"] == "Kolkata":
        return KOLKATA
    if params["name"] == "Nurenglisch" and params["language"] == "en":
        return KOLKATA
    return {}                                    # Open-Meteo antwortet ohne "results", wenn nichts passt


geo = WeatherService(fetch=geo_fetch)
assert geo.locate("Kalkutta")["label"] == "Kolkata, West Bengal, Indien" and searches == [("Kolkata", "de")], searches
searches.clear()
assert geo.locate("kalkutta") is not None and searches == [], "zweites Mal aus dem Zwischenspeicher"
assert geo.locate("Nurenglisch")["timezone"] == "Asia/Kolkata" and searches == [("Nurenglisch", "de"), ("Nurenglisch", "en")], searches
searches.clear()
assert geo.locate("Gibtsnicht") is None and searches == [("Gibtsnicht", "de"), ("Gibtsnicht", "en")], searches
searches.clear()
assert geo.locate("Tokio") is None and searches == [("Tokyo", "de"), ("Tokyo", "en"), ("Tokio", "de"), ("Tokio", "en")], searches
assert "kalkutta" in weather_tool.GERMAN_NAMES and all(v and v == v.strip() for v in weather_tool.GERMAN_NAMES.values())

print("ALL TESTS PASSED")
