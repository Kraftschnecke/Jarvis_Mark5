"""Weltuhr (Mark 5, Step 2.4): Zeitzonen, ohne Internet getestet."""

import sys
import tempfile
import types
from datetime import datetime, timezone
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
from tools import weather_tool, world_time_tool
from tools.weather_tool import WeatherService
from tools.world_time_tool import WorldTimeService, describe_difference, format_offset, load_zone
from zoneinfo import ZoneInfo


# 0) Ohne Zeitzonen-Datenbank gehen die Tests nicht: unter Windows liefert sie das Paket tzdata
try:
    ZoneInfo("Europe/Berlin")
except Exception:
    raise SystemExit("Die Zeitzonen-Datenbank fehlt. Bitte:  pip install -r requirements.txt  (Paket tzdata)")
assert "tzdata" in (PROJECT_DIR / "requirements.txt").read_text(encoding="utf-8")

BERLIN = ZoneInfo("Europe/Berlin")
located = []
zones = {"edmonton": {"label": "Edmonton, Alberta, Canada", "timezone": "America/Edmonton"},
         "tokio": {"label": "Tokio, Tokyo, Japan", "timezone": "Asia/Tokyo"},
         "kalkutta": {"label": "Kolkata, West Bengal, India", "timezone": "Asia/Kolkata"},
         "new york": {"label": "New York, United States", "timezone": "America/New_York"},
         "london": {"label": "London, England, United Kingdom", "timezone": "Europe/London"},
         "unsinn": {"label": "Irgendwo", "timezone": "Mars/Olympus"},
         "ohnezone": {"label": "Ohne Zone", "timezone": None}}
state = {"fail": False}


def fake_locate(text):
    located.append(text)
    if state["fail"]:
        raise NetError("Keine Verbindung zum Dienst.")
    return zones.get(text.casefold())


now = [datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)]      # Donnerstag, 14:00 in Berlin (Sommerzeit)
service = WorldTimeService(locate=fake_locate, clock=lambda: now[0], local_zone=BERLIN)

# 1) Hilfsfunktionen
assert format_offset(0) == "UTC+0" and format_offset(-360) == "UTC-6" and format_offset(330) == "UTC+5:30" and format_offset(-210) == "UTC-3:30"
assert describe_difference(0) == "Dort ist es genauso spät wie bei dir."
assert describe_difference(-480) == "Dort ist es 8 Stunden früher als bei dir."
assert describe_difference(60) == "Dort ist es 1 Stunde später als bei dir."
assert describe_difference(210) == "Dort ist es 3 Stunden und 30 Minuten später als bei dir."
assert describe_difference(-45) == "Dort ist es 45 Minuten früher als bei dir."

# 2) Orte: Uhrzeit, Datum, Unterschied (Sommerzeit-genau)
r = service.get_world_time("Edmonton")
assert r.success, r.error
d = r.data
assert d["place"] == "Edmonton, Alberta, Canada" and d["timezone"] == "America/Edmonton"
assert d["time"] == "06:00" and d["your_time"] == "14:00" and d["utc_offset"] == "UTC-6"
assert d["date"] == "Donnerstag, 22.10.2026" and d["difference_minutes"] == -480
assert d["difference"] == "Dort ist es 8 Stunden früher als bei dir."
tokyo = service.get_world_time("Tokio").data
assert tokyo["time"] == "21:00" and tokyo["date"] == "Donnerstag, 22.10.2026" and tokyo["difference_minutes"] == 420
india = service.get_world_time("Kalkutta").data
assert india["time"] == "17:30" and india["utc_offset"] == "UTC+5:30" and india["difference"].endswith("3 Stunden und 30 Minuten später als bei dir.")
# anderes Datum als bei dir
now[0] = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)
assert service.get_world_time("Tokio").data["date"] == "Freitag, 23.10.2026" and service.get_world_time("Tokio").data["time"] == "05:00"
# Sommerzeit-Wechsel: Europa stellt am 25.10. zurueck, die USA erst am 1.11. (New York als Beispiel)
now[0] = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
assert service.get_world_time("London").data["difference_minutes"] == -60        # London BST, Berlin CEST
assert service.get_world_time("New York").data["difference_minutes"] == -360     # EDT / CEST
now[0] = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
assert service.get_world_time("London").data["time"] == "12:00" and service.get_world_time("London").data["difference_minutes"] == -60
assert service.get_world_time("New York").data["difference_minutes"] == -300     # EDT / CET: nur 5 Stunden
now[0] = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
newyork = service.get_world_time("New York").data                                # beide in Winterzeit
assert newyork["utc_offset"] == "UTC-5" and newyork["difference_minutes"] == -360
now[0] = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)

