"""PC-Fakten und Leistungsdaten (Mark 5, Step 2.8): Chat-Fragen ("Wie viel RAM ist frei?") und die Seitenleisten-Widgets.

- ``facts()``      was der Rechner ist (System, Prozessor, Kerne, RAM, Laufwerke, Python): aendert sich kaum
- ``PerformanceMonitor.sample()``  wie ausgelastet er gerade ist (CPU, RAM, Laufwerk, Akku, Netzwerk, Laufzeit)
- ``top_processes()``  die Programme mit dem meisten Arbeitsspeicher (nur Name und Summe, nie Pfade oder Befehlszeilen)
- ``get_system_info()``  alles zusammen fuer die Antwort im Chat

Alles bleibt auf dem Rechner (psutil, keine Internetverbindung). Nur im Chat gehen die Werte mit der Frage an OpenAI,
wie jedes Aufgabenergebnis. Die Widgets lesen ueber den lokalen Server (127.0.0.1).
Nicht enthalten: Temperaturen und Grafikkarte (unter Windows ohne Zusatzprogramme nicht zuverlaessig lesbar).
"""

import platform
import threading
import time
from pathlib import Path

import psutil

from tools.tool_result import ToolResult

GB = 1024 ** 3
MIN_INTERVAL = 1.0          # Abfragen in kuerzerem Abstand bekommen den letzten Messwert (Schutz vor Dauerfeuer)
MAX_DRIVES = 6
TOP_PROCESSES = 5


def _gb(value):
    return round(value / GB, 1)


def _percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(100.0, max(0.0, number)), 1)


