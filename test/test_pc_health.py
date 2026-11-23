"""PC-Lage (Mark 5): Laufwerks-Zuordnung (mit den echten Werten von Moritz' PC), Messung mit erfundenem psutil, Bewertung."""

import json
import sys
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
try:
    import psutil  # noqa: F401
except ImportError:
    sys.modules["psutil"] = types.ModuleType("psutil")

from tools import pc_health as ph
from tools import system_status_tool as sst

GB = 1024 ** 3
NS = types.SimpleNamespace

# 1) Zuordnung mit den echten Werten: Partition D liegt auf Disk 2, die Physical-Disks heissen aber 0 und 1 -> Zuordnung ueber Name/Groesse
REAL = {
    "disks": [{"number": 1, "name": "INTEL SSDPEKKW256G7", "serial": "0000_0000_0100_0000_E4D2_5C0A_1B2C_3D4E.", "size": 256060514304},
              {"number": 2, "name": "WDC WD10EZEX-21WN4A0", "serial": "WD-WCC6Y1234567", "size": 1000204886016}],
    "physical": [{"name": "INTEL SSDPEKKW256G7", "serial": "E4D25C0A1B2C3D4E", "media": "SSD", "health": "Healthy", "size": 256060514304},
                 {"name": "WDC WD10EZEX-21WN4A0", "serial": "WD-WCC6Y1234567", "media": "HDD", "health": "Healthy", "size": 1000204886016}],
    "partitions": [{"letter": "C", "disk": 1}, {"letter": "D", "disk": 2}],
}
m = ph.map_drives(REAL)
assert m["C"] == {"media": "SSD", "health": "Healthy", "health_state": "ok", "model": "INTEL SSDPEKKW256G7", "disk_number": 1}, m["C"]
assert m["D"] == {"media": "HDD", "health": "Healthy", "health_state": "ok", "model": "WDC WD10EZEX-21WN4A0", "disk_number": 2}, m["D"]
# die Nummer allein waere falsch gewesen: Physical-Disk "2" gibt es nicht
# ohne Seriennummern: Name; gleiche Namen, aber verschiedene Groessen: Groesse; sonst unbekannt statt falsch
noserial = json.loads(json.dumps(REAL))
for d in noserial["disks"] + noserial["physical"]:
    d["serial"] = ""
assert ph.map_drives(noserial)["D"]["media"] == "HDD" and ph.map_drives(noserial)["C"]["media"] == "SSD"
same = {"disks": [{"number": 0, "name": "Disk X", "serial": "", "size": 500}, {"number": 1, "name": "Disk X", "serial": "", "size": 1000}],
        "physical": [{"name": "Disk X", "serial": "", "media": "SSD", "health": "Healthy", "size": 500}, {"name": "Disk X", "serial": "", "media": "HDD", "health": "Warning", "size": 1000}],
        "partitions": [{"letter": "e", "disk": 0}, {"letter": "F", "disk": 1}]}
sm = ph.map_drives(same)
assert sm["E"]["media"] == "SSD" and sm["F"]["media"] == "HDD" and sm["F"]["health_state"] == "warning", sm      # Buchstabe gross
same["physical"][1]["size"] = 500
sm = ph.map_drives(same)
assert sm["E"]["media"] == "unbekannt" and sm["F"]["media"] == "unbekannt" and sm["F"]["health_state"] == "unknown", "nicht eindeutig = unbekannt"
assert sm["E"]["model"] == "Disk X"
# Seriennummer entscheidet vor dem Namen
swap = {"disks": [{"number": 0, "name": "Gleich", "serial": "AAA", "size": 1}, {"number": 1, "name": "Gleich", "serial": "BBB", "size": 1}],
        "physical": [{"name": "Gleich", "serial": "BBB", "media": "HDD", "health": "Healthy", "size": 1}, {"name": "Gleich", "serial": "AAA", "media": "SSD", "health": "Healthy", "size": 1}],
        "partitions": [{"letter": "C", "disk": 0}, {"letter": "D", "disk": 1}]}