# 3) Zeitzone direkt genannt: keine Ortssuche
located.clear()
assert service.get_world_time("Europe/Stockholm").data["place"] == "Europe/Stockholm"
assert service.get_world_time("Europe/Stockholm").data["difference_minutes"] == 0
assert service.get_world_time("UTC").data["time"] == "12:00" and service.get_world_time("GMT").success
assert service.get_world_time("America/Argentina/Buenos_Aires").data["time"] == "09:00"
assert located == []

# 4) Fehler als Saetze
assert "Für welchen Ort" in service.get_world_time("").error and "Für welchen Ort" in service.get_world_time("heimat").error
assert "Für welchen Ort" in service.get_world_time(None).error and "Für welchen Ort" in service.get_world_time(5).error
assert service.get_world_time("Gibtsnicht").error == "Den Ort „Gibtsnicht“ habe ich nicht gefunden."
assert "kenne ich keine Zeitzone" in service.get_world_time("Unsinn").error and "tzdata" in service.get_world_time("ohnezone").error
state["fail"] = True
assert service.get_world_time("Edmonton").error == "Die Ortssuche ist gerade nicht erreichbar: Keine Verbindung zum Dienst."
assert service.get_world_time("Europe/Berlin").success, "direkte Zeitzone geht auch ohne Netz"
state["fail"] = False

# 5) Zeitzonennamen sind keine Dateipfade: nur feste Schreibweise, sonst Ortssuche
for sneaky in ("../../etc/passwd", "Europe/../../x", "/etc/passwd", "Europe\\Berlin", "europe/berlin ", "Europe/Berlin\n", "A/" + "b" * 200, "Etc/GMT+99999"):
    assert load_zone(sneaky) is None, sneaky
assert load_zone("Europe/Berlin") is not None and load_zone("UTC") is not None and load_zone("Etc/GMT+5") is not None
assert load_zone(None) is None and load_zone("Mars/Olympus") is None

# 6) Mit der echten Ortssuche (Open-Meteo-Antwort mit Zeitzone) und Zwischenspeicher
fetched = []


def fake_fetch(url, hosts, params=None, **kwargs):
    fetched.append(params["name"])
    return {"results": [{"name": "Växjö", "admin1": "Kronoberg", "country": "Schweden", "latitude": 56.88, "longitude": 14.81,
                         "timezone": "Europe/Stockholm"}]}


weather_tool.set_default_service(WeatherService(fetch=fake_fetch))
real = WorldTimeService(clock=lambda: now[0], local_zone=BERLIN)
r = real.get_world_time("Vaxjo")
assert r.success and r.data["place"] == "Växjö, Kronoberg, Schweden" and r.data["timezone"] == "Europe/Stockholm" and r.data["time"] == "14:00"
real.get_world_time("vaxjo")
assert fetched == ["Vaxjo"], "gleicher Ort: aus dem Zwischenspeicher"
assert weather_tool.default_service().locate("   ") is None and weather_tool.default_service().locate(5) is None

# 7) Einbindung
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("GET_WORLD_TIME")
assert [a.name for a in task.actions] == ["get_world_time"] and risk.task_risk(task) == "safe"
assert abilities.ability_of("GET_WORLD_TIME").id == "worldtime"
world_time_tool.set_default_service(service)
done = action_executor.execute_action(Action("get_world_time", {"place": "Tokio"}))
assert done.success and done.data["time"] == "21:00"
assert not action_executor.execute_action(Action("get_world_time", {})).success
settings = SettingsManager(Path(tempfile.mkdtemp()) / "s.json")
assert abilities.task_enabled("GET_WORLD_TIME", settings)
settings.set("abilities", "worldtime", False)
assert not abilities.task_enabled("GET_WORLD_TIME", settings)
import guest
assert "GET_WORLD_TIME" not in guest.GUEST_TASKS

print("ALL TESTS PASSED")
