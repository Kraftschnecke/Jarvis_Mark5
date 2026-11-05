"""Freigegebene Ordner (Mark 5, Step 2.14): Pruefung von Ordnern und Pfaden, Liste, Aufgabe, Schutz vor Ausbruechen."""

import json
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

import os

import abilities
import action_executor
import folders
import risk
from action import Action
from folders import AccessError, FolderList
from task_registry import TaskRegistry
from tasks import register_all_tasks


def refused(fn, part):
    try:
        fn()
    except AccessError as error:
        assert part in str(error), (part, str(error))
        return str(error)
    raise AssertionError("AccessError erwartet: " + part)


base = Path(tempfile.mkdtemp()).resolve()
home = base / "home"
docs = home / "Dokumente"
docs2 = home / "Dokumente2"                                   # gleicher Anfang wie "Dokumente"
other = base / "other"
project = base / "jarvis_project"
for d in (docs / "sub", docs2, other, project, project / "projects"):
    d.mkdir(parents=True, exist_ok=True)
(docs / "notiz.txt").write_text("hallo", encoding="utf-8")
(docs / "sub" / "tief.txt").write_text("tief", encoding="utf-8")
(docs2 / "fremd.txt").write_text("fremd", encoding="utf-8")
(other / "geheim.txt").write_text("geheim", encoding="utf-8")
(project / ".env").write_text("KEY=1", encoding="utf-8")
(project / "settings.json").write_text("{}", encoding="utf-8")
os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)    # ~ zeigt auf den Testordner
system = base / "system"
system.mkdir()



def link_to(target, name):
    """Symlink anlegen (unter Windows nur mit Berechtigung: dort wird der Teil übersprungen)."""
    os.symlink(target, name, target_is_directory=Path(target).is_dir())


def _can_symlink():
    probe = base / "probe_link"
    try:
        link_to(base, probe)
    except (OSError, NotImplementedError, AttributeError):
        return False
    probe.unlink()
    return True


CAN_SYMLINK = _can_symlink()

def make(name="f.json"):
    return FolderList(base / name, project_dir=project, home=home, system_dirs=[system])


fl = make()

# 1) Ordner prüfen
assert fl.validate_folder(str(docs)) == str(docs) and fl.validate_folder(f" {docs} ") == str(docs)
assert fl.validate_folder("~/Dokumente") == str(docs)                                        # ~ wird aufgelöst
refused(lambda: fl.validate_folder(""), "kein Ordner")
refused(lambda: fl.validate_folder(None), "kein Ordner")
refused(lambda: fl.validate_folder("Dokumente"), "vollständigen Pfad")
refused(lambda: fl.validate_folder(str(base / "gibtsnicht")), "gibt es nicht")
refused(lambda: fl.validate_folder(str(docs / "notiz.txt")), "gibt es nicht")                # Datei statt Ordner
refused(lambda: fl.validate_folder("https://example.com/x"), "keine Web- oder Netzwerkadressen")
refused(lambda: fl.validate_folder("\\\\server\\freigabe"), "keine Web- oder Netzwerkadressen")
refused(lambda: fl.validate_folder("//server/freigabe"), "keine Web- oder Netzwerkadressen")
refused(lambda: fl.validate_folder(str(docs) + "\x00x"), "nicht gültig")
refused(lambda: fl.validate_folder("/" + "a" * 500), "nicht gültig")
refused(lambda: fl.validate_folder(base.anchor), "Laufwerk")                                  # "/" bzw. "C:\\"
refused(lambda: fl.validate_folder(str(home)), "Benutzerordner")                           # der ganze Benutzerordner
refused(lambda: fl.validate_folder(str(base)), "Benutzerordner")                            # ein Ordner darüber
refused(lambda: fl.validate_folder(str(system)), "Systemordner")
(system / "inner").mkdir()
refused(lambda: fl.validate_folder(str(system / "inner")), "Systemordner")
refused(lambda: fl.validate_folder(str(project)), "geschützt")                              # Jarvis' eigener Ordner
refused(lambda: fl.validate_folder(str(project / "projects")), "geschützt")
(docs / ".ssh").mkdir()
refused(lambda: fl.validate_folder(str(docs / ".ssh")), "geschützt")
(home / ".aws").mkdir()
refused(lambda: fl.validate_folder(str(home / ".aws")), "geschützt")
if CAN_SYMLINK:                                                                    # Symlink auf Verbotenes zählt als Ziel
    link = base / "link_to_project"
    link_to(project, link)
    refused(lambda: fl.validate_folder(str(link)), "geschützt")
    link2 = base / "link_to_home"
    link_to(home, link2)
    refused(lambda: fl.validate_folder(str(link2)), "Benutzerordner")

