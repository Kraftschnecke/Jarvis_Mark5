"""Notizen schreiben (Mark 5, Step 2.18): Regeln des Schreibens (nur freigegebene Ordner, nur .txt/.md, nie ueberschreiben) und der Ablauf mit Rueckfrage."""
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
import contextlib
import io
import tools.note_tool as nt
import guest
import risk
import jarvis as jarvis_module
from action import Action
from folders import FolderList
from jarvis import Jarvis
from task_registry import TaskRegistry
from tasks import register_all_tasks
from tools.note_tool import NoteWriter



base = Path(tempfile.mkdtemp()).resolve()
home = base / "home"
docs = home / "Dokumente"
notes = home / "Notizen"
other = base / "other"
project = base / "jarvis_project"
for d in (docs, notes, other, project):
    d.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
NL = nt._newline()
FIXED = datetime(2026, 11, 5, 12, 0)

folder_list = FolderList(base / "f.json", project_dir=project, home=home, system_dirs=[])
folder_list.add(str(docs))
writer = NoteWriter(folder_list, clock=lambda: FIXED)


def content_of(path):
    return Path(path).read_bytes().decode("utf-8")


def refused(call, part):
    try:
        call()
    except nt.NoteError as error:
        assert part in str(error), (part, str(error))
        return
    raise AssertionError("NoteError erwartet: " + part)


def listing(folder=docs):
    return sorted(p.name for p in Path(folder).iterdir())


# 1) Neue Datei: Name, Endung, Zeilenumbrueche, UTF-8, Ergebnis
r = writer.write("Einkaufen", "Milch\nBrot\r\nÄpfel & Eier")
assert r.success and r.data == {"saved": True, "file": "Einkaufen.txt", "folder": "Dokumente", "characters": 23, "appended": False}, r.data
assert content_of(docs / "Einkaufen.txt") == f"Milch{NL}Brot{NL}Äpfel & Eier{NL}"
assert (docs / "Einkaufen.txt").read_bytes().count(b"\r\r") == 0
assert writer.write("Ideen.MD", "x").data["file"] == "Ideen.md"                              # Endung klein, .md erlaubt
assert writer.write("Mit Leerzeichen (1)", "x").data["file"] == "Mit Leerzeichen (1).txt"
assert writer.write("", "x").data["file"] == "Notiz 2026-11-05.txt"                          # ohne Namen: Datum
assert writer.write(None, "x").data["file"] == "Notiz 2026-11-05 (2).txt"                    # gleicher Standardname: nicht ersetzt
assert writer.write("alle", "x").data["file"] == "Notiz 2026-11-05 (3).txt"
assert writer.write("leer", "x").data["file"] == "Notiz 2026-11-05 (4).txt"                    # "leer" vom Router = kein Name
assert writer.write("Größe äöü", "x").data["file"] == "Größe äöü.txt"

# 2) Nie ueberschreiben: gleicher Name -> (2), (3) ...; die alte Datei bleibt unveraendert
r = writer.write("Einkaufen", "neuer Text")
assert r.data["file"] == "Einkaufen (2).txt" and r.data["name_was_taken"] == "Einkaufen.txt" and not r.data["appended"]
assert content_of(docs / "Einkaufen.txt").startswith("Milch") and content_of(docs / "Einkaufen (2).txt").startswith("neuer Text")
assert writer.write("Einkaufen.txt", "dritter").data["file"] == "Einkaufen (3).txt"
assert writer.write("Einkaufen (2)", "vierter").data["file"] == "Einkaufen (2) (2).txt"

# 2b) Auch wenn die Datei erst zwischen Pruefen und Schreiben entsteht: exklusiv geoeffnet, nichts wird ersetzt
(docs / "Rennen.txt").write_text("Original", encoding="utf-8")
real_plan = writer.plan


def stale_plan(*a, **k):
    plan = real_plan("Anderer Name", *a[1:], **k)
    plan.update(path=str(docs / "Rennen.txt"), name="Rennen.txt", append=False, renamed_from=None)
    return plan


writer.plan = stale_plan
r = writer.write("egal", "Ersatz")
writer.plan = real_plan
assert r.success and r.data["file"] == "Rennen (2).txt" and r.data["name_was_taken"] == "Rennen.txt"
assert content_of(docs / "Rennen.txt") == "Original" and content_of(docs / "Rennen (2).txt").startswith("Ersatz")

