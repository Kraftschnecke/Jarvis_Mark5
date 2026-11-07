"""Einkaufs- und Packlisten (Mark 5, Step 2.30): Speicher, Chat-Aufgaben, Seite."""
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

import json
import tempfile
from datetime import date

import abilities
import action_executor
import guest
import risk
import widgets
import tools.lists_tool as lt
from action import Action
from settings_manager import SettingsManager
from task_registry import TaskRegistry
from tasks import register_all_tasks
from widgets import WidgetStore

folder = Path(tempfile.mkdtemp())
store = WidgetStore(folder / "w.json", today=lambda: date(2026, 11, 5))
lists = lambda: store.get()["lists"]
widgets.set_default_store(store)

# 1) Namen
key = WidgetStore.list_key
assert key("Einkaufsliste") == "einkaufs" and key("Einkauf") == "einkauf" and key(" Pack Liste ") == "pack" and key("Liste") == "liste" and key("List") == "list"
assert key("Shopping List") == "shopping" and key("") == "" and key(None) == "none"

# 2) Setzen
r = lt.add_to_list("Einkauf", "Milch, Eier; Brot\nKäse,, ,")
assert r.success and r.data == {"list": "Einkauf", "created": True, "added": ["Milch", "Eier", "Brot", "Käse"], "already": []}, r.data
assert lists() == [{"name": "Einkauf", "items": [{"text": t, "done": False} for t in ("Milch", "Eier", "Brot", "Käse")]}]
r = lt.add_to_list("Einkaufsliste", "milch, Butter, BUTTER")                 # andere Schreibweise, doppelt
assert r.data == {"list": "Einkauf", "created": False, "added": ["Butter"], "already": ["Milch"]}, r.data
assert len(lists()) == 1, "Einkaufsliste ist die Liste Einkauf"
r = lt.add_to_list("Packliste", "Ladekabel")
assert r.data["created"] is True and r.data["list"] == "Packliste" and len(lists()) == 2
r = lt.add_to_list("Packen", "Pass")                                          # Packen ~ Packliste (beginnt gleich, ab 4 Zeichen)
assert r.data["created"] is False and r.data["list"] == "Packliste" and len(lists()) == 2
r = lt.add_to_list("Ein", "Zeug")                                             # zu kurz zum Raten: neue Liste
assert r.data["created"] is True and len(lists()) == 3
store.set_lists([{"name": "Einkauf", "items": []}, {"name": "Einkaufen heute", "items": []}])
r = lt.add_to_list("Einkau", "X")
assert not r.success and "Einkauf" in r.error and "Einkaufen heute" in r.error and "?" in r.error, "mehrere passen"
r = lt.add_to_list("Einkauf", "X")
assert r.success, "genau passt immer"
for bad in (("", "Milch"), ("  ", "Milch"), ("Einkauf", ""), ("Einkauf", " , ;"), ("Einkauf", None), (None, None), ("x" * 41, "a"), ("Einkauf", "y" * 101)):
    r = lt.add_to_list(*bad)
    assert not r.success and r.error, bad
r = lt.add_to_list("Einkauf", ["a1", "b1"])
assert r.success and r.data["added"] == ["a1", "b1"]
assert len(lt.add_to_list("Viel", ", ".join(f"e{n}" for n in range(50))).data["added"]) == lt.MAX_ADD
# Grenzen
store.set_lists([])
for n in range(widgets.MAX_LISTS):
    assert lt.add_to_list(f"Liste{n}x", "a").success
r = lt.add_to_list("Neu", "a")
assert not r.success and str(widgets.MAX_LISTS) in r.error
assert lt.add_to_list("Liste0x", "b").success, "auf bestehende Listen geht es weiter"
store.set_lists([{"name": "L", "items": [{"text": f"i{n}", "done": False} for n in range(widgets.MAX_LIST_ITEMS)]}])
r = lt.add_to_list("L", "voll")
assert not r.success and str(widgets.MAX_LIST_ITEMS) in r.error and len(lists()[0]["items"]) == widgets.MAX_LIST_ITEMS

# 3) Zeigen
store.set_lists([{"name": "Einkauf", "items": [{"text": "Milch", "done": True}, {"text": "Brot", "done": False}]},
                 {"name": "Packliste", "items": []}])
