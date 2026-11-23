"""PC-Agent (S6, DESIGN_GERAET.md): ein kleines Programm auf dem PC, das sich beim Jarvis-Server anmeldet und Auftraege ausfuehrt.

Der PC ruft den Server an (nie umgekehrt): Es muss kein Port am PC offen sein. Der Agent fragt per Long-Polling "gibt es etwas fuer
mich?", fuehrt hoechstens Auftraege aus der festen Liste in device_commands.py aus und schickt das Ergebnis zurueck.

Aufruf:  py pc_agent.py --pair CODE --server https://jarvis-1.taild3a628.ts.net     einmal koppeln (Code vom Server: server_main.py --pair-agent)
         py pc_agent.py                                                              laufen lassen (beenden mit Strg+C)

Das Token steht nur in agent_config.json auf diesem PC (nicht in Git). Nur Standardbibliothek, keine zusaetzlichen Pakete.
"""
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import device_commands

CONFIG_FILE = Path(__file__).resolve().parent / "agent_config.json"
POLL_WAIT = 25                    # Sekunden, die der Server einen Long-Poll offen halten darf
REQUEST_TIMEOUT = POLL_WAIT + 15  # Netz-Zeitlimit pro Anfrage
RETRY_MIN = 2
RETRY_MAX = 30


