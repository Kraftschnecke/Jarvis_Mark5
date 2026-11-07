"""Remote R3 (Mark 5): Nachrichten vom Handy. Nur Aufgaben der freigegebenen Stufen, nie Rueckfragen/Plaene/Befehle, PC-Rueckfragen bleiben unberuehrt."""
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

import contextlib
import io
import json
import tempfile
import threading

import action_log
import jarvis as jarvis_module
import remote_policy
import task_executor
from jarvis import Jarvis
from settings_manager import SettingsManager
from tasks import register_all_tasks
from task_registry import TaskRegistry
from tools.tool_result import ToolResult

tmp = Path(tempfile.mkdtemp())
settings = SettingsManager(tmp / "settings.json")

ran = []
logged = []
remote_logged = []
prompts = []
state = {"route": {"kind": "CHAT"}, "seen_other_thread": None, "j": None}

task_executor.execute_action = lambda action: ran.append(action.name) or ToolResult(success=True, data="ok")
action_log.record = lambda task, decision, status=None: logged.append((task.task_type, decision, status))
action_log.record_remote = lambda device, text, outcome: remote_logged.append((device, text, outcome))


class FakeClient:
    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        text = str(kwargs.get("input"))
        prompts.append(text)

        if "User message (as a JSON string)" in text:
            if state["seen_other_thread"] is not None:
                seen = []
                worker = threading.Thread(target=lambda: seen.append(state["j"].task_registry.get("START_PROGRAM") is not None))
                worker.start()
                worker.join()
                state["seen_other_thread"] = seen[0]
            return types.SimpleNamespace(output_text=json.dumps(state["route"]))

        return types.SimpleNamespace(output_text="Fertig.")


class FakeConversation:
    def __init__(self):
        self.messages = []

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})


normal_calls = []


def make_jarvis():
    j = object.__new__(Jarvis)
    j.client = FakeClient()
    j.settings_manager = settings
    j.task_registry = TaskRegistry(is_enabled=lambda t: jarvis_module.abilities.task_enabled(t, settings))
    register_all_tasks(j.task_registry)
    j.pending_project_confirmation = None
    j.memory_enabled = lambda: False
    j.get_memory_context = lambda: ""
    j.workspace = types.SimpleNamespace(
        project_state=types.SimpleNamespace(active_project=(1, "P"), active_conversation=(5, "C")),
        conversation=FakeConversation(),
    )
    state["j"] = j
    return j


def reset():
    ran.clear()
    logged.clear()
    remote_logged.clear()
    prompts.clear()
    normal_calls.clear()
    state["route"] = {"kind": "CHAT"}
    state["seen_other_thread"] = None


def remote(j, text, levels=None, device="iPhone"):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return j.process_remote_message(text, device, levels or remote_policy.DEFAULT_LEVELS)


def task_route(task_type, parameters=None):
    return {"kind": "TASK", "task_type": task_type, "parameters": parameters or {}}


def command_route(intent, **extra):
    raw = {"kind": "COMMAND", "intent": intent}
    raw.update(extra)
    return raw


# Normale Unterhaltung vom Handy merken wir uns, ohne die echte Antwort-Logik
jarvis_module.ask_jarvis = lambda client, conversation, memory_context, project_context: "Antwort vom Modell"
jarvis_module.get_project_context = lambda project_id: None
jarvis_module.save_message = lambda *a, **k: None
project_jobs = []
jarvis_module.process_project_context = lambda client, project_id, message: project_jobs.append(message) or {
    "status": "confirmation_required", "section": "notes", "content": "Neuer Fakt"}

REFUSAL = "Das geht nur am PC."

# =====================================================================
# 1) Die Aufgabenliste fuer das Handy: genau die freigegebenen Stufen
# =====================================================================

