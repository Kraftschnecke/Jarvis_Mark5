"""PC-Agent (S6, DESIGN_GERAET.md): ein kleines Programm auf dem PC, das sich beim Jarvis-Server anmeldet und Auftraege ausfuehrt.

Der PC ruft den Server an (nie umgekehrt): Es muss kein Port am PC offen sein. Der Agent fragt per Long-Polling "gibt es etwas fuer
mich?", fuehrt hoechstens Auftraege aus der festen Liste in device_commands.py aus und schickt das Ergebnis zurueck.

Aufruf:  py pc_agent.py --pair CODE --server https://jarvis-1.taild3a628.ts.net     einmal koppeln (Code vom Server: server_main.py --pair-agent)
         py pc_agent.py                                                              laufen lassen (beenden mit Strg+C)
         py pc_agent.py --autostart on|off|status                                    beim Anmelden am PC automatisch (unsichtbar) starten
         py pc_agent.py --folders list|add PFAD|remove PFAD                          Ordner freigeben (nur hier am PC), die Jarvis durchsuchen darf
         py pc_agent.py --stop | --restart                                           den laufenden Agent beenden / neu starten (z. B. nach einem Update)

Das Token steht nur in agent_config.json auf diesem PC (nicht in Git). Nur Standardbibliothek, keine zusaetzlichen Pakete.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import device_commands
from tools.tool_result import ToolResult

CONFIG_FILE = Path(__file__).resolve().parent / "agent_config.json"
LOG_FILE = Path(__file__).resolve().parent / "agent.log"
LOG_MAX_BYTES = 200 * 1024
INSTANCE_PORT = 47831             # nur auf 127.0.0.1: verhindert, dass der Agent zweimal laeuft, und nimmt "stop" an
AUTOSTART_NAME = "JarvisAgent.vbs"
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

    def volume_set(args):
        from tools import volume_tool
        result = volume_tool.set_volume(args["percent"])
        if not result.success:
            raise RuntimeError("volume")                 # Text bleibt auf dem PC: der Server nimmt keinen Fehlertext vom Agenten an
        return {"percent": args["percent"]}

    def media_key(args):
        from tools import media_tool
        result = media_tool.media_control(args["action"])
        if not result.success:
            raise RuntimeError("media")
        return {"command": args["action"]}

    def envelope(result):
        """ToolResult -> Antwort an den Server: ok/Fehler, Fehlertext (vom Werkzeug selbst, ohne Pfade aus Ausnahmen) und Daten."""
        error = result.error if isinstance(result.error, str) else None
        return {"success": bool(result.success), "error": None if result.success else (error or "Das hat nicht geklappt.")[:400],
                "data": result.data if result.success else None}

    def files_find(args):
        from tools import file_search_tool
        return envelope(file_search_tool.default_search().find(args["query"], args["mode"], args["file_type"], args["folder"], args["count"]))

    def files_read(args):
        from tools import document_tool
        return envelope(document_tool.default_reader().read(args["file"], args["part"], args["question"]))

    def note(method):
        def run(args):
            from tools import note_tool
            writer = note_tool.default_writer()
            call = (args["filename"], args["content"], args["folder"], args["mode"])
            if method == "write":
                return envelope(writer.write(*call))
            if method == "check":
                return envelope(ToolResult(success=True, data={"problem": writer.check(*call)}))
            return envelope(ToolResult(success=True, data={"lines": writer.describe(*call)}))
        return run

    def system_run(args):
        from tools import system_tool
        return envelope(system_tool.system_control(args["command"], args["value"]))

    def programs_find(args):
        from tools import program_tool
        return envelope(program_tool.find_program(args["program"]))

    def programs_launch(args):
        from tools import program_tool
        return envelope(program_tool.launch_program(args["target"]))

    def processes_list(args):
        from tools import process_tool
        result = process_tool.get_running_programs()
        if not result.success:
            return {"success": False, "error": "Die Prozessliste ließ sich nicht lesen.", "data": None}
        return {"success": True, "error": None, "data": [str(name)[:100] for name in result.data][:300]}

    def clipboard_read(args):
        from tools import clipboard_tool
        return envelope(clipboard_tool.read_clipboard(args["question"]))

    def screen_capture(args):
        from tools import screen_tool
        result = screen_tool.describe_screen("")
        if not result.success:
            return {"success": False, "error": (result.error or "Die Bildschirmaufnahme hat nicht geklappt.")[:400], "data": None}
        return {"success": True, "error": None, "data": {"image": result.data[screen_tool.IMAGE_KEY]}}

    def browser_open(args):
        from tools import browser_tool
        return envelope(browser_tool.open_website(args["url"], args["query"]))

    def folders_list(args):
        import folders
        return {"folders": folders.default_list().list()}

    return {
        "folders.list": folders_list,
        "files.find": files_find,
        "files.read": files_read,
        "notes.check": note("check"),
        "notes.describe": note("describe"),
        "notes.write": note("write"),
        "system.run": system_run,
        "programs.find": programs_find,
        "programs.launch": programs_launch,
        "processes.list": processes_list,
        "clipboard.read": clipboard_read,
        "screen.capture": screen_capture,
        "browser.open": browser_open,
        "volume.set": volume_set,
        "media.key": media_key,
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


# --- Hintergrundbetrieb: Logdatei, nur eine Instanz, Autostart ----------------------------------------
def file_logger(path=LOG_FILE, max_bytes=LOG_MAX_BYTES):
    """Log-Funktion fuer den unsichtbaren Betrieb (kein Fenster): schreibt Zeitstempel + Text in eine Datei, die nie gross wird."""
    path = Path(path)

    def log(text):
        try:
            if path.exists() and path.stat().st_size > max_bytes:
                old = path.with_name(path.name + ".old")
                old.unlink(missing_ok=True)
                path.replace(old)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now().isoformat(timespec='seconds')}  {text}\n")
        except OSError:
            pass                                    # Logdatei nicht schreibbar: der Agent laeuft trotzdem
    return log


class SingleInstance:
    """Haelt einen Port auf 127.0.0.1 besetzt: Ein zweiter Agent merkt es und beendet sich. Wer dort "stop" schickt, beendet den ersten."""

    def __init__(self, port=INSTANCE_PORT):
        self.port = port
        self.stopped = threading.Event()
        self._sock = None
        self._thread = None

    def acquire(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):          # Windows: kein zweiter Besitzer des Ports (SO_REUSEADDR waere dort das Gegenteil)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:                                               # sonst: kurz nach "stop" darf der Port sofort wieder belegt werden
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", self.port))
            sock.listen(2)
            sock.settimeout(0.5)
        except OSError:
            sock.close()
            return False
        self.port = sock.getsockname()[1]
        self._sock = sock
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return True

    def _listen(self):
        while self._sock is not None:
            try:
                connection, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(1)
                    if connection.recv(16).strip() == b"stop":
                        self.stopped.set()
                except OSError:
                    pass

    def release(self):
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()
        if self._thread is not None:
            self._thread.join(2)


def request_stop(port=INSTANCE_PORT, wait=60, sleep=time.sleep):
    """Sagt dem laufenden Agent "stop" und wartet, bis er weg ist. Gibt zurueck: "none" (lief keiner), "stopped" oder "timeout"."""
    def alive():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1) as connection:
                connection.sendall(b"stop")
            return True
        except OSError:
            return False

    if not alive():
        return "none"
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        sleep(1)
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        except OSError:
            return "stopped"
    return "timeout"


def background_python():
    """pythonw.exe (ohne Konsolenfenster), wenn es neben python.exe liegt, sonst der aktuelle Python."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def autostart_script(python, script):
    """Text der kleinen .vbs-Datei im Autostart-Ordner: startet den Agent unsichtbar (Fenstermodus 0), im Jarvis-Ordner."""
    quote = lambda text: str(text).replace('"', '""')
    folder = Path(script).parent
    return ('Set shell = CreateObject("WScript.Shell")\r\n'
            f'shell.CurrentDirectory = "{quote(folder)}"\r\n'
            f'shell.Run """{quote(python)}"" ""{quote(script)}"" --background", 0, False\r\n')


