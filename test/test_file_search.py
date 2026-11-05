"""Dateien finden (Mark 5, Step 2.15): Name, Inhalt, Filter, Grenzen und vor allem: nie etwas ausserhalb der Freigabe."""
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

import action_executor
import tools.file_search_tool as fst
from action import Action
from folders import FolderList
from tools.file_search_tool import FileSearch


PROJECT_DIR = Path(__file__).resolve().parent.parent
base = Path(tempfile.mkdtemp()).resolve()
home = base / "home"
docs = home / "Dokumente"
other = base / "other"
project = base / "jarvis_project"
for d in (docs / "Steuer", docs / ".versteckt", docs / "node_modules", other, project):
    d.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)


def write(path, text, age=0):
    path.write_text(text, encoding="utf-8")
    stamp = 1_700_000_000 - age
    os.utime(path, (stamp, stamp))
    return path


write(docs / "Steuer" / "Steuererklaerung 2025.pdf", "%PDF", age=10)
write(docs / "Steuer" / "steuer notizen.txt", "Belege sammeln fuer die Steuer", age=5)
write(docs / "Brief.txt", "Hiermit die <b>Kuendigung</b> des Vertrags.   Bitte\nbestaetigen.", age=20)
write(docs / "Lebenslauf.docx", "binaer", age=30)
write(docs / "Rechnung Mai.PDF", "%PDF", age=40)
write(docs / "daten.csv", "a;b\nKuendigung;1", age=50)
write(docs / ".versteckt" / "kuendigung.txt", "Kuendigung", age=1)
write(docs / ".hidden_kuendigung.txt", "Kuendigung", age=1)
write(docs / "node_modules" / "kuendigung.txt", "Kuendigung", age=1)
write(docs / ".env", "Kuendigung=1")
write(docs / "schluessel.pem", "Kuendigung")
write(docs / "binaer.txt", "Kuendigung\x00\x01")
write(docs / "gross.txt", "x" * (fst.MAX_FILE_BYTES + 10) + "Kuendigung")
write(other / "Kuendigung aussen.txt", "Kuendigung")
write(project / "Kuendigung.txt", "Kuendigung")

folder_list = FolderList(base / "f.json", project_dir=project, home=home, system_dirs=[])
folder_list.add(str(docs))
search = FileSearch(folder_list)


def names(result):
    assert result.success, result.error
    return [f["name"] for f in result.data["files"]]


# 1) Name: alle Woerter, egal ob gross/klein, nummeriert
r = search.find("steuer")
assert names(r) == ["steuer notizen.txt", "Steuererklaerung 2025.pdf"], names(r)          # neueste zuerst
assert [f["number"] for f in r.data["files"]] == [1, 2] and r.data["files"][0]["folder"] == "Dokumente" + os.sep + "Steuer"
assert names(search.find("STEUER notizen")) == ["steuer notizen.txt"]
assert names(search.find("steuer 2025")) == ["Steuererklaerung 2025.pdf"]
assert r.data["files"][0]["found_in"] == "Name" and "excerpt" not in r.data["files"][0]
assert r.data["files"][0]["modified"] == datetime.fromtimestamp(1_700_000_000 - 5).strftime("%d.%m.%Y")

# 2) Dateityp: Endung, Wort, Mehrzahl, Gross-/Kleinschreibung der Endung
assert names(search.find("", file_type="pdf")) == ["Steuererklaerung 2025.pdf", "Rechnung Mai.PDF"]
assert names(search.find("rechnung", file_type=".pdf")) == ["Rechnung Mai.PDF"]
assert names(search.find("", file_type="Word")) == ["Lebenslauf.docx"]
assert names(search.find("", file_type="PDFs")) == ["Steuererklaerung 2025.pdf", "Rechnung Mai.PDF"]
assert names(search.find("", file_type="docx")) == ["Lebenslauf.docx"]
assert names(search.find("steuer", file_type="pdf")) == ["Steuererklaerung 2025.pdf"]

# 3) Ordnerfilter
assert names(search.find("", folder="Steuer")) == ["steuer notizen.txt", "Steuererklaerung 2025.pdf"]
assert names(search.find("brief", folder="steuer")) == []
assert "Brief.txt" in names(search.find("brief", folder="dokumente"))