# 2) Liste: hinzufügen, doppelt, Höchstzahl, entfernen, Speicherung
assert fl.list() == [] and fl.roots() == []
assert fl.add(str(docs)) == [{"path": str(docs), "exists": True}]
refused(lambda: fl.add(str(docs)), "schon freigegeben")
refused(lambda: fl.add("~/Dokumente"), "schon freigegeben")
assert [f["path"] for f in fl.add(str(other))] == [str(docs), str(other)]
assert make().list() == fl.list()                                                           # liegt in der Datei
raw = json.loads((base / "f.json").read_text(encoding="utf-8"))
assert raw == {"folders": [str(docs), str(other)]} and not list(base.glob("*.tmp"))
refused(lambda: fl.remove(str(base / "x")), "nicht in der Liste")
refused(lambda: fl.remove(""), "kein Ordner")
assert [f["path"] for f in fl.remove(str(other))] == [str(docs)]
many = FolderList(base / "many.json", project_dir=project, home=home, system_dirs=[system])
dirs = []
for n in range(folders.MAX_FOLDERS):
    d = base / "m" / f"d{n}"
    d.mkdir(parents=True)
    dirs.append(d)
    many.add(str(d))
extra = base / "m" / "extra"
extra.mkdir()
refused(lambda: many.add(str(extra)), "höchstens 10 Ordner")
(base / "kaputt.json").write_text("{kaputt", encoding="utf-8")
assert FolderList(base / "kaputt.json", project_dir=project, home=home, system_dirs=[system]).list() == []
(base / "falsch.json").write_text('{"folders": "x"}', encoding="utf-8")
assert FolderList(base / "falsch.json", project_dir=project, home=home, system_dirs=[system]).list() == []
(base / "gemischt.json").write_text(json.dumps({"folders": [str(docs), 5, None]}), encoding="utf-8")
assert [f["path"] for f in FolderList(base / "gemischt.json", project_dir=project, home=home, system_dirs=[system]).list()] == [str(docs)]

# 3) Zugriff: nur innerhalb, ohne Ausbrüche
fl = make("g.json")
refused(lambda: fl.resolve(str(docs / "notiz.txt")), "noch kein Ordner freigegeben")
fl.add(str(docs))
assert fl.resolve(str(docs / "notiz.txt")) == str(docs / "notiz.txt")
assert fl.resolve(str(docs / "sub" / "tief.txt")) == str(docs / "sub" / "tief.txt") and fl.resolve(str(docs)) == str(docs)
assert fl.resolve("notiz.txt") == str(docs / "notiz.txt") and fl.resolve("sub/tief.txt") == str(docs / "sub" / "tief.txt")   # relativ
assert fl.resolve("~/Dokumente/notiz.txt") == str(docs / "notiz.txt")
outside_message = "nicht in einem freigegebenen Ordner"
for bad in (str(other / "geheim.txt"), str(docs2 / "fremd.txt"), str(docs) + "2/fremd.txt", "/etc/passwd", str(home / "x.txt"),
            str(docs / ".." / "other" / "geheim.txt"), str(docs / "sub" / ".." / ".." / "Dokumente2" / "fremd.txt"),
            "../other/geheim.txt", "sub/../../Dokumente2/fremd.txt", "..", "../..", str(base)):
    refused(lambda bad=bad: fl.resolve(bad), outside_message)