def autostart(action, folder=None, python=None, script=None, log=print):
    """--autostart on|off|status. 0 = ok, 1 = Fehler."""
    folder = startup_dir() if folder is None else Path(folder)
    if folder is None or not folder.parent.exists():
        log("Den Autostart-Ordner von Windows gibt es hier nicht (das geht nur unter Windows).")
        return 1
    target = folder / AUTOSTART_NAME
    if action == "status":
        log("Autostart ist AN." if target.exists() else "Autostart ist AUS.")
        return 0
    if action == "off":
        try:
            target.unlink(missing_ok=True)
        except OSError as error:
            log(f"Das ging nicht: {error}")
            return 1
        log("Autostart ist jetzt AUS.")
        return 0
    if action == "on":
        text = autostart_script(python or background_python(), script or Path(__file__).resolve())
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-16")      # mit Kennzeichen, so liest Windows auch Umlaute im Pfad richtig
        except OSError as error:
            log(f"Das ging nicht: {error}")
            return 1
        log("Autostart ist jetzt AN: Der Agent startet bei jeder Anmeldung am PC von selbst (unsichtbar, Protokoll: agent.log).")
        return 0
    log("Aufruf: py pc_agent.py --autostart on|off|status")
    return 1


def folders_command(words, folder_list=None, log=print):
    """--folders list | add PFAD | remove PFAD: Ordner freigeben geht nur hier am PC (der Server kann es nicht)."""
    import folders as folders_module
    shared = folder_list or folders_module.default_list()
    action = words[0] if words else ""
    try:
        if action == "list" and len(words) == 1:
            items = shared.list()
        elif action in ("add", "remove") and len(words) == 2:
            items = shared.add(words[1]) if action == "add" else shared.remove(words[1])
        else:
            log("Aufruf: py pc_agent.py --folders list | add \"C:\\Pfad\" | remove \"C:\\Pfad\"")
            return 1
    except folders_module.AccessError as error:
        log(str(error))
        return 1
    log("Freigegebene Ordner: " + (", ".join(f["path"] + ("" if f["exists"] else " (gibt es nicht mehr)") for f in items) or "keine"))
    return 0


