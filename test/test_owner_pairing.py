"""Vollzugriff-Kopplung (remote_auth, Server S4): nur mit full=True, nur Besitzer, Code als Hash in einer Datei, einmal benutzbar."""
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import remote_auth

tmp = Path(tempfile.mkdtemp())
devices_file = tmp / "remote_devices.json"
pending_file = tmp / remote_auth.FULL_PENDING_NAME


class Clock:
    now = 1000.0
    def __call__(self):
        return self.now
clock = Clock()


def store():
    return remote_auth.DeviceStore(devices_file, clock=clock)


# 1) Normale Kopplung: kein Vollzugriff, keine Datei
server_store = store()
normal = server_store.create_pairing("Handy")
assert normal["full"] is False and not pending_file.exists()
status, token, device = server_store.redeem(normal["code"])
assert status == "ok" and device["full"] is False and server_store.authenticate(token)["full"] is False

# 2) Vollzugriff nur fuer den Besitzer; Gast-Bereich + full ist ein Fehler
for bad in ("a1b2c3d4", "kein-bereich"):
    try:
        server_store.create_pairing("X", profile=bad, full=True)
        raise SystemExit("Gast mit Vollzugriff darf es nicht geben")
    except ValueError:
        pass
assert not pending_file.exists() and server_store.pending_count() == 0
guest = server_store.create_pairing("Gast", profile="a1b2c3d4")
assert guest["full"] is False

# 3) Terminal (ein anderer Store) legt den Code an; der laufende Server loest ihn ein
terminal = store()
made = terminal.create_pairing("PC Moritz", full=True)
assert made["full"] is True and made["profile"] == remote_auth.OWNER and pending_file.exists()
raw = pending_file.read_text(encoding="utf-8")
assert made["code"] not in raw and remote_auth.normalize_code(made["code"]) not in raw                        # nur der Hash steht in der Datei
assert remote_auth.hash_token(remote_auth.normalize_code(made["code"])) in raw and "PC Moritz" in raw
if os.name == "posix":
    assert oct(pending_file.stat().st_mode & 0o777) == "0o600"
status, token, device = server_store.redeem(made["code"].lower().replace("-", " "))
assert status == "ok" and device["full"] is True and device["name"] == "PC Moritz" and device["profile"] == remote_auth.OWNER
assert server_store.authenticate(token)["full"] is True
assert not pending_file.exists()                                                                                # verbraucht, Datei weg
assert server_store.redeem(made["code"])[0] == "invalid"                                                        # nur einmal
assert store().devices()[-1]["full"] is True                                                                    # ueberlebt einen Neustart

# 4) Code aus demselben Store: auch die Datei-Kopie ist danach verbraucht
same = server_store.create_pairing("Laptop", full=True)
assert pending_file.exists()
assert server_store.redeem(same["code"])[0] == "ok" and not pending_file.exists()
assert store().redeem(same["code"])[0] == "invalid"
again = server_store.create_pairing("Laptop 2", full=True)
other = store()
assert other.redeem(again["code"])[0] == "ok"
assert server_store.redeem(again["code"])[0] == "invalid"                                                       # der andere war schneller

# 5) Abgelaufen: 5 Minuten, dann ungueltig und aus der Datei gefegt
old = terminal.create_pairing("Alt", full=True)
clock.now += remote_auth.PAIRING_TTL - 1
assert server_store.redeem("ABCD-EFGH")[0] == "invalid"           # falscher Code ist kein Fehler im Ablauf
fresh = terminal.create_pairing("Frisch", full=True)
clock.now += 2
assert server_store.redeem(old["code"])[0] == "invalid"
assert server_store.redeem(fresh["code"])[0] == "ok"
expired = terminal.create_pairing("Zu spaet", full=True)
clock.now += remote_auth.PAIRING_TTL
assert store().redeem(expired["code"])[0] == "invalid"

# 5b) Abgelaufene Eintraege verschwinden aus der Datei: beim naechsten Anlegen und nach einer Einloesung
terminal.create_pairing("Veraltet", full=True)
clock.now += remote_auth.PAIRING_TTL + 5
terminal.create_pairing("Neu", full=True)
names = [e["name"] for e in json.loads(pending_file.read_text(encoding="utf-8")).values()]
assert names == ["Neu"], names
clock.now += remote_auth.PAIRING_TTL + 5
assert store().redeem("ABCD-EFGH")[0] == "invalid" and not pending_file.exists()                                # nur Abgelaufenes: Datei wird geleert

# 6) Falsche Codes zaehlen fuer die Sperre; Code mit Vollzugriff ist gegen Raten genauso geschuetzt
guard_store = remote_auth.DeviceStore(devices_file, clock=clock, guard=remote_auth.PairingGuard(clock, max_failures=3))
target = guard_store.create_pairing("Ziel", full=True)
for _ in range(3):
    assert guard_store.redeem("AAAA-AAAA", "quelle")[0] == "invalid"
assert guard_store.redeem(target["code"], "quelle")[0] == "locked"
assert guard_store.redeem(target["code"], "andere")[0] == "ok"

# 7) Kaputte oder fremde Pending-Datei: ignoriert, kein Absturz, kein Vollzugriff
for junk in ("{", "[]", "5", json.dumps({"x": 5}), json.dumps({"x": {"name": 5, "expires": 9e9}}),
             json.dumps({remote_auth.hash_token("ABCDEFGH"): {"name": "Boese", "expires": "morgen"}}),
             json.dumps({remote_auth.hash_token("ABCDEFGH"): {"name": "Boese", "expires": True}})):
    pending_file.write_text(junk, encoding="utf-8")
    assert store().redeem("ABCD-EFGH")[0] == "invalid", junk
pending_file.write_text(json.dumps({remote_auth.hash_token("ABCDEFGH"): {"name": "Eingeschmuggelt", "expires": clock.now + 100, "profile": "a1b2c3d4", "full": False}}), encoding="utf-8")
status, token, device = store().redeem("ABCD-EFGH")                    # Wer die Datei schreiben kann, hat Shell-Zugriff: es ist ein Besitzer-Code
assert status == "ok" and device["profile"] == remote_auth.OWNER and device["full"] is True
pending_file.unlink(missing_ok=True)

# 8) Hoechstens MAX_PENDING offene Codes in der Datei
for n in range(remote_auth.MAX_PENDING + 3):
    terminal.create_pairing(f"G{n}", full=True)
assert len(json.loads(pending_file.read_text(encoding="utf-8"))) == remote_auth.MAX_PENDING
pending_file.unlink(missing_ok=True)

# 9) Gesperrte Geraete mit Vollzugriff verlieren ihn mit dem Token
cp = store().create_pairing("Weg", full=True)
s2 = store()
status, token, device = s2.redeem(cp["code"])
assert s2.authenticate(token)["full"] is True
s2.revoke(device["id"])
assert s2.authenticate(token) is None

assert "remote_pending_full.json" in (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")          # Hashes offener Codes gehoeren nie nach Git
assert remote_auth.FULL_PENDING_NAME == "remote_pending_full.json"

print("ALL TESTS PASSED")
