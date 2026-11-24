"""Notiz anhaengen (S6, G5): die Notiz wird in den freigegebenen Ordnern gesucht - genau ein Name, mehrere, aehnliche, keine."""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import tools.note_tool as nt
from folders import FolderList
from tools.note_tool import NoteWriter

base = Path(tempfile.mkdtemp()).resolve()
home, project = base / "home", base / "jarvis"
docs, notes, outside = home / "Dokumente", home / "Notizen", base / "aussen"
for folder in (docs / "sub", notes, outside, project):
    folder.mkdir(parents=True, exist_ok=True)
NL = nt._newline()


def put(path, text="Start"):
    Path(path).write_text(text, encoding="utf-8", newline="")


put(docs / "Test1.txt", "Milch")
put(notes / "Test1.txt", "Brot")
put(docs / "Test1.pdf", "kein Text")
put(docs / "Einkaufsliste.txt")
put(docs / "Reise.md")
put(docs / "Küche.txt")
put(docs / "sub" / "Idee.txt")
put(docs / ".versteckt.txt")
put(docs / "Bericht.pdf")
put(docs / "Reiseplanung2026.txt")
put(docs / "Zebra Notiz.txt")
put(docs / "Aaa Notiz.txt")
put(outside / "Geheim.txt")
put(project / ".env", "OPENAI_API_KEY=sk-geheim")

folder_list = FolderList(base / "f.json", project_dir=project, home=home, system_dirs=[])
folder_list.add(str(docs))
folder_list.add(str(notes))
writer = NoteWriter(folder_list)


def text_of(path):
    return Path(path).read_bytes().decode("utf-8")


def question(call, *parts):
    """Die Rueckfrage (NoteError) muss alle Teile enthalten und ist eine Frage (der Ablauf merkt sich die Notiz an dem Fragezeichen)."""
    try:
        call()
    except nt.NoteError as error:
        message = str(error)
        assert "?" in message and all(part in message for part in parts), (parts, message)
        return message
    raise AssertionError("Rueckfrage erwartet: " + str(parts))


def refused(call, part):
    try:
        call()
    except nt.NoteError as error:
        assert part in str(error) and "?" not in str(error), (part, str(error))
        return
    raise AssertionError("NoteError erwartet: " + part)


def snapshot():
    return sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())


# 1) Genau ein Treffer: ohne Endung, egal ob gross/klein, Umlaute; .md wird gefunden; Text kommt mit Leerzeile dahinter
r = writer.write("Reise", "Lissabon", mode="append")
assert r.success and r.data == {"saved": True, "file": "Reise.md", "folder": "Dokumente", "characters": 8, "appended": True}, r.data
assert text_of(docs / "Reise.md") == f"Start{NL}{NL}Lissabon{NL}"
assert writer.write("rEiSe", "x", mode="anhängen").data["file"] == "Reise.md"
assert writer.write("kueche", "x", mode="append").data["file"] == "Küche.txt" and writer.write("KÜCHE", "y", mode="append").data["file"] == "Küche.txt"
assert writer.write("Einkaufsliste.txt", "x", mode="append").data["file"] == "Einkaufsliste.txt"            # mit Endung geht es auch

# 2) Unterordner einer Freigabe zaehlen mit; die Rueckfrage und die Vorschau zeigen den Weg
r = writer.write("Idee", "Neu", mode="append")
assert r.success and r.data["file"] == "Idee.txt" and text_of(docs / "sub" / "Idee.txt").endswith(f"Neu{NL}")
assert writer.describe("Idee", "Neu", mode="append")[0] == f"Anhängen an die Datei: Dokumente{os.sep}sub{os.sep}Idee.txt"

# 3) Mehrere mit genau dem Namen: Rueckfrage mit beiden Orten; mit Ordnerangabe geht es; .pdf zaehlt nicht
message = question(lambda: writer.plan("Test1", "Eier", mode="append"), "mehrere Notizen", f"Dokumente{os.sep}Test1.txt", f"Notizen{os.sep}Test1.txt")
assert "Test1.pdf" not in message
assert writer.write("Test1", "Eier", folder="Dokumente", mode="append").data["folder"] == "Dokumente" and text_of(docs / "Test1.txt").endswith(f"Eier{NL}")
assert writer.write("Test1", "Eier", folder="notizen", mode="append").data["folder"] == "Notizen" and text_of(notes / "Test1.txt").endswith(f"Eier{NL}")
assert text_of(docs / "Test1.pdf") == "kein Text"