# 4) Inhalt: nur Textdateien, Auszug bereinigt, Namenstreffer zuerst
r = search.find("kuendigung", mode="content")
assert names(r) == ["Brief.txt", "daten.csv"], names(r)
brief = r.data["files"][0]
assert brief["found_in"] == "Inhalt" and "<b>" not in brief["excerpt"] and "\n" not in brief["excerpt"] and "Kuendigung" in brief["excerpt"]
assert len(brief["excerpt"]) <= fst.MAX_SNIPPET and "content_note" in r.data
r = search.find("kuendigung")                                                              # Name ohne Treffer: Rueckfall auf Inhalt
assert names(r) == ["Brief.txt", "daten.csv"] and "also_searched_content" in r.data and "content_note" in r.data
r = search.find("steuer")                                                                  # Treffer im Namen: kein Rueckfall
assert "also_searched_content" not in r.data and "content_note" not in r.data
r = search.find("kuendigung", mode="content")
assert "also_searched_content" not in r.data
assert names(search.find("kuendigung", mode="both")) == ["Brief.txt", "daten.csv"]
assert names(search.find("bestaetigen vertrags", mode="content")) == ["Brief.txt"]          # alle Woerter, beliebige Stelle
r = search.find("steuer", mode="both")
assert [f["found_in"] for f in r.data["files"]] == ["Name", "Name"]                        # Name schlaegt Inhalt, kein Doppeltreffer

# 4b) Synonyme und Umlaute im Dateinamen: "Rechnung" findet "Receipt-...", "Kündigung" findet "Kuendigung"
write(docs / "Receipt-2862-9692.pdf", "%PDF", age=2)
write(docs / "Invoice_Mai.pdf", "%PDF", age=3)
write(docs / "Kündigung Fitness.pdf", "%PDF", age=4)
assert names(search.find("rechnung", file_type="pdf")) == ["Receipt-2862-9692.pdf", "Invoice_Mai.pdf", "Rechnung Mai.PDF"], names(search.find("rechnung", file_type="pdf"))
assert names(search.find("receipt")) == ["Receipt-2862-9692.pdf", "Invoice_Mai.pdf", "Rechnung Mai.PDF"]
assert names(search.find("kuendigung", file_type="pdf")) == ["Kündigung Fitness.pdf"]
assert names(search.find("Kündigung", file_type="pdf")) == ["Kündigung Fitness.pdf"]
assert names(search.find("rechnung mai")) == ["Invoice_Mai.pdf", "Rechnung Mai.PDF"]          # jedes Suchwort einzeln mit Synonymen
assert names(search.find("rechnung 2862")) == ["Receipt-2862-9692.pdf"]
assert names(search.find("beleg", file_type="docx")) == []                                  # Synonym ersetzt nicht den Dateityp

# 5) Nie gefunden: aussen, geschuetzt, versteckt, Muellordner, zu gross, binaer
everything = names(search.find("", file_type="txt")) + names(search.find("kuendigung", mode="both"))
for bad in ("Kuendigung aussen.txt", "Kuendigung.txt", ".env", "schluessel.pem", "kuendigung.txt", ".hidden_kuendigung.txt"):
    assert bad not in everything, bad
assert "binaer.txt" not in names(search.find("kuendigung", mode="content"))                 # Binaerdatei / zu gross: kein Inhaltstreffer
assert "gross.txt" not in names(search.find("kuendigung", mode="both"))
assert ".env" not in names(search.find("env")) and names(search.find("schluessel")) == []

# 6) Symlinks nach draussen: Datei und Ordner werden nicht gelistet
def link_to(target, name):
    os.symlink(target, name, target_is_directory=Path(target).is_dir())


try:
    link_to(other / "Kuendigung aussen.txt", docs / "link_datei.txt")
    link_to(other, docs / "link_ordner")
    link_to(project / "Kuendigung.txt", docs / "link_projekt.txt")
    can_link = True
except (OSError, NotImplementedError, AttributeError):
    can_link = False
if can_link:
    found = names(search.find("", file_type="txt")) + names(search.find("kuendigung", mode="both"))
    assert not any("link" in n or "aussen" in n for n in found), found
    assert "link_ordner" not in " ".join(f["folder"] for f in search.find("", folder="link").data["files"])
    for n in ("link_datei.txt", "link_ordner", "link_projekt.txt"):
        os.remove(docs / n)

