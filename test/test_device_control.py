"""PC steuern ueber den Agent (S6, G3): Lautstaerke und Medientasten. Feste Auftraege, geprueft auf beiden Seiten, Fehler ohne Agent-Text."""
import sys
import threading
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_commands as dc
import device_hub
import pc_agent
import remote_pc
from tools import media_tool, volume_tool
from tools.tool_result import ToolResult


def raises(call, error=dc.CommandError):
    try:
        call()
    except error:
        return True
    return False


# 1) Parameter: Lautstaerke nur ganze Zahl 0..100, genau ein Schluessel
assert dc.check_args("volume.set", {"percent": 0}) == {"percent": 0} and dc.check_args("volume.set", {"percent": 100}) == {"percent": 100}
for bad in (None, {}, {"percent": -1}, {"percent": 101}, {"percent": 50.5}, {"percent": "50"}, {"percent": True}, {"percent": None},
            {"percent": 5, "x": 1}, {"vol": 5}, 5, [50]):
    assert raises(lambda: dc.check_args("volume.set", bad)), bad

# 2) Parameter: Medientaste nur die drei festen Namen (keine Aliase, keine Tastennummern)
for good in dc.MEDIA_ACTIONS:
    assert dc.check_args("media.key", {"action": good}) == {"action": good}
assert dc.MEDIA_ACTIONS == ("play_pause", "next", "previous")
for bad in (None, {}, {"action": "pause"}, {"action": "stop"}, {"action": 179}, {"action": ["next"]}, {"action": "next", "x": 1}, {"key": "next"}, "next"):
    assert raises(lambda: dc.check_args("media.key", bad)), bad

# 3) Ergebnisse: Pflichtfelder, Wertebereich, Fremdes wird verworfen
assert dc.check_result("volume.set", {"percent": 40, "evil": "x"}) == {"percent": 40}
for bad in ({}, {"percent": 101}, {"percent": -3}, {"percent": 1.5}, {"percent": True}, {"percent": "40"}, None):
    assert raises(lambda: dc.check_result("volume.set", bad)), bad
assert dc.check_result("media.key", {"command": "next", "note": "Hallo"}) == {"command": "next"}
for bad in ({}, {"command": "format c:"}, {"command": 5}, {"command": "x" * 50}, None):
    assert raises(lambda: dc.check_result("media.key", bad)), bad

# 4) Agent: ruft die lokalen Werkzeuge; Fehler bleiben auf dem PC (nur "Fehler", kein Text)
calls = []
orig_vol, orig_media = volume_tool.set_volume, media_tool.media_control
fail = {"on": False}


def fake_volume(percent):
    calls.append(("volume", percent))
    return ToolResult(success=False, error="GEHEIM pfad C:\\x") if fail["on"] else ToolResult(success=True, data=percent)


def fake_media(command):
    calls.append(("media", command))
    return ToolResult(success=False, error="GEHEIM") if fail["on"] else ToolResult(success=True, data={"command": command})


volume_tool.set_volume, media_tool.media_control = fake_volume, fake_media
try:
    logs = []
    agent = pc_agent.Agent(transport=None, token="t", log=logs.append)
    assert agent.run_job({"id": "1", "command": "volume.set", "args": {"percent": 35}}) == (True, {"percent": 35}) and calls[-1] == ("volume", 35)
    assert agent.run_job({"id": "2", "command": "media.key", "args": {"action": "previous"}}) == (True, {"command": "previous"}) and calls[-1] == ("media", "previous")
    n = len(calls)
    assert agent.run_job({"id": "3", "command": "volume.set", "args": {"percent": 500}}) == (False, None) and len(calls) == n     # ungueltig: gar nicht ausgefuehrt
    assert agent.run_job({"id": "4", "command": "media.key", "args": {"action": "pause"}}) == (False, None) and len(calls) == n
    fail["on"] = True
    assert agent.run_job({"id": "5", "command": "volume.set", "args": {"percent": 10}}) == (False, None)
    assert agent.run_job({"id": "6", "command": "media.key", "args": {"action": "next"}}) == (False, None)
    assert not any("GEHEIM" in line for line in logs), logs
finally:
    volume_tool.set_volume, media_tool.media_control = orig_vol, orig_media


# 5) Server-Seite: die Werkzeuge pruefen selbst und schicken dann den Auftrag; PC aus = klare Meldung
class FakeHub:
    def __init__(self):
        self.calls = []
        self.error = None

    def request(self, command, args=None, **kw):
        self.calls.append((command, args))
        if self.error:
            raise self.error
        return {"percent": args["percent"]} if command == "volume.set" else {"command": args["action"]}


