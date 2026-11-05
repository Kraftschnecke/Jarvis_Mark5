"""Musiksteuerung (Mark 5, Step 2.21): nur drei feste Medientasten, nur unter Windows, keine Konten."""
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

import action_executor
import guest
import risk
import abilities
import tools.media_tool as mt
from action import Action
from task_registry import TaskRegistry
from tasks import register_all_tasks

pressed = []
mt._press = lambda key: pressed.append(key)
REAL_PLATFORM = sys.platform


def as_windows():
    sys.platform = "win32"


def restore():
    sys.platform = REAL_PLATFORM


# 1) Befehle und Woerter, die das Modell statt der festen Namen schreiben kann
for raw, expected in (("play_pause", "play_pause"), ("play", "play_pause"), ("Pause", "play_pause"), (" STOP ", "play_pause"),
                      ("next", "next"), ("Nächster", "next"), ("next track", "next"), ("skip", "next"),
                      ("previous", "previous"), ("zurück", "previous"), ("Previous Track", "previous"), ("back", "previous")):
    assert mt.normalize_command(raw) == expected, raw
for raw in ("", "  ", None, 5, {"description": "x"}, "lauter", "ordner loeschen", "rm -rf", "volume_up", "play; calc.exe"):
    assert mt.normalize_command(raw) is None, raw

# 2) Jede Taste ist die richtige (genau die drei Medientasten, sonst nichts)
assert set(mt.COMMANDS) == {"play_pause", "next", "previous"}
assert {k for k, _ in mt.COMMANDS.values()} == {0xB3, 0xB0, 0xB1}

as_windows()
for command, vk in (("play_pause", 0xB3), ("next", 0xB0), ("previous", 0xB1), ("pause", 0xB3), ("Nächster", 0xB0)):
    pressed.clear()
    result = mt.media_control(command)
    assert result.success and pressed == [vk], (command, pressed)
    assert result.data["command"] in mt.COMMANDS and result.data["done"]
assert "note" in mt.media_control("play").data and "note" not in mt.media_control("next").data

# 3) Ungueltige Eingaben druecken nichts
pressed.clear()
for bad in ("", None, "lauter", {"description": "x", "type": "string"}, "play; calc.exe"):
    result = mt.media_control(bad)
    assert not result.success and "Musikbefehl" in result.error and pressed == [], bad

# 4) Nicht unter Windows: klarer Satz, keine Taste
restore()
sys.platform = "linux"
pressed.clear()
result = mt.media_control("next")
assert not result.success and "Windows" in result.error and pressed == []

# 5) Tastenfehler wird zum Tool-Fehler, keine Ausnahme nach aussen
as_windows()


def boom(key):
    raise OSError("kaputt")


mt._press = boom
result = mt.media_control("next")
assert not result.success and "kaputt" in result.error
mt._press = lambda key: pressed.append(key)

# 6) Einbindung: Aufgabe, Action, Executor, Risiko, Fähigkeit
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("MEDIA_CONTROL") if hasattr(registry, "get") else next(t for t in registry.get_all() if t.task_type == "MEDIA_CONTROL")
assert [a.name for a in task.actions] == ["media_control"]
assert risk.task_risk(task) == risk.SAFE
pressed.clear()
action = Action("media_control", {"command": "next"})
assert action_executor.execute_action(action).success and pressed == [0xB0]

# Router hat den Parameter weggelassen -> Schema-Dict statt Text: nichts wird gedrueckt
pressed.clear()
default_action = Action("media_control", {"command": {"description": "play_pause ...", "type": "string"}})
assert not action_executor.execute_action(default_action).success and pressed == []

music = abilities.get("music") if hasattr(abilities, "get") else next(a for a in abilities.ABILITIES if a.id == "music")
assert music.tasks == ("MEDIA_CONTROL",) and music.default is True

# 7) Gastmodus: nicht erlaubt
assert "MEDIA_CONTROL" not in guest.GUEST_TASKS

# 8) Es gibt keinen Weg zu einer zweiten Taste ueber den Namen (keine Ausfuehrung von Text)
source = Path(PROJECT_DIR / "tools" / "media_tool.py").read_text(encoding="utf-8")
assert "subprocess" not in source and "os.system" not in source and "startfile" not in source

restore()
print("ALL TESTS PASSED")
