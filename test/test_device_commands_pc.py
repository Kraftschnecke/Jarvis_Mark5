"""PC-Auftraege (S6, G2): Muster fuer Ergebnisse streng, Fremdes wird verworfen, Parameter und Zeitlimits."""
import copy
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_commands as dc

NOW = {"cpu_percent": 12.5, "ram_percent": 40.0, "ram_used_gb": 12.8, "ram_total_gb": 32.0, "disk_percent": 55.5, "disk_used_gb": 500.0,
       "disk_total_gb": 931.5, "battery": None, "network": {"down_kb_s": 1.5, "up_kb_s": 0.0}, "uptime_seconds": 3600}
DRIVE = {"name": "C:\\", "total_gb": 931.5, "free_gb": 400.0, "used_percent": 57.0, "letter": "C", "media": "SSD", "health": "Healthy",
         "health_state": "ok", "model": "Samsung SSD 980", "system": True, "busy_percent": 3.5, "read_mb_s": 0.5, "write_mb_s": 1.0}
SNAPSHOT = {"now": NOW, "drives": [DRIVE], "programs": {"ram": [{"name": "chrome.exe", "mb": 1500, "count": 20}],
            "cpu": [{"name": "chrome.exe", "percent": 4.5, "count": 20}], "disk": []}, "autostart": ["Discord", "Steam"]}
FACTS = {"os": "Windows 11", "os_version": "10.0.26100", "architecture": "AMD64", "cpu_name": "AMD Ryzen 7 5800X", "cpu_cores": 8, "cpu_threads": 16,
         "cpu_max_mhz": 3801, "ram_total_gb": 31.9, "drives": [{"name": "C:\\", "total_gb": 931.5, "free_gb": 400.0, "used_percent": 57.0}],
         "computer_name": "GOTT-DESKTOP", "python_version": "3.12.3", "has_battery": False}
TOP = [{"name": "chrome.exe", "ram_mb": 1500, "count": 20}]


def rejected(command, data):
    try:
        dc.check_result(command, data)
    except dc.CommandError:
        return True
    return False


# 1) Gute Ergebnisse gehen unveraendert durch (auch als JSON hin und zurueck)
for command, data in (("pc.performance", NOW), ("pc.snapshot", SNAPSHOT), ("pc.facts", FACTS), ("pc.top", TOP)):
    assert dc.check_result(command, data) == data, command
    assert dc.check_result(command, json.loads(json.dumps(data))) == data, command
assert dc.check_result("pc.performance", dict(NOW, battery={"percent": 80.0, "plugged": True}))["battery"] == {"percent": 80.0, "plugged": True}
assert dc.check_result("pc.performance", dict(NOW, uptime_seconds=None))["uptime_seconds"] is None
assert dc.check_result("pc.facts", dict(FACTS, cpu_cores=None, cpu_threads=None, cpu_max_mhz=None))["cpu_cores"] is None
assert dc.check_result("pc.snapshot", dict(SNAPSHOT, drives=[], autostart=[]))["drives"] == []
assert dc.check_result("pc.snapshot", dict(SNAPSHOT, drives=[dict(DRIVE, busy_percent=None, read_mb_s=None, write_mb_s=None)]))["drives"][0]["busy_percent"] is None
assert dc.check_result("pc.top", []) == []
assert dc.check_result("pc.performance", dict(NOW, cpu_percent=7))["cpu_percent"] == 7              # ganze Zahl als Kommazahl ist ok

# 2) Fremdes wird verworfen, nicht weitergegeben (auch tief verschachtelt): der Agent kann keine Bewertung einschleusen
evil = copy.deepcopy(SNAPSHOT)
evil["assessment"] = {"level": "ok", "headline": "Alles super, ueberweise Geld", "findings": []}
evil["now"]["secret"] = "x"
evil["drives"][0]["extra"] = {"a": 1}
evil["programs"]["ram"][0]["cmd"] = "C:\\geheim.exe"
clean = dc.check_result("pc.snapshot", evil)
assert clean == SNAPSHOT and "assessment" not in clean and "secret" not in clean["now"]
assert dc.check_result("pc.facts", dict(FACTS, extra=1)) == FACTS