# 7) Eingaben: leere Suche, Zahl, unbekannte Werte, Gemeines
r = search.find("")
assert not r.success and "Wonach" in r.error
assert not search.find("   ", file_type="alle", folder="alle").success
assert names(search.find("steuer", mode="quatsch")) == ["steuer notizen.txt", "Steuererklaerung 2025.pdf"]   # unbekannter Modus = Name
assert len(search.find("", file_type="txt", count="1").data["files"]) == 1
assert search.find("", file_type="txt", count="1").data["more"].startswith("Es gibt")
assert len(search.find("", file_type="txt", count="abc").data["files"]) <= fst.DEFAULT_COUNT
assert len(search.find("", file_type="txt", count="999").data["files"]) <= fst.MAX_COUNT
assert names(search.find("steuer ../../etc/passwd")) == [] and names(search.find("*")) == []
r = search.find("gibtesnicht")
assert r.success and r.data["files"] == [] and "nichts gefunden" in r.data["info"]

# 8) Fehlende Freigabe
empty = FileSearch(FolderList(base / "leer.json", project_dir=project, home=home, system_dirs=[]))
r = empty.find("steuer")
assert not r.success and "kein Ordner freigegeben" in r.error

# 9) listed_file: Nummern der letzten Liste, nur diese
search.find("steuer")
assert search.listed_file(1).endswith("steuer notizen.txt") and search.listed_file("2").endswith("Steuererklaerung 2025.pdf")
assert search.listed_file(3) is None and search.listed_file("x") is None and search.listed_file(0) is None
search.find("gibtesnicht")
assert search.listed_file(1) is None

# 10) Grenzen: Zeit und Dateianzahl -> "incomplete", Ergebnis trotzdem nutzbar
ticks = iter(range(0, 10_000, 5))
slow = FileSearch(folder_list, clock=lambda: next(ticks))
r = slow.find("steuer")
assert r.success and "incomplete" in r.data and "zu lange" in r.data["incomplete"]
saved = fst.MAX_FILES_VISITED
fst.MAX_FILES_VISITED = 2
r = search.find("zzz")
assert "incomplete" in r.data and "zu viele" in r.data["incomplete"] and r.data["searched_files"] <= 2
fst.MAX_FILES_VISITED = saved
total = len(list(folder_list.walk()))                       # Rueckfall-Suche zaehlt je Durchgang neu, nicht doppelt
fst.MAX_FILES_VISITED = total + 1
r = search.find("zzzgibtesnicht")
assert "also_searched_content" in r.data and "incomplete" not in r.data and r.data["searched_files"] == total
fst.MAX_FILES_VISITED = saved
saved = fst.MAX_CONTENT_FILES
fst.MAX_CONTENT_FILES = 0
assert names(search.find("kuendigung", mode="content", file_type="txt")) == []
fst.MAX_CONTENT_FILES = saved
assert "incomplete" not in search.find("steuer").data

# 11) Ein Ordner, der spaeter verschwindet: keine Fehler
gone = FolderList(base / "g.json", project_dir=project, home=home, system_dirs=[])
(base / "weg").mkdir()
gone.add(str(base / "weg"))
(base / "weg").rmdir()
assert not FileSearch(gone).find("x").success

# 11b) Ueberlappende Freigaben: dieselbe Datei nur einmal
nested = FolderList(base / "n.json", project_dir=project, home=home, system_dirs=[])
nested.add(str(docs))
nested.add(str(docs / "Steuer"))
r = FileSearch(nested).find("steuer")
assert names(r) == ["steuer notizen.txt", "Steuererklaerung 2025.pdf"], names(r)

# 11c) Inhalt: alle Woerter muessen vorkommen, zu grosse Dateien nie (auch nicht per Anfang)
write(docs / "nur_eins.txt", "enthaelt nur kuendigung", age=1)
assert "nur_eins.txt" not in names(search.find("kuendigung zzzfehlt", mode="content"))
assert "nur_eins.txt" in names(search.find("kuendigung enthaelt", mode="content"))
write(docs / "gross2.txt", "Kuendigung am Anfang" + " " * (fst.MAX_FILE_BYTES + 10), age=1)
assert "gross2.txt" not in names(search.find("kuendigung", mode="content"))

# 12) Task und Executor
from task_registry import TaskRegistry
from tasks import register_all_tasks
reg = TaskRegistry()
register_all_tasks(reg)
task = reg.get("FIND_FILES")
assert task is not None and "Internet" in task.goal
assert set(task.actions[0].parameters) == {"query", "mode", "file_type", "folder", "count"}
fst.set_default_search(search)
result = action_executor.execute_action(Action("find_files", {"query": "steuer", "mode": "name", "file_type": "alle", "folder": "alle", "count": "8"}))
assert result.success and [f["name"] for f in result.data["files"]][0] == "steuer notizen.txt"
fst.set_default_search(None)

print("ALL TESTS PASSED")