same = refused(lambda: fl.resolve(str(other / "gibtsnicht.txt")), outside_message)           # existiert nicht: gleiche Meldung wie "draußen"
assert same == refused(lambda: fl.resolve(str(other / "geheim.txt")), outside_message)       # verrät nicht, ob es existiert
refused(lambda: fl.resolve(str(docs / "gibtsnicht.txt")), "gibt es nicht")                    # innen, aber nicht da
assert fl.resolve(str(docs / "neu.txt"), must_exist=False) == str(docs / "neu.txt")
refused(lambda: fl.resolve(str(docs / "kein_ordner" / "neu.txt"), must_exist=False), "gibt es nicht")
refused(lambda: fl.resolve(str(other / "neu.txt"), must_exist=False), outside_message)
for bad, part in (("", "kein Pfad"), (None, "kein Pfad"), ("https://x.de/a", "Web- oder Netzwerk"), ("//srv/share/a", "Web- oder Netzwerk"),
                  ("\\\\srv\\share\\a", "Web- oder Netzwerk"), (str(docs) + "/a\x00b", "nicht gültig"), ("a\nb", "nicht gültig"),
                  ("x" * 500, "nicht gültig")):
    refused(lambda bad=bad: fl.resolve(bad), part)

# Symlinks: ein Link nach draußen führt nicht hinaus, ein Link nach innen ist erlaubt
if CAN_SYMLINK:
    link_to(other, docs / "link_out")
    link_to(other / "geheim.txt", docs / "datei_out.txt")
    link_to(docs / "sub", docs / "link_in")
    refused(lambda: fl.resolve(str(docs / "link_out" / "geheim.txt")), outside_message)
    refused(lambda: fl.resolve("link_out/geheim.txt"), outside_message)
    refused(lambda: fl.resolve(str(docs / "datei_out.txt")), outside_message)
    refused(lambda: fl.resolve(str(docs / "link_out")), outside_message)
    assert fl.resolve(str(docs / "link_in" / "tief.txt")) == str(docs / "sub" / "tief.txt")

# Geschützte Dateien auch innerhalb einer Freigabe
for name in (".env", ".env.local", "id_rsa", "id_ed25519.pub", "server.pem", "x.KEY", "tresor.kdbx"):
    (docs / name).write_text("x", encoding="utf-8")
    refused(lambda name=name: fl.resolve(str(docs / name)), "geschützt")
(docs / ".git").mkdir()
(docs / ".git" / "config").write_text("x", encoding="utf-8")
refused(lambda: fl.resolve(str(docs / ".git" / "config")), "geschützt")
refused(lambda: fl.resolve(str(docs / ".ssh" / "id")), "geschützt")
(docs / "environment.txt").write_text("ok", encoding="utf-8")                                 # fängt nur mit ".env" an, nicht mit "env"
assert fl.resolve("environment.txt") == str(docs / "environment.txt")
# Jarvis' eigener Ordner innerhalb einer Freigabe (Freigabe ist ein Elternordner)
parent = FolderList(base / "p.json", project_dir=project, home=home, system_dirs=[system])
parent.add(str(docs))
inner_project = docs / "jarvis"
inner_project.mkdir()
(inner_project / ".env").write_text("KEY=1", encoding="utf-8")
(inner_project / "settings.json").write_text("{}", encoding="utf-8")
(inner_project / "readme.txt").write_text("x", encoding="utf-8")
pp = FolderList(base / "pp.json", project_dir=inner_project, home=home, system_dirs=[system])
pp.add(str(docs))
refused(lambda: pp.resolve(str(inner_project / "settings.json")), "geschützt")
refused(lambda: pp.resolve(str(inner_project / "readme.txt")), "geschützt")
refused(lambda: pp.resolve(str(inner_project)), "geschützt")
assert pp.resolve(str(docs / "notiz.txt")) == str(docs / "notiz.txt")

# 4) Ein Ordner verschwindet oder wird zum Ausbruch: er gilt nicht mehr
gone = make("h.json")
victim = home / "Weg"
victim.mkdir()
gone.add(str(victim))
assert gone.roots() == [str(victim)]
victim.rmdir()
assert gone.roots() == [] and gone.list() == [{"path": str(victim), "exists": False}]
refused(lambda: gone.resolve(str(victim / "a.txt")), "noch kein Ordner freigegeben")
if CAN_SYMLINK:
    swap = home / "Tausch"
    swap.mkdir()
    gone2 = make("i.json")
    gone2.add(str(swap))
    swap.rmdir()
    link_to(project, swap)                                                                 # ersetzt durch Link auf Jarvis' Ordner
    assert gone2.roots() == []
    refused(lambda: gone2.resolve(str(swap / ".env")), "noch kein Ordner freigegeben")

