"""PC-Lage (Mark 5): Wie geht es dem Rechner, wo hakt es, und was kann man verbessern?

Drei getrennte Teile, damit man jeden einzeln verstehen und testen kann:

1. Zuordnung   ``map_drives()``  Laufwerksbuchstabe -> SSD/HDD, Gesundheit, Modell (aus drei Windows-Listen)
2. Messen      ``PcHealth``      Laufwerke mit Auslastung, groesste Programme (RAM, CPU, Festplatte), Autostart-Namen
3. Bewerten    ``assess()``      reine Funktion: Messwerte rein, Ampel + Hinweise mit Tipps raus (feste Regeln, keine KI)

Die KI formuliert nur die Antwort auf eine Frage; was "knapp" oder "kritisch" ist, entscheiden die Zahlen hier.

Datenschutz: alles bleibt auf dem Rechner. Von Programmen gibt es nur Namen und Summen (nie Pfade oder Befehlszeilen),
vom Autostart nur die Namen der Eintraege. Die Laufwerkstypen liest eine feste PowerShell-Abfrage (ohne Eingaben von aussen).
Nicht enthalten: Temperaturen, Verschleiss (SMART) und Grafikkarte, denn die brauchen Admin-Rechte oder Zusatzprogramme.
"""

import subprocess
import sys
import threading
import time

import psutil

from tools import system_status_tool as sst
from untrusted import clean_text

DISK_INFO_SECONDS = 600         # Laufwerkstypen aendern sich kaum (und die Abfrage dauert eine Sekunde)
PROGRAMS_SECONDS = 15           # die Programm-Messung dauert eine halbe Sekunde: nicht bei jeder Anfrage
AUTOSTART_SECONDS = 300
IO_WINDOW_SECONDS = 0.3         # so lange wird die Laufwerks-Last beim allerersten Mal gemessen
PROGRAM_WINDOW_SECONDS = 0.5    # so lange wird die Last der Programme gemessen
IO_MAX_AGE_SECONDS = 60         # eine aeltere Vergleichsmessung taugt nicht mehr
TOP_COUNT = 3
MAX_AUTOSTART_NAMES = 40
IGNORED_PROGRAMS = ("System Idle Process", "Idle")

# Schwellen der Bewertung
RAM_WARN, RAM_BAD = 90, 95                  # Prozent belegt
CPU_WARN, CPU_BAD = 90, 95                  # Prozent ausgelastet
FULL_WARN_FREE = 15                         # Prozent frei: darunter "fast voll"
FULL_BAD_FREE = 5                           # darunter kritisch ...
FULL_BAD_FREE_SYSTEM = 10                   # ... auf dem Systemlaufwerk schon bei 10 Prozent
BUSY_WARN = 90                              # Laufwerk so viel Prozent der Zeit beschaeftigt
UPTIME_TIP_DAYS = 14
BATTERY_WARN, BATTERY_BAD = 20, 10
AUTOSTART_TIP = 12                          # ab so vielen Autostart-Eintraegen ein Tipp
SPARE_GB = 50                               # so viel muss frei sein, damit ein anderes Laufwerk als Ausweichort genannt wird

# Die feste Abfrage: drei Listen, die Python zusammensetzt (Disk-Nummern von Get-Disk und Get-PhysicalDisk stimmen oft NICHT ueberein)
POWERSHELL_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$disks = @(Get-Disk | ForEach-Object { @{ number = [int]$_.Number; name = "$($_.FriendlyName)"; serial = "$($_.SerialNumber)"; size = [int64]$_.Size } })
$physical = @(Get-PhysicalDisk | ForEach-Object { @{ name = "$($_.FriendlyName)"; serial = "$($_.SerialNumber)"; media = "$($_.MediaType)"; health = "$($_.HealthStatus)"; size = [int64]$_.Size } })
$parts = @(Get-Partition | Where-Object { $_.DriveLetter } | ForEach-Object { @{ letter = "$($_.DriveLetter)"; disk = [int]$_.DiskNumber } })
@{ disks = $disks; physical = $physical; partitions = $parts } | ConvertTo-Json -Compress -Depth 4
"""
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

LEVEL_ORDER = {"bad": 0, "warn": 1, "tip": 2}


# ---------------------------------------------------------------- 1. Zuordnung

def _as_list(value):
    """PowerShell macht aus einer Liste mit einem Eintrag ein einzelnes Objekt."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _name_key(text):
    return " ".join(str(text or "").split()).casefold()