reset()
j = make_jarvis()
for levels, present, absent in (
    ({"info": True, "daily": True, "pc": False}, ("GET_WEATHER", "START_TIMER", "STOP_RINGING", "GET_TIME"), ("SET_VOLUME", "START_PROGRAM", "WRITE_NOTE", "OPEN_WEBSITE", "READ_MAIL")),
    ({"info": True, "daily": True, "pc": True}, ("SET_VOLUME", "MEDIA_CONTROL", "GET_SYSTEM_INFO"), ("START_PROGRAM", "OPEN_FILE", "READ_CLIPBOARD", "DESCRIBE_SCREEN", "FIND_FILES")),
    ({"info": False, "daily": False, "pc": False}, (), ("GET_WEATHER", "START_TIMER", "GET_TIME")),
    ({"info": True, "daily": False, "pc": False}, ("GET_WEATHER",), ("START_TIMER", "STOP_RINGING")),
):
    registry = j.remote_registry(levels)
    for task_type in present:
        assert registry.get(task_type) is not None, (levels, task_type)
    for task_type in absent:
        assert registry.get(task_type) is None, (levels, task_type)

# Ist eine Faehigkeit in den Abilities ausgeschaltet, fehlt sie auch am Handy
settings.set("abilities", "weather", False)
assert j.remote_registry(remote_policy.DEFAULT_LEVELS).get("GET_WEATHER") is None
settings.set("abilities", "weather", True)
assert j.remote_registry(remote_policy.DEFAULT_LEVELS).get("GET_WEATHER") is not None

# =====================================================================
# 2) Der Router sieht beim Handy nur die erlaubte Liste, der PC-Thread weiter alles
# =====================================================================

reset()
j = make_jarvis()
state["seen_other_thread"] = False
out = remote(j, "Hallo")
router_prompt = [p for p in prompts if "User message (as a JSON string)" in p][0]
available, switched_off = router_prompt.split("SWITCHED OFF by the user")
assert "GET_WEATHER" in available and "START_TIMER" in available
for task_type in ("START_PROGRAM", "WRITE_NOTE", "SET_VOLUME", "OPEN_WEBSITE", "READ_MAIL"):
    assert task_type not in available, task_type        # nicht als Aufgabe angeboten ...
for task_type in ("START_PROGRAM", "WRITE_NOTE", "SET_VOLUME"):
    assert task_type in switched_off, task_type         # ... nur als "aus", damit die Antwort feststeht
assert "GET_WEATHER" not in switched_off
assert state["seen_other_thread"] is True                      # ein anderer Thread (z.B. der PC) sieht weiter alles
assert j.task_registry.get("START_PROGRAM") is not None        # und danach ist alles wieder normal
assert j.task_registry.get("SET_VOLUME") is not None

# Auch bei einem Fehler mittendrin wird die Einschraenkung wieder aufgehoben
j.client.responses.create = lambda **k: (_ for _ in ()).throw(RuntimeError("kaputt"))
out = remote(j, "Hallo")
assert out["status"] == "response" and "Fehler" in out["content"]
assert j.task_registry.get("START_PROGRAM") is not None
assert jarvis_module._remote_scope.registry is None

# =====================================================================
# 3) Erlaubte Aufgabe wird ausgefuehrt und protokolliert
# =====================================================================

reset()
j = make_jarvis()
state["route"] = task_route("GET_TIME")
out = remote(j, "Wie spaet ist es?", device="iPhone Moritz")
assert out == {"status": "response", "content": "Fertig."} and ran != []
assert remote_logged == [("iPhone Moritz", "Wie spaet ist es?", "TASK:GET_TIME")]

# =====================================================================
# 4) Nicht erlaubte Aufgaben: nicht ausgefuehrt, feste Antwort, protokolliert
# =====================================================================