# 4) Kein Treffer mit genau dem Namen, aber aehnliche: Auswahl (Teilwort, Tippfehler, Endung passt nicht); nichts wird geschrieben
before = snapshot()
question(lambda: writer.plan("Einkauf", "x", mode="append"), "Ähnlich heißen", "Einkaufsliste.txt", "neue Notiz anlegen", "„neu“")
question(lambda: writer.plan("Einkaufliste", "x", mode="append"), "Einkaufsliste.txt")
question(lambda: writer.plan("Reise.txt", "x", mode="append"), "Reise.md", "Ähnlich")
message = question(lambda: writer.plan("Test", "x", mode="append"), "Ähnlich", "Test1.txt")
assert message.count("Test1.txt") == 2 and "Test1.pdf" not in message
question(lambda: writer.plan("Plan", "x", mode="append"), "Reiseplanung2026.txt")          # Teilwort zaehlt, auch wenn die Buchstaben sonst wenig gleich sind
message = question(lambda: writer.plan("Notiz", "x", mode="append"), "Aaa Notiz.txt", "Zebra Notiz.txt")
assert message.index("Aaa Notiz.txt") < message.index("Zebra Notiz.txt")                  # gleich aehnlich: nach Name sortiert
assert snapshot() == before

# 5) Gar nichts Aehnliches: Frage, ob eine neue Notiz angelegt werden soll (Notizen anderer Art, versteckte, fremde und geschuetzte Dateien zaehlen nicht)
for name in ("Zzzzzz", "Geheim", "Bericht", "OPENAI"):
    question(lambda: writer.plan(name, "x", mode="append"), "nicht gefunden", "Soll ich eine neue Notiz anlegen")
for name in (".versteckt", ".env"):                                                                           # Namen mit Punkt vorn gibt es hier nie
    try:
        writer.plan(name, "x", mode="append")
        raise AssertionError(name)
    except nt.NoteError as error:
        assert "Dateiname geht nicht" in str(error)
assert snapshot() == before
question(lambda: writer.plan("Reise", "x", folder="Notizen", mode="append"), "nicht gefunden")                 # nur im genannten Ordner suchen
try:
    writer.plan("Test1", "x", folder="Nirgendwo", mode="append")                                              # falscher Ordner: wie bisher
    raise AssertionError("falscher Ordner")
except nt.NoteError as error:
    assert "Einen freigegebenen Ordner „Nirgendwo“ gibt es nicht" in str(error)

# 6) Ohne Namen: nach dem Namen fragen; "leer" vom Router heisst auch kein Name
for none in ("", None, "alle", "leer", "  "):
    question(lambda: writer.plan(none, "x", mode="append"), "Zu welcher Notiz")

# 7) Auf Wunsch eine neue Notiz ("create" oder "new") - das alte Verhalten, ersetzt nie etwas
r = writer.write("Zzzzzz", "Hallo", folder="Dokumente", mode="create")
assert r.success and not r.data["appended"] and text_of(docs / "Zzzzzz.txt") == f"Hallo{NL}"
r = writer.write("Zzzzzz", "Nochmal", folder="Dokumente", mode="create")
assert r.data["file"] == "Zzzzzz (2).txt" and text_of(docs / "Zzzzzz.txt") == f"Hallo{NL}"
assert nt.wants_append("append") and nt.wants_append(" Anhängen ") and not (nt.wants_append("create") or nt.wants_append("new") or nt.wants_append(None) or nt.wants_append(5))

# 8) Kein Ordner freigegeben; zu grosse Datei; Vorschau der Rueckfrage
empty = NoteWriter(FolderList(base / "leer.json", project_dir=project, home=home, system_dirs=[]))
refused(lambda: empty.plan("Reise", "x", mode="append"), "kein Ordner freigegeben")
put(docs / "Gross.txt", "x" * nt.MAX_APPEND_FILE_BYTES)
try:
    writer.plan("Gross", "mehr", mode="append")
    raise AssertionError("zu gross")
except nt.NoteError as error:
    assert "zu groß" in str(error)
lines = writer.describe("Test1", "Eier", mode="append")
assert len(lines) == 1 and lines[0].startswith("Das geht nicht: Es gibt mehrere Notizen")
assert writer.check("Test1", "Eier", mode="append").startswith("Es gibt mehrere Notizen") and writer.check("Test1", "Eier", folder="Notizen", mode="append") is None
assert writer.check("Test1", "", folder="Notizen", mode="append").startswith("Was soll in die Notiz")

# 9) Die Suche ist begrenzt (Zeit) und bleibt eine Rueckfrage, kein Absturz
saved = nt.SEARCH_SECONDS
nt.SEARCH_SECONDS = -1
try:
    question(lambda: writer.plan("Reise", "x", mode="append"), "nicht gefunden")
finally:
    nt.SEARCH_SECONDS = saved

print("ALL TESTS PASSED")
