"""Der PC aus Sicht des Servers (S6, DESIGN_GERAET.md): PC-Daten kommen vom PC-Agent statt vom eigenen Rechner.

Im Server-Betrieb (server_main.py) ersetzt ``install`` die lokalen Messungen: Fenster (PC-Status, PC-Lage, Laufwerke), Chat und die
automatischen PC-Warnungen fragen dann den PC. Der Agent liefert nur Messwerte; die Bewertung ("PC-Lage") rechnet der Server selbst
(``pc_health.assess``), so kann der Agent keine Texte in die Anzeige oder den Chat einschleusen. Ist der PC aus, wirft jeder Aufruf
``device_hub.DeviceOffline`` ("Der PC ist gerade nicht erreichbar.").
"""
from tools import pc_health
import remote_files
from tools import media_tool, system_status_tool, volume_tool


class RemoteMonitor:
    """Wie PerformanceMonitor, aber gemessen auf dem PC."""

    def __init__(self, hub):
        self.hub = hub

    def sample(self, fresh_cpu=False):
        return self.hub.request("pc.performance", {"fresh": bool(fresh_cpu)})


class RemoteHealth:
    """Wie PcHealth, aber gemessen auf dem PC; bewertet wird hier."""

    def __init__(self, hub):
        self.hub = hub

    def snapshot(self):
        return self.hub.request("pc.snapshot")

    def report(self):
        data = self.snapshot()
        return {**data, "assessment": pc_health.assess(data)}


class RemotePc:
    def __init__(self, hub):
        self.hub = hub
        self.monitor = RemoteMonitor(hub)
        self.health = RemoteHealth(hub)

    def facts(self):
        return self.hub.request("pc.facts")

    def top_processes(self):
        return self.hub.request("pc.top")


def install(server):
    """Haengt den PC-Agent als Quelle aller PC-Daten ein (Fenster, Chat, Warnungen). Gibt das RemotePc zurueck."""
    pc = RemotePc(server.hub)
    system_status_tool.set_remote(pc)
    system_status_tool.set_default_monitor(pc.monitor)
    pc_health.set_default_health(pc.health)
    remote_files.install(server.hub)
    volume_tool.set_remote(server.hub)
    media_tool.set_remote(server.hub)
    server.monitor = pc.monitor
    server.health = pc.health
    return pc
