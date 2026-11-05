"""Bildschirm ansehen (Mark 5, Step 2.25): erst nach Rueckfrage, Bild nie als Text und nie gespeichert, nur in einem einzigen Modellaufruf."""
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

import base64
import subprocess
import types

import abilities
import action_executor
import brain
import guest
import plan as plan_module
import risk
import task_executor
import tools.screen_tool as sc
from action import Action
from task import Task
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools.tool_result import ToolResult

REAL_PLATFORM = sys.platform
PNG = base64.b64encode(sc.PNG_SIGNATURE + b"\x00" * 64).decode("ascii")
shots = []
state = {"value": PNG}


def fake_capture():
    shots.append(1)
    value = state["value"]
    if isinstance(value, Exception):
        raise value
    return value


sc._capture = fake_capture
sys.platform = "win32"

# 1) Aufnahme: Bild unter dem internen Schluessel, Frage gesaeubert
r = sc.describe_screen("Was bedeutet der Fehler?")
assert r.success and r.data[sc.IMAGE_KEY] == PNG and r.data["question"] == "Was bedeutet der Fehler?" and "image" in r.data
assert "question" not in sc.describe_screen("").data and "question" not in sc.describe_screen(None).data
assert "question" not in sc.describe_screen({"description": "x"}).data
q = sc.describe_screen("x\u200b" * 400).data["question"]
assert len(q) <= sc.MAX_QUESTION and "\u200b" not in q
assert sc.IMAGE_KEY.startswith("_"), "interne Schluessel beginnen mit _ und werden nie als Text ausgegeben"

# 2) Ungueltige Bilder werden abgelehnt (nichts Unbekanntes geht an das Modell)
huge = base64.b64encode(sc.PNG_SIGNATURE + b"\x00" * (sc.MAX_BYTES + 10)).decode("ascii")
for bad in ("", None, 5, "kein base64!", "AAAA", base64.b64encode(b"GIF89a-kein-png").decode(), huge, PNG + "\n", "data:image/png;base64," + PNG):
    state["value"] = bad
    r = sc.describe_screen("")
    assert not r.success and "brauchbares Bild" in r.error, repr(bad)[:40]
edge_ok = base64.b64encode(sc.PNG_SIGNATURE + b"\x00" * (sc.MAX_BYTES - len(sc.PNG_SIGNATURE))).decode("ascii")
edge_big = base64.b64encode(sc.PNG_SIGNATURE + b"\x00" * (sc.MAX_BYTES - len(sc.PNG_SIGNATURE) + 1)).decode("ascii")
assert sc._valid_png(edge_ok) and not sc._valid_png(edge_big), "genau MAX_BYTES ist erlaubt, ein Byte mehr nicht"
state["value"] = PNG
assert sc._valid_png(PNG) and not sc._valid_png(PNG + "!")

# 3) Fehler: ein Satz, keine Ausnahme, keine Details
for exc, part in ((OSError("boom C:\\geheim"), "nicht geklappt"), (RuntimeError("x"), "nicht geklappt"),
                  (subprocess.TimeoutExpired("powershell", 30), "zu lange")):
    state["value"] = exc
    r = sc.describe_screen("")
    assert not r.success and part in r.error and "geheim" not in r.error and "boom" not in r.error, exc
state["value"] = PNG
sys.platform = "linux"
shots.clear()
r = sc.describe_screen("")
assert not r.success and "Windows" in r.error and shots == [], "nicht unter Windows: keine Aufnahme"
sys.platform = "win32"

# 4) Die echte Huelle: festes Skript, Base64 per -EncodedCommand, Ausgabe als Bytes
real_capture_source = open(PROJECT_DIR / "tools" / "screen_tool.py", encoding="utf-8").read()
ns = {}
exec(compile(real_capture_source, "screen_tool_copy", "exec"), ns)
runs = []


def fake_run(cmd, **kw):
    runs.append((cmd, kw))
    return types.SimpleNamespace(returncode=fake_run.code, stdout=fake_run.out)


ns["subprocess"].run, saved_run = fake_run, subprocess.run
subprocess.run = fake_run
try:
    fake_run.code, fake_run.out = 0, (PNG + "\r\n").encode()
    assert ns["_capture"]() == PNG
    cmd, kw = runs[0]
    assert cmd[0] == "powershell" and cmd[-2] == "-EncodedCommand" and "text" not in kw and kw["timeout"] == sc.CAPTURE_TIMEOUT
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "CopyFromScreen" in script and "PrimaryScreen" in script and str(sc.MAX_WIDTH) in script
    assert "Save(" in script and "MemoryStream" in script and ".png" not in script.lower().replace("imageformat]::png", "") and "Out-File" not in script and "Set-Content" not in script
    fake_run.code = 1
    try:
        ns["_capture"]()
        raise SystemExit("Fehlercode ignoriert")
    except OSError:
        pass
finally:
    subprocess.run = saved_run

# 5) Rueckfrage: sagt, was passiert; liest/ nimmt nichts auf
shots.clear()
text = " ".join(sc.describe("egal"))
assert "OpenAI" in text and "nicht gespeichert" in text and "Passwörter" in text and shots == []