sw = ph.map_drives(swap)
assert sw["C"]["media"] == "SSD" and sw["D"]["media"] == "HDD", sw
# Seriennummer zaehlt mehr als der Name; Punkt, Unterstrich, Gross/Klein und Leerzeichen in der Seriennummer stoeren nicht
ser = {"disks": [{"number": 0, "name": "Name A", "serial": " AbC_123. ", "size": 1}],
       "physical": [{"name": "Name A", "serial": "ZZZ", "media": "HDD", "health": "Healthy", "size": 1}, {"name": "Name B", "serial": "abc123", "media": "SSD", "health": "Healthy", "size": 1}],
       "partitions": [{"letter": "C", "disk": 0}]}
assert ph.map_drives(ser)["C"]["media"] == "SSD" and ph.map_drives(ser)["C"]["model"] == "Name B"
# jeder Schritt grenzt ein: Name trifft zwei, die Groesse waehlt unter diesen beiden (nicht unter allen)
narrow = {"disks": [{"number": 0, "name": "Name X", "serial": "", "size": 9}],
          "physical": [{"name": "Name X", "serial": "", "media": "HDD", "health": "Healthy", "size": 5}, {"name": "Name X", "serial": "", "media": "SSD", "health": "Healthy", "size": 9},
                       {"name": "Name Y", "serial": "", "media": "HDD", "health": "Warning", "size": 9}],
          "partitions": [{"letter": "C", "disk": 0}]}
assert ph.map_drives(narrow)["C"]["media"] == "SSD" and ph.map_drives(narrow)["C"]["health_state"] == "ok"
# Einzelobjekt statt Liste (PowerShell), unbekannter Typ, Unhealthy, kaputte Eintraege
# Speicherplatz (virtuelle Disk "Speicherplatz", D bei Moritz): ohne Treffer bekommt sie die einzige freie echte Disk
vd = json.loads(json.dumps(REAL))
for d in vd["disks"]:
    if d["number"] == 2:
        d["name"], d["serial"], d["size"] = "Speicherplatz", "", 998561021952
vm = ph.map_drives(vd)
assert vm["D"]["media"] == "HDD" and vm["D"]["model"] == "WDC WD10EZEX-21WN4A0" and vm["D"]["health_state"] == "ok" and vm["D"]["disk_number"] == 2, vm["D"]
assert vm["C"]["media"] == "SSD" and vm["C"]["model"] == "INTEL SSDPEKKW256G7"
# zwei ungeklaerte Laufwerke oder zwei freie Disks: lieber "unbekannt" als raten
two = json.loads(json.dumps(vd))
two["physical"].append({"name": "Dritte", "serial": "Q", "media": "SSD", "health": "Healthy", "size": 7})
assert ph.map_drives(two)["D"]["media"] == "unbekannt" and ph.map_drives(two)["D"]["model"] == "Speicherplatz"
two2 = json.loads(json.dumps(vd))
two2["partitions"].append({"letter": "E", "disk": 3})
two2["disks"].append({"number": 3, "name": "Speicherplatz 2", "serial": "", "size": 5})
assert ph.map_drives(two2)["D"]["media"] == "unbekannt" and ph.map_drives(two2)["E"]["media"] == "unbekannt"

single = {"disks": {"number": 3, "name": "USB", "serial": "", "size": 5}, "physical": {"name": "USB", "serial": "", "media": "Unspecified", "health": "Unhealthy", "size": 5},
          "partitions": {"letter": "G", "disk": 3}}
assert ph.map_drives(single)["G"] == {"media": "unbekannt", "health": "Unhealthy", "health_state": "bad", "model": "USB", "disk_number": 3}
for junk in (None, [], "x", {}, {"disks": None}, {"partitions": [None, 5, {"letter": "", "disk": 1}, {"letter": "1", "disk": 1}, {"letter": "H", "disk": 99}], "disks": [], "physical": []}):
    out = ph.map_drives(junk)
    assert out == {} or list(out) == ["H"], (junk, out)
assert ph.map_drives({"partitions": [{"letter": "H", "disk": 99}]})["H"] == {"media": "unbekannt", "health": "", "health_state": "unknown", "model": "", "disk_number": 99}
long_name = ph.map_drives({"disks": [{"number": 1, "name": "A" * 200 + "\x00\x1b", "serial": "", "size": 1}], "physical": [], "partitions": [{"letter": "C", "disk": 1}]})
assert len(long_name["C"]["model"]) <= 60 and "\x00" not in long_name["C"]["model"] and "\x1b" not in long_name["C"]["model"]

