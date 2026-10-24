"""PC-Fakten und Leistungsdaten (Mark 5, Step 2.8): mit einem erfundenen psutil getestet, damit die Werte bekannt sind."""

import sys
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
try:
    import psutil  # noqa: F401
except ImportError:
    sys.modules["psutil"] = types.ModuleType("psutil")

from tools import system_status_tool as st

GB = 1024 ** 3


class Fake:
    """Nachbau der psutil-Teile, die wir nutzen."""

    def __init__(self):
        self.cpu = 25.0
        self.cpu_calls = []
        self.mem = types.SimpleNamespace(total=32 * GB, available=19 * GB, percent=40.6)
        self.net = types.SimpleNamespace(bytes_recv=0, bytes_sent=0)
        self.battery = types.SimpleNamespace(percent=80.0, power_plugged=True)
        self.parts = [types.SimpleNamespace(mountpoint="C:\\", fstype="NTFS", opts="rw,fixed"),
                      types.SimpleNamespace(mountpoint="D:\\", fstype="", opts="cdrom"),
                      types.SimpleNamespace(mountpoint="E:\\", fstype="NTFS", opts="rw,fixed"),
                      types.SimpleNamespace(mountpoint="F:\\", fstype="NTFS", opts="rw,fixed")]
        self.procs = []

    def cpu_percent(self, interval=None):
        self.cpu_calls.append(interval)
        return self.cpu

    def cpu_count(self, logical=True):
        return 16 if logical else 8

    def cpu_freq(self):
        return types.SimpleNamespace(max=4700.0, current=3000.0)

    def virtual_memory(self):
        return self.mem

    def disk_partitions(self, all=False):
        return self.parts

    def disk_usage(self, path):
        if path.startswith("F"):
            raise PermissionError("Kartenleser leer")
        return types.SimpleNamespace(total=500 * GB, used=380 * GB, free=120 * GB, percent=76.0)

    def sensors_battery(self):
        return self.battery

    def net_io_counters(self):
        return self.net

    def boot_time(self):
        import time
        return time.time() - 3 * 3600 - 12 * 60

    def process_iter(self, attrs):
        for name, rss in self.procs:
            yield types.SimpleNamespace(info={"name": name, "memory_info": types.SimpleNamespace(rss=rss)})


ps = Fake()
now = [100.0]
monitor = st.PerformanceMonitor(ps, clock=lambda: now[0])
assert ps.cpu_calls == [None], "CPU wird beim Start einmal angewaermt"

# 1) Messung: Werte, Rundung, Netz beim ersten Mal 0
s = monitor.sample()
assert s["cpu_percent"] == 25.0 and s["ram_percent"] == 40.6 and s["ram_used_gb"] == 13.0 and s["ram_total_gb"] == 32.0
assert s["disk_percent"] == 76.0 and s["disk_used_gb"] == 380.0 and s["disk_total_gb"] == 500.0
assert s["battery"] == {"percent": 80.0, "plugged": True}
assert s["network"] == {"down_kb_s": 0.0, "up_kb_s": 0.0}
assert 3 * 3600 + 11 * 60 <= s["uptime_seconds"] <= 3 * 3600 + 14 * 60

# 2) Abfragen im Abstand unter einer Sekunde bekommen den letzten Wert, ohne neu zu messen
ps.cpu = 99.0
now[0] += 0.5
assert monitor.sample()["cpu_percent"] == 25.0 and len(ps.cpu_calls) == 2

# 3) Nach 2 s: neue CPU, Netz-Tempo aus dem Unterschied (1 MiB runter, 512 KiB hoch in 2 s)
now[0] += 1.5
ps.net = types.SimpleNamespace(bytes_recv=1024 * 1024, bytes_sent=512 * 1024)
s = monitor.sample()
assert s["cpu_percent"] == 99.0 and s["network"] == {"down_kb_s": 512.0, "up_kb_s": 256.0}

# 4) Zaehler zurueckgesetzt (Neustart des Adapters): nie negatives Tempo
now[0] += 2
ps.net = types.SimpleNamespace(bytes_recv=10, bytes_sent=10)
assert monitor.sample()["network"] == {"down_kb_s": 0.0, "up_kb_s": 0.0}