# 3) Anhaengen: nur auf ausdruecklichen Wunsch, mit Leerzeile; ohne vorhandene Datei wird sie neu angelegt
(docs / "Tagebuch.txt").write_bytes(f"Montag{NL}".encode())
r = writer.write("Tagebuch", "Dienstag", mode="append")
assert r.data["appended"] and r.data["file"] == "Tagebuch.txt" and "name_was_taken" not in r.data
assert content_of(docs / "Tagebuch.txt") == f"Montag{NL}{NL}Dienstag{NL}"
(docs / "Ohne.txt").write_bytes(b"ohne Zeilenende")
writer.write("Ohne", "Mehr", mode="Anhängen")
assert content_of(docs / "Ohne.txt") == f"ohne Zeilenende{NL}{NL}Mehr{NL}"
r = writer.write("Neu per Anhaengen", "x", mode="append")
assert r.success and not r.data["appended"] and "Neu per Anhaengen.txt" in listing()
(docs / "Leerdatei.txt").write_bytes(b"")
writer.write("Leerdatei", "Start", mode="append")
assert content_of(docs / "Leerdatei.txt") == f"Start{NL}", (repr(content_of(docs / "Leer.txt")), listing())
(docs / "Gross.txt").write_bytes(b"x" * nt.MAX_APPEND_FILE_BYTES)
refused(lambda: writer.plan("Gross", "mehr", mode="append"), "zu groß")
assert (docs / "Gross.txt").stat().st_size == nt.MAX_APPEND_FILE_BYTES
for odd_mode in ("new", "", None, "überschreiben", "replace", "write", 5):
    before = content_of(docs / "Tagebuch.txt")
    r = writer.write("Tagebuch", "x", mode=odd_mode)
    assert content_of(docs / "Tagebuch.txt") == before and not r.data["appended"], odd_mode        # nie ersetzen, nie anhaengen

# 4) Dateiname: nur ein Name, nur .txt/.md
for bad, part in [("a/b.txt", "keinen Pfad"), ("a\\b.txt", "keinen Pfad"), ("../x.txt", "keinen Pfad"), ("C:\\x.txt", "keinen Pfad"),
                  ("C:x.txt", "keinen Pfad"), ("x.txt:ads", "keinen Pfad"), ("a*b", "keinen Pfad"), ("a?b", "keinen Pfad"),
                  ("a<b>", "keinen Pfad"), ("a|b", "keinen Pfad"), ("a\nb", "keinen Pfad"),
                  ("tool.bat", "keine .bat"), ("run.ps1", "keine .ps1"), ("x.exe", "keine .exe"), ("x.lnk", "keine .lnk"),
                  ("brief.docx", "keine .docx"), ("x.TXT.bat", "keine .bat"), (".env", "geht nicht"), (".hidden.txt", "geht nicht"),
                  ("...", "geht nicht"), (" . ", "geht nicht"), ("x" * 100, "geht nicht"), ("a" * 77 + ".md", None), ("-x", "geht nicht")]:
    if part is None:
        assert writer.plan(bad, "x")["name"] == bad
        continue
    try:
        writer.plan(bad, "x")
        raise AssertionError(f"abgelehnt erwartet: {bad!r}")
    except nt.NoteError as error:
        assert part in str(error), (bad, str(error))
assert writer.plan("a\x00b\u202e", "x")["name"] == "ab.txt"                                    # unsichtbare Zeichen werden entfernt
assert not [n for n in listing() if n.endswith((".bat", ".ps1", ".exe", ".lnk", ".docx", ".env"))]
for reserved in ("CON", "nul.txt", "COM1", "prn.md"):                                          # Windows-Geraetenamen (resolve prueft sie)
    if os.name == "nt":
        refused(lambda: writer.plan(reserved, "x"), "")

# 5) Text: leer, zu lang, Steuerzeichen
for empty in ("", "   \n\t ", None, 5, ["a"], b"abc"):
    refused(lambda: writer.plan("x", empty), "Was soll in die Notiz")
refused(lambda: writer.plan("x", "a" * (nt.MAX_CONTENT + 1)), "zu lang")
assert writer.plan("x", "a" * nt.MAX_CONTENT)["text"] == "a" * nt.MAX_CONTENT
assert writer.plan("x", "Hallo\u202e\x00\x1b Welt\u200b")["text"] == "Hallo Welt"

