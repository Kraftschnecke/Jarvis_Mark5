"""Remote R1 (Mark 5): Kopplung, Token als Hash, Sperren, Grenzen, Stufen und Adressliste (reine Logik)."""
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def stub_if_missing(name, **attrs):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("requests")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

project_stub = types.ModuleType("project")
for name in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
             "save_message", "get_conversation", "rename_conversation", "create_project", "reset_conversation",
             "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub
import re

import json
import os
import tempfile
from datetime import datetime

import abilities
import remote_auth
import remote_policy
from remote_auth import DeviceStore, PairingGuard, UsageLimits, clean_device_name, hash_token
from risk import SAFE, task_risk
from task_registry import TaskRegistry
from tasks import register_all_tasks


class Clock:
    def __init__(self, start=1_800_000_000.0):
        self.now = start
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


tmp = Path(tempfile.mkdtemp())
clock = Clock()
store_path = tmp / "remote_devices.json"
store = DeviceStore(store_path, clock=clock)

# 1) Hilfen
assert hash_token("a") == hash_token("a") and hash_token("a") != hash_token("b")
assert len(hash_token("geheim-token")) == 64 and "geheim" not in hash_token("geheim-token")
assert clean_device_name("  iPhone \n Moritz ") == "iPhone Moritz"
assert clean_device_name("") == "Gerät" and clean_device_name(None) == "Gerät" and clean_device_name("\x00\x01") == "Gerät"
assert len(clean_device_name("x" * 200)) == 40

# 2) Kopplung: Code -> Token, Datei ohne Klartext
pairing = store.create_pairing("iPhone Moritz")
code = pairing["code"]
assert len(code) >= 32 and pairing["expires"] == clock.now + 300 and pairing["name"] == "iPhone Moritz"
assert store.pending_count() == 1 and store.devices() == []
status, token, device = store.redeem(code, "ip1")
assert status == "ok" and token.startswith(device["id"] + ".") and device["name"] == "iPhone Moritz"
assert "token_hash" not in device and device["revoked"] is False
file_text = store_path.read_text(encoding="utf-8")
assert token not in file_text and code not in file_text and hash_token(token) in file_text
assert "token_hash" not in json.dumps(store.devices())
assert store.pending_count() == 0
assert store.authenticate(token)["id"] == device["id"]

# 3) Ein Code gilt nur einmal, nur 5 Minuten, falsche Codes zaehlen nicht als Erfolg
assert store.redeem(code, "ip1")[0] == "invalid"
second = store.create_pairing("Tablet")["code"]
clock.advance(301)
assert store.redeem(second, "ip1")[0] == "invalid"
for bad in (None, "", 123, "falsch", [], {}):
    assert store.redeem(bad, "ip9")[0] in ("invalid", "locked")
assert len(store.devices()) == 1

# 4) Sperre bei Fehlversuchen: je Quelle, loest sich nach der Wartezeit, Erfolg setzt den Zaehler zurueck
guard_clock = Clock()
guarded = DeviceStore(tmp / "g.json", clock=guard_clock)
for _ in range(5):
    assert guarded.redeem("falsch", "boese")[0] == "invalid"
valid = guarded.create_pairing("X")["code"]
assert guarded.redeem(valid, "boese")[0] == "locked"                 # auch der richtige Code hilft dann nicht
assert guarded.redeem(valid, "anderer")[0] == "ok"                   # andere Quelle ist nicht betroffen
guard_clock.advance(901)
valid2 = guarded.create_pairing("Y")["code"]
assert guarded.redeem(valid2, "boese")[0] == "ok"                    # Sperre ist abgelaufen
reset = DeviceStore(tmp / "r.json", clock=guard_clock)
for _ in range(4):
    reset.redeem("falsch", "s")
assert reset.redeem(reset.create_pairing("A")["code"], "s")[0] == "ok"
for _ in range(4):
    reset.redeem("falsch", "s")
assert reset.redeem(reset.create_pairing("B")["code"], "s")[0] == "ok"   # Erfolg hat die Fehler gestrichen

slow = DeviceStore(tmp / "w.json", clock=guard_clock)
for _ in range(4):
    slow.redeem("falsch", "langsam")
guard_clock.advance(901)                                                  # alte Fehlversuche verfallen
slow.redeem("falsch", "langsam")
assert slow.redeem(slow.create_pairing("W")["code"], "langsam")[0] == "ok"