for task_type, params in (("START_PROGRAM", {"program": "notepad"}), ("WRITE_NOTE", {"filename": "a", "content": "b"}),
                          ("SET_VOLUME", {"level": 10}), ("OPEN_WEBSITE", {"url": "https://example.org"}),
                          ("READ_MAIL", {"which": "1"}), ("OPEN_FILE", {"filename": "x.txt"})):
    reset()
    j = make_jarvis()
    state["route"] = task_route(task_type, params)
    out = remote(j, "mach das")
    assert out == {"status": "response", "content": REFUSAL}, task_type
    assert ran == [] and j.pending_action is None, task_type
    assert remote_logged == [("iPhone", "mach das", "REFUSED")], task_type

# PC-Stufe an: Lautstaerke geht, Programme starten weiterhin nicht
reset()
j = make_jarvis()
state["route"] = task_route("SET_VOLUME", {"level": 10})
out = remote(j, "leiser", levels={"info": True, "daily": True, "pc": True})
assert out["content"] == "Fertig." and ran != []
reset()
j = make_jarvis()
state["route"] = task_route("START_PROGRAM", {"program": "notepad"})
assert remote(j, "oeffne notepad", levels={"info": True, "daily": True, "pc": True})["content"] == REFUSAL and ran == []

# =====================================================================
# 5) Erlaubte Aufgabe, die eine Rueckfrage braeuchte: abgelehnt, nichts vorgemerkt
# =====================================================================

reset()
j = make_jarvis()
state["route"] = task_route("CANCEL_REMINDER", {"which": "alle"})
out = remote(j, "loesche alle Erinnerungen")
confirm_needed = jarvis_module.risk.task_risk(jarvis_module.prepare_registered_task(j.task_registry, "CANCEL_REMINDER", {"which": "alle"})) == "confirm"
assert confirm_needed                                          # sonst prueft dieser Fall nichts
assert out == {"status": "response", "content": REFUSAL} and j.pending_action is None and ran == []
assert logged == [("CANCEL_REMINDER", "refused", "BLOCKED")]
assert remote_logged == [("iPhone", "loesche alle Erinnerungen", "REFUSED")]
# dieselbe Aufgabe mit einer einzelnen Erinnerung ist harmlos und laeuft
reset()
state["route"] = task_route("CANCEL_REMINDER", {"which": "1"})
assert remote(make_jarvis(), "loesche Erinnerung 1")["content"] == "Fertig." and ran != []

# =====================================================================
# 6) Plaene und Befehle gibt es nur am PC
# =====================================================================

for route in ({"kind": "PLAN"},
              command_route("EXIT"), command_route("RESET_CONVERSATION"), command_route("OPEN_PROJECT", project_name="X"),
              command_route("CREATE_PROJECT", project_name="X"), command_route("OPEN_CONVERSATION", conversation_name="Y")):
    reset()
    j = make_jarvis()
    j.pending_plan = None
    state["route"] = route
    out = remote(j, "tu es")
    assert out == {"status": "response", "content": REFUSAL}, route
    # nichts wurde ausgefuehrt (Reset, Projektwechsel ...): im Verlauf steht nur die Nachricht samt Absage
    assert j.workspace.conversation.messages == [{"role": "user", "content": "tu es"}, {"role": "assistant", "content": REFUSAL}] and ran == []
    assert remote_logged == [("iPhone", "tu es", "REFUSED")]
    assert not any("Create a plan of steps" in p for p in prompts)      # kein Planer-Aufruf

# "Was kannst du?" zeigt nur, was am Handy geht
reset()
j = make_jarvis()
state["route"] = command_route("SHOW_CAPABILITIES")
out = remote(j, "Was kannst du?")
assert out["status"] == "response" and out["content"] != REFUSAL
assert remote_logged[0][2] == "COMMAND:SHOW_CAPABILITIES"
assert out["content"].startswith("Am Handy kann ich dir helfen mit:") and out["content"].endswith("geht nur am PC.")
for word in ("Wetter", "Timer"):
    assert word in out["content"], word
for word in ("Projekt", "beenden", "programs.json", "Notizen schreiben"):
    assert word not in out["content"].split("Außerdem")[0], word