# 2) PowerShell-Abfrage: fest, ohne Eingaben; Fehler geben None
calls = []
def fake_run_ok(cmd, **kw):
    calls.append((cmd, kw))
    return NS(returncode=0, stdout=json.dumps(REAL))
assert ph.read_drive_info(fake_run_ok) == REAL
cmd, kw = calls[0]
assert cmd[0] == "powershell" and "-NoProfile" in cmd and "-NonInteractive" in cmd and cmd[-1] == ph.POWERSHELL_SCRIPT and kw["timeout"] == 25 and not kw.get("shell")
for needed in ("Get-Disk", "Get-PhysicalDisk", "Get-Partition", "ConvertTo-Json"):
    assert needed in ph.POWERSHELL_SCRIPT
assert ph.read_drive_info(lambda *a, **k: NS(returncode=1, stdout="{}")) is None
assert ph.read_drive_info(lambda *a, **k: NS(returncode=0, stdout="kein json")) is None
assert ph.read_drive_info(lambda *a, **k: NS(returncode=0, stdout="[1, 2]")) is None
def boom(*a, **k):
    raise FileNotFoundError("powershell")
assert ph.read_drive_info(boom) is None

# 3) Messung mit erfundenem psutil
class Clock:
    def __init__(self):
        self.t = 100.0
    def __call__(self):
        return self.t
    def sleep(self, seconds):
        self.t += seconds

class Proc:
    def __init__(self, pid, name, cpu, rss, io=(0, 0), io_after=(0, 0), io_error=False):
        self.pid, self.info = pid, {"name": name, "memory_info": NS(rss=rss)}
        self.cpu, self.io_error, self._cpu_calls, self._io_calls = cpu, io_error, 0, 0
        self.io_first, self.io_second = io, io_after
    def cpu_percent(self, interval=None):
        self._cpu_calls += 1
        return 0.0 if self._cpu_calls == 1 else self.cpu
    def io_counters(self):
        if self.io_error:
            raise PermissionError("Zugriff verweigert")
        self._io_calls += 1
        r, w = self.io_first if self._io_calls == 1 else self.io_second
        return NS(read_bytes=r, write_bytes=w)

class FakePs:
    def __init__(self, clock):
        self.clock = clock
        self.parts = [NS(mountpoint="C:\\", fstype="NTFS", opts="rw,fixed"), NS(mountpoint="D:\\", fstype="NTFS", opts="rw,fixed")]
        self.usage = {"C:\\": NS(total=238 * GB, free=60 * GB, percent=74.8), "D:\\": NS(total=931 * GB, free=500 * GB, percent=46.3)}
        self.io = {"PhysicalDrive1": NS(read_bytes=0, write_bytes=0, read_time=0, write_time=0), "PhysicalDrive2": NS(read_bytes=0, write_bytes=0, read_time=0, write_time=0)}
        self.procs = []
        self.io_calls = 0
    def disk_partitions(self, all=False):
        return self.parts
    def disk_usage(self, mount):
        return self.usage[mount]
    def disk_io_counters(self, perdisk=False):
        self.io_calls += 1
        return {k: NS(**vars(v)) for k, v in self.io.items()}
    def cpu_count(self, logical=True):
        return 8
    def process_iter(self, attrs=None):
        return iter(self.procs)

clock = Clock()
ps = FakePs(clock)
run_calls = []
def run_real(cmd, **kw):
    run_calls.append(cmd)
    return NS(returncode=0, stdout=json.dumps(REAL))
health = ph.PcHealth(ps=ps, run=run_real, clock=clock, sleep=clock.sleep, windows=True, autostart=lambda: ["Steam", " Discord ", "Steam", "", None, "Spotify\x00"], monitor=NS(sample=lambda fresh_cpu=False: {"ram_percent": 40, "cpu_percent": 10, "fresh": fresh_cpu}))

# erste Messung: Vergleichswert wird gesammelt, 0,3 s gewartet; waehrenddessen arbeitet HDD (PhysicalDrive2) 150 ms von 300 ms
orig_sleep = clock.sleep
def busy_sleep(seconds):
    orig_sleep(seconds)
    ps.io["PhysicalDrive2"] = NS(read_bytes=30 * 1024 ** 2, write_bytes=3 * 1024 ** 2, read_time=100, write_time=50)
