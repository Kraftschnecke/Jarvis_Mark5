"""PC aus Sicht des Servers (S6, G2): Daten kommen vom Agent, bewertet wird auf dem Server, aus = klare Meldung."""
import sys
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_hub
import remote_pc
from tools import pc_health, system_status_tool

SNAP = {"now": {"cpu_percent": 5.0, "ram_percent": 95.0, "ram_used_gb": 30.0, "ram_total_gb": 32.0, "disk_percent": 50.0, "disk_used_gb": 400.0,
                "disk_total_gb": 800.0, "battery": None, "network": {"down_kb_s": 0.0, "up_kb_s": 0.0}, "uptime_seconds": 10},
        "drives": [], "programs": {"ram": [{"name": "chrome.exe", "mb": 20000, "count": 30}], "cpu": [], "disk": []}, "autostart": ["Steam"]}
FACTS = {"os": "Windows 11", "os_version": "10", "architecture": "AMD64", "cpu_name": "CPU", "cpu_cores": 8, "cpu_threads": 16, "cpu_max_mhz": 3800,
         "ram_total_gb": 32.0, "drives": [], "computer_name": "PC", "python_version": "3.12", "has_battery": False}
TOP = [{"name": "chrome.exe", "ram_mb": 20000, "count": 30}]


class FakeHub:
    def __init__(self):
        self.calls = []
        self.replies = {"pc.snapshot": SNAP, "pc.facts": FACTS, "pc.top": TOP, "pc.performance": SNAP["now"]}
        self.offline = False

    def request(self, command, args=None, **kw):
        self.calls.append((command, args))
        if self.offline:
            raise device_hub.DeviceOffline("Der PC ist gerade nicht erreichbar.")
        return self.replies[command]


hub = FakeHub()
pc = remote_pc.RemotePc(hub)

# 1) Jeder Aufruf geht als der richtige Auftrag an den PC
assert pc.monitor.sample() == SNAP["now"] and hub.calls[-1] == ("pc.performance", {"fresh": False})
assert pc.monitor.sample(fresh_cpu=True) == SNAP["now"] and hub.calls[-1] == ("pc.performance", {"fresh": True})
assert pc.monitor.sample(fresh_cpu=1) and hub.calls[-1] == ("pc.performance", {"fresh": True})
assert pc.facts() == FACTS and hub.calls[-1] == ("pc.facts", None)
assert pc.top_processes() == TOP and hub.calls[-1] == ("pc.top", None)
assert pc.health.snapshot() == SNAP and hub.calls[-1] == ("pc.snapshot", None)

# 2) Die Bewertung rechnet der Server aus den Messwerten: RAM 95 % ergibt eine Warnung, auch wenn der Agent etwas anderes behauptet
hub.replies["pc.snapshot"] = dict(SNAP, assessment={"level": "ok", "headline": "Alles super", "findings": []})
report = pc.health.report()
assert report["assessment"] == pc_health.assess(SNAP) and report["assessment"]["level"] in ("warn", "bad")
assert any(f["id"] == "ram" for f in report["assessment"]["findings"]) and "Alles super" not in str(report["assessment"])
for key in ("now", "drives", "programs", "autostart"):
    assert report[key] == SNAP[key]

# 3) PC aus: jeder Aufruf wirft DeviceOffline mit der klaren Meldung
hub.offline = True
for call in (pc.monitor.sample, pc.facts, pc.top_processes, pc.health.snapshot, pc.health.report):
    try:
        call()
        raise AssertionError(call)
    except device_hub.DeviceOffline as error:
        assert "nicht erreichbar" in str(error)
hub.offline = False

# 4) install(): Fenster, Chat und Warnungen nutzen jetzt den PC; die Vorgabe ist danach wieder frei
server = types.SimpleNamespace(hub=hub, monitor="lokal", health="lokal")
try:
    installed = remote_pc.install(server)
    assert server.monitor is installed.monitor and server.health is installed.health
    assert pc_health.default_health() is installed.health and system_status_tool.default_monitor() is installed.monitor
    assert system_status_tool.current_facts() == FACTS and system_status_tool.current_top_processes() == TOP
    # der Chat ("Wie viel RAM ist frei?") bekommt die Werte vom PC samt Bewertung, nicht die des Servers
    hub.calls.clear()
    result = system_status_tool.get_system_info()
    assert result.success and result.data["computer_name"] == "PC" and result.data["now"] == SNAP["now"]
    assert result.data["top_programs"] == TOP and result.data["pc_lage"]["level"] in ("warn", "bad") and result.data["autostart_count"] == 1
    assert ("pc.performance", {"fresh": True}) in hub.calls and ("pc.facts", None) in hub.calls
    # PC aus: der Chat sagt es ehrlich, statt die Werte des Servers zu zeigen
    hub.offline = True
    result = system_status_tool.get_system_info()
    assert not result.success and "nicht erreichbar" in result.error
    hub.offline = False
finally:
    system_status_tool.set_remote(None)
    system_status_tool.set_default_monitor(None)
    pc_health.set_default_health(None)
assert system_status_tool._remote is None and isinstance(system_status_tool.current_facts(), dict) and "computer_name" in system_status_tool.current_facts()

print("ALL TESTS PASSED")