reset()
j = make_jarvis()
state["route"] = command_route("SHOW_CAPABILITIES")
only_info = remote(j, "Was kannst du?", levels={"info": True, "daily": False, "pc": False})["content"]
assert "Wetter" in only_info and "Timer" not in only_info and "Wecker" not in only_info
none_at_all = remote(j, "Was kannst du?", levels={"info": False, "daily": False, "pc": False})["content"]
assert "helfen mit: plaudern." in none_at_all

# Kommt aus dem normalen Weg etwas anderes als eine Antwort (Rueckfrage, Plan), wird daraus die feste Absage
reset()
j = make_jarvis()
j.process_normal_message = lambda m, remote=False: {"status": "confirmation", "content": "Soll ich?", "confirmation": {"id": "x"}}
out = remote(j, "Hallo")
assert out == {"status": "response", "content": REFUSAL} and remote_logged == [("iPhone", "Hallo", "REFUSED")]

# =====================================================================
# 7) Offene Rueckfragen am PC bleiben, "ja" vom Handy bestaetigt nichts
# =====================================================================

reset()
j = make_jarvis()
j.pending_action = {"id": "abc", "task": object(), "message": "x", "expires": 10**12}
j.pending_plan = {"id": "p1", "plan": object(), "approved": set(), "message": "y", "expires": 10**12}
j.pending_project_confirmation = {"project_id": 1, "section": "notes", "content": "Fakt"}
state["route"] = {"kind": "CHAT"}
out = remote(j, "ja")
assert out["content"] == "Antwort vom Modell"
assert j.pending_action is not None and j.pending_plan is not None and j.pending_project_confirmation is not None
assert ran == [] and logged == []
assert project_jobs == []                                      # keine Projekt-Pruefung mit Rueckfrage vom Handy
assert "Frage" not in out["content"] and "soll ich" not in out["content"]
assert [m["role"] for m in j.workspace.conversation.messages] == ["user", "assistant"]    # gleiche Unterhaltung wie am PC

# Auch ein Fehler vom Handy raeumt die Rueckfrage am PC nicht ab
j.client.responses.create = lambda **k: (_ for _ in ()).throw(RuntimeError("kaputt"))
remote(j, "noch eins")
assert j.pending_action is not None and j.pending_plan is not None

# ... und das Tageslimit auch nicht
import cost_guard
def over_limit(**k):
    raise cost_guard.LimitReached("ai", 500)
j.client.responses.create = over_limit
out = remote(j, "und noch eins")
assert "tageslimit" in out["content"].lower() and j.pending_action is not None and j.pending_plan is not None
# Am PC raeumt dasselbe Limit die Rueckfrage ab (wie bisher)
with contextlib.redirect_stdout(io.StringIO()):
    j.process_message("am PC")
assert j.pending_action is None and j.pending_plan is None

# Am PC bleibt alles wie gehabt: normale Nachricht raeumt auf und fragt nach
reset()
project_jobs.clear()
j = make_jarvis()
j.pending_action = {"id": "abc", "task": object(), "message": "x", "expires": 10**12}
with contextlib.redirect_stdout(io.StringIO()):
    out = j.process_normal_message("Ich arbeite jetzt an Etwas Neuem")
assert project_jobs == ["Ich arbeite jetzt an Etwas Neuem"] and j.pending_action is None
assert j.pending_project_confirmation is not None and "Neuer Fakt" in out["content"]

# =====================================================================
# 8) Laeutet etwas, schaltet "Wecker aus" vom Handy ab (nur mit Stufe Alltag)
# =====================================================================

import ringing
calls = []
real_handle = ringing.handle_message
ringing.handle_message = lambda message, address: calls.append(message) or "Wecker aus."
reset()
j = make_jarvis()
out = remote(j, "Wecker aus")
assert out["content"] == "Wecker aus." and remote_logged[0][2] == "TASK:STOP_RINGING" and prompts == []
reset()
calls.clear()
out = remote(make_jarvis(), "Wecker aus", levels={"info": True, "daily": False, "pc": False})
assert calls == [] and prompts != []                           # ohne Alltag: nicht abgefangen, ganz normal weiter
ringing.handle_message = real_handle