def _serial_key(text):
    """Seriennummern gleichen sich nur in Buchstaben und Ziffern (Punkte, Unterstriche, Leerzeichen und Gross/Klein wechseln je nach Abfrage)."""
    return "".join(ch for ch in str(text or "").casefold() if ch.isalnum())


def _size_key(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def match_physical(disk, physical):
    """Zur Disk (Get-Disk) die passende Physical-Disk (Get-PhysicalDisk): Seriennummer, dann Name, dann Groesse.

    Jeder Schritt grenzt die Kandidaten ein; am Ende zaehlt nur ein eindeutiger Treffer, sonst None (lieber "unbekannt" als falsch).
    """
    candidates = [p for p in physical if isinstance(p, dict)]
    for key, norm in (("serial", _serial_key), ("name", _name_key), ("size", _size_key)):
        wanted = norm(disk.get(key))
        if not wanted:
            continue
        found = [p for p in candidates if norm(p.get(key)) == wanted]
        if len(found) == 1:
            return found[0]
        if found:
            candidates = found
    return candidates[0] if len(candidates) == 1 else None


def _media(value):
    text = str(value or "").strip().upper()
    return text if text in ("SSD", "HDD") else "unbekannt"


def _health_state(value):
    return {"healthy": "ok", "warning": "warning", "unhealthy": "bad"}.get(str(value or "").strip().casefold(), "unknown")


def map_drives(info):
    """{"C": {"media": "SSD"|"HDD"|"unbekannt", "health", "health_state", "model", "disk_number"}} aus den drei Listen."""
    if not isinstance(info, dict):
        return {}
    disks = {d.get("number"): d for d in _as_list(info.get("disks")) if isinstance(d, dict)}
    physical = [p for p in _as_list(info.get("physical")) if isinstance(p, dict)]
    entries = []
    for part in _as_list(info.get("partitions")):
        if not isinstance(part, dict):
            continue
        letter = str(part.get("letter") or "").strip().upper()[:1]
        if not letter.isalpha():
            continue
        disk = disks.get(part.get("disk"))
        entries.append((letter, part, disk, match_physical(disk, physical) if disk else None))
    # Speicherplaetze (virtuelle Disk, Name "Speicherplatz") haben weder Seriennummer noch Namen einer echten Disk:
    # bleibt genau EINE echte Disk uebrig, die kein anderes Laufwerk belegt, gehoert sie dazu
    used = [m for _, _, _, m in entries if m is not None]
    free = [p for p in physical if not any(p is u for u in used)]
    unmatched = [i for i, e in enumerate(entries) if e[3] is None and e[2] is not None]
    if len(unmatched) == 1 and len(free) == 1:
        letter, part, disk, _ = entries[unmatched[0]]
        entries[unmatched[0]] = (letter, part, disk, free[0])
    result = {}
    for letter, part, disk, match in entries:
        result[letter] = {
            "media": _media(match.get("media")) if match else "unbekannt",
            "health": clean_text(match.get("health"), 20).strip() if match else "",
            "health_state": _health_state(match.get("health")) if match else "unknown",
            "model": clean_text((match or disk or {}).get("name"), 60).strip() if (match or disk) else "",
            "disk_number": part.get("disk") if isinstance(part.get("disk"), int) else None,
        }
    return result


def read_drive_info(run=subprocess.run):
    """Die drei Windows-Listen als Dict oder None (kein Windows, Fehler, Zeitueberschreitung, kein JSON)."""
    import json
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_SCRIPT],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, creationflags=flags)
        if done.returncode != 0:
            return None
        data = json.loads(done.stdout)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def read_autostart_names():
    """Namen der Autostart-Eintraege in der Registry (nur die Namen, nie die Befehle). Ohne Windows: leer."""
    try:
        import winreg
    except ImportError:
        return []
    names = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, RUN_KEY) as key:
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumValue(key, index)[0])
                    except OSError:
                        break
                    index += 1
        except OSError:
            continue
    return names