# 6) Ordner: ohne Freigabe, genau einer, mehrere, Teilname
empty_writer = NoteWriter(FolderList(base / "leer.json", project_dir=project, home=home, system_dirs=[]))
refused(lambda: empty_writer.plan("x", "y"), "kein Ordner freigegeben")
folder_list.add(str(notes))
refused(lambda: writer.plan("x", "y"), "In welchen Ordner")
refused(lambda: writer.plan("x", "y", folder="alle"), "In welchen Ordner")
assert writer.plan("x", "y", folder="Notizen")["root"] == str(notes)
assert writer.plan("x", "y", folder="notiz")["root"] == str(notes)                              # Teilname
assert writer.plan("x", "y", folder="DOKUMENTE")["root"] == str(docs)
refused(lambda: writer.plan("x", "y", folder="Desktop"), "gibt es nicht")
refused(lambda: writer.plan("x", "y", folder=str(other)), "gibt es nicht")                      # kein freier Pfad
refused(lambda: writer.plan("x", "y", folder="o"), "Mehrere")                                   # "o" steckt in beiden Namen
assert writer.write("Im Notizordner", "z", folder="Notizen").data["folder"] == "Notizen" and (notes / "Im Notizordner.txt").exists()
assert not (other / "x.txt").exists() and listing(other) == []

# 6b) Genauer Ordnername schlaegt Teiltreffer ("Notizen" meint nicht "Notizen alt")
(home / "Notizen alt").mkdir()
pair_list = FolderList(base / "pair.json", project_dir=project, home=home, system_dirs=[])
pair_list.add(str(notes))
pair_list.add(str(home / "Notizen alt"))
pair = NoteWriter(pair_list, clock=lambda: FIXED)
assert pair.plan("x", "y", folder="Notizen")["root"] == str(notes)
assert pair.plan("x", "y", folder="notizen alt")["root"] == str(home / "Notizen alt")
refused(lambda: pair.plan("x", "y", folder="notiz"), "Mehrere")

# 6c) Zeilenumbrueche: unter Windows CRLF, sonst LF (hier fuer beide geprueft)
real_newline = nt._newline
for nl_style in ("\r\n", "\n"):
    nt._newline = lambda nl_style=nl_style: nl_style
    writer.write(f"Umbruch {len(nl_style)}", "eins\nzwei\r\ndrei", folder="Dokumente")
    raw = (docs / f"Umbruch {len(nl_style)}.txt").read_bytes()
    assert raw == f"eins{nl_style}zwei{nl_style}drei{nl_style}".encode(), (nl_style, raw)
nt._newline = real_newline

# 7) Links und Schutz: eine Datei im Ordner, die auf etwas ausserhalb zeigt, wird weder ersetzt noch angehaengt
(other / "fremd.txt").write_text("fremd", encoding="utf-8")
try:
    os.symlink(other / "fremd.txt", notes / "Link.txt")
    os.symlink(other, notes / "LinkOrdner.txt", target_is_directory=True)
    can_link = True
except (OSError, NotImplementedError, AttributeError):
    can_link = False
if can_link:
    refused(lambda: writer.plan("Link", "x", folder="Notizen"), "nicht in einem freigegebenen")
    refused(lambda: writer.plan("Link", "x", folder="Notizen", mode="append"), "nicht in einem freigegebenen")
    refused(lambda: writer.plan("LinkOrdner", "x", folder="Notizen"), "nicht in einem freigegebenen")
    assert content_of(other / "fremd.txt") == "fremd" and listing(other) == ["fremd.txt"]
(notes / "Ordner.txt").mkdir()
refused(lambda: writer.plan("Ordner", "x", folder="Notizen"), "keine Datei")

# 8) Vorschau fuer die Rueckfrage und Vorab-Pruefung
d = writer.describe("Einkaufen", "Milch\nBrot", folder="Dokumente")
assert d[0] == f"Neue Datei: Dokumente{os.sep}Einkaufen (4).txt (Einkaufen.txt gibt es schon, sie bleibt unverändert)", d
assert d[1] == "Inhalt: Milch Brot"
d = writer.describe("Tagebuch", "mehr", folder="Dokumente", mode="append")
assert d[0] == f"Anhängen an die Datei: Dokumente{os.sep}Tagebuch.txt"
long = writer.describe("Lang", "wort " * 100, folder="Dokumente")
assert long[1].endswith("(499 Zeichen)") and len(long[1]) < 260
assert writer.describe("x.bat", "y", folder="Dokumente")[0].startswith("Das geht nicht: Ich schreibe nur Textnotizen")
assert writer.check("Gut", "Text", folder="Dokumente") is None and "Pfad" in writer.check("a/b", "x", folder="Dokumente")
assert not (docs / "Lang.txt").exists() and not (docs / "Gut.txt").exists()                      # Pruefen schreibt nichts