# 5) Groß-/Kleinschreibung (Windows): hier nur der Vergleich selbst, denn das Dateisystem dieses Rechners unterscheidet sie
if os.path.normcase("A") == "A":                                                              # Linux/macOS: Groß-/Kleinschreibung zählt
    assert not folders._same_or_inside(str(docs).upper() + "/sub", str(docs))
else:                                                                                         # Windows: gleicher Ordner
    assert folders._same_or_inside(str(docs).upper() + "\\sub", str(docs))
folders._normcase = str.casefold                                                              # so verhält sich os.path.normcase unter Windows
try:
    assert folders._same_or_inside(str(docs).upper() + "/sub", str(docs))
    assert folders._same_or_inside(str(docs).upper(), str(docs))
    assert not folders._same_or_inside(str(docs2).upper(), str(docs)) and not folders._same_or_inside(str(base).upper(), str(docs))
finally:
    folders._normcase = os.path.normcase

# 6) Windows-Fallen (reine Textprüfung, läuft auch hier): Datenströme, Gerätenamen
folders._IS_WINDOWS = True
try:
    for bad in ("C:\\Users\\du\\Docs\\datei.txt:geheim", "C:\\Users\\du\\Docs\\NUL", "C:\\Users\\du\\Docs\\con.txt", "C:\\Users\\du\\COM1",
                "C:\\Users\\du\\LPT3.log", "C:\\Users\\du\\aux. ", "1:\\x"):
        refused(lambda bad=bad: fl.resolve(bad), "nicht gültig")
        refused(lambda bad=bad: fl.validate_folder(bad), "nicht gültig")
    folders._basic_checks("C:\\Users\\du\\Docs\\Kontakte.txt", "Pfad")                            # normaler Name bleibt erlaubt
    folders._basic_checks("C:\\Users\\du\\console\\notes.txt", "Pfad")
finally:
    folders._IS_WINDOWS = os.name == "nt"

# 7) Aufgabe LIST_FOLDERS
registry = TaskRegistry()
register_all_tasks(registry)
task = registry.get("LIST_FOLDERS")
assert task is not None and [a.name for a in task.actions] == ["list_folders"] and risk.task_risk(task) == risk.SAFE
ability = [a for a in abilities.ABILITIES if a.id == "documents"][0]
assert ability.tasks == ("LIST_FOLDERS", "FIND_FILES", "READ_DOCUMENT") and ability.default is True
assert not [t for t in registry.get_all() if "ADD" in t.task_type and "FOLDER" in t.task_type]      # kein Weg, per Chat freizugeben
folders.set_default_list(make("k.json"))
empty = action_executor.execute_action(Action("list_folders"))
assert empty.success and empty.data["folders"] == [] and "Einstellungen" in empty.data["info"]
folders.default_list().add(str(docs))
vanished = home / "Bald weg"
vanished.mkdir()
folders.default_list().add(str(vanished))
vanished.rmdir()
shown = action_executor.execute_action(Action("list_folders"))
assert shown.success and shown.data["folders"] == [str(docs)] and "nur der Nutzer" in shown.data["note"]       # Verschwundene werden nicht genannt
folders.set_default_list(None)

# 8) Quelltext: keine Aufgabe schreibt die Liste; Konfiguration und Git
tasks_source = open(PROJECT_DIR / "tasks.py", encoding="utf-8").read() + open(PROJECT_DIR / "action_executor.py", encoding="utf-8").read()
assert ".add(" not in tasks_source.split("list_folders")[1].split("get_briefing")[0]
assert "folders.json" in open(PROJECT_DIR / ".gitignore", encoding="utf-8").read()
import config
assert config.FOLDERS_FILE.name == "folders.json" and config.FOLDERS_FILE.parent == PROJECT_DIR
print("ALL TESTS PASSED")
