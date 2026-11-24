"""PC-Agent im Hintergrund (S6, G4): Logdatei, nur eine Instanz, stop/restart, Autostart-Datei."""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import pc_agent

tmp = Path(tempfile.mkdtemp())

# 1) Logdatei: Zeitstempel, wird nie gross (alte Datei wandert nach .old), unbeschreibbar = kein Absturz
log_file = tmp / "agent.log"
log = pc_agent.file_logger(log_file, max_bytes=300)
log("Hallo Wörld")
line = log_file.read_text(encoding="utf-8")
assert line.endswith("  Hallo Wörld\n") and line[4] == "-" and "T" in line[:19], line
for i in range(40):
    log(f"Zeile {i} " + "x" * 20)
assert log_file.stat().st_size <= 300 + 80 and (tmp / "agent.log.old").exists()
assert "Zeile 39" in log_file.read_text(encoding="utf-8")
pc_agent.file_logger(tmp / "fehlt" / "x.log")("kein Absturz")

# 2) Nur eine Instanz: zweiter Versuch scheitert, nach release geht es wieder
first = pc_agent.SingleInstance(0)
assert first.acquire() and first.port > 0
second = pc_agent.SingleInstance(first.port)
assert not second.acquire()
assert not first.stopped.is_set()
assert first._sock.getsockname()[0] == "127.0.0.1"                 # nie von aussen erreichbar
first.release()
third = pc_agent.SingleInstance(first.port)
assert third.acquire()
third.release()

# 3) stop: niemand da = "none"; sonst setzt es das Flag, und "stopped" kommt erst, wenn der Agent den Port freigibt
free = pc_agent.SingleInstance(0)
assert free.acquire()
port = free.port
free.release()
assert pc_agent.request_stop(port, wait=2) == "none"

inst = pc_agent.SingleInstance(0)
assert inst.acquire()


def exit_when_stopped():
    inst.stopped.wait(10)
    time.sleep(0.3)
    inst.release()


worker = threading.Thread(target=exit_when_stopped)
worker.start()
assert pc_agent.request_stop(inst.port, wait=10) == "stopped" and inst.stopped.is_set()
worker.join(5)

stubborn = pc_agent.SingleInstance(0)                             # nimmt "stop" an, beendet sich aber nie
assert stubborn.acquire()
assert pc_agent.request_stop(stubborn.port, wait=1.5) == "timeout" and stubborn.stopped.is_set()
stubborn.release()

# nur das Wort "stop" zaehlt; anderes Zeug an dem Port ist harmlos
import socket
other = pc_agent.SingleInstance(0)
assert other.acquire()
with socket.create_connection(("127.0.0.1", other.port)) as c:
    c.sendall(b"hallo")
time.sleep(0.4)
assert not other.stopped.is_set()
other.release()

# 4) Autostart-Datei: unsichtbar (0), richtiger Ordner, pythonw, Anfuehrungszeichen verdoppelt, Umlaute im Pfad
startup = tmp / "AppData" / "Startup"
startup.parent.mkdir(parents=True)
messages = []
script = tmp / "Jarvis Mörit" / "pc_agent.py"
assert pc_agent.autostart("status", folder=startup, log=messages.append) == 0 and "AUS" in messages[-1]
assert pc_agent.autostart("on", folder=startup, python=r"C:\Python\pythonw.exe", script=script, log=messages.append) == 0 and "AN" in messages[-1]
target = startup / pc_agent.AUTOSTART_NAME
text = target.read_text(encoding="utf-16")
assert 'CreateObject("WScript.Shell")' in text and ", 0, False" in text and "--background" in text, text
assert f'shell.CurrentDirectory = "{script.parent}"' in text and 'Jarvis Mörit' in text
assert 'shell.Run """C:\\Python\\pythonw.exe"" ""' in text and 'pc_agent.py"" --background"' in text
assert pc_agent.autostart("status", folder=startup, log=messages.append) == 0 and "AN" in messages[-1]
assert pc_agent.autostart("on", folder=startup, python="p.exe", script=script, log=messages.append) == 0     # zweimal an ist ok
assert pc_agent.autostart("off", folder=startup, log=messages.append) == 0 and not target.exists()
assert pc_agent.autostart("off", folder=startup, log=messages.append) == 0                                    # zweimal aus ist ok
assert pc_agent.autostart("kaputt", folder=startup, log=messages.append) == 1 and "Aufruf" in messages[-1]
assert pc_agent.autostart("", folder=startup, log=messages.append) == 1
assert pc_agent.autostart("on", folder=tmp / "gibts" / "nicht", log=messages.append) == 1 and "Windows" in messages[-1]
assert pc_agent.autostart_script('a"b', Path("/x/y.py")).count('""') >= 2