def _cpu_name():
    """Lesbarer Prozessorname. Unter Windows steht er in der Registry (platform.processor() liefert nur 'Intel64 Family 6 ...')."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
        if isinstance(name, str) and name.strip():
            return " ".join(name.split())
    except Exception:
        pass
    return platform.processor() or platform.machine() or "unbekannt"


def _system_name():
    system = platform.system() or "unbekannt"
    release = platform.release()
    return f"{system} {release}".strip()


def _system_drive():
    anchor = Path.home().anchor
    return anchor or "/"


def _drives(ps):
    """Feste Laufwerke mit Groesse und freiem Platz. Kaputte oder leere (Kartenleser) werden uebersprungen."""
    drives = []
    try:
        partitions = ps.disk_partitions(all=False)
    except Exception:
        partitions = []
    for part in partitions:
        if len(drives) >= MAX_DRIVES:
            break
        if "cdrom" in (getattr(part, "opts", "") or "").lower() or not getattr(part, "fstype", ""):
            continue
        try:
            usage = ps.disk_usage(part.mountpoint)
        except Exception:
            continue
        if usage.total < GB:
            continue                    # winzige/virtuelle Laufwerke interessieren nicht
        drives.append({"name": part.mountpoint, "total_gb": _gb(usage.total),
                       "free_gb": _gb(usage.free), "used_percent": _percent(usage.percent)})
    return drives


def facts(ps=psutil):
    """Feste Eigenschaften des Rechners."""
    memory = ps.virtual_memory()
    frequency = None
    try:
        info = ps.cpu_freq()
        frequency = round(info.max or info.current) if info else None
    except Exception:
        pass
    return {
        "os": _system_name(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "cpu_name": _cpu_name(),
        "cpu_cores": ps.cpu_count(logical=False),
        "cpu_threads": ps.cpu_count(logical=True),
        "cpu_max_mhz": frequency or None,
        "ram_total_gb": _gb(memory.total),
        "drives": _drives(ps),
        "computer_name": platform.node(),
        "python_version": platform.python_version(),
        "has_battery": ps.sensors_battery() is not None if hasattr(ps, "sensors_battery") else False,
    }


class PerformanceMonitor:
    """Aktuelle Auslastung. Netzwerk-Tempo = Unterschied zwischen zwei Messungen."""

    def __init__(self, ps=psutil, clock=time.monotonic):
        self.ps = ps
        self.clock = clock
        self._lock = threading.Lock()
        self._last = None
        self._last_time = None
        self._net = None            # (zeit, bytes_recv, bytes_sent) der vorigen Messung
        try:
            self.ps.cpu_percent(interval=None)      # erste Messung ist immer 0: einmal "anwaermen"
        except Exception:
            pass

    def _network(self, now):
        try:
            counters = self.ps.net_io_counters()
        except Exception:
            return {"down_kb_s": 0.0, "up_kb_s": 0.0}
        if counters is None:
            return {"down_kb_s": 0.0, "up_kb_s": 0.0}
        previous, self._net = self._net, (now, counters.bytes_recv, counters.bytes_sent)
        if previous is None or now <= previous[0]:
            return {"down_kb_s": 0.0, "up_kb_s": 0.0}
        seconds = now - previous[0]
        down = max(0, counters.bytes_recv - previous[1]) / seconds / 1024
        up = max(0, counters.bytes_sent - previous[2]) / seconds / 1024
        return {"down_kb_s": round(down, 1), "up_kb_s": round(up, 1)}

    def _battery(self):
        try:
            battery = self.ps.sensors_battery()
        except Exception:
            return None
        if battery is None or battery.percent is None:
            return None
        return {"percent": _percent(battery.percent), "plugged": bool(battery.power_plugged)}

    def sample(self, fresh_cpu=False):
        """Messwerte als Dict. ``fresh_cpu`` misst die CPU 0,3 s lang (fuer einzelne Chat-Fragen)."""
        with self._lock:
            now = self.clock()
            if self._last is not None and now - self._last_time < MIN_INTERVAL and not fresh_cpu:
                return dict(self._last)
            memory = self.ps.virtual_memory()
            try:
                disk = self.ps.disk_usage(_system_drive())
                disk_info = {"disk_percent": _percent(disk.percent), "disk_used_gb": _gb(disk.used), "disk_total_gb": _gb(disk.total)}
            except Exception:
                disk_info = {"disk_percent": 0.0, "disk_used_gb": 0.0, "disk_total_gb": 0.0}
            try:
                boot = self.ps.boot_time()
                uptime = max(0, int(time.time() - boot))
            except Exception:
                uptime = None
            result = {
                "cpu_percent": _percent(self.ps.cpu_percent(interval=0.3 if fresh_cpu else None)),
                "ram_percent": _percent(memory.percent),
                "ram_used_gb": _gb(memory.total - memory.available),
                "ram_total_gb": _gb(memory.total),
                **disk_info,
                "battery": self._battery(),
                "network": self._network(now),
                "uptime_seconds": uptime,
            }
            self._last, self._last_time = result, now
            return dict(result)


def top_processes(ps=psutil, count=TOP_PROCESSES):
    """Programme mit dem meisten Arbeitsspeicher, nach Namen zusammengefasst: [{name, ram_mb, count}]."""
    totals = {}
    try:
        for proc in ps.process_iter(["name", "memory_info"]):
            try:
                info = proc.info
                name = info.get("name")
                memory = info.get("memory_info")
                if not isinstance(name, str) or memory is None:
                    continue
                entry = totals.setdefault(name[:60], [0, 0])
                entry[0] += memory.rss
                entry[1] += 1
            except Exception:
                continue
    except Exception:
        return []
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)[:count]
    return [{"name": name, "ram_mb": round(rss / (1024 ** 2)), "count": number} for name, (rss, number) in ranked]


_default_monitor = None


def default_monitor():
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = PerformanceMonitor()
    return _default_monitor


def set_default_monitor(monitor):
    global _default_monitor
    _default_monitor = monitor


def get_system_info():
    """Fakten + aktuelle Auslastung + groesste Programme fuer die Antwort im Chat."""
    try:
        data = {**facts(), "now": default_monitor().sample(fresh_cpu=True), "top_programs": top_processes()}
    except Exception as error:
        return ToolResult(success=False, error=f"Die Systemdaten konnten nicht gelesen werden: {error}")
    return ToolResult(success=True, data=data)