health.sleep = busy_sleep
drives = health.drives()
c, d = drives
assert (c["letter"], c["media"], c["health_state"], c["model"], c["system"]) == ("C", "SSD", "ok", "INTEL SSDPEKKW256G7", True) or c["system"] is False, c
assert d["letter"] == "D" and d["media"] == "HDD" and d["model"] == "WDC WD10EZEX-21WN4A0"
assert d["busy_percent"] == 50.0, d                                  # 150 ms von 300 ms
assert d["read_mb_s"] == 100.0 and d["write_mb_s"] == 10.0, d
assert c["busy_percent"] == 0.0 and c["read_mb_s"] == 0.0
assert (d["total_gb"], d["free_gb"], d["used_percent"]) == (931.0, 500.0, 46.3) and d["name"] == "D:\\"
assert len(run_calls) == 1
# gleich danach: zu kurzer Abstand -> letzte Werte, kein neuer Zaehlerstand, kein Warten
before_calls, before_t = ps.io_calls, clock.t
health.drives()
assert ps.io_calls == before_calls and clock.t == before_t
# spaeter: Unterschied zur letzten Messung (4 s, HDD 4 s lang voll ausgelastet, aber nie ueber 100 %)
health.sleep = clock.sleep
clock.t += 4.0
ps.io["PhysicalDrive2"] = NS(read_bytes=30 * 1024 ** 2 + 40 * 1024 ** 2, write_bytes=3 * 1024 ** 2, read_time=100 + 6000, write_time=50)
d = health.drives()[1]
assert d["busy_percent"] == 100.0 and d["read_mb_s"] == 10.0 and d["write_mb_s"] == 0.0, d
# Laufwerkstypen kommen aus dem Zwischenspeicher, nach 10 Minuten neu
assert len(run_calls) == 1
clock.t += ph.DISK_INFO_SECONDS + 1
health.drives()
assert len(run_calls) == 2
# sehr alte Vergleichsmessung wird nicht benutzt: neu gemessen mit Wartezeit
slept = []
health.sleep = lambda s: (slept.append(s), clock.sleep(s))
clock.t += 1000
health.drives()
assert slept == [ph.IO_WINDOW_SECONDS], slept
health.sleep = clock.sleep
# Zaehler zurueckgesetzt (Neustart des Zaehlers): keine negativen Werte
ps.io["PhysicalDrive2"] = NS(read_bytes=0, write_bytes=0, read_time=0, write_time=0)
clock.t += 5
d = health.drives()[1]
assert d["busy_percent"] == 0.0 and d["read_mb_s"] == 0.0, d

# kein Windows: keine PowerShell-Abfrage, alles "unbekannt", nichts bricht
other = ph.PcHealth(ps=ps, run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("kein Aufruf")), clock=clock, sleep=clock.sleep, windows=False)
o = other.drives()
assert [x["media"] for x in o] == ["unbekannt", "unbekannt"] and o[0]["busy_percent"] is None and o[0]["health_state"] == "unknown"
# Abfrage scheitert: ebenfalls unbekannt
failing = ph.PcHealth(ps=ps, run=boom, clock=clock, sleep=clock.sleep, windows=True)
assert failing.drives()[0]["media"] == "unbekannt"
# psutil ohne Laufwerkszaehler
class NoIo(FakePs):
    def disk_io_counters(self, perdisk=False):
        raise RuntimeError("keine Zaehler")
none_io = ph.PcHealth(ps=NoIo(clock), run=run_real, clock=clock, sleep=clock.sleep, windows=True).drives()
assert none_io[1]["busy_percent"] is None and none_io[1]["media"] == "HDD"

# Programme: RAM nach Namen, CPU durch Kerne geteilt, Festplatte in MB/s, Leerlauf und Fehler ausgeschlossen
ps.procs = [
    Proc(0, "System Idle Process", 700.0, 1),
    Proc(0, "Kernel", 600.0, 1),
    Proc(10, "chrome.exe", 40.0, 900 * 1024 ** 2, io=(0, 0), io_after=(5 * 1024 ** 2, 0)),
    Proc(11, "chrome.exe", 24.0, 800 * 1024 ** 2, io=(0, 0), io_after=(0, 5 * 1024 ** 2)),
    Proc(12, "game.exe", 8.0, 3000 * 1024 ** 2, io=(100, 100), io_after=(100 + 50 * 1024 ** 2, 100)),
    Proc(13, "ruhig.exe", 0.4, 10 * 1024 ** 2, io=(1, 1), io_after=(2, 2)),
    Proc(14, "gesperrt.exe", 16.0, 20 * 1024 ** 2, io_error=True),
]
for p in ps.procs:
    p._cpu_calls = 0