r = lt.show_list("")
assert r.data == {"lists": [{"name": "Einkauf", "open": ["Brot"], "done": ["Milch"]}, {"name": "Packliste", "open": [], "done": []}]}
assert lt.show_list("einkaufsliste").data["lists"][0]["name"] == "Einkauf" and len(lt.show_list("Einkauf").data["lists"]) == 1
r = lt.show_list("Garten")
assert not r.success and "gibt es nicht" in r.error
store.set_lists([])
assert lt.show_list("").data == {"lists": [], "info": "Es gibt noch keine Liste."}

# 4) Abhaken und Streichen
store.set_lists([{"name": "Einkauf", "items": [{"text": "Milch", "done": False}, {"text": "Hafermilch", "done": False}, {"text": "Brot", "done": False}]}])
r = lt.remove_from_list("Einkauf", "Brot", "done")
assert r.data == {"list": "Einkauf", "item": "Brot", "mode": "done"} and lists()[0]["items"][2]["done"] is True
r = lt.remove_from_list("Einkauf", "milch")                                   # genau schlaegt Teilwort
assert r.success and r.data["item"] == "Milch" and r.data["mode"] == "done"
r = lt.remove_from_list("Einkauf", "hafer", "streichen")
assert r.success and r.data["mode"] == "remove" and [i["text"] for i in lists()[0]["items"]] == ["Milch", "Brot"]
store.set_lists([{"name": "Einkauf", "items": [{"text": "Milch", "done": False}, {"text": "Hafermilch", "done": False}]}])
r = lt.remove_from_list("Einkauf", "mil")
assert not r.success and "Milch" in r.error and "Hafermilch" in r.error, "mehrdeutig"
assert [i["done"] for i in lists()[0]["items"]] == [False, False]
r = lt.remove_from_list("", "Hafermilch", "remove")                           # nur eine Liste: Name darf fehlen
assert r.success and [i["text"] for i in lists()[0]["items"]] == ["Milch"]
r = lt.remove_from_list("Garten", "x")
assert not r.success and "gibt es nicht" in r.error
r = lt.remove_from_list("Einkauf", "Eier")
assert not r.success and "steht nicht auf der Liste" in r.error
r = lt.remove_from_list("Einkauf", "")
assert not r.success
store.set_lists([{"name": "A", "items": [{"text": "x", "done": False}]}, {"name": "B", "items": []}])
r = lt.remove_from_list("", "x")
assert not r.success and r.error == "Diese Liste gibt es nicht." and lists()[0]["items"][0]["done"] is False, "zwei Listen und kein Name: nicht raten"
store.set_lists([])
assert lt.remove_from_list("", "x").error == "Es gibt noch keine Liste."
# Abgehakten Eintrag erneut setzen: wieder offen
store.set_lists([{"name": "Einkauf", "items": [{"text": "Milch", "done": True}]}])
r = lt.add_to_list("Einkauf", "milch")
assert r.data["added"] == ["Milch"] and r.data["already"] == [] and lists()[0]["items"] == [{"text": "Milch", "done": False}]

# 5) Seite -> set_lists (streng), get() bereinigt
store.set_lists([{"name": " Einkauf ", "items": [{"text": " Milch  frisch ", "done": True}]}])
assert lists() == [{"name": "Einkauf", "items": [{"text": "Milch frisch", "done": True}]}]
for bad in ("x", None, [1], [{"name": "A"}], [{"name": "", "items": []}], [{"name": "A", "items": "x"}], [{"name": "A", "items": [{"text": "a"}]}],
            [{"name": "A", "items": [{"text": "", "done": False}]}], [{"name": "A", "items": [{"text": "a", "done": "ja"}]}],
            [{"name": "A", "items": []}, {"name": "a", "items": []}], [{"name": "Packliste", "items": []}, {"name": "Pack Liste", "items": []}],
            [{"name": "A" * 41, "items": []}], [{"name": "A", "items": [{"text": "x" * 101, "done": False}]}],
            [{"name": f"N{n}", "items": []} for n in range(widgets.MAX_LISTS + 1)],
            [{"name": "A", "items": [{"text": f"i{n}", "done": False} for n in range(widgets.MAX_LIST_ITEMS + 1)]}]):
    try:
        store.set_lists(bad)
        raise AssertionError(f"haette scheitern muessen: {str(bad)[:60]}")
    except ValueError:
        pass
