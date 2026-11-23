"""PC-Agent (S6): fuehrt nur Auftraege aus der Liste aus, gibt nie auf, endet bei ungueltigem Token, koppelt sicher."""
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_commands
import pc_agent


class FakeTransport:
    """Antwortet der Reihe nach; merkt sich jede Anfrage."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, path, body, token=None):
        self.calls.append((path, body, token))
        return self.replies.pop(0) if self.replies else (200, {"job": None})


def agent_with(replies, handlers=None):
    logs = []
    sleeps = []
    transport = FakeTransport(replies)
    return pc_agent.Agent(transport, "tok.secret", handlers=handlers, log=logs.append, sleep=sleeps.append), transport, logs, sleeps


# 1) Adresse: https, oder http nur zum eigenen Rechner; kein Pfad, kein Unsinn
assert pc_agent.HttpTransport("https://jarvis-1.taild3a628.ts.net").base == "https://jarvis-1.taild3a628.ts.net"
assert pc_agent.HttpTransport("http://localhost:8000").base == "http://localhost:8000"
assert pc_agent.HttpTransport("http://127.0.0.1:8000/").base == "http://127.0.0.1:8000"
for bad in ("http://jarvis-1.taild3a628.ts.net", "ftp://x", "jarvis-1", "", "https://", "https://host/pfad", "file:///etc/passwd"):
    try:
        pc_agent.HttpTransport(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

# 2) Nichts da: "idle"; die Anfrage traegt das Token und die Wartezeit
agent, transport, logs, _ = agent_with([(200, {"job": None})])
assert agent.step() == "idle"
assert transport.calls == [("/agent/next", {"wait": pc_agent.POLL_WAIT}, "tok.secret")]

# 3) Ping: ausgefuehrt, Ergebnis passt zur Liste und geht mit der Auftrags-Id zurueck
agent, transport, logs, _ = agent_with([(200, {"job": {"id": "j1", "command": "ping", "args": {}}}), (200, {"ok": True})])
assert agent.step() == "done"
path, body, token = transport.calls[1]
assert path == "/agent/result" and token == "tok.secret" and body["id"] == "j1" and body["ok"] is True
assert device_commands.check_result("ping", body["data"]) == body["data"] and body["data"]["version"] == device_commands.AGENT_VERSION
assert logs == ["Auftrag ping: ok"]

# 4) Alles ausserhalb der Liste wird nicht ausgefuehrt und als Fehler gemeldet (der Agent laeuft weiter)
ran = []
handlers = {"ping": lambda args: ran.append("ping") or {"name": "x", "time": "t", "version": 1}, "rm": lambda args: ran.append("rm")}
for job in ({"id": "j", "command": "rm", "args": {}}, {"id": "j", "command": "ping", "args": {"x": 1}},
            {"id": "j", "command": 5, "args": {}}, {"id": "j", "command": "ping", "args": "text"},
            {"id": "j", "command": "ping" * 1000, "args": None}):
    agent, transport, logs, _ = agent_with([(200, {"job": job}), (200, {"ok": True})], handlers)
    assert agent.step() == "done"
    assert transport.calls[1][1] == {"id": "j", "ok": False, "data": None}, job
assert ran == []

# 5) Ein Handler, der abstuerzt, beendet den Agent nicht; im Log steht nur der Fehlertyp
def kaputt(args):
    raise RuntimeError("geheim C:\\Users\\x")


agent, transport, logs, _ = agent_with([(200, {"job": {"id": "j", "command": "ping", "args": {}}}), (200, {"ok": True})], {"ping": kaputt})
assert agent.step() == "done" and transport.calls[1][1]["ok"] is False
assert any("RuntimeError" in line for line in logs) and not any("geheim" in line for line in logs)

# 6) Kein Auftrag im Antwortformat (kaputte Antworten) = nichts zu tun, kein Absturz
for reply in ((200, {"job": "x"}), (200, {"job": {"command": "ping"}}), (200, {"job": {"id": 5}}), (200, {})):
    agent, transport, _, _ = agent_with([reply])
    assert agent.step() == "idle", reply

# 7) Server nicht erreichbar oder Fehler: "offline"; Token ungueltig (auch erst beim Ergebnis): "unauthorized"
for reply in ((0, None), (500, {"error": "x"}), (200, None), (503, None)):
    agent, _, _, _ = agent_with([reply])
    assert agent.step() == "offline", reply
agent, _, _, _ = agent_with([(401, {"error": "Nicht angemeldet."})])
assert agent.step() == "unauthorized"
agent, _, _, _ = agent_with([(200, {"job": {"id": "j", "command": "ping", "args": {}}}), (401, {})])
assert agent.step() == "unauthorized"

# 8) Dauerschleife: Pause waechst bis 30 und beginnt nach Erfolg wieder bei 2; "Verbunden" nur einmal, "nicht erreichbar" nur wenn vorher verbunden
agent, transport, logs, sleeps = agent_with([(0, None)] * 6 + [(200, {"job": None}), (200, {"job": None}), (0, None), (0, None),
                                                              (200, {"job": None}), (401, {})])
assert agent.run() == 1
assert sleeps == [2, 4, 8, 16, 30, 30, 2, 4], sleeps       # nach Erfolg wieder bei 2
assert logs.count("Verbunden mit dem Jarvis-Server.") == 2
assert sum("nicht erreichbar" in line for line in logs) == 1
assert any("neu koppeln" in line for line in logs)

stops = iter([False, False, True])
agent, transport, logs, _ = agent_with([(200, {"job": None})] * 5)
assert agent.run(should_stop=lambda: next(stops)) == 0 and len(transport.calls) == 2

# 9) Kopplung: Token wird gespeichert (nur Besitzer darf lesen), das Token steht nie im Log
folder = Path(tempfile.mkdtemp())
config = folder / "agent_config.json"
logs = []
transport = FakeTransport([(200, {"token": "abcd1234.verySecretToken", "name": "PC Moritz"})])
assert pc_agent.pair("K7M2-QX9P", "https://jarvis-1.taild3a628.ts.net", transport=transport, path=config, log=logs.append) == 0
assert transport.calls == [("/agent/pair", {"code": "K7M2-QX9P"}, None)]
assert json.loads(config.read_text()) == {"server": "https://jarvis-1.taild3a628.ts.net", "token": "abcd1234.verySecretToken"}
assert not any("verySecretToken" in line for line in logs) and any("PC Moritz" in line for line in logs)
if os.name != "nt":
    assert oct(config.stat().st_mode & 0o777) == "0o600"
assert pc_agent.load_config(config) == {"server": "https://jarvis-1.taild3a628.ts.net", "token": "abcd1234.verySecretToken"}

# 10) Kopplung scheitert: nichts wird geschrieben, die Meldung ist verstaendlich
for reply, expected in (((0, None), "nicht erreichbar"), ((400, {"error": "Der Code ist ungültig, abgelaufen oder schon benutzt."}), "ungültig"),
                        ((200, {"token": 5}), "nicht geklappt"), ((200, None), "nicht geklappt"), ((429, {"error": "Zu viele Versuche."}), "Zu viele")):
    other = folder / "x.json"
    logs = []
    assert pc_agent.pair("CODE", "https://h.ts.net", transport=FakeTransport([reply]), path=other, log=logs.append) == 1
    assert not other.exists() and expected in logs[0], (reply, logs)
logs = []
assert pc_agent.pair("CODE", "http://boese.example", path=folder / "y.json", log=logs.append) == 1 and not (folder / "y.json").exists()

# 11) Konfiguration: kaputte oder unvollstaendige Dateien zaehlen als "nicht gekoppelt"
for content in ("{kaputt", "[]", '{"server": "x"}', '{"token": "t"}', '{"server": 1, "token": 2}', ""):
    config.write_text(content)
    assert pc_agent.load_config(config) is None, content
assert pc_agent.load_config(folder / "gibt_es_nicht.json") is None

# 12) Start ohne Kopplung / falsche Aufrufe
logs = []
assert pc_agent.main([], config_path=folder / "nix.json", log=logs.append) == 1 and "Noch nicht gekoppelt" in logs[0]
for argv in (["--pair"], ["--pair", "CODE"], ["--pair", "CODE", "--server"], ["--pair", "--server", "https://x.ts.net"], ["--pair", "CODE", "--server", "--pair"]):
    logs = []
    assert pc_agent.main(argv, config_path=folder / "nix.json", log=logs.append) == 1 and logs and "Aufruf" in logs[0], argv

# 13) Die echten Auftraege des PCs (S6, G2): laden die Messfunktionen erst beim ersten Auftrag, geben "fresh" weiter, teilen sich den Monitor
from tools import pc_health, system_status_tool

calls = []
made = []


class FakeMonitor:
    def __init__(self):
        made.append(self)

    def sample(self, fresh_cpu=False):
        calls.append(("sample", fresh_cpu))
        return {"cpu_percent": 1.0}


class FakeHealth:
    def __init__(self, monitor=None):
        self.monitor = monitor

    def snapshot(self):
        calls.append(("snapshot", self.monitor is made[0]))
        return {"drives": []}


real = (system_status_tool.PerformanceMonitor, system_status_tool.facts, system_status_tool.top_processes, pc_health.PcHealth)
system_status_tool.PerformanceMonitor = FakeMonitor
system_status_tool.facts = lambda: calls.append("facts") or {"os": "Test"}
system_status_tool.top_processes = lambda: calls.append("top") or []
pc_health.PcHealth = FakeHealth
try:
    handlers = pc_agent.default_handlers()
    assert set(handlers) == set(device_commands.COMMANDS) and made == [] and calls == [], "nichts wird vor dem ersten Auftrag geladen"
    assert handlers["pc.performance"]({"fresh": True}) == {"cpu_percent": 1.0} and calls[-1] == ("sample", True)
    assert handlers["pc.performance"]({"fresh": False}) and calls[-1] == ("sample", False)
    assert handlers["pc.facts"]({}) == {"os": "Test"} and handlers["pc.top"]({}) == []
    assert handlers["pc.snapshot"]({}) == {"drives": []} and calls[-1] == ("snapshot", True), "PC-Lage nutzt denselben Monitor"
    assert len(made) == 1, "ein Monitor fuer alles"
    assert pc_agent.default_handlers() is not handlers and set(pc_agent.HANDLERS) == {"ping"}
finally:
    system_status_tool.PerformanceMonitor, system_status_tool.facts, system_status_tool.top_processes, pc_health.PcHealth = real

# 14) Jeder Auftrag der Liste hat einen Handler und umgekehrt; echte Messwerte (ohne PC-Lage: sie startet PowerShell) passen zu den Mustern
assert set(pc_agent.default_handlers()) == set(device_commands.COMMANDS)
real_handlers = pc_agent.default_handlers()
for command, args in (("pc.facts", None), ("pc.top", None), ("pc.performance", {"fresh": True}), ("ping", None)):
    clean_args = device_commands.check_args(command, args)
    data = json.loads(json.dumps(real_handlers[command](clean_args)))
    assert device_commands.check_result(command, data), command

print("ALL TESTS PASSED")