clock.t += 100
prog = health.programs()
assert prog["ram"] == [{"name": "game.exe", "mb": 3000, "count": 1}, {"name": "chrome.exe", "mb": 1700, "count": 2}, {"name": "gesperrt.exe", "mb": 20, "count": 1}], prog["ram"]
assert prog["cpu"] == [{"name": "chrome.exe", "percent": 8.0, "count": 2}, {"name": "gesperrt.exe", "percent": 2.0, "count": 1}, {"name": "game.exe", "percent": 1.0, "count": 1}], prog["cpu"]
assert [p["name"] for p in prog["disk"]] == ["game.exe", "chrome.exe"], prog["disk"]
assert prog["disk"][0]["mb_s"] == 100.0 and prog["disk"][1]["mb_s"] == 20.0, prog["disk"]       # 50 MB bzw. 10 MB in 0,5 s
assert all("System Idle" not in p["name"] for p in prog["ram"] + prog["cpu"] + prog["disk"])
# zwischengespeichert: zweiter Aufruf misst nicht noch einmal
stamp = clock.t
assert health.programs() is prog and clock.t == stamp
clock.t += ph.PROGRAMS_SECONDS + 1
for p in ps.procs:
    p._cpu_calls = 0
assert health.programs() is not prog
# Fehler beim Auflisten der Programme bricht nichts
class BadIter(FakePs):
    def process_iter(self, attrs=None):
        raise RuntimeError("kaputt")
assert ph.PcHealth(ps=BadIter(clock), run=run_real, clock=clock, sleep=clock.sleep, windows=True).programs() == {"ram": [], "cpu": [], "disk": []}

# Autostart: nur Namen, ohne Doppelte, Leere und Steuerzeichen, zwischengespeichert
assert health.autostart() == ["Steam", "Discord", "Spotify"], health.autostart()
broken = ph.PcHealth(ps=ps, autostart=boom, clock=clock, windows=True)
assert broken.autostart() == []

# Gesamt-Bericht
report = health.report()
assert set(report) == {"now", "drives", "programs", "autostart", "assessment"} and report["now"]["ram_percent"] == 40 and report["now"]["fresh"] is True
assert report["assessment"]["level"] in ("ok", "warn", "bad")

# 4) Bewertung: reine Funktion
def drive(letter, media, total, free, **over):
    d = {"name": letter + ":\\", "letter": letter, "total_gb": total, "free_gb": free, "used_percent": round(100 - free / total * 100, 1) if total else 0.0, "media": media,
         "health": "Healthy", "health_state": "ok", "model": "M", "system": letter == "C", "busy_percent": 5.0, "read_mb_s": 0.0, "write_mb_s": 0.0}
    d.update(over)
    return d

def snap(**over):
    base = {"now": {"ram_percent": 40, "ram_used_gb": 6.4, "ram_total_gb": 16.0, "cpu_percent": 10, "battery": None, "uptime_seconds": 3600},
            "drives": [drive("C", "SSD", 238, 120), drive("D", "HDD", 931, 500)], "programs": {"ram": [], "cpu": [], "disk": []}, "autostart": []}
    for key, value in over.items():
        if key == "now":
            base["now"].update(value)
        else:
            base[key] = value
    return base

ids = lambda a: [f["id"] for f in a["findings"]]
calm = ph.assess(snap())
assert calm == {"level": "ok", "headline": "Alles ruhig.", "findings": []}, calm
assert ph.assess({}) == calm or ph.assess({})["level"] == "ok"        # leere Daten: keine Meldung, kein Absturz
assert ph.assess({"now": None, "drives": None, "programs": None})["level"] == "ok"