def restart_background(script=None, python=None):
    """Startet einen neuen Agent unsichtbar und ohne Verbindung zu diesem Fenster."""
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    script = str(script or Path(__file__).resolve())
    subprocess.Popen([python or background_python(), script, "--background"], cwd=str(Path(script).parent), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


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


def main(argv=None, config_path=CONFIG_FILE, log=print, lock_port=INSTANCE_PORT, log_path=LOG_FILE, startup=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--background" in argv:
        log = file_logger(log_path)                      # unsichtbar gestartet: es gibt kein Fenster zum Mitlesen
    if "--autostart" in argv:
        index = argv.index("--autostart")
        return autostart(argv[index + 1] if index + 1 < len(argv) else "", folder=startup, log=log)
    if "--folders" in argv:
        index = argv.index("--folders")
        return folders_command(argv[index + 1:index + 3], log=log)
    if "--stop" in argv or "--restart" in argv:
        outcome = request_stop(lock_port)
        if outcome == "timeout":
            log("Der Agent hat sich nicht beendet (bitte im Task-Manager \"pythonw.exe\" beenden).")
            return 1
        log("Der Agent wurde beendet." if outcome == "stopped" else "Es lief kein Agent.")
        if "--restart" in argv:
            restart_background()
            log("Neuer Agent gestartet (unsichtbar, Protokoll: agent.log).")
        return 0
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
    instance = SingleInstance(lock_port)
    if not instance.acquire():
        log("Der PC-Agent läuft schon. (Beenden: py pc_agent.py --stop)")
        return 0
    log("PC-Agent läuft (beenden mit Strg+C)." if "--background" not in argv else "PC-Agent gestartet.")
    try:
        result = agent.run(should_stop=instance.stopped.is_set)
        log("PC-Agent beendet.")
        return result
    except KeyboardInterrupt:
        log("PC-Agent beendet.")
        return 0
    finally:
        instance.release()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
