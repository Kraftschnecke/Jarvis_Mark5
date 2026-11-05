"""Notizen in eine Datei schreiben (Mark 5, Step 2.18): der erste Weg, auf dem Jarvis etwas auf die Platte schreibt.

Deshalb die engsten Regeln im ganzen Programm:
- **Immer erst fragen** (risk.py: `write_note` = confirm). Die Rueckfrage zeigt Ordner, Dateiname, ob neu oder angehaengt
  und den Anfang des Textes (`describe`). Ungueltiges (falsche Endung, Pfad, kein Ordner) wird schon VOR der Frage
  abgelehnt (`check`), ohne dass etwas gefragt wird.
- **Nur in freigegebene Ordner** und nur ueber `FolderList.resolve(..., must_exist=False)` (folders.py): kein `..`, kein
  Link nach draussen, nichts Geschuetztes. Der Name ist nur ein Dateiname, nie ein Pfad; Ordner werden nicht angelegt.
- **Nur .txt und .md** (nie .bat, .ps1, .exe, .lnk ...): Eine Notiz kann nie ein Programm werden. Versteckte Namen
  (mit Punkt vorn) und Sonderzeichen sind nicht erlaubt.
- **Nie ueberschreiben:** Gibt es die Datei schon, legt Jarvis "Name (2).txt" an (exklusiv geoeffnet: auch bei Gleichzeitigkeit
  wird nichts ersetzt). Nur auf ausdruecklichen Wunsch ("haenge an") wird an eine bestehende Datei angehaengt.
- Begrenzt: 20 000 Zeichen je Notiz, Dateien bis 1 MB beim Anhaengen.

Der Text kommt vom Nutzer oder ist Jarvis' letzte Antwort ("Speichere das"); er wird nur gesaeubert (Steuerzeichen) und nie
ausgefuehrt oder als Anweisung gelesen.
"""

import os
import re
from datetime import datetime

import folders as folders_module
from folders import AccessError
from tools.tool_result import ToolResult
from untrusted import clean_text

ALLOWED_EXTENSIONS = (".txt", ".md")
MAX_CONTENT = 20_000
MAX_NAME = 80
MAX_APPEND_FILE_BYTES = 1024 * 1024
MAX_COPIES = 99
PREVIEW_CHARS = 200

_NAME = re.compile(r"[\w][\w .()\-]*")
_APPEND_WORDS = {"append", "anhängen", "anhaengen", "anfügen", "anfuegen", "hinzufügen", "hinzufuegen", "ergänzen", "ergaenzen"}
_NO_VALUE = {"", "alle", "egal", "none", "null", "-", "n/a", "unbekannt", "leer"}


class NoteError(Exception):
    """Ein Grund, warum nicht geschrieben wird; der Text geht als Antwort an den Nutzer."""


def _newline():
    return "\r\n" if os.name == "nt" else "\n"