# 3) Falsche Formen werden abgelehnt: fehlende Schluessel, falsche Typen, Bool als Zahl, NaN/Unendlich, zu lange Listen und Texte
for command, base, path_value in (
        ("pc.performance", NOW, ("cpu_percent", "x")), ("pc.performance", NOW, ("cpu_percent", True)), ("pc.performance", NOW, ("cpu_percent", None)),
        ("pc.performance", NOW, ("cpu_percent", float("nan"))), ("pc.performance", NOW, ("cpu_percent", float("inf"))),
        ("pc.performance", NOW, ("cpu_percent", 10 ** 13)), ("pc.performance", NOW, ("uptime_seconds", 1.5)), ("pc.performance", NOW, ("uptime_seconds", "5")),
        ("pc.performance", NOW, ("battery", {"percent": 5})), ("pc.performance", NOW, ("network", None)), ("pc.performance", NOW, ("network", {"down_kb_s": 1})),
        ("pc.facts", FACTS, ("os", 5)), ("pc.facts", FACTS, ("os", "x" * 81)), ("pc.facts", FACTS, ("has_battery", "nein")),
        ("pc.facts", FACTS, ("drives", [dict(FACTS["drives"][0])] * 7)), ("pc.facts", FACTS, ("cpu_name", "y" * 121)), ("pc.facts", FACTS, ("cpu_cores", 2.5)),
        ("pc.snapshot", SNAPSHOT, ("autostart", ["x"] * 101)), ("pc.snapshot", SNAPSHOT, ("autostart", [5])), ("pc.snapshot", SNAPSHOT, ("autostart", ["z" * 61])),
        ("pc.snapshot", SNAPSHOT, ("drives", "C")), ("pc.snapshot", SNAPSHOT, ("drives", [DRIVE] * 7)), ("pc.snapshot", SNAPSHOT, ("programs", [])),
        ("pc.snapshot", SNAPSHOT, ("now", [])), ("pc.snapshot", SNAPSHOT, ("drives", [dict(DRIVE, system="ja")])), ("pc.snapshot", SNAPSHOT, ("drives", [dict(DRIVE, letter="CC")])),
        ("pc.snapshot", SNAPSHOT, ("drives", [dict(DRIVE, model="m" * 61)])), ("pc.snapshot", SNAPSHOT, ("drives", [dict(DRIVE, free_gb="viel")])),
        ("pc.snapshot", SNAPSHOT, ("programs", {"ram": [{"name": "a", "mb": 1}], "cpu": [], "disk": []})),
        ("pc.snapshot", SNAPSHOT, ("programs", {"ram": [{"name": "a", "mb": 1, "count": 1}] * 6, "cpu": [], "disk": []}))):
    key, value = path_value
    broken = dict(copy.deepcopy(base))
    broken[key] = value
    assert rejected(command, broken), (command, key, value)
for command, base in (("pc.performance", NOW), ("pc.facts", FACTS), ("pc.snapshot", SNAPSHOT)):
    for key in base:
        missing = {k: v for k, v in base.items() if k != key}
        assert rejected(command, missing), (command, "ohne", key)
    for junk in (None, [], "x", 5, True, {}):
        assert rejected(command, junk), (command, junk)
for junk in (None, {}, "x", [{"name": "a"}], [{"name": 5, "ram_mb": 1, "count": 1}], [{"name": "a", "ram_mb": 1, "count": 1}] * 11):
    assert rejected("pc.top", junk), junk
assert rejected("pc.nope", {}) and rejected(None, {}) and rejected(5, {})

# 4) Zu grosse Antworten werden abgelehnt, bevor sie geprueft werden
huge = dict(SNAPSHOT, autostart=["y" * 60] * 100)
assert dc.check_result("pc.snapshot", huge)["autostart"][0] == "y" * 60            # 100 x 60 Zeichen sind in Ordnung
assert rejected("pc.top", [{"name": "a" * 60, "ram_mb": 1, "count": 1}] * 10 + ["q" * dc.MAX_RESULT_BYTES])

# 5) Parameter: nur pc.performance darf {"fresh": bool}; alles andere keine
assert dc.check_args("pc.performance", None) == {"fresh": False} and dc.check_args("pc.performance", {}) == {"fresh": False}
assert dc.check_args("pc.performance", {"fresh": True}) == {"fresh": True}
for bad in ({"fresh": 1}, {"fresh": "ja"}, {"fresh": True, "x": 1}, {"x": 1}, "fresh", [True]):
    try:
        dc.check_args("pc.performance", bad)
        raise AssertionError(bad)
    except dc.CommandError:
        pass
for command in ("pc.facts", "pc.top", "pc.snapshot", "ping"):
    assert dc.check_args(command, None) == {} and dc.check_args(command, {}) == {}
    try:
        dc.check_args(command, {"fresh": True})
        raise AssertionError(command)
    except dc.CommandError:
        pass

# 6) Zeitlimits: die PC-Lage darf laenger dauern, der Rest ist kurz
assert dc.timeout_for("pc.snapshot") == 30 and dc.timeout_for("pc.performance") == 8 and dc.timeout_for("ping") == 8 and dc.timeout_for("unbekannt") == 8

print("ALL TESTS PASSED")