# RAM: Grenzen 90 / 95, Verbraucher und Tipp nach Groesse
a = ph.assess(snap(now={"ram_percent": 89.9}))
assert a["level"] == "ok"
a = ph.assess(snap(now={"ram_percent": 90, "ram_used_gb": 14.4}, programs={"ram": [{"name": "chrome.exe", "mb": 3300, "count": 24}], "cpu": [], "disk": []}))
f = a["findings"][0]
assert a["level"] == "warn" and f["id"] == "ram" and f["level"] == "warn" and f["sustained"] is True
assert "90 %" in f["text"] and "14,4 von 16,0 GB" in f["text"] and "chrome.exe mit 3,2 GB (24 Prozesse)" in f["text"], f["text"]
assert "Browser-Tabs" in f["tip"] and a["headline"] == "RAM knapp (90 %), größter Verbraucher: chrome.exe", a["headline"]
assert ph.assess(snap(now={"ram_percent": 95}))["level"] == "bad"
assert "mehr RAM ist die wirksamste" in ph.assess(snap(now={"ram_percent": 92, "ram_total_gb": 8.0}))["findings"][0]["tip"]
assert "Speicher frisst" in ph.assess(snap(now={"ram_percent": 92, "ram_total_gb": 32.0}))["findings"][0]["tip"]
assert "Größter Verbraucher" not in ph.assess(snap(now={"ram_percent": 92}))["findings"][0]["text"]

# CPU
a = ph.assess(snap(now={"cpu_percent": 96}, programs={"ram": [], "cpu": [{"name": "render.exe", "percent": 71.4, "count": 1}], "disk": []}))
f = a["findings"][0]
assert a["level"] == "bad" and f["id"] == "cpu" and f["sustained"] and "render.exe (71 %)" in f["text"] and "render.exe" in a["headline"], (f, a["headline"])
assert ph.assess(snap(now={"cpu_percent": 89}))["level"] == "ok" and ph.assess(snap(now={"cpu_percent": 90}))["level"] == "warn"

# Laufwerk fast voll: SSD und HDD, Systemlaufwerk strenger, Ausweichort
a = ph.assess(snap(drives=[drive("C", "SSD", 238, 30), drive("D", "HDD", 931, 500)]))        # 12,6 % frei: warn
f = a["findings"][0]
assert f["id"] == "full:C" and f["level"] == "warn" and a["level"] == "warn" and not f["sustained"]
assert "30,0 GB frei (13 %)" in f["text"] and "verschleißt" in f["tip"] and "D: (500 GB frei)" in f["tip"], f
assert ph.assess(snap(drives=[drive("C", "SSD", 238, 20), drive("D", "HDD", 931, 500)]))["findings"][0]["level"] == "bad"       # 8,4 % < 10 % am System
assert ph.assess(snap(drives=[drive("C", "SSD", 238, 150), drive("D", "HDD", 931, 60)]))["findings"][0]["level"] == "warn"      # 6,4 %: HDD ohne System noch nicht kritisch
assert ph.assess(snap(drives=[drive("C", "SSD", 238, 150), drive("D", "HDD", 931, 40)]))["findings"][0]["level"] == "bad"       # 4,3 % < 5 %
a = ph.assess(snap(drives=[drive("C", "SSD", 238, 150), drive("D", "HDD", 931, 60)]))
assert "ein anderes Laufwerk" in a["findings"][0]["tip"] and "Verschiebe" in a["findings"][0]["tip"] and "C: (150 GB frei)" in a["findings"][0]["tip"]
assert "Verschiebe" not in ph.assess(snap(drives=[drive("C", "SSD", 238, 20), drive("D", "HDD", 931, 40)]))["findings"][0]["tip"], "kein Ausweichort unter 50 GB"
assert ph.assess(snap(drives=[drive("C", "SSD", 200, 30)]))["level"] == "ok"            # genau 15 % frei: noch in Ordnung
assert ph.assess(snap(drives=[drive("C", "SSD", 200, 29.9)]))["level"] == "warn"
assert ph.assess(snap(drives=[drive("C", "SSD", 0, 0)]))["level"] == "ok"               # Groesse 0: kein Teilen durch null