class NoteWriter:
    def __init__(self, folder_list=None, clock=datetime.now):
        self._folders = folder_list
        self.clock = clock

    @property
    def folders(self):
        return self._folders if self._folders is not None else folders_module.default_list()

    # --- Planen (reine Pruefung, schreibt nichts) ------------------------
    def _clean_name(self, filename):
        text = clean_text(filename, 300).strip() if isinstance(filename, str) else ""
        if text.casefold() in _NO_VALUE:
            text = f"Notiz {self.clock().strftime('%Y-%m-%d')}"
        if re.search(r"[\\/:*?\"<>|\x00-\x1f]", text):
            raise NoteError("Als Dateiname nehme ich nur einen Namen, keinen Pfad und keine Sonderzeichen. "
                            "Den Ordner suchst du mit „im Ordner …“ aus.")
        text = text.strip().rstrip(" .")
        base, extension = os.path.splitext(text)
        if extension:
            if extension.casefold() not in ALLOWED_EXTENSIONS:
                raise NoteError(f"Ich schreibe nur Textnotizen (.txt oder .md), keine {extension}-Dateien.")
            text = base + extension.casefold()
        else:
            text += ".txt"
        if len(text) > MAX_NAME or not _NAME.fullmatch(text):
            raise NoteError("Dieser Dateiname geht nicht: Buchstaben, Ziffern, Leerzeichen und . ( ) - sind erlaubt "
                            f"(höchstens {MAX_NAME} Zeichen, nicht mit einem Punkt beginnen).")
        return text

    def _clean_content(self, content):
        if not isinstance(content, str) or not content.strip():
            raise NoteError("Was soll in die Notiz? Sag mir den Text, oder „speichere das“ für meine letzte Antwort.")
        text = clean_text(content.replace("\r\n", "\n").replace("\r", "\n"), MAX_CONTENT + 100).strip()
        if len(text) > MAX_CONTENT:
            raise NoteError(f"Der Text ist zu lang für eine Notiz (höchstens {MAX_CONTENT} Zeichen).")
        return text

    def _pick_root(self, folder):
        roots = self.folders.roots()
        if not roots:
            raise NoteError("Es ist noch kein Ordner freigegeben. Trage Ordner in den Einstellungen unter „Folders“ ein.")
        wanted = clean_text(folder, 100).strip().casefold() if isinstance(folder, str) else ""
        if wanted in _NO_VALUE:
            if len(roots) == 1:
                return roots[0]
            names = ", ".join(os.path.basename(r) or r for r in roots)
            raise NoteError(f"In welchen Ordner soll die Notiz? Freigegeben sind: {names}.")
        matches = [r for r in roots if wanted in (os.path.basename(r) or r).casefold() or wanted == r.casefold()]
        exact = [r for r in matches if wanted == (os.path.basename(r) or r).casefold()]
        matches = exact if len(exact) == 1 else matches
        if not matches:
            names = ", ".join(os.path.basename(r) or r for r in roots)
            raise NoteError(f"Einen freigegebenen Ordner „{clean_text(folder, 40)}“ gibt es nicht. Freigegeben sind: {names}.")
        if len(matches) > 1:
            raise NoteError("Mehrere freigegebene Ordner passen: " + ", ".join(os.path.basename(r) or r for r in matches) + ". Welcher?")
        return matches[0]

    def plan(self, filename="", content="", folder="", mode="new"):
        """Prueft alles und sagt, was geschehen wuerde. Wirft NoteError. Schreibt nichts."""
        text = self._clean_content(content)
        name = self._clean_name(filename)
        root = self._pick_root(folder)
        append = isinstance(mode, str) and mode.strip().casefold() in _APPEND_WORDS

        try:
            real = self.folders.resolve(os.path.join(root, name), must_exist=False)
        except AccessError as error:
            raise NoteError(str(error)) from error
        if os.path.dirname(real) != root:
            raise NoteError("Dieser Dateiname geht nicht.")

        exists = os.path.lexists(real)
        if exists and not os.path.isfile(real):
            raise NoteError("Unter diesem Namen gibt es schon etwas, das keine Datei ist.")
        renamed_from = None
        if exists and append:
            if os.path.getsize(real) + len(text) > MAX_APPEND_FILE_BYTES:
                raise NoteError("Die Datei ist schon zu groß zum Anhängen (über 1 MB).")
        elif exists:
            renamed_from = name
            base, extension = os.path.splitext(name)
            for number in range(2, MAX_COPIES + 2):
                candidate = os.path.join(root, f"{base} ({number}){extension}")
                if not os.path.lexists(candidate):
                    name, real = f"{base} ({number}){extension}", candidate
                    break
            else:
                raise NoteError("Es gibt schon zu viele Dateien mit diesem Namen. Nimm bitte einen anderen.")
            try:
                real = self.folders.resolve(real, must_exist=False)
            except AccessError as error:
                raise NoteError(str(error)) from error

        return {"path": real, "root": root, "name": name, "text": text, "append": bool(exists and append),
                "renamed_from": renamed_from}

    def check(self, filename="", content="", folder="", mode="new"):
        """Fehlertext, wenn die Notiz so nicht geschrieben wird (sonst None). Fuer die Pruefung vor der Rueckfrage."""
        try:
            self.plan(filename, content, folder, mode)
        except NoteError as error:
            return str(error)
        return None

    def describe(self, filename="", content="", folder="", mode="new"):
        """Zeilen fuer die Rueckfrage: was genau wird wohin geschrieben?"""
        try:
            plan = self.plan(filename, content, folder, mode)
        except NoteError as error:
            return [f"Das geht nicht: {error}"]
        place = f"{os.path.basename(plan['root']) or plan['root']}{os.sep}{plan['name']}"
        if plan["append"]:
            first = f"Anhängen an die Datei: {place}"
        elif plan["renamed_from"]:
            first = f"Neue Datei: {place} ({plan['renamed_from']} gibt es schon, sie bleibt unverändert)"
        else:
            first = f"Neue Datei: {place}"
        preview = " ".join(plan["text"].split())
        if len(preview) > PREVIEW_CHARS:
            preview = preview[:PREVIEW_CHARS].rstrip() + f" … ({len(plan['text'])} Zeichen)"
        return [first, f"Inhalt: {preview}"]

    # --- Schreiben -------------------------------------------------------
    def write(self, filename="", content="", folder="", mode="new"):
        try:
            plan = self.plan(filename, content, folder, mode)
        except NoteError as error:
            return ToolResult(success=False, error=str(error))

        newline = _newline()
        body = plan["text"].replace("\n", newline) + newline
        path = plan["path"]
        try:
            if plan["append"]:
                separator = ""
                if os.path.getsize(path) > 0:
                    with open(path, "rb") as stream:
                        stream.seek(-1, os.SEEK_END)
                        ends_with_newline = stream.read(1) in (b"\n", b"\r")
                    separator = newline if ends_with_newline else newline * 2
                with open(path, "a", encoding="utf-8", newline="") as stream:
                    stream.write(separator + body)
            else:
                written = False
                base, extension = os.path.splitext(plan["name"])
                for number in range(1, MAX_COPIES + 2):
                    try:
                        with open(path, "x", encoding="utf-8", newline="") as stream:   # exklusiv: ersetzt nie etwas
                            stream.write(body)
                        written = True
                        break
                    except FileExistsError:
                        stem = re.sub(r" \(\d+\)$", "", base)
                        plan["name"] = f"{stem} ({number + 1}){extension}"
                        plan["renamed_from"] = plan["renamed_from"] or f"{stem}{extension}"
                        path = os.path.join(plan["root"], plan["name"])
                if not written:
                    return ToolResult(success=False, error="Es gibt schon zu viele Dateien mit diesem Namen.")
        except OSError as error:
            return ToolResult(success=False, error=f"Die Notiz konnte ich nicht speichern ({type(error).__name__}).")

        data = {"saved": True, "file": plan["name"], "folder": os.path.basename(plan["root"]) or plan["root"],
                "characters": len(plan["text"]), "appended": plan["append"]}
        if plan["renamed_from"]:
            data["name_was_taken"] = plan["renamed_from"]
        return ToolResult(success=True, data=data)


_default = None


def default_writer():
    global _default
    if _default is None:
        _default = NoteWriter()
    return _default


def set_default_writer(writer):
    global _default
    _default = writer