# 9) Fehler beim Schreiben werden gemeldet, nicht geworfen
real_open = open


def broken_open(*a, **k):
    raise PermissionError("kein Zugriff")


import builtins
builtins.open = broken_open
try:
    r = writer.write("Kaputt", "x", folder="Dokumente")
finally:
    builtins.open = real_open
assert not r.success and "konnte ich nicht speichern" in r.error and "PermissionError" in r.error

# =====================================================================
# Ablauf in Jarvis: Rueckfrage, Ja/Nein, Vorab-Pruefung, "Speichere das"
# =====================================================================
flow_base = Path(tempfile.mkdtemp()).resolve()
flow_docs = flow_base / "Dokumente"
flow_docs.mkdir()
flow_list = FolderList(flow_base / "f.json", project_dir=project, home=home, system_dirs=[])
flow_list.add(str(flow_docs))
nt.set_default_writer(NoteWriter(flow_list, clock=lambda: FIXED))

enabled = [True]
registry = TaskRegistry(is_enabled=lambda t: enabled[0] or t != "WRITE_NOTE")
register_all_tasks(registry)
routes, model_calls = [], []


class FakeClient:
    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        model_calls.append(kwargs)
        return types.SimpleNamespace(output_text="Gespeichert.")


def route_for(parameters):
    return {"kind": "TASK", "task_type": "WRITE_NOTE", "parameters": parameters,
            "command": {"intent": "NORMAL_MESSAGE", "project_name": None, "conversation_name": None, "new_conversation_name": None}}


jarvis_module.route_message = lambda client, message, reg: routes.pop(0)


def make_jarvis():
    j = object.__new__(Jarvis)
    j.client = FakeClient()
    j.task_registry = registry
    j.pending_project_confirmation = None
    j.process_normal_message = lambda m: {"status": "response", "content": "Das ist meine Zusammenfassung."}
    return j


def run(j, message):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        return j.process_message(message)


def files():
    return sorted(p.name for p in flow_docs.iterdir())


# a) Rueckfrage mit Vorschau; erst nach "Ja" (Button) wird geschrieben
j = make_jarvis()
routes.append(route_for({"filename": "Einkaufen", "content": "Milch\nBrot", "folder": "", "mode": "new"}))
out = run(j, "Schreib eine Notiz Einkaufen: Milch, Brot")
assert out["status"] == "confirmation" and files() == [] and model_calls == []
assert out["confirmation"]["title"] == "Notiz in eine Datei schreiben" and "Beispiel" not in out["content"] and "Schreib eine Notiz Einkaufen" not in out["content"]
assert out["confirmation"]["details"] == [f"Neue Datei: Dokumente{os.sep}Einkaufen.txt", "Inhalt: Milch Brot"], out["confirmation"]["details"]
assert "Milch Brot" in out["content"] and "ja" in out["content"]
out = j.confirm_action(out["confirmation"]["id"], True)
assert out == {"status": "response", "content": "Gespeichert."} and files() == ["Einkaufen.txt"]
assert content_of(flow_docs / "Einkaufen.txt") == f"Milch{NL}Brot{NL}"
assert "saved" in str(model_calls[-1]["input"]) and "Einkaufen.txt" in str(model_calls[-1]["input"])
assert "nicht mehr gueltig" in j.confirm_action("x" * 16, True)["content"] and files() == ["Einkaufen.txt"]

# b) "nein" (Chat und Button): nichts geschrieben
for answer in ("nein", None):
    routes.append(route_for({"filename": "Abgelehnt", "content": "x", "folder": "", "mode": "new"}))
    out = run(j, "Schreib eine Notiz Abgelehnt")
    assert out["status"] == "confirmation"
    result = run(j, "nein") if answer else j.confirm_action(out["confirmation"]["id"], False)
    assert "nichts ausgefuehrt" in result["content"] and files() == ["Einkaufen.txt"], result

# c) Vorab-Pruefung: Ungueltiges wird ohne Rueckfrage abgelehnt, nichts offen, nichts geschrieben
for bad, part in (({"filename": "start.bat", "content": "x"}, "keine .bat"), ({"filename": "../x.txt", "content": "x"}, "keinen Pfad"),
                  ({"filename": "x", "content": "x", "folder": "Systemordner"}, "gibt es nicht"),
                  ({"filename": "x", "content": ""}, "was soll in die notiz")):
    j.last_reply = None
    routes.append(route_for(bad))
    out = run(j, "Schreib eine Notiz")
    assert out["status"] == "response" and j.pending_action is None and files() == ["Einkaufen.txt"], (bad, out)
    assert out["content"].startswith("Sir, ") and part.lower() in out["content"].lower(), (bad, out["content"])