class HttpTransport:
    """POST mit JSON an den Server. Gibt (Status, Antwort) zurueck; (0, None) heisst: nicht erreichbar."""

    def __init__(self, base_url, timeout=REQUEST_TIMEOUT):
        parsed = urlparse(base_url)
        local = parsed.hostname in ("localhost", "127.0.0.1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local) or not parsed.hostname or parsed.path not in ("", "/"):
            raise ValueError("Die Server-Adresse muss so aussehen: https://jarvis-1.taild3a628.ts.net")
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.timeout = timeout

    def post(self, path, body, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, _json(response.read())
        except urllib.error.HTTPError as error:
            return error.code, _json(error.read())
        except (urllib.error.URLError, OSError, ValueError):
            return 0, None


def _json(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


# --- die Auftraege, die dieser Agent kann (jeder steht auch in device_commands.COMMANDS) -------------------
def handle_ping(args):
    return {"name": socket.gethostname()[:40], "time": datetime.now().isoformat(timespec="seconds"),
            "version": device_commands.AGENT_VERSION}


def default_handlers():
    """Die Auftraege dieses PCs. Die Messfunktionen werden erst beim ersten Auftrag geladen (und behalten ihre Zwischenspeicher)."""
    state = {}

    def tools():
        if not state:
            from tools import pc_health, system_status_tool
            monitor = system_status_tool.PerformanceMonitor()
            state.update(sst=system_status_tool, monitor=monitor, health=pc_health.PcHealth(monitor=monitor))
        return state

    return {
        "ping": handle_ping,
        "pc.facts": lambda args: tools()["sst"].facts(),
        "pc.performance": lambda args: tools()["monitor"].sample(fresh_cpu=args["fresh"]),
        "pc.top": lambda args: tools()["sst"].top_processes(),
        "pc.snapshot": lambda args: tools()["health"].snapshot(),
    }


HANDLERS = {"ping": handle_ping}


class Agent:
    def __init__(self, transport, token, handlers=None, log=print, sleep=time.sleep):
        self.transport = transport
        self.token = token
        self.handlers = default_handlers() if handlers is None else handlers
        self.log = log
        self.sleep = sleep

    def run_job(self, job):
        """Fuehrt einen Auftrag aus der Liste aus. Gibt (ok, Ergebnis) zurueck; nie eine Ausnahme."""
        try:
            command = job.get("command")
            args = device_commands.check_args(command, job.get("args"))
            handler = self.handlers.get(command)
            if handler is None:
                raise device_commands.CommandError("Auftrag nicht eingebaut.")
            return True, handler(args)
        except Exception as error:                       # ein kaputter Auftrag darf den Agent nie beenden
            self.log(f"Auftrag fehlgeschlagen: {type(error).__name__}")
            return False, None

    def step(self):
        """Ein Durchgang: Auftrag holen, ausfuehren, Ergebnis abgeben.

        Gibt zurueck: "idle" (nichts da), "done" (Auftrag erledigt), "offline" (Server nicht erreichbar), "unauthorized" (Token ungueltig oder gesperrt)."""
        status, data = self.transport.post("/agent/next", {"wait": POLL_WAIT}, self.token)
        if status == 401:
            return "unauthorized"
        if status != 200 or data is None:
            return "offline"
        job = data.get("job")
        if not isinstance(job, dict) or not isinstance(job.get("id"), str):
            return "idle"
        ok, result = self.run_job(job)
        status, _ = self.transport.post("/agent/result", {"id": job["id"], "ok": ok, "data": result}, self.token)
        if status == 401:
            return "unauthorized"
        self.log(f"Auftrag {job.get('command')}: {'ok' if ok else 'Fehler'}")
        return "done"

    def run(self, should_stop=lambda: False):
        """Dauerschleife. Bei Netzproblemen wird mit wachsender Pause neu versucht; bei ungueltigem Token endet sie."""
        pause = RETRY_MIN
        connected = False
        while not should_stop():
            state = self.step()
            if state == "unauthorized":
                self.log("Der Server nimmt das Token nicht mehr an (gesperrt oder entfernt). Bitte neu koppeln: --pair CODE --server ...")
                return 1
            if state == "offline":
                if connected:
                    self.log("Server nicht erreichbar, ich versuche es weiter ...")
                connected = False
                self.sleep(pause)
                pause = min(pause * 2, RETRY_MAX)
                continue
            if not connected:
                self.log("Verbunden mit dem Jarvis-Server.")
                connected = True
            pause = RETRY_MIN
        return 0


# --- Kopplung und Start ------------------------------------------------------------------------
def pair(code, server_url, transport=None, path=CONFIG_FILE, log=print):
    """Loest den Kopplungscode ein und speichert Adresse und Token. 0 = gekoppelt, 1 = Fehler."""
    try:
        transport = transport or HttpTransport(server_url)
    except ValueError as error:
        log(str(error))
        return 1
    status, data = transport.post("/agent/pair", {"code": code})
    if status != 200 or not data or not isinstance(data.get("token"), str):
        if status == 0:
            log("Der Server ist nicht erreichbar. Läuft Tailscale auf diesem PC und der Server?")
        else:
            log((data or {}).get("error") or "Die Kopplung hat nicht geklappt.")
        return 1
    path = Path(path)
    path.write_text(json.dumps({"server": server_url, "token": data["token"]}), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    log(f"Gekoppelt als \"{data.get('name', 'PC')}\". Starte den Agent jetzt mit:  py pc_agent.py")
    return 0


def load_config(path=CONFIG_FILE):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("server"), str) and isinstance(data.get("token"), str):
        return data
    return None


def main(argv=None, config_path=CONFIG_FILE, log=print):
    argv = sys.argv[1:] if argv is None else argv
    if "--pair" in argv:
        index = argv.index("--pair")
        code = argv[index + 1] if index + 1 < len(argv) and not argv[index + 1].startswith("--") else ""
        server_url = argv[argv.index("--server") + 1] if "--server" in argv and argv.index("--server") + 1 < len(argv) else ""
        if server_url.startswith("--"):
            server_url = ""
        if not code or not server_url:
            log("Aufruf: py pc_agent.py --pair CODE --server https://jarvis-1.taild3a628.ts.net")
            return 1
        return pair(code, server_url, path=config_path, log=log)
    config = load_config(config_path)
    if config is None:
        log("Noch nicht gekoppelt. Zuerst: py pc_agent.py --pair CODE --server https://...  (Code vom Server: server_main.py --pair-agent)")
        return 1
    try:
        agent = Agent(HttpTransport(config["server"]), config["token"], log=log)
    except ValueError as error:
        log(str(error))
        return 1
    log("PC-Agent läuft (beenden mit Strg+C).")
    try:
        return agent.run()
    except KeyboardInterrupt:
        log("PC-Agent beendet.")
        return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
