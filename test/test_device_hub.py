"""Geraete-Warteschlange (S6): feste Auftragsliste, Long-Poll, Ergebnis, Zeitlimit, Offline, fremde Ergebnisse."""
import sys
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_commands
import device_hub

GOOD = {"name": "PC", "time": "2026-11-23T20:40:00", "version": 1}

# 1) Auftragsliste: nur "ping", ohne Parameter; Ergebnisse streng geprueft
assert device_commands.check_args("ping", None) == {} and device_commands.check_args("ping", {}) == {}
for bad_command in ("rm", "", None, 5, ["ping"]):
    try:
        device_commands.check_args(bad_command, {})
        raise AssertionError(bad_command)
    except device_commands.CommandError:
        pass
try:
    device_commands.check_args("ping", {"x": 1})
    raise AssertionError("Parameter bei ping")
except device_commands.CommandError:
    pass
assert device_commands.check_result("ping", GOOD) == GOOD
assert device_commands.check_result("ping", dict(GOOD, extra="fremd")) == GOOD          # Fremdes wird verworfen, nicht weitergegeben
for bad in (None, [], {}, dict(GOOD, name=5), dict(GOOD, name="x" * 41), dict(GOOD, version=True),
            dict(GOOD, version=0), dict(GOOD, version="1"), {k: v for k, v in GOOD.items() if k != "time"},
            dict(GOOD, time="y" * 41), float("nan")):
    try:
        device_commands.check_result("ping", bad)
        raise AssertionError(bad)
    except device_commands.CommandError:
        pass
try:
    device_commands.check_result("ping", dict(GOOD, name="z" * (device_commands.MAX_RESULT_BYTES + 1)))
    raise AssertionError("zu gross")
except device_commands.CommandError as error:
    assert "gross" in str(error)
try:
    device_commands.check_result("nope", GOOD)
    raise AssertionError("unbekannt")
except device_commands.CommandError:
    pass

# 2) Ohne verbundenes Geraet: sofort "nicht erreichbar", nichts bleibt in der Warteschlange
now = [100.0]
hub = device_hub.DeviceHub(clock=lambda: now[0])
assert hub.online() is False and hub.online_device() is None
try:
    hub.request("ping", timeout=1)
    raise AssertionError("offline")
except device_hub.DeviceOffline as error:
    assert "nicht erreichbar" in str(error)
assert hub._queue == {} and hub._jobs == {}
try:
    hub.request("rm -rf", timeout=1)
    raise AssertionError("unbekannter Auftrag")
except device_commands.CommandError:
    pass

# 3) Verbunden bleibt ein Geraet 45 Sekunden nach der letzten Anfrage; mehrere Geraete: das zuletzt gesehene gewinnt
hub.touch("aaaa")
assert hub.online() and hub.online("aaaa") and not hub.online("bbbb")
now[0] += 44
assert hub.online("aaaa")
now[0] += 2
assert not hub.online("aaaa") and hub.online_device() is None
hub.touch("aaaa")
now[0] += 1
hub.touch("bbbb")
assert hub.online_device() == "bbbb" and hub.online_device("aaaa") == "aaaa"

# 4) Echter Ablauf mit Thread (reale Uhr): Auftrag, Long-Poll, Ergebnis
hub = device_hub.DeviceHub()
box = {}


def agent_side(device="pc01", result=GOOD, ok=True, delay=0.0):
    job = hub.next_job(device, wait=5)
    box["job"] = job
    if job is not None:
        time.sleep(delay)
        box["accepted"] = hub.submit(device, job["id"], ok, result)


hub.touch("pc01")
thread = threading.Thread(target=agent_side)
thread.start()
assert hub.request("ping", timeout=5) == GOOD
thread.join()
assert box["job"]["command"] == "ping" and box["job"]["args"] == {} and box["accepted"] is True
assert hub._jobs == {} and hub._queue["pc01"] == []

# 5) Das Geraet meldet einen Fehler: der Text des Geraets wird nie weitergegeben
thread = threading.Thread(target=agent_side, kwargs={"ok": False, "result": "geheimer Pfad C:\\Users\\x"})
thread.start()
try:
    hub.request("ping", timeout=5)
    raise AssertionError("Fehler")
except device_hub.DeviceFailed as error:
    assert "C:" not in str(error) and "konnte" in str(error)
thread.join()

# 6) Ungueltiges Ergebnis (falsche Form) wird abgelehnt
thread = threading.Thread(target=agent_side, kwargs={"result": {"name": "PC"}})
thread.start()
try:
    hub.request("ping", timeout=5)
    raise AssertionError("ungueltig")