# d) "Speichere das": ohne Text gilt Jarvis' letzte Antwort; Rueckfrage zeigt sie, "ja"/"nein" und Rueckfragen zaehlen nicht
j = make_jarvis()
routes.append({"kind": "CHAT", "task_type": None, "parameters": {}, "command": {"intent": "NORMAL_MESSAGE", "project_name": None, "conversation_name": None, "new_conversation_name": None}})
assert run(j, "Fass es zusammen")["content"] == "Das ist meine Zusammenfassung." and j.last_reply == "Das ist meine Zusammenfassung."
routes.append(route_for({"filename": "Zusammenfassung", "content": "", "folder": "", "mode": "new"}))
out = run(j, "Speichere das als Notiz Zusammenfassung")
assert out["status"] == "confirmation" and out["confirmation"]["details"][1] == "Inhalt: Das ist meine Zusammenfassung."
assert j.last_reply == "Das ist meine Zusammenfassung."                                       # die Rueckfrage selbst wird nicht gemerkt
result = run(j, "ja")
assert files() == ["Einkaufen.txt", "Zusammenfassung.txt"] and content_of(flow_docs / "Zusammenfassung.txt") == f"Das ist meine Zusammenfassung.{NL}"
assert j.last_reply == "Das ist meine Zusammenfassung."                                       # "Gespeichert." ersetzt sie nicht
fresh = make_jarvis()                                                                          # noch keine Antwort: nichts zu speichern
routes.append(route_for({"filename": "Leer", "content": "", "folder": "", "mode": "new"}))
out = run(fresh, "Speichere das")
assert out["status"] == "response" and "was soll in die Notiz" in out["content"] and fresh.pending_action is None

# e) Eigener Text gewinnt gegen die letzte Antwort
routes.append(route_for({"filename": "Eigen", "content": "mein Text", "folder": "", "mode": "new"}))
out = run(j, "Notiz Eigen: mein Text")
assert out["confirmation"]["details"][1] == "Inhalt: mein Text"
j.confirm_action(out["confirmation"]["id"], True)
assert content_of(flow_docs / "Eigen.txt") == f"mein Text{NL}"

# f) Existiert die Datei schon: Rueckfrage sagt es, geschrieben wird unter neuem Namen, die alte bleibt
routes.append(route_for({"filename": "Eigen", "content": "zweiter Text", "folder": "", "mode": "new"}))
out = run(j, "Notiz Eigen: zweiter Text")
assert "gibt es schon" in out["confirmation"]["details"][0]
j.confirm_action(out["confirmation"]["id"], True)
assert content_of(flow_docs / "Eigen.txt") == f"mein Text{NL}" and content_of(flow_docs / "Eigen (2).txt") == f"zweiter Text{NL}"

# g) Zwischen Rueckfrage und Ja geaendert: Datei erscheint -> beim Ja gilt der dann freie Name; Faehigkeit aus -> nichts
routes.append(route_for({"filename": "Spaet", "content": "a", "folder": "", "mode": "new"}))
out = run(j, "Notiz Spaet: a")
(flow_docs / "Spaet.txt").write_text("inzwischen da", encoding="utf-8")
j.confirm_action(out["confirmation"]["id"], True)
assert content_of(flow_docs / "Spaet.txt") == "inzwischen da" and content_of(flow_docs / "Spaet (2).txt") == f"a{NL}"
routes.append(route_for({"filename": "Aus", "content": "a", "folder": "", "mode": "new"}))
out = run(j, "Notiz Aus: a")
enabled[0] = False
result = j.confirm_action(out["confirmation"]["id"], True)
enabled[0] = True
assert "ausgeschaltet" in result["content"] and "Aus.txt" not in files()

# h) Gast und Risiko
assert "WRITE_NOTE" not in guest.GUEST_TASKS
assert risk.task_risk(registry.get("WRITE_NOTE")) == risk.CONFIRM
assert risk.action_risk(Action("write_note", {"filename": "x", "content": "y"})) == risk.CONFIRM
assert risk.ACTION_RISK["write_note"] == risk.CONFIRM

print("ALL TESTS PASSED")