# ---------------------------------------------------------------- 2. Messen

class PcHealth:
    def __init__(self, ps=psutil, run=subprocess.run, clock=time.monotonic, sleep=time.sleep,
                 windows=None, autostart=read_autostart_names, monitor=None):
        self.ps = ps
        self.run = run
        self.clock = clock
        self.sleep = sleep
        self.windows = sys.platform.startswith("win") if windows is None else windows
        self.autostart_reader = autostart
        self.monitor = monitor
        self._lock = threading.RLock()
        self._disk_info = (None, {})        # (Zeitpunkt, {Buchstabe: Angaben})
        self._io_prev = None                # (Zeitpunkt, {Laufwerk: Zaehler})
        self._io_rates = {}
        self._io_rates_time = None
        self._programs = (None, {})
        self._autostart = (None, [])

    # -- Laufwerkstypen (zwischengespeichert)
    def disk_info(self):
        with self._lock:
            now = self.clock()
            stamp, cached = self._disk_info
            if stamp is not None and now - stamp < DISK_INFO_SECONDS:
                return cached
            mapped = map_drives(read_drive_info(self.run)) if self.windows else {}
            self._disk_info = (now, mapped)
            return mapped

    # -- Auslastung der Laufwerke: Unterschied zwischen zwei Zaehlerstaenden
    def _counters(self):
        try:
            raw = self.ps.disk_io_counters(perdisk=True) or {}
        except Exception:
            return {}
        result = {}
        for name, c in raw.items():
            try:
                result[name] = (c.read_bytes, c.write_bytes, c.read_time, c.write_time)
            except AttributeError:
                continue
        return result

    @staticmethod
    def _rates_between(before, after, seconds):
        rates = {}
        for name, (rb1, wb1, rt1, wt1) in after.items():
            if name not in before or seconds <= 0:
                continue
            rb0, wb0, rt0, wt0 = before[name]
            busy_ms = max(0, rt1 - rt0) + max(0, wt1 - wt0)
            rates[name] = {
                "busy_percent": round(min(100.0, busy_ms / (seconds * 1000) * 100), 1),
                "read_mb_s": round(max(0, rb1 - rb0) / seconds / (1024 ** 2), 1),
                "write_mb_s": round(max(0, wb1 - wb0) / seconds / (1024 ** 2), 1),
            }
        return rates

    def io_rates(self):
        """{"PhysicalDrive1": {busy_percent, read_mb_s, write_mb_s}}. Beim ersten Mal wird kurz gemessen, danach gilt der Abstand zur letzten Messung."""
        with self._lock:
            now = self.clock()
            if self._io_rates_time is not None and now - self._io_rates_time < 1.0:
                return self._io_rates                       # Schutz vor Dauerfeuer: zu kurzer Abstand gibt kaum Aussage
            current = self._counters()
            if self._io_prev is None or now - self._io_prev[0] > IO_MAX_AGE_SECONDS:
                self._io_prev = (now, current)
                self.sleep(IO_WINDOW_SECONDS)
                now = self.clock()
                current = self._counters()
            self._io_rates = self._rates_between(self._io_prev[1], current, now - self._io_prev[0])
            self._io_prev = (now, current)
            self._io_rates_time = now
            return self._io_rates

    def drives(self):
        """Feste Laufwerke: Platz, SSD/HDD, Gesundheit, Auslastung. Fehlendes bleibt None bzw. "unbekannt"."""
        info = self.disk_info()
        rates = self.io_rates()
        system_letter = sst._system_drive()[:1].upper()
        result = []
        for drive in sst._drives(self.ps):
            letter = drive["name"][:1].upper()
            extra = info.get(letter) or {}
            number = extra.get("disk_number")
            rate = rates.get(f"PhysicalDrive{number}") if number is not None else None
            result.append({
                **drive,
                "letter": letter,
                "media": extra.get("media", "unbekannt"),
                "health": extra.get("health", ""),
                "health_state": extra.get("health_state", "unknown"),
                "model": extra.get("model", ""),
                "system": letter == system_letter,
                "busy_percent": rate["busy_percent"] if rate else None,
                "read_mb_s": rate["read_mb_s"] if rate else None,
                "write_mb_s": rate["write_mb_s"] if rate else None,
            })
        return result

    # -- Programme: RAM, CPU und Festplatte nach Namen zusammengefasst
    def _measure_programs(self):
        cores = self.ps.cpu_count(logical=True) or 1
        started = []
        try:
            for proc in self.ps.process_iter(["name"]):
                try:
                    name = proc.info.get("name")
                    if not isinstance(name, str) or proc.pid == 0 or name in IGNORED_PROGRAMS:
                        continue
                    proc.cpu_percent(None)                  # erste Messung ist immer 0: Startpunkt setzen
                    try:
                        io = proc.io_counters()
                        before = io.read_bytes + io.write_bytes
                    except Exception:
                        before = None
                    started.append((proc, name[:60], before))
                except Exception:
                    continue
        except Exception:
            return {"cpu": [], "disk": []}
        started_at = self.clock()
        self.sleep(PROGRAM_WINDOW_SECONDS)
        seconds = max(0.05, self.clock() - started_at)
        cpu, disk = {}, {}
        for proc, name, before in started:
            try:
                share = proc.cpu_percent(None) / cores
            except Exception:
                share = 0.0
            entry = cpu.setdefault(name, [0.0, 0])
            entry[0] += share
            entry[1] += 1
            if before is not None:
                try:
                    io = proc.io_counters()
                    moved = max(0, io.read_bytes + io.write_bytes - before) / seconds / (1024 ** 2)
                except Exception:
                    moved = 0.0
                entry = disk.setdefault(name, [0.0, 0])
                entry[0] += moved
                entry[1] += 1
        top_cpu = sorted(((n, v[0], v[1]) for n, v in cpu.items() if v[0] >= 1.0), key=lambda x: x[1], reverse=True)[:TOP_COUNT]
        top_disk = sorted(((n, v[0], v[1]) for n, v in disk.items() if v[0] >= 0.05), key=lambda x: x[1], reverse=True)[:TOP_COUNT]
        return {"cpu": [{"name": n, "percent": round(p, 1), "count": c} for n, p, c in top_cpu],
                "disk": [{"name": n, "mb_s": round(m, 1), "count": c} for n, m, c in top_disk]}

    def programs(self):
        """{"ram": [{name, mb, count}], "cpu": [{name, percent, count}], "disk": [{name, mb_s, count}]}, hoechstens je drei."""
        with self._lock:
            now = self.clock()
            stamp, cached = self._programs
            if stamp is not None and now - stamp < PROGRAMS_SECONDS:
                return cached
            ram = [{"name": p["name"], "mb": p["ram_mb"], "count": p["count"]} for p in sst.top_processes(self.ps, TOP_COUNT)]
            result = {"ram": ram, **self._measure_programs()}
            self._programs = (self.clock(), result)
            return result

    def autostart(self):
        with self._lock:
            now = self.clock()
            stamp, cached = self._autostart
            if stamp is not None and now - stamp < AUTOSTART_SECONDS:
                return cached
            try:
                raw = self.autostart_reader()
            except Exception:
                raw = []
            names = list(dict.fromkeys(clean_text(n, 60).strip() for n in raw if isinstance(n, str) and n.strip()))
            self._autostart = (now, names)
            return names

    def snapshot(self):
        monitor = self.monitor or sst.default_monitor()
        return {"now": monitor.sample(fresh_cpu=True), "drives": self.drives(), "programs": self.programs(), "autostart": self.autostart()}

    def report(self):
        """Messwerte plus Bewertung: das, was Fenster und Chat bekommen."""
        data = self.snapshot()
        return {**data, "assessment": assess(data)}


