"""Mark 5 C1: Gast-Bereiche (profiles.py) und die Zuordnung von Geraeten zu einem Bereich (remote_auth)."""
import json
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import profiles
import remote_auth
from profiles import OWNER, ProfileError, ProfileStore

tmp = Path(tempfile.mkdtemp())
ids = iter(["aaaaaaaa", "bbbbbbbb", "bbbbbbbb", "cccccccc", "dddddddd", "eeeeeeee", "ffffffff", "11111111"])
store = ProfileStore(tmp / "profiles.json", tmp / "profiles", clock=lambda: 1000.0, id_factory=lambda: next(ids))

# Anfang: leer, Besitzer gibt es immer
assert store.list() == [] and store.exists(OWNER) and not store.exists("aaaaaaaa")

# Anlegen: Name bereinigt, Standard-Limits, Datei geschrieben
first = store.create("  Bruder  ")
assert first == {"id": "aaaaaaaa", "name": "Bruder", "created": 1000.0, "limits": {"ai_per_day": 100, "messages_per_10min": 20}}
assert store.exists("aaaaaaaa") and store.get("aaaaaaaa") == first
assert json.loads((tmp / "profiles.json").read_text(encoding="utf-8"))["profiles"][0]["name"] == "Bruder"
assert store.get("aaaaaaaa")["limits"] is not first["limits"]           # Kopien, keine Innenleben
first["limits"]["ai_per_day"] = 5
assert store.get("aaaaaaaa")["limits"]["ai_per_day"] == 100

# Namen: leer, doppelt (auch anders geschrieben), zu lang, Steuerzeichen
for bad in ("", "   ", None, 5, "\n\t"):
    try:
        store.create(bad)
        raise AssertionError(bad)
    except ProfileError:
        pass
try:
    store.create("BRUDER")
    raise AssertionError("doppelt")
except ProfileError:
    pass
assert store.create("x" * 80)["name"] == "x" * profiles.MAX_NAME_LENGTH     # id-Wiederholung wird uebersprungen: bbbbbbbb nur einmal vergeben
assert [p["id"] for p in store.list()] == ["aaaaaaaa", "bbbbbbbb"]
assert store.create("Gast\x00 Zwei")["name"] == "Gast Zwei"

# Hoechstens MAX_PROFILES
store.create("Vier")
store.create("Fuenf")
assert len(store.list()) == profiles.MAX_PROFILES
try:
    store.create("Sechs")
    raise AssertionError("zu viele")
except ProfileError:
    pass
assert len(store.list()) == profiles.MAX_PROFILES

# Limits: Werte pruefen, nichts halb aendern
assert store.set_limits("aaaaaaaa", ai_per_day=5)["limits"] == {"ai_per_day": 5, "messages_per_10min": 20}
assert store.set_limits("aaaaaaaa", ai_per_day=0, messages_per_10min=0)["limits"] == {"ai_per_day": 0, "messages_per_10min": 0}
for bad in (-1, 1.5, "7", True, None, profiles.MAX_LIMIT + 1, float("nan")):
    try:
        store.set_limits("aaaaaaaa", ai_per_day=bad)
        raise AssertionError(bad)
    except ProfileError:
        pass
try:
    store.set_limits("aaaaaaaa", ai_per_day=9, messages_per_10min=-1)
    raise AssertionError("halb")
except ProfileError:
    pass
assert store.get("aaaaaaaa")["limits"] == {"ai_per_day": 0, "messages_per_10min": 0}      # ai_per_day=9 wurde NICHT uebernommen
try:
    store.set_limits("aaaaaaaa", sudo=1)
    raise AssertionError("unbekannt")
except ProfileError:
    pass
try:
    store.set_limits("zzzzzzzz", ai_per_day=1)
    raise AssertionError("unbekannter Bereich")
except KeyError:
    pass

# Datenordner: nur fuer angelegte Bereiche, Zuruecksetzen und Loeschen entfernen die Daten
folder = store.path_for("aaaaaaaa")
assert folder == tmp / "profiles" / "aaaaaaaa"
for bad in ("zzzzzzzz", "../aaaaaaaa", OWNER, ""):
    try:
        store.path_for(bad)
        raise AssertionError(bad)
    except ProfileError:
        pass
folder.mkdir(parents=True)
(folder / "widgets.json").write_text("{}", encoding="utf-8")
(tmp / "profiles" / "bbbbbbbb").mkdir()
assert store.reset_data("aaaaaaaa") is True and not folder.exists() and store.exists("aaaaaaaa")
assert (tmp / "profiles" / "bbbbbbbb").exists()                           # fremde Bereiche bleiben
assert store.reset_data("zzzzzzzz") is False
folder.mkdir()
assert store.delete("aaaaaaaa") is True and not folder.exists() and not store.exists("aaaaaaaa")
assert store.delete("aaaaaaaa") is False
assert (tmp / "profiles" / "bbbbbbbb").exists()