# 5) Hoechstens 5 offene Kopplungen: die aelteste faellt weg
many = DeviceStore(tmp / "m.json", clock=clock)
codes = []
for index in range(6):
    codes.append(many.create_pairing(f"G{index}")["code"])
    clock.advance(1)
assert many.pending_count() == 5
assert many.redeem(codes[0], "q")[0] == "invalid" and many.redeem(codes[5], "q")[0] == "ok"

# 6) Anmeldung: falsches Token, fremdes Geraet, veraendertes Token, ungueltige Formen
assert store.authenticate(None) is None and store.authenticate("") is None and store.authenticate(5) is None
assert store.authenticate("ohnepunkt") is None and store.authenticate("x" * 500) is None
assert store.authenticate(device["id"] + ".falsch") is None
assert store.authenticate("deadbeef." + token.split(".", 1)[1]) is None
assert store.authenticate(token + "x") is None and store.authenticate(token.upper()) is None

# 7) Letzter Zugriff und Laufzeit: nicht bei jeder Anfrage schreiben, aber nach einer Minute
fresh = DeviceStore(tmp / "s.json", clock=clock)
_, t2, d2 = fresh.redeem(fresh.create_pairing("Zeit")["code"], "z")
written = (tmp / "s.json").read_text(encoding="utf-8")
clock.advance(30)
fresh.authenticate(t2)
assert (tmp / "s.json").read_text(encoding="utf-8") == written          # zu frueh: keine neue Schreibung
clock.advance(40)
fresh.authenticate(t2)
assert (tmp / "s.json").read_text(encoding="utf-8") != written
assert DeviceStore(tmp / "s.json", clock=clock).devices()[0]["last_seen"] == clock.now
clock.advance(90 * 24 * 3600 - 10)
assert fresh.authenticate(t2) is not None                                 # durch Benutzung verlaengert
clock.advance(91 * 24 * 3600)
assert fresh.authenticate(t2) is None                                     # lange nicht benutzt: abgelaufen

# 8) Sperren und Entfernen
rv = DeviceStore(tmp / "v.json", clock=clock)
_, ta, da = rv.redeem(rv.create_pairing("A")["code"], "a")
_, tb, db_ = rv.redeem(rv.create_pairing("B")["code"], "a")
assert rv.revoke(da["id"]) is True and rv.revoke(da["id"]) is False and rv.revoke("nichtda") is False
assert rv.authenticate(ta) is None and rv.authenticate(tb) is not None
assert [d["revoked"] for d in rv.devices()] == [True, False]
rv.create_pairing("offen")
assert rv.revoke_all() == 1 and rv.authenticate(tb) is None and rv.pending_count() == 0
assert rv.revoke_all() == 0
# Entsperren: derselbe Token geht wieder; nur Gesperrte; abgelaufene Laufzeit beginnt neu
assert rv.restore(db_["id"]) is True and rv.authenticate(tb) is not None
assert rv.restore(db_["id"]) is False and rv.restore("nichtda") is False
assert rv.authenticate(ta) is None                                      # das andere bleibt gesperrt
assert rv.restore(da["id"]) is True and rv.authenticate(ta) is not None
# abgelaufen und gesperrt: Entsperren gibt wieder volle Laufzeit
rv.revoke(da["id"])
clock.advance(100 * 24 * 3600)
assert rv.authenticate(ta) is None
assert rv.restore(da["id"]) is True and rv.authenticate(ta) is not None
assert rv.revoke(db_["id"]) is True
assert rv.forget(da["id"]) is True and rv.forget(da["id"]) is False and len(rv.devices()) == 1
assert DeviceStore(tmp / "v.json", clock=clock).authenticate(tb) is None  # Sperre ueberlebt den Neustart

# 9) Neustart: Geraete bleiben, kaputte Datei bricht nichts
reopened = DeviceStore(store_path, clock=Clock(clock.now - 400 * 24 * 3600))
assert len(reopened.devices()) == 1 and reopened.authenticate(token) is not None
broken_path = tmp / "b.json"
broken_path.write_text("{kaputt", encoding="utf-8")
broken = DeviceStore(broken_path, clock=clock)
assert broken.devices() == [] and (tmp / "b.json.defekt").exists() and not broken_path.exists()
junk_path = tmp / "j.json"
junk_path.write_text(json.dumps({"devices": [1, "x", {"id": 5}, {"id": "ok1", "token_hash": "h", "name": "N"}]}), encoding="utf-8")
assert [d["id"] for d in DeviceStore(junk_path, clock=clock).devices()] == ["ok1"]
assert DeviceStore(tmp / "nichtda.json", clock=clock).devices() == []