# ---------------------------------------------------------------- 3. Bewerten

def _de(number, digits=1):
    return f"{number:.{digits}f}".replace(".", ",")


def _mb(value):
    return f"{_de(value / 1024)} GB" if value >= 1024 else f"{round(value)} MB"


def _label(drive):
    media = drive.get("media")
    return f"{drive['letter']}: ({media})" if media in ("SSD", "HDD") else f"{drive['letter']}:"


def _free_percent(drive):
    total = drive.get("total_gb") or 0
    return (drive.get("free_gb", 0) / total * 100) if total > 0 else 100.0


def _spare(drives, exclude):
    """Das andere Laufwerk mit dem meisten freien Platz (mindestens SPARE_GB) oder None."""
    others = [d for d in drives if d is not exclude and d.get("free_gb", 0) >= SPARE_GB]
    return max(others, key=lambda d: d["free_gb"]) if others else None


def _finding(fid, level, short, text, tip, sustained=False):
    return {"id": fid, "level": level, "sustained": sustained, "short": short, "text": text, "tip": tip}


def assess(data):
    """Messwerte -> {"level": ok|warn|bad, "headline": Satz, "findings": [{id, level, sustained, short, text, tip}]}.

    level der Hinweise: bad = kritisch, warn = Problem, tip = nur eine Verbesserungsmoeglichkeit (aendert die Ampel nicht).
    sustained = nur ein Problem, wenn es laenger anhaelt (kurze Spitzen sind normal); die Warnung von selbst wartet darauf.
    """
    now = data.get("now") or {}
    drives = data.get("drives") or []
    programs = data.get("programs") or {}
    top_ram = (programs.get("ram") or [None])[0]
    top_cpu = (programs.get("cpu") or [None])[0]
    top_disk = (programs.get("disk") or [None])[0]
    found = []

    for d in drives:
        label = _label(d)
        # Gesundheit: das Wichtigste, denn danach sind Daten weg
        if d.get("health_state") in ("warning", "bad"):
            found.append(_finding(f"health:{d['letter']}", "bad", f"{label} meldet Gesundheitsproblem",
                                  f"Das Laufwerk {label} meldet den Gesundheitsstatus „{d.get('health')}“.",
                                  "Mach jetzt ein Backup der Daten darauf und lass das Laufwerk prüfen, es kann bald ausfallen."))
        # Platz
        free = _free_percent(d)
        bad_below = FULL_BAD_FREE_SYSTEM if d.get("system") else FULL_BAD_FREE
        if free < FULL_WARN_FREE:
            spare = _spare(drives, d)
            where = f" Verschiebe große Dateien auf {spare['letter']}: ({_de(spare['free_gb'], 0)} GB frei)." if spare else ""
            if d.get("media") == "SSD":
                tip = "Eine fast volle SSD wird langsamer und verschleißt schneller. Lass 10 bis 20 % frei." + where
            else:
                tip = "Räume auf oder lagere Daten auf ein anderes Laufwerk aus." + where
            found.append(_finding(f"full:{d['letter']}", "bad" if free < bad_below else "warn", f"{label} fast voll ({_de(free, 0)} % frei)",
                                  f"{label} ist fast voll: nur noch {_de(d.get('free_gb', 0))} GB frei ({_de(free, 0)} %).", tip))
        # Auslastung
        busy = d.get("busy_percent")
        if isinstance(busy, (int, float)) and busy >= BUSY_WARN:
            who = f" Größter Verursacher: {top_disk['name']} ({_de(top_disk['mb_s'])} MB/s)." if top_disk else ""
            slows = " Das bremst den PC." if d.get("media") == "HDD" else ""
            tip = ("Programme und Spiele, die oft laden, gehören auf die SSD." if d.get("media") == "HDD"
                   else "Meist ist das kurz (Update, Installation, Virenscan). Bleibt es dauerhaft so, schau dir den Verursacher an.")
            found.append(_finding(f"busy:{d['letter']}", "warn", f"{label} stark ausgelastet",
                                  f"{label} ist zu {_de(busy, 0)} % ausgelastet.{slows}{who}", tip, sustained=True))
        # Windows auf einer HDD
        if d.get("system") and d.get("media") == "HDD":
            found.append(_finding("system_hdd", "tip", "Windows läuft auf einer HDD", f"Windows läuft auf {label}, einer klassischen Festplatte.",
                                  "Windows und die Programme auf eine SSD zu legen macht den PC am deutlichsten schneller."))

    ram = now.get("ram_percent")
    if isinstance(ram, (int, float)) and ram >= RAM_WARN:
        who = f" Größter Verbraucher: {top_ram['name']} mit {_mb(top_ram['mb'])} ({top_ram['count']} Prozesse)." if top_ram else ""
        total = now.get("ram_total_gb") or 0
        if total and total <= 8:
            tip = "Mit 8 GB wird es schnell eng, mehr RAM ist die wirksamste Lösung."
        elif total and total <= 16:
            tip = "Schließe, was du nicht brauchst (zum Beispiel Browser-Tabs). Kommt das oft vor, lohnt sich mehr RAM."
        else:
            tip = "Schließe oder starte das größte Programm neu. Bei so viel RAM deutet das auf ein Programm hin, das Speicher frisst."
        found.append(_finding("ram", "bad" if ram >= RAM_BAD else "warn",
                              f"RAM knapp ({_de(ram, 0)} %)" + (f", größter Verbraucher: {top_ram['name']}" if top_ram else ""),
                              f"Der Arbeitsspeicher ist zu {_de(ram, 0)} % belegt ({_de(now.get('ram_used_gb', 0))} von {_de(total)} GB).{who}", tip, sustained=True))

    cpu = now.get("cpu_percent")
    if isinstance(cpu, (int, float)) and cpu >= CPU_WARN:
        who = f" Größter Verbraucher: {top_cpu['name']} ({_de(top_cpu['percent'], 0)} %)." if top_cpu else ""
        found.append(_finding("cpu", "bad" if cpu >= CPU_BAD else "warn",
                              f"CPU voll ausgelastet ({_de(cpu, 0)} %)" + (f", {top_cpu['name']}" if top_cpu else ""),
                              f"Der Prozessor ist zu {_de(cpu, 0)} % ausgelastet.{who}",
                              "Kurze Spitzen sind normal. Bleibt es dauerhaft so, starte das Programm neu oder prüfe, was es tut.", sustained=True))

    battery = now.get("battery")
    if isinstance(battery, dict) and not battery.get("plugged") and isinstance(battery.get("percent"), (int, float)) and battery["percent"] < BATTERY_WARN:
        found.append(_finding("battery", "bad" if battery["percent"] < BATTERY_BAD else "warn", f"Akku niedrig ({_de(battery['percent'], 0)} %)",
                              f"Der Akku ist bei {_de(battery['percent'], 0)} % und der Laptop hängt nicht am Strom.", "Schließe das Ladegerät an."))

    uptime = now.get("uptime_seconds")
    if isinstance(uptime, (int, float)) and uptime >= UPTIME_TIP_DAYS * 86400:
        days = int(uptime // 86400)
        found.append(_finding("uptime", "tip", f"seit {days} Tagen nicht neu gestartet", f"Der PC läuft seit {days} Tagen ohne Neustart.",
                              "Ein Neustart räumt Speicher auf und installiert Updates."))

    names = data.get("autostart") or []
    if len(names) >= AUTOSTART_TIP:
        found.append(_finding("autostart", "tip", f"{len(names)} Autostart-Einträge", f"{len(names)} Programme sind für den Start mit Windows eingetragen.",
                              "Das verlängert den Start. Im Task-Manager unter „Autostart“ kannst du Unnötiges abschalten."))

    found.sort(key=lambda f: LEVEL_ORDER[f["level"]])
    problems = [f for f in found if f["level"] != "tip"]
    level = "bad" if any(f["level"] == "bad" for f in found) else "warn" if problems else "ok"
    if not problems:
        headline = "Alles ruhig." + (" Es gibt kleine Verbesserungs-Tipps." if found else "")
    else:
        headline = " · ".join(f["short"] for f in problems[:2]) + (f" (+{len(problems) - 2} weitere)" if len(problems) > 2 else "")
    return {"level": level, "headline": headline, "findings": found}


# ---------------------------------------------------------------- Standard-Instanz

_default = None


def default_health():
    global _default
    if _default is None:
        _default = PcHealth()
    return _default


def set_default_health(health):
    """Nur fuer Tests."""
    global _default
    _default = health