# =====================================================================
# 9) Am PC aendert sich nichts: letzte Antwort wird nur dort gemerkt
# =====================================================================

reset()
j = make_jarvis()
j.last_reply = "PC-Antwort"
remote(j, "Hallo")
assert j.last_reply == "PC-Antwort"
state["route"] = {"kind": "CHAT"}
with contextlib.redirect_stdout(io.StringIO()):
    out = j.process_message("Hallo vom PC")
assert out["status"] == "response" and j.last_reply == out["content"]

# =====================================================================
# 9b) Gemeinsame Unterhaltung: auch Aufgaben und Ablehnungen vom Handy stehen am PC im Verlauf
# =====================================================================

saved = []
jarvis_module.save_message = lambda conversation_id, role, content: saved.append((conversation_id, role, content))

# Aufgabe
reset()
saved.clear()
j = make_jarvis()
state["route"] = task_route("GET_TIME")
remote(j, "Wie spaet ist es?")
assert j.conversation.messages == [{"role": "user", "content": "Wie spaet ist es?"}, {"role": "assistant", "content": "Fertig."}]
assert saved == [(5, "user", "Wie spaet ist es?"), (5, "assistant", "Fertig.")]

# Ablehnung
reset()
saved.clear()
j = make_jarvis()
state["route"] = task_route("START_PROGRAM", {"program": "notepad"})
remote(j, "oeffne notepad")
assert j.conversation.messages == [{"role": "user", "content": "oeffne notepad"}, {"role": "assistant", "content": REFUSAL}]
assert saved == [(5, "user", "oeffne notepad"), (5, "assistant", REFUSAL)]

# Befehl (kommt nur am PC vor)
reset()
j = make_jarvis()
state["route"] = command_route("SHOW_CAPABILITIES")
remote(j, "was kannst du")
assert [m["role"] for m in j.conversation.messages] == ["user", "assistant"]

# Normale Unterhaltung: genau einmal, nicht doppelt
reset()
saved.clear()
j = make_jarvis()
remote(j, "Hallo")
assert j.conversation.messages == [{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Antwort vom Modell"}]
assert saved == [(5, "user", "Hallo"), (5, "assistant", "Antwort vom Modell")]

# Reihenfolge ueber mehrere Nachrichten, ohne offene Konversation wird nur der Verlauf im Speicher gefuehrt
reset()
saved.clear()
j = make_jarvis()
j.workspace.project_state.active_conversation = None
state["route"] = task_route("GET_TIME")
remote(j, "eins")
state["route"] = {"kind": "CHAT"}
remote(j, "zwei")
assert [m["content"] for m in j.conversation.messages] == ["eins", "Fertig.", "zwei", "Antwort vom Modell"] and saved == []

# Der Fingerabdruck fuer den Live-Abgleich aendert sich dadurch (der PC holt es sich)
import server
reset()
j = make_jarvis()
j.get_active = lambda: None
j.get_tree = lambda: []
before = server.sync_state(j)["version"]
state["route"] = task_route("GET_TIME")
remote(j, "Wie spaet ist es?")
assert server.sync_state(j, before)["version"] != before

# =====================================================================
# 10) Quelltext: nichts Verbotenes im neuen Weg
# =====================================================================

source = (PROJECT_DIR / "jarvis.py").read_text(encoding="utf-8")
remote_source = source.split("# ---------- Handy (Remote R3) ----------")[1].split("def _process_message")[0]
for forbidden in ("pending_action =", "pending_plan =", "clear_pending", "handle_pending", "run_plan_request", "confirm_action", "handle_command", "open_project"):
    assert forbidden not in remote_source, forbidden

print("ALL TESTS PASSED")