# 10) Speichern schlaegt fehl: dann ist nichts gekoppelt
class FailingStore(DeviceStore):
    def _save(self):
        raise OSError("Platte voll")
failing = FailingStore(tmp / "f.json", clock=clock)
try:
    failing.redeem(failing.create_pairing("F")["code"], "f")
except OSError:
    pass
else:
    raise AssertionError("Fehler haette durchgereicht werden muessen")
assert failing.devices() == []

# 11) Grenzen: 0 = unbegrenzt, sonst je Geraet bzw. pro Tag
free = UsageLimits()
assert all(free.allow_message("a") for _ in range(500)) and all(free.allow_ai_call() for _ in range(500))
limit_clock = Clock(datetime(2026, 11, 7, 12, 0).timestamp())
limits = UsageLimits(max_messages=3, window=600, max_daily=2, clock=limit_clock)
assert [limits.allow_message("a") for _ in range(4)] == [True, True, True, False]
assert limits.allow_message("b") is True                                  # anderes Geraet zaehlt getrennt
limit_clock.advance(601)
assert limits.allow_message("a") is True                                  # Fenster ist vorbei
assert [limits.allow_ai_call() for _ in range(3)] == [True, True, False]
limit_clock.advance(2 * 24 * 3600)
assert limits.allow_ai_call() is True                                     # neuer Tag

# 12) Stufen
assert remote_policy.normalize_levels(None) == {"info": True, "daily": True, "pc": False}
assert remote_policy.normalize_levels({"pc": True, "info": "ja", "extra": True}) == {"info": True, "daily": True, "pc": True}
default_tasks = remote_policy.allowed_tasks(None)
by_id = {a.id: a for a in abilities.ABILITIES}
for ability_id in ("web_search", "weather", "timers", "reminders", "lists", "goals", "calendar"):
    assert set(by_id[ability_id].tasks) <= default_tasks, ability_id
assert {"GET_TIME", "GET_DATE", "CALCULATE", "STOP_RINGING"} <= default_tasks
for ability_id in ("volume", "music", "system"):
    assert not set(by_id[ability_id].tasks) & default_tasks                # PC-Steuerung ist aus
assert "GET_SYSTEM_INFO" not in default_tasks
with_pc = remote_policy.allowed_tasks({"pc": True})
assert set(by_id["volume"].tasks) <= with_pc and "GET_SYSTEM_INFO" in with_pc
assert remote_policy.allowed_tasks({"info": False, "daily": False, "pc": False}) == frozenset()
assert remote_policy.allowed_tasks({"info": True, "daily": False, "pc": False}) < default_tasks

# Jede Faehigkeit ist entschieden: genau eine Stufe oder "nie"; neue Faehigkeiten fallen hier auf
leveled = [a for level in remote_policy.LEVELS for a in remote_policy.LEVEL_ABILITIES[level]]
assert len(leveled) == len(set(leveled))
assert set(leveled).isdisjoint(remote_policy.NEVER_REMOTE)
assert set(leveled) | set(remote_policy.NEVER_REMOTE) == {a.id for a in abilities.ABILITIES}
assert set(remote_policy.LEVEL_CORE_TASKS) == set(remote_policy.LEVELS) == set(remote_policy.LEVEL_ABILITIES) == set(remote_policy.LEVEL_LABELS)
assert all(task in abilities.CORE_TASKS for tasks in remote_policy.LEVEL_CORE_TASKS.values() for task in tasks)
# nichts davon ist je ueber Remote erreichbar, auch nicht mit allen Stufen an
everything = remote_policy.allowed_tasks({"info": True, "daily": True, "pc": True})
for ability_id in remote_policy.NEVER_REMOTE:
    assert not set(by_id[ability_id].tasks) & everything, ability_id

# Alles, was Remote kennt, ist harmlos (Stufe "safe") und wirklich registriert
registry = TaskRegistry()
register_all_tasks(registry)
for task_type in everything:
    task = registry.get(task_type)
    assert task is not None, task_type
    assert task_risk(task) == SAFE, task_type