# 5) main: --autostart, --background (Log in Datei statt Fenster), schon laufend, stop/restart, sauberes Beenden
config = tmp / "cfg.json"
config.write_text(json.dumps({"server": "https://jarvis-1.example.ts.net", "token": "t"}), encoding="utf-8")
console = []
bg_log = tmp / "bg.log"
assert pc_agent.main(["--autostart", "on", "--background"], config_path=config, log=console.append, log_path=bg_log, startup=startup) == 0
assert not console and (startup / pc_agent.AUTOSTART_NAME).exists() and "Autostart ist jetzt AN" in bg_log.read_text(encoding="utf-8")
assert pc_agent.main(["--autostart", "off"], config_path=config, log=console.append, startup=startup) == 0 and "AUS" in console[-1]
assert pc_agent.main(["--autostart"], config_path=config, log=console.append, startup=startup) == 1

holder = pc_agent.SingleInstance(0)
assert holder.acquire()
console.clear()
assert pc_agent.main([], config_path=config, log=console.append, lock_port=holder.port) == 0 and "läuft schon" in console[0]

restarts = []
orig_restart = pc_agent.restart_background
pc_agent.restart_background = lambda *a, **k: restarts.append(1)
try:
    threading.Thread(target=lambda: (holder.stopped.wait(10), time.sleep(0.3), holder.release())).start()
    console.clear()
    assert pc_agent.main(["--restart"], config_path=config, log=console.append, lock_port=holder.port) == 0
    assert "beendet" in console[0] and restarts == [1] and "Neuer Agent" in console[-1]
    assert pc_agent.main(["--stop"], config_path=config, log=console.append, lock_port=holder.port) == 0 and "kein Agent" in console[-1]
    assert restarts == [1]                                         # --stop startet nichts neu
    stubborn = pc_agent.SingleInstance(0)
    assert stubborn.acquire()
    orig_stop = pc_agent.request_stop
    pc_agent.request_stop = lambda port, **k: orig_stop(port, wait=1.2)
    try:
        assert pc_agent.main(["--stop"], config_path=config, log=console.append, lock_port=stubborn.port) == 1 and "Task-Manager" in console[-1]
    finally:
        pc_agent.request_stop = orig_stop
        stubborn.release()
finally:
    pc_agent.restart_background = orig_restart

# Lauf: der Agent bekommt das Stop-Flag der Instanz; nach "stop" endet main sauber und der Port ist frei
class FakeAgent:
    def __init__(self, transport, token, log=print):
        self.token = token

    def run(self, should_stop=lambda: False):
        while not should_stop():
            time.sleep(0.05)
        return 0


orig_agent = pc_agent.Agent
pc_agent.Agent = FakeAgent
try:
    probe = pc_agent.SingleInstance(0)
    assert probe.acquire()
    run_port = probe.port
    probe.release()
    result = []
    run_logs = []
    runner = threading.Thread(target=lambda: result.append(pc_agent.main(["--background"], config_path=config, log=run_logs.append,
                                                                          lock_port=run_port, log_path=bg_log)))
    runner.start()
    for _ in range(200):                                              # warten, bis der Agent den Port belegt hat (nur anklopfen, nicht belegen)
        time.sleep(0.05)
        try:
            socket.create_connection(("127.0.0.1", run_port), timeout=1).close()
            break
        except OSError:
            pass
    assert pc_agent.request_stop(run_port, wait=10) == "stopped"
    runner.join(10)
    assert result == [0] and not run_logs                           # --background: nichts im Fenster
    assert "PC-Agent beendet." in bg_log.read_text(encoding="utf-8")
    again = pc_agent.SingleInstance(run_port)
    assert again.acquire()
    again.release()
finally:
    pc_agent.Agent = orig_agent
holder.release()

print("ALL TESTS PASSED")