hub = FakeHub()
volume_tool.set_remote(hub)
media_tool.set_remote(hub)
try:
    result = volume_tool.set_volume(40)
    assert result.success and result.data == 40 and hub.calls == [("volume.set", {"percent": 40})]
    assert volume_tool.set_volume("55.6").success and hub.calls[-1] == ("volume.set", {"percent": 56})
    n = len(hub.calls)
    for bad in (-1, 101, "laut", None, float("nan"), float("inf")):
        assert not volume_tool.set_volume(bad).success, bad
    assert len(hub.calls) == n                                   # ungueltige Werte erreichen den PC nie

    for word, expected in (("play_pause", "play_pause"), ("pause", "play_pause"), ("Nächster", "next"), ("zurück", "previous")):
        r = media_tool.media_control(word)
        assert r.success and r.data["command"] == expected and hub.calls[-1] == ("media.key", {"action": expected}), word
    assert media_tool.media_control("play_pause").data["note"]   # Hinweistext kommt vom Server, nicht vom PC
    assert media_tool.media_control("next").data["done"] == "nächster Titel"
    n = len(hub.calls)
    assert not media_tool.media_control("sprenge den PC").success and not media_tool.media_control(None).success and len(hub.calls) == n

    hub.error = device_hub.DeviceOffline("Der PC ist gerade nicht erreichbar.")
    for r in (volume_tool.set_volume(10), media_tool.media_control("next")):
        assert not r.success and r.error == "Der PC ist gerade nicht erreichbar."
    hub.error = device_hub.DeviceFailed("Fehler beim Gerät.")
    assert volume_tool.set_volume(10).error == "Fehler beim Gerät." and media_tool.media_control("next").error == "Fehler beim Gerät."
    hub.error = device_hub.DeviceTimeout("Der PC hat nicht rechtzeitig geantwortet.")
    assert "rechtzeitig" in media_tool.media_control("next").error
finally:
    volume_tool.set_remote(None)
    media_tool.set_remote(None)

# 6) ohne Server-Hub: lokales Verhalten bleibt (Medientaste nur unter Windows, Meldung unveraendert)
assert volume_tool._remote is None and media_tool._remote is None
if not sys.platform.startswith("win"):
    assert media_tool.media_control("next").error == "Die Musiksteuerung funktioniert nur unter Windows."

# 7) install() haengt die Hub-Verbindung in beide Werkzeuge
class Srv:
    pass


srv = Srv()
srv.hub = hub
from tools import pc_health, system_status_tool
try:
    remote_pc.install(srv)
    assert volume_tool._remote is hub and media_tool._remote is hub
finally:
    volume_tool.set_remote(None)
    media_tool.set_remote(None)
    system_status_tool.set_remote(None)
    system_status_tool.set_default_monitor(None)
    pc_health.set_default_health(None)

# 8) Ganze Strecke mit echtem Hub: Werkzeug -> Hub -> Agent (Thread) -> Hub -> Ergebnis; ein Agent, der Unsinn meldet, wird abgewiesen
hub2 = device_hub.DeviceHub()
agent = pc_agent.Agent(transport=None, token="t", log=lambda m: None, handlers={
    "volume.set": lambda a: {"percent": a["percent"]},
    "media.key": lambda a: {"command": "rm -rf" if a["action"] == "next" else a["action"]}})
seen = []
stop = threading.Event()


def worker():
    while not stop.is_set():
        job = hub2.next_job("dev1", wait=0.2)
        if job:
            seen.append((job["command"], job["args"]))
            ok, data = agent.run_job(job)
            hub2.submit("dev1", job["id"], ok, data)


thread = threading.Thread(target=worker, daemon=True)
thread.start()
volume_tool.set_remote(hub2)
media_tool.set_remote(hub2)
try:
    assert volume_tool.set_volume(25).success and seen[-1] == ("volume.set", {"percent": 25})
    assert media_tool.media_control("previous").success and seen[-1] == ("media.key", {"action": "previous"})
    bad = media_tool.media_control("next")                        # Ergebnis ausserhalb der Liste -> Fehler, nicht durchgereicht
    assert not bad.success and "rm" not in str(bad.error)
finally:
    stop.set()
    thread.join(5)
    volume_tool.set_remote(None)
    media_tool.set_remote(None)

print("ALL TESTS PASSED")