# 6) Einbindung: Risiko (immer fragen), Rueckfrage, Fähigkeit, Gast, Plaene
registry = TaskRegistry()
register_all_tasks(registry)
task = next(t for t in registry.get_all() if t.task_type == "DESCRIBE_SCREEN")
assert [a.name for a in task.actions] == ["describe_screen"]
assert risk.task_risk(task) == risk.CONFIRM and risk.ACTION_RISK["describe_screen"] == risk.CONFIRM
goal, details = risk.describe_task(task)
assert goal == "Bildschirm ansehen" and "Hauptbildschirm" in " ".join(details) and "Beispiel" not in " ".join(details) and shots == []
screen = next(a for a in abilities.ABILITIES if a.id == "screen")
assert screen.default is False and screen.tasks == ("DESCRIBE_SCREEN",)
assert "DESCRIBE_SCREEN" not in guest.GUEST_TASKS
assert "DESCRIBE_SCREEN" in plan_module.NOT_IN_PLANS
try:
    plan_module.parse_plan({"goal": "Bildschirm", "steps": [{"task_type": "DESCRIBE_SCREEN", "parameters": {}}]}, registry)
    raise SystemExit("Bildschirm in einem Plan erlaubt")
except plan_module.PlanError as error:
    assert "einzeln" in str(error)

# Ohne Bestaetigung wird nichts aufgenommen; mit Bestaetigung genau einmal
task.actions[0].parameters = {"question": "Was siehst du?"}
shots.clear()
task_executor.execute_task(task, confirmed=False)
assert task.status == "BLOCKED" and shots == [], "ohne Ja keine Aufnahme"
task_executor.execute_task(task, confirmed=True)
assert task.status == "COMPLETED" and shots == [1] and task.result[0].data[sc.IMAGE_KEY] == PNG

# 7) Das Bild reist nur in EINEM Modellaufruf mit, nie als Text, und ist danach weg
class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text="Ich sehe einen Editor.")


client = FakeClient()
assert brain.respond_to_task(client, "Was siehst du auf meinem Bildschirm?", task) == "Ich sehe einen Editor."
assert len(client.calls) == 1
call = client.calls[0]
assert isinstance(call["input"], list) and call["input"][0]["role"] == "user"
parts = call["input"][0]["content"]
assert [p["type"] for p in parts] == ["input_text", "input_image"]
assert parts[1]["image_url"] == "data:image/png;base64," + PNG
assert PNG not in parts[0]["text"] and PNG not in call["instructions"], "das Bild steht nie im Text"
assert "describe_screen" in parts[0]["text"].lower() or "DESCRIBE_SCREEN" in parts[0]["text"]
assert "Was siehst du?" in parts[0]["text"], "die Frage steht im Text"
assert sc.IMAGE_KEY not in task.result[0].data and "question" in task.result[0].data, "nach der Antwort ist das Bild weg"
assert PNG not in repr(task.result[0].data) and PNG not in brain.results_to_json(task.result)

# auch wenn der Modellaufruf scheitert, wird das Bild weggeworfen
task_executor.execute_task(task, confirmed=True)
assert task.result[0].data[sc.IMAGE_KEY] == PNG


class BrokenClient:
    responses = None

    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        raise RuntimeError("API kaputt")


try:
    brain.respond_to_task(BrokenClient(), "x", task)
    raise SystemExit("Fehler verschluckt")
except RuntimeError:
    pass
assert sc.IMAGE_KEY not in task.result[0].data

# Andere Aufgaben bleiben reiner Text; Ergebnisse ohne Bild aendern sich nicht
other = Task("GET_TIME", "Zeit")
other.status = "COMPLETED"
other.result = [ToolResult(True, data={"time": "12:00"})]
client = FakeClient()
brain.respond_to_task(client, "Wie spät?", other)
assert isinstance(client.calls[0]["input"], str) and "12:00" in client.calls[0]["input"]

# Interne Schluessel (Anfang "_") kommen nie in den Text, auch nicht bei anderen Werkzeugen
leaky = [ToolResult(True, data={"ok": 1, "_geheim": "XYZ", "_image_png_base64": PNG})]
assert "XYZ" not in brain.results_to_json(leaky) and PNG not in brain.results_to_json(leaky) and '"ok": 1' in brain.results_to_json(leaky)
assert brain.public_data([1, 2]) == [1, 2] and brain.public_data(None) is None and brain.public_data("x") == "x"
assert len(brain.collect_images([ToolResult(True, data={"_image_png_base64": PNG}) for _ in range(5)])) == 3
assert brain.collect_images([ToolResult(True, data={"_image_png_base64": 5}), ToolResult(True, data=None), object()]) == []

# 8) Das Bild landet nie im Aktionsprotokoll: summarize nennt keine Daten
import action_log
registry2 = TaskRegistry()
register_all_tasks(registry2)
logged = next(t for t in registry2.get_all() if t.task_type == "DESCRIBE_SCREEN")
task_executor.execute_task(logged, confirmed=True)
assert logged.status == "COMPLETED" and logged.result[0].data[sc.IMAGE_KEY] == PNG
assert PNG not in action_log.summarize(logged) and action_log.summarize(logged) == "Daten erhalten"

# Kein Schreibweg fuer das Bild im Modul (nichts auf die Festplatte)
code = real_capture_source.split('"""', 2)[2]
for forbidden in ("open(", "write(", "Out-File", "Set-Content", ".Save($", "tempfile", "shell=True", "os.system"):
    assert forbidden not in code.replace(".Save($ms,", ""), forbidden

sys.platform = REAL_PLATFORM
print("ALL TESTS PASSED")