except device_hub.DeviceFailed as error:
    assert "passt nicht" in str(error)
thread.join()

# 7) Zeitlimit: das Geraet holt den Auftrag nie ab -> Timeout, Auftrag verschwindet aus der Warteschlange
hub.touch("pc01")
started = time.monotonic()
try:
    hub.request("ping", timeout=0.3)
    raise AssertionError("timeout")
except device_hub.DeviceTimeout:
    pass
assert time.monotonic() - started < 3 and hub._queue["pc01"] == [] and hub._jobs == {}

# 8) Zu spaetes Ergebnis nach dem Timeout und Ergebnisse fuer fremde oder erfundene Auftraege werden abgelehnt
hub.touch("pc01")
slow = threading.Thread(target=lambda: box.update(job=hub.next_job("pc01", wait=5)))
slow.start()
try:
    hub.request("ping", timeout=0.1)
except device_hub.DeviceTimeout:
    pass
slow.join()
if box["job"] is not None:                                    # abgeholt, aber zu spaet beantwortet
    assert hub.submit("pc01", box["job"]["id"], True, GOOD) is False
assert hub.submit("pc01", "erfunden", True, GOOD) is False
assert hub.submit("pc01", None, True, GOOD) is False
assert hub.submit("pc01", ["x"], True, GOOD) is False

# 9) Ein anderes Geraet darf das Ergebnis nicht abgeben; ein Ergebnis zaehlt nur einmal
hub = device_hub.DeviceHub()
hub.touch("pc01")
captured = {}


def grab():
    captured["job"] = hub.next_job("pc01", wait=5)


grabber = threading.Thread(target=grab)
grabber.start()
result_box = {}
requester = threading.Thread(target=lambda: result_box.update(out=hub.request("ping", timeout=5)))
requester.start()
grabber.join()
job = captured["job"]
assert hub.submit("evil", job["id"], True, GOOD) is False         # fremdes Geraet
assert hub.submit("pc01", job["id"], True, GOOD) is True
assert hub.submit("pc01", job["id"], True, GOOD) is False         # zweites Mal
requester.join()
assert result_box["out"] == GOOD

# 9b) Ein Ergebnis fuer einen Auftrag, den das Geraet noch gar nicht abgeholt hat, wird abgelehnt (erfundene Antwort im Voraus)
hub = device_hub.DeviceHub()
hub.touch("pc01")
early = {}
waiting = threading.Thread(target=lambda: early.update(out=_try(hub)))


def _try(h):
    try:
        return h.request("ping", timeout=0.6)
    except device_hub.DeviceTimeout:
        return "timeout"


waiting.start()
time.sleep(0.2)
pending_id = next(iter(hub._jobs))
assert hub.submit("pc01", pending_id, True, GOOD) is False        # noch nicht abgeholt
waiting.join()
assert early["out"] == "timeout"

# 10) Long-Poll ohne Auftrag endet nach der Wartezeit mit None; die Wartezeit ist nach oben begrenzt
hub = device_hub.DeviceHub()
started = time.monotonic()
assert hub.next_job("pc01", wait=0.3) is None
assert 0.25 <= time.monotonic() - started < 3
assert hub.online("pc01")
original_max = device_hub.MAX_WAIT
device_hub.MAX_WAIT = 0.3
started = time.monotonic()
assert hub.next_job("pc01", wait=999) is None                      # nach oben begrenzt, nicht 999 Sekunden
assert time.monotonic() - started < 3
started = time.monotonic()
assert hub.next_job("pc01", wait=-5) is None and time.monotonic() - started < 0.5       # negativ = sofort zurueck
device_hub.MAX_WAIT = original_max

# 11) forget(): Geraet nicht mehr verbunden, wartende Auftraege scheitern sofort
hub = device_hub.DeviceHub()
hub.touch("pc01")
outcome = {}


def requester_fn():
    try:
        hub.request("ping", timeout=5)
    except device_hub.DeviceFailed as error:
        outcome["error"] = str(error)


waiter = threading.Thread(target=requester_fn)
waiter.start()
time.sleep(0.2)
hub.forget("pc01")
waiter.join(timeout=3)
assert "getrennt" in outcome.get("error", "") and not hub.online("pc01")

# 12) Warteschlange ist begrenzt
hub = device_hub.DeviceHub()
hub.touch("pc01")
hub._queue["pc01"] = [{"id": str(n)} for n in range(device_hub.MAX_QUEUED)]
try:
    hub.request("ping", timeout=0.1)
    raise AssertionError("voll")
except device_hub.DeviceFailed as error:
    assert "Zu viele" in str(error)

print("ALL TESTS PASSED")