# 13) Adressen
for path in ("/api/message", "/api/speak", "/api/ringing/stop", "/api/timer/cancel", "/api/focus/stop", "/api/conversation/open", "/api/conversation/new", "/api/project/open"):
    assert remote_policy.api_allowed("POST", path) and not remote_policy.api_allowed("GET", path), path
for path in ("/api/settings", "/api/background", "/api/timers", "/api/ringing", "/api/alarms", "/api/widgets", "/api/weather",
             "/api/projects", "/api/focus", "/api/sync", "/api/remote/whoami"):
    assert remote_policy.api_allowed("GET", path) and not remote_policy.api_allowed("POST", path), path
for path in ("/api/confirm", "/api/plan/confirm", "/api/plan/abort", "/api/memory/delete", "/api/memory/delete_all",
             "/api/memory/update", "/api/memories", "/api/actions", "/api/folders", "/api/folders/add", "/api/alarms/add",
             "/api/alarms/delete", "/api/alarms/update", "/api/project/delete", "/api/project/rename", "/api/project/new",
             "/api/conversation/delete", "/api/conversation/rename", "/api/conversation/reset",
             "/api/hints", "/api/goals/evening", "/api/widgets/notes", "/api/widgets/lists", "/api/widgets/events",
             "/api/system", "/api/performance", "/api/hockey", "/api/remote/pair", "/api/remote/devices", "/", "/pair", "", "/api/"):
    assert not remote_policy.api_allowed("GET", path), path
    assert not remote_policy.api_allowed("POST", path), path
# Ziele und Listen: nur mit der Stufe "Alltag" (und nie ohne Angabe der Stufen)
for path in ("/api/widgets/goals", "/api/widgets/lists", "/api/widgets/notes", "/api/widgets/device_note"):
    assert not remote_policy.api_allowed("POST", path) and not remote_policy.api_allowed("POST", path, None)
    assert remote_policy.api_allowed("POST", path, {"info": False, "daily": True, "pc": False}), path
    assert remote_policy.api_allowed("POST", path, {"daily": True}), path
    assert not remote_policy.api_allowed("POST", path, {"info": True, "daily": False, "pc": True}), path
    assert not remote_policy.api_allowed("GET", path, {"daily": True}), path
for path in ("/api/widgets/events", "/api/widgets/events/delete", "/api/widgets/events/delete_series", "/api/goals/evening", "/api/alarms/add"):
    assert not remote_policy.api_allowed("POST", path, {"info": True, "daily": True, "pc": True}), path
assert not remote_policy.api_allowed("PUT", "/api/widgets/goals", {"daily": True})
assert not remote_policy.api_allowed("PUT", "/api/message") and not remote_policy.api_allowed("DELETE", "/api/timers")
assert not remote_policy.api_allowed("get", "/api/timers") and not remote_policy.api_allowed(None, None)
assert remote_policy.is_public("GET", "/pair") and remote_policy.is_public("POST", "/api/remote/pair")
assert not remote_policy.is_public("POST", "/pair") and not remote_policy.is_public("GET", "/api/remote/pair")
assert not remote_policy.is_public("GET", "/api/message") and not remote_policy.is_public("GET", "/api/settings")

# Die Listen enthalten nur Adressen, die es gibt (oder in R2 noch gebaut werden), nichts Verschriebenes
server_source = (PROJECT_DIR / "server.py").read_text(encoding="utf-8")
routes = set(re.findall(r'"(/api/[a-z_/]+)"', server_source))
upcoming = {"/api/sync", "/api/remote/whoami", "/api/remote/pair"}
for path in remote_policy.GET_API | remote_policy.POST_API | remote_policy.PUBLIC_POST:
    assert path in routes or path in upcoming, path

# 14) Sicherheit der Quelle
for name in ("remote_auth.py", "remote_policy.py"):
    source = (PROJECT_DIR / name).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "eval(", "exec(", "shell=True", "print(", "requests", "urllib"):
        assert forbidden not in source, (name, forbidden)
assert "random." not in (PROJECT_DIR / "remote_auth.py").read_text(encoding="utf-8").replace("secrets.", "")
assert "remote_devices.json" in (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")

print("ALL TESTS PASSED")