# Gesundheit: kritisch, nicht "sustained"
a = ph.assess(snap(drives=[drive("C", "SSD", 238, 120), drive("D", "HDD", 931, 500, health="Warning", health_state="warning")]))
f = a["findings"][0]
assert a["level"] == "bad" and f["id"] == "health:D" and f["level"] == "bad" and not f["sustained"] and "Backup" in f["tip"] and "„Warning“" in f["text"], f
assert ph.assess(snap(drives=[drive("D", "HDD", 931, 500, health="Unhealthy", health_state="bad")]))["level"] == "bad"
assert ph.assess(snap(drives=[drive("D", "HDD", 931, 500, health="", health_state="unknown")]))["level"] == "ok"

# Auslastung: HDD bremst, mit Verursacher; SSD kurzfristig
busy_hdd = snap(drives=[drive("C", "SSD", 238, 120), drive("D", "HDD", 931, 500, busy_percent=97.3)], programs={"ram": [], "cpu": [], "disk": [{"name": "game.exe", "mb_s": 12.34, "count": 1}]})
a = ph.assess(busy_hdd)
f = a["findings"][0]
assert f["id"] == "busy:D" and f["level"] == "warn" and f["sustained"] and "97 %" in f["text"] and "Das bremst den PC." in f["text"] and "game.exe (12,3 MB/s)" in f["text"], f
assert "auf die SSD" in f["tip"]
f = ph.assess(snap(drives=[drive("C", "SSD", 238, 120, busy_percent=95.0)]))["findings"][0]
assert "bremst" not in f["text"] and "Virenscan" in f["tip"]
assert ph.assess(snap(drives=[drive("C", "SSD", 238, 120, busy_percent=89.9)]))["level"] == "ok"
assert ph.assess(snap(drives=[drive("C", "SSD", 238, 120, busy_percent=None)]))["level"] == "ok"

# Tipps aendern die Ampel nicht: Windows auf HDD, lange Laufzeit, viele Autostart-Eintraege
a = ph.assess(snap(drives=[drive("C", "HDD", 931, 500)], now={"uptime_seconds": 15 * 86400}, autostart=["p%d" % i for i in range(12)]))
assert a["level"] == "ok" and set(ids(a)) == {"system_hdd", "uptime", "autostart"} and all(f["level"] == "tip" for f in a["findings"])
assert a["headline"] == "Alles ruhig. Es gibt kleine Verbesserungs-Tipps."
assert "15 Tagen" in [f for f in a["findings"] if f["id"] == "uptime"][0]["text"]
assert ph.assess(snap(now={"uptime_seconds": 14 * 86400}))["findings"][0]["id"] == "uptime"
assert ph.assess(snap(now={"uptime_seconds": 14 * 86400 - 1}))["findings"] == [] and ph.assess(snap(autostart=["p"] * 11))["findings"] == []
assert ph.assess(snap(drives=[drive("D", "HDD", 931, 500, system=False)]))["findings"] == [], "HDD als Datenlaufwerk ist in Ordnung"

# Akku
a = ph.assess(snap(now={"battery": {"percent": 19, "plugged": False}}))
assert a["level"] == "warn" and a["findings"][0]["id"] == "battery"
assert ph.assess(snap(now={"battery": {"percent": 9, "plugged": False}}))["level"] == "bad"
assert ph.assess(snap(now={"battery": {"percent": 5, "plugged": True}}))["level"] == "ok"
assert ph.assess(snap(now={"battery": {"percent": 20, "plugged": False}}))["level"] == "ok"

# Reihenfolge und Kopfzeile bei mehreren Problemen: kritisch zuerst, hoechstens zwei, Rest gezaehlt
many = snap(now={"ram_percent": 92, "cpu_percent": 91, "battery": {"percent": 5, "plugged": False}}, drives=[drive("C", "SSD", 238, 120), drive("D", "HDD", 931, 500, health="Warning", health_state="warning")])
a = ph.assess(many)
assert [f["level"] for f in a["findings"]] == sorted((f["level"] for f in a["findings"]), key=lambda l: ph.LEVEL_ORDER[l])
assert ids(a)[:2] == ["health:D", "battery"] and a["level"] == "bad", ids(a)
assert a["headline"].endswith("(+2 weitere)") and a["headline"].count(" · ") == 1, a["headline"]
for f in a["findings"]:
    assert set(f) == {"id", "level", "sustained", "short", "text", "tip"} and f["short"] and f["text"] and f["tip"]
assert len(set(ids(a))) == len(ids(a)), "jeder Hinweis nur einmal"

print("ALL TESTS PASSED")
