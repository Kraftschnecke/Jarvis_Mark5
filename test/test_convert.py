"""Umrechnen (Mark 5, Step 2.3): Einheiten und EZB-Kurse, ohne Internet getestet."""

import sys
import tempfile
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
from tools import calc_tool, convert_tool


from net_fetch import NetError
from tools.convert_tool import ConvertService, parse_rates, parse_value, format_number
from decimal import Decimal

XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<gesmes:subject>Reference rates</gesmes:subject><gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
<Cube><Cube time="2026-10-21"><Cube currency="USD" rate="1.1634"/><Cube currency="JPY" rate="180.50"/><Cube currency="GBP" rate="0.8700"/>
<Cube currency="CHF" rate="0.9300"/><Cube currency="PLN" rate="4.2000"/><Cube currency="SEK" rate="11.0000"/></Cube></Cube></gesmes:Envelope>"""

calls, state, clock = [], {"xml": XML, "fail": False}, [1000.0]


def fake_fetch(url, hosts, **kwargs):
    calls.append((url, hosts))
    if state["fail"]:
        raise NetError("Keine Verbindung zum Dienst.")
    return state["xml"]


service = ConvertService(fetch=fake_fetch, clock=lambda: clock[0])


def ok(value, a, b):
    r = service.convert(value, a, b)
    assert r.success, (value, a, b, r.error)
    return r.data


def fails(value, a, b):
    r = service.convert(value, a, b)
    assert not r.success and r.error, (value, a, b)
    return r.error


# 1) Einheiten (offline: dabei wird nichts abgerufen)
assert ok("100", "km", "mi")["result"] == "62.13711922"
assert ok("1", "Meile", "Kilometer")["result"] == "1.609344"
assert ok("1", "zoll", "mm")["result"] == "25.4" and ok("6", "fuß", "cm")["result"] == "182.88"
assert ok("1", "pound", "g")["result"] == "453.59237" and ok("1", "pfund", "g")["result"] == "500"
assert ok("2", "gallone", "liter")["result"] == "7.570823568"
assert ok("100", "km/h", "mph")["result"] == "62.13711922" and ok("10", "knoten", "km/h")["result"] == "18.52"
assert ok("10", "hektar", "qm")["result"] == "100000"
assert ok("1", "gb", "mb")["result"] == "1000" and ok("1", "GiB", "MiB")["result"] == "1024" and ok("8", "bit", "byte")["result"] == "1"
assert ok("90", "min", "h")["result"] == "1.5" and ok("1", "Wochen", "Tage")["result"] == "7" and ok("2", "h", "s")["result"] == "7200"
assert ok("1", "m³", "l")["result"] == "1000" and ok("250", "ml", "cl")["result"] == "25"
assert calls == [], "Einheiten brauchen kein Internet"

# 2) Temperatur (nicht nur Faktor, auch Versatz)
assert ok("0", "celsius", "fahrenheit")["result"] == "32" and ok("100", "°C", "°F")["result"] == "212"
assert ok("36,6", "celsius", "fahrenheit")["result"] == "97.88" and ok("98.6", "F", "C")["result"] == "37"
assert ok("0", "c", "k")["result"] == "273.15" and ok("-40", "c", "f")["result"] == "-40"
assert "Nullpunkt" in fails("-300", "c", "f") and "Nullpunkt" in fails("-1", "k", "c")

# 3) Schreibweisen der Zahl und der Namen
assert ok("1,5", "km", "m")["result"] == "1500" and ok(" 1 000 ", "m", "km")["result"] == "1" and ok(5, "km", "m")["result"] == "5000"
assert ok(2.5, "KILOMETER", " Meter. ")["result"] == "2500" and ok("1e3", "m", "km")["result"] == "1"
assert ok("0.0000001", "km", "m")["result"] == "0.0001"
for bad in ("abc", "", "1;2", "1/2", "NaN", "inf", "--1", "1e9999", "9" * 20, None, True, [], {}):
    assert fails(bad, "km", "m"), bad

# 4) Passt nicht zusammen / unbekannt: klare Saetze
assert fails("1", "km", "liter") == "Das passt nicht zusammen: „km“ ist eine Länge, „liter“ ist ein Volumen."
assert "ein Gewicht" in fails("1", "kg", "euro") and "eine Währung" in fails("1", "kg", "euro")
assert fails("1", "foo", "km") == "Die Einheit „foo“ kenne ich nicht."
assert fails("1", "km", "bar") == "Die Einheit „bar“ kenne ich nicht."
assert "Von welcher Einheit" in fails("1", "", "km") and "Von welcher Einheit" in fails("1", "km", None)
assert ok("1", "m", "m")["result"] == "1", "gleiche Einheit ist erlaubt"

# 5) Waehrungen: EZB-Kurse, Zwischenspeicher, Rundung auf Cent
data = ok("100", "usd", "eur")
assert data == {"category": "currency", "value": "100", "from": "USD", "result": "85.95", "to": "EUR",
                "note": "EZB-Referenzkurs vom 2026-10-21 (kein Handelskurs)"}, data
assert len(calls) == 1 and calls[0] == (convert_tool.ECB_URL, convert_tool.ECB_HOSTS)
assert ok("100", "Euro", "Dollar")["result"] == "116.34" and ok("1000", "eur", "jpy")["result"] == "180500.00"
assert ok("100", "USD", "GBP")["result"] == "74.78"            # ueber Euro: 100 / 1.1634 * 0.87
assert ok("50", "pfund", "euro")["from"] == "GBP" and ok("50", "pfund", "euro")["result"] == "57.47", "Pfund: Waehrung, wenn die Gegenseite eine ist"
assert ok("500", "pfund", "kg")["result"] == "250", "Pfund: Gewicht, wenn die Gegenseite eines ist"
assert ok("10", "franken", "zloty")["result"] == "45.16" and ok("10", "sek", "eur")["result"] == "0.91"
assert ok("1", "eur", "eur")["result"] == "1.00"
assert len(calls) == 1, "eine Stunde lang aus dem Zwischenspeicher"
assert "keinen EZB-Referenzkurs" in fails("1", "isk", "eur"), "bekannte Waehrung ohne Kurs in der Tabelle"
assert "kenne ich nicht" in fails("1", "eur", "xyz")

# 6) Abruf nach einer Stunde neu; faellt er aus: letzter Kurs mit Hinweis; ohne Kurs: klarer Fehler
clock[0] += convert_tool.RATES_CACHE_SECONDS + 1
state["xml"] = XML.replace('rate="1.1634"', 'rate="1.2000"').replace("2026-10-21", "2026-10-22")
data = ok("120", "usd", "eur")
assert data["result"] == "100.00" and "2026-10-22" in data["note"] and len(calls) == 2
clock[0] += convert_tool.RATES_CACHE_SECONDS + 1
state["fail"] = True
data = ok("120", "usd", "eur")
assert data["result"] == "100.00" and "nicht abrufbar" in data["note"] and "2026-10-22" in data["note"]
fresh = ConvertService(fetch=fake_fetch, clock=lambda: clock[0])
error = fresh.convert("1", "usd", "eur")
assert not error.success and error.error == "Die Wechselkurse sind gerade nicht abrufbar: Keine Verbindung zum Dienst."
assert fresh.convert("1", "km", "m").success, "Einheiten gehen auch ohne Internet"
state["fail"] = False

# 7) Kaputte Kurstabellen werden abgelehnt, nichts wird gespeichert
for bad_xml in ("", "<x>", "<?xml version='1.0'?><!DOCTYPE a [<!ENTITY e 'x'>]><Cube time='2026-10-22'/>", "<Cube/>",
                XML.replace('time="2026-10-21"', 'time="gestern"'),
                XML.replace('rate="1.1634"', 'rate="-3"').replace("180.50", "abc").replace("0.8700", "1e999").replace("0.9300", "0").replace("4.2000", "NaN").replace("11.0000", "x"), None):
    try:
        parse_rates(bad_xml)
        raise AssertionError(f"haette abgelehnt werden muessen: {bad_xml!r}")
    except NetError:
        pass
broken = ConvertService(fetch=lambda url, hosts, **k: "<Cube/>", clock=lambda: 0)
assert not broken.convert("1", "usd", "eur").success and broken._rates is None

# 8) Einbindung: Aufgabe, Risiko, Executor, Faehigkeit
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("CONVERT")
assert [a.name for a in task.actions] == ["convert"] and set(task.actions[0].parameters) == {"value", "from_unit", "to_unit"}
assert risk.task_risk(task) == "safe" and abilities.ability_of("CONVERT").id == "convert"
convert_tool.set_default_service(service)
done = action_executor.execute_action(Action("convert", {"value": "100", "from_unit": "km", "to_unit": "mi"}))
assert done.success and done.data["result"] == "62.13711922"
assert not action_executor.execute_action(Action("convert", {})).success, "fehlende Parameter: Fehlersatz statt Absturz"
settings = SettingsManager(Path(tempfile.mkdtemp()) / "s.json")
assert abilities.task_enabled("CONVERT", settings)
settings.set("abilities", "convert", False)
assert not abilities.task_enabled("CONVERT", settings)
import guest
assert "CONVERT" not in guest.GUEST_TASKS

# 9) Hilfsfunktionen
assert parse_value("1,5") == Decimal("1.5") and parse_value(3) == 3 and parse_value("+2") == 2
assert format_number(Decimal("1234.5678901234")) == "1234.56789"
assert format_number(Decimal("0")) == "0" and format_number(Decimal("1E+3")) == "1000" and format_number(Decimal("-0.5")) == "-0.5"

print("ALL TESTS PASSED")
