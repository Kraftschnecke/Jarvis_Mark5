"""PC-Agent koppeln (S6): eigene Geraeteart, Code nur fuer den Agent, Token nie als Browser-Zugang, gesperrt = draussen."""
import json
import sys
import tempfile
import types
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import remote_auth
import remote_gate
from profiles import OWNER

tmp = Path(tempfile.mkdtemp())
path = tmp / "remote_devices.json"
store = remote_auth.DeviceStore(path)
settings = types.SimpleNamespace(get=lambda *a, **k: None)
gate = remote_gate.RemoteGate("jarvis.tail1234.ts.net", store, settings)

# 1) Agent-Code (im selben Prozess erzeugt) -> Agent-Geraet: Besitzer, kein Vollzugriff, Token ok
pairing = store.create_pairing("PC Moritz", agent=True)
assert pairing["agent"] is True and pairing["full"] is False and pairing["profile"] == OWNER
status, token, device = store.redeem(pairing["code"], "t", kind="agent")
assert status == "ok" and device["agent"] is True and device["full"] is False and device["profile"] == OWNER
assert store.devices()[0]["agent"] is True
assert not (tmp / remote_auth.FULL_PENDING_NAME).exists()                      # Code verbraucht, Datei weg
assert store.redeem(pairing["code"], "t", kind="agent")[0] == "invalid"        # nur einmal

# 2) Der Code der anderen Art gilt nicht: Agent-Code im Browser, Browser-Code und Vollzugriff-Code beim Agent
store.guard._failures.clear()
agent_code = store.create_pairing("A", agent=True)["code"]
assert store.redeem(agent_code, "t")[0] == "invalid"                            # Standard kind="browser"
browser_code = store.create_pairing("B")["code"]
assert store.redeem(browser_code, "t", kind="agent")[0] == "invalid"
full_code = store.create_pairing("C", full=True)["code"]
assert store.redeem(full_code, "t", kind="agent")[0] == "invalid"
assert not (tmp / remote_auth.FULL_PENDING_NAME).exists() or store._read_full_pending() == {}
store.guard._failures.clear()
good = store.create_pairing("D")["code"]
assert store.redeem(good, "t")[0] == "ok"                                       # ein normaler Browser-Code geht weiter

# 3) Das Server-Terminal ist ein anderer Prozess: Code in der Datei, Einloesen im Server
terminal = remote_auth.DeviceStore(path)
code = terminal.create_pairing("PC Terminal", agent=True)["code"]
pending = json.loads((tmp / remote_auth.FULL_PENDING_NAME).read_text())
assert len(pending) == 1 and list(pending.values())[0]["agent"] is True and code not in json.dumps(pending)     # nur der Hash
status, agent_token, agent = store.redeem(code, "t", kind="agent")
assert status == "ok" and agent["agent"] is True and agent["full"] is False and agent["name"] == "PC Terminal"
assert store.redeem(code, "t", kind="agent")[0] == "invalid"
# Der Besitzer-Code aus dem Terminal bleibt ein Vollzugriff und wird nie zum Agent
owner_code = terminal.create_pairing("PC", full=True)["code"]
status, _, owner_device = store.redeem(owner_code, "t")
assert status == "ok" and owner_device["full"] is True and owner_device["agent"] is False

# 4) Nicht erlaubte Kombinationen
for kwargs in ({"agent": True, "full": True}, {"agent": True, "profile": "a1b2c3d4"}):
    try:
        store.create_pairing("X", **kwargs)
        raise AssertionError(kwargs)
    except ValueError:
        pass

# 5) Das Token eines Agents ist nie ein Browser-Zugang, im Authorization-Kopf aber gueltig; ein Browser-Token ist kein Agent
assert gate.agent_from_header(f"Bearer {agent_token}")["id"] == agent["id"]
assert gate.device_from_cookie(f"{remote_gate.COOKIE_NAME}={agent_token}") is None
store.guard._failures.clear()
code = store.create_pairing("Handy")["code"]
status, phone_token, phone = store.redeem(code, "t")
assert gate.device_from_cookie(f"{remote_gate.COOKIE_NAME}={phone_token}")["id"] == phone["id"]
assert gate.agent_from_header(f"Bearer {phone_token}") is None
for bad in (None, "", "Bearer", "Bearer ", "bearer " + agent_token, agent_token, "Basic " + agent_token, "Bearer " + agent_token + "x",
            "Bearer " + "a" * 400, 5, ["Bearer " + agent_token]):
    assert gate.agent_from_header(bad) is None, bad

# 6) Gesperrt: sofort draussen; wieder freigegeben: wieder drin
assert store.revoke(agent["id"]) is True
assert gate.agent_from_header(f"Bearer {agent_token}") is None
assert store.restore(agent["id"]) is True
assert gate.agent_from_header(f"Bearer {agent_token}") is not None

# 7) Zu viele falsche Codes sperren die Kopplung (auch fuer den Agent)
fresh = remote_auth.DeviceStore(tmp / "other.json")
for _ in range(remote_auth.MAX_FAILURES):
    assert fresh.redeem("AAAA-BBBB", "x", kind="agent")[0] == "invalid"
assert fresh.redeem("AAAA-BBBB", "x", kind="agent")[0] == "locked"

# 8) Gespeichert und neu geladen: das Merkmal bleibt; Unsinn in der Datei zaehlt nie als Agent
reloaded = remote_auth.DeviceStore(path)
assert [d["agent"] for d in reloaded.devices() if d["id"] == agent["id"]] == [True]
raw = json.loads(path.read_text())
for item in raw["devices"]:
    if item["id"] == agent["id"]:
        item["agent"] = "ja"
    elif item["id"] == owner_device["id"]:
        item["agent"] = True                    # Vollzugriff + Agent zugleich
    elif item["id"] == phone["id"]:
        item["profile"] = "a1b2c3d4"
        item["agent"] = True                    # Gast + Agent
path.write_text(json.dumps(raw))
flags = {d["id"]: d["agent"] for d in remote_auth.DeviceStore(path).devices()}
assert flags[agent["id"]] is False and flags[owner_device["id"]] is False and flags[phone["id"]] is False

print("ALL TESTS PASSED")