# 5) Ohne Akku, ungueltige Werte begrenzt, kaputte Teile werfen nicht
ps.battery = None
ps.cpu = 250.0
ps.mem.percent = -5
now[0] += 2
s = monitor.sample()
assert s["battery"] is None and s["cpu_percent"] == 100.0 and s["ram_percent"] == 0.0
ps.net_io_counters = lambda: None
ps.disk_usage = lambda path: (_ for _ in ()).throw(OSError("weg"))
ps.boot_time = lambda: (_ for _ in ()).throw(OSError("weg"))
now[0] += 2
s = monitor.sample()
assert s["network"] == {"down_kb_s": 0.0, "up_kb_s": 0.0} and s["disk_percent"] == 0.0 and s["uptime_seconds"] is None

# 6) fresh_cpu misst 0,3 s lang und ignoriert den Zwischenspeicher
ps2 = Fake()
fresh = st.PerformanceMonitor(ps2, clock=lambda: 5.0)
fresh.sample()
fresh.sample(fresh_cpu=True)
assert ps2.cpu_calls == [None, None, 0.3]

# 7) Fakten: Kerne, RAM, Laufwerke (CD ohne Dateisystem und gesperrtes Laufwerk uebersprungen)
ps3 = Fake()
f = st.facts(ps3)
assert f["cpu_cores"] == 8 and f["cpu_threads"] == 16 and f["cpu_max_mhz"] == 4700 and f["ram_total_gb"] == 32.0
assert [d["name"] for d in f["drives"]] == ["C:\\", "E:\\"]
assert f["drives"][0] == {"name": "C:\\", "total_gb": 500.0, "free_gb": 120.0, "used_percent": 76.0}
assert f["has_battery"] is True and isinstance(f["cpu_name"], str) and f["cpu_name"]
ps3.cpu_freq = lambda: None
assert st.facts(ps3)["cpu_max_mhz"] is None
ps3.parts = [types.SimpleNamespace(mountpoint=f"{c}:\\", fstype="NTFS", opts="") for c in "CDEFGHIJ"]
ps3.disk_usage = lambda path: types.SimpleNamespace(total=GB // 2, used=0, free=GB // 2, percent=0.0)
assert st.facts(ps3)["drives"] == [], "unter 1 GB wird uebersprungen"
ps3.disk_usage = lambda path: types.SimpleNamespace(total=GB, used=0, free=GB, percent=0.0)
assert len(st.facts(ps3)["drives"]) == st.MAX_DRIVES
ps3.disk_partitions = lambda all=False: (_ for _ in ()).throw(OSError("weg"))
assert st.facts(ps3)["drives"] == []

# 8) Groesste Programme: gleiche Namen addiert, sortiert, nur Name und MB (keine Pfade), maximal 5
ps4 = Fake()
ps4.procs = [("chrome.exe", 400 * 1024 ** 2), ("chrome.exe", 600 * 1024 ** 2), ("code.exe", 700 * 1024 ** 2),
             ("a.exe", 10), ("b.exe", 20), ("c.exe", 30), ("d.exe", 40), (None, 5 * GB), ("x" * 100 + ".exe", 1)]
top = st.top_processes(ps4)
assert top[0] == {"name": "chrome.exe", "ram_mb": 1000, "count": 2} and top[1]["name"] == "code.exe"
assert len(top) == 5 and all(set(t) == {"name", "ram_mb", "count"} for t in top)
ps4.process_iter = lambda attrs: (_ for _ in ()).throw(OSError("weg"))
assert st.top_processes(ps4) == []

# 9) Chat-Ergebnis: alles zusammen; Fehler werden ein sauberer Fehlertext
st.set_default_monitor(monitor)
result = st.get_system_info()
assert result.success and {"cpu_name", "ram_total_gb", "drives", "now", "top_programs"} <= set(result.data)
assert "cpu_percent" in result.data["now"]
import json
json.dumps(result.data)       # muss als JSON an die KI gehen koennen
broken = types.SimpleNamespace(sample=lambda fresh_cpu=False: (_ for _ in ()).throw(RuntimeError("kaputt")))
st.set_default_monitor(broken)
result = st.get_system_info()
assert not result.success and "Systemdaten" in result.error
st.set_default_monitor(None)

# 10) Verdrahtung: alte Importadresse, Aufgabe, Risiko
import risk
from action import Action
from tools import system_info_tool
assert system_info_tool.get_system_info is st.get_system_info
assert risk.action_risk(Action("get_system_info", {})) == risk.SAFE

print("ALL TESTS PASSED")