# Ein Symlink als Datenordner wird nie verfolgt
outside = tmp / "outside"
outside.mkdir()
(outside / "keep.txt").write_text("x", encoding="utf-8")
link = tmp / "profiles" / "bbbbbbbb"
link.rmdir()
try:
    link.symlink_to(outside, target_is_directory=True)
except (OSError, NotImplementedError):
    link = None
if link is not None:
    store.reset_data("bbbbbbbb")
    assert (outside / "keep.txt").exists()
    link.unlink()

# Neu laden: gleicher Stand; kaputte Datei wird beiseitegelegt, nichts stuerzt ab
again = ProfileStore(tmp / "profiles.json", tmp / "profiles")
assert [p["id"] for p in again.list()] == [p["id"] for p in store.list()] and again.list() == store.list()
(tmp / "profiles.json").write_text("{kaputt", encoding="utf-8")
broken = ProfileStore(tmp / "profiles.json", tmp / "profiles")
assert broken.list() == [] and (tmp / "profiles.json.defekt").exists()
(tmp / "profiles.json").write_text(json.dumps({"profiles": [
    {"id": "aaaaaaaa", "name": "Ok", "limits": {"ai_per_day": -4, "messages_per_10min": 3}},
    {"id": "../../etc", "name": "Boese"}, {"id": "aaaaaaaa", "name": "Doppelt"}, {"id": "bbbbbbbb", "name": ""}, "muell",
]}), encoding="utf-8")
cleaned = ProfileStore(tmp / "profiles.json", tmp / "profiles").list()
assert [p["name"] for p in cleaned] == ["Ok"] and cleaned[0]["limits"] == {"ai_per_day": 100, "messages_per_10min": 3}

# --- Geraete gehoeren einem Bereich ------------------------------------------------
devices = remote_auth.DeviceStore(tmp / "remote_devices.json")
mine = devices.create_pairing("Handy")
assert mine["profile"] == OWNER
guest = devices.create_pairing("Laptop", "aaaaaaaa")
assert guest["profile"] == "aaaaaaaa"
for bad in ("../x", "", "OWNER", None, 5, "aaaaaaaaa"):
    try:
        devices.create_pairing("X", bad)
        raise AssertionError(bad)
    except ValueError:
        pass
status_mine, token_mine, public_mine = devices.redeem(mine["code"])
status_guest, token_guest, public_guest = devices.redeem(guest["code"])
assert status_mine == status_guest == "ok" and token_mine and token_guest
assert public_mine["profile"] == OWNER and public_guest["profile"] == "aaaaaaaa"
assert "aaaaaaaa" not in token_guest
by_name = {d["name"]: d for d in devices.devices()}
assert by_name["Handy"]["profile"] == OWNER and by_name["Laptop"]["profile"] == "aaaaaaaa"

# Das Token verraet den Bereich nicht und er steht in der Datei, nicht im Token
raw = (tmp / "remote_devices.json").read_text(encoding="utf-8")
assert '"profile": "aaaaaaaa"' in raw
reloaded = remote_auth.DeviceStore(tmp / "remote_devices.json")
assert {d["name"]: d["profile"] for d in reloaded.devices()} == {"Handy": OWNER, "Laptop": "aaaaaaaa"}

# Aeltere Dateien ohne Bereich und Muell im Feld: der Besitzer, nie ein Gast
data = json.loads(raw)
for item in data["devices"] if isinstance(data, dict) else data:
    item.pop("profile", None) if item["name"] == "Handy" else item.__setitem__("profile", "../../x")
(tmp / "remote_devices.json").write_text(json.dumps(data), encoding="utf-8")
assert {d["name"]: d["profile"] for d in remote_auth.DeviceStore(tmp / "remote_devices.json").devices()} == {"Handy": OWNER, "Laptop": OWNER}

# Bereich entfernen: nur dessen Geraete und offene Links gehen
devices = remote_auth.DeviceStore(tmp / "dev2.json")
a = devices.create_pairing("A", "aaaaaaaa")
b = devices.create_pairing("B", "bbbbbbbb")
o = devices.create_pairing("O")
devices.redeem(a["code"])
devices.redeem(o["code"])
assert devices.remove_profile_devices(OWNER) == 0                          # den Besitzer entfernt man so nie
assert devices.remove_profile_devices("aaaaaaaa") == 1
assert [d["name"] for d in devices.devices()] == ["O"]
assert devices.pending_count() == 1                                         # B wartet noch
assert devices.remove_profile_devices("bbbbbbbb") == 0 and devices.pending_count() == 0      # gezaehlt werden nur Geraete
assert devices.redeem(b["code"])[0] == "invalid"        # der Link fuer einen geloeschten Bereich geht nicht mehr

print("ALL TESTS PASSED")