assert lists()[0]["name"] == "Einkauf", "Fehlversuche aendern nichts"
(folder / "k.json").write_text(json.dumps({"lists": [5, {"name": "  ", "items": []}, {"name": "A", "items": [3, {"text": 4}, {"text": "ok", "done": 1}]}, {"name": "B", "items": None}]}), encoding="utf-8")
assert WidgetStore(folder / "k.json").get()["lists"] == [{"name": "A", "items": [{"text": "ok", "done": False}]}, {"name": "B", "items": []}]
(folder / "k3.json").write_text(json.dumps({"lists": [{"name": f"L{n}", "items": [{"text": f"i{m}"} for m in range(80)]} for n in range(15)]}), encoding="utf-8")
big = WidgetStore(folder / "k3.json").get()["lists"]
assert len(big) == widgets.MAX_LISTS and all(len(l["items"]) == widgets.MAX_LIST_ITEMS for l in big), "Lesen kappt zu grosse Dateien"
(folder / "k2.json").write_text('{"lists": "x"}', encoding="utf-8")
assert WidgetStore(folder / "k2.json").get()["lists"] == []
# Notizen und Ziele speichern loescht Listen nicht
store.set_notes("n"); store.set_goals([])
assert lists()[0]["items"][0]["text"] == "Milch frisch"

# 6) Einbindung
registry = TaskRegistry()
register_all_tasks(registry)
for task_type, action, params in (("ADD_TO_LIST", "add_to_list", {"list", "items"}), ("SHOW_LIST", "show_list", {"list"}),
                                  ("REMOVE_FROM_LIST", "remove_from_list", {"list", "item", "mode"})):
    task = registry.get(task_type)
    assert [a.name for a in task.actions] == [action] and set(task.actions[0].parameters) == params, task_type
    assert risk.task_risk(task) == risk.SAFE and risk.ACTION_RISK[action] == risk.SAFE
store.set_lists([])
res = action_executor.execute_action(Action("add_to_list", {"list": "Einkauf", "items": "Milch, Eier"}))
assert res.success and res.data["added"] == ["Milch", "Eier"]
res = action_executor.execute_action(Action("show_list", {"list": ""}))
assert res.data["lists"][0]["open"] == ["Milch", "Eier"]
res = action_executor.execute_action(Action("remove_from_list", {"list": "Einkauf", "item": "Eier", "mode": "remove"}))
assert res.data["mode"] == "remove"
res = action_executor.execute_action(Action("remove_from_list", {"list": "Einkauf", "item": "Milch"}))
assert res.data["mode"] == "done", "ohne Angabe: abhaken"
ab = next(a for a in abilities.ABILITIES if a.id == "lists")
assert ab.tasks == ("ADD_TO_LIST", "SHOW_LIST", "REMOVE_FROM_LIST") and ab.default is True
assert not set(ab.tasks) & set(guest.GUEST_TASKS)

# 7) Einstellungen, Server, Seite
assert SettingsManager.CHOICES[("widgets", "middle")] == ("Off", "Notes", "Goals", "Lists")
for slot in ("fourth", "fifth"):
    assert "Lists" in SettingsManager.CHOICES[("widgets", slot)]
server_source = open(PROJECT_DIR / "server.py", encoding="utf-8").read()
assert '"/api/widgets/lists"' in server_source and "store.set_lists(data.get(\"lists\"))" in server_source
app_js = open(PROJECT_DIR / "web" / "app.js", encoding="utf-8").read()
assert "Lists: renderLists" in app_js and '"/api/widgets/lists"' in app_js and "function renderLists" in app_js
assert app_js.count('"Performance", "Lists"]') == 2 and '"Goals", "Lists"]' in app_js
assert ".w-list-head" in open(PROJECT_DIR / "web" / "style.css", encoding="utf-8").read()
src = open(PROJECT_DIR / "tools" / "lists_tool.py", encoding="utf-8").read().split('"""', 2)[2]
for forbidden in ("subprocess", "os.system", "requests", "eval(", "exec(", "open("):
    assert forbidden not in src, forbidden

# Der Name einer Liste aendert sich nicht, wenn Eintraege dazukommen: die Zahl der offenen Eintraege steht daneben
draw_block = app_js.split("function renderLists(section) {")[1].split("function draw() {")[1].split("picker.value = String(selected);")[0]
assert 'wEl("option", "", l.name)' in draw_block and "open" not in draw_block.split("wEl(\"option\"")[1].split("\n")[0]
assert 'const count = wEl("span", "w-list-count w-muted");' in app_js and "head.append(picker, count, removeList);" in app_js
assert 'count.textContent = openCount ? openCount + " offen" : "";' in app_js

print("ALL TESTS PASSED")
