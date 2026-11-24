"""Dateien und Notizen auf dem PC, gesehen vom Server (S6, G5, DESIGN_GERAET.md).

Im Server-Betrieb ersetzen diese Klassen die lokalen Werkzeuge (Dateisuche, Lesen, Notizen, Ordnerliste): Sie haben dieselben
Methoden, schicken aber einen Auftrag an den PC-Agent. Dort laufen die echten Werkzeuge mit den dort freigegebenen Ordnern
(folders.json auf dem PC). Der Server kann Ordner weder erweitern noch umgehen: Freigeben geht nur am PC (py pc_agent.py --folders add ...).

Was der PC zurueckschickt, ist fuer den Server unvertraut: Form und Groesse prueft device_commands, jeder Text wird hier noch einmal
bereinigt (untrusted.clean_text). Ist der PC aus oder antwortet nicht, kommt eine klare Meldung statt eines Fehlers.
"""
import time

import device_commands
import device_hub
import folders as folders_module
from tools import document_tool, file_search_tool, note_tool
from tools.tool_result import ToolResult
from untrusted import clean_text


def _text(value, limit):
    """Text fuer einen Auftrag: Zahlen werden zu Text, alles andere zu ''."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (str, int)):
        return str(value)[:limit]
    return ""


def _number(value, default, low, high):
    try:
        return max(low, min(high, int(str(value).strip())))
    except (TypeError, ValueError):
        return default


def _clean_tree(value):
    if isinstance(value, str):
        return clean_text(value, device_commands.MAX_BODY_TEXT)
    if isinstance(value, list):
        return [_clean_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_tree(item) for key, item in value.items()}
    return value


class _Remote:
    def __init__(self, hub):
        self.hub = hub

    def call(self, command, args):
        """Auftrag an den PC. Gibt ein ToolResult zurueck; auch PC-aus und Zeitueberschreitung sind ein (klarer) Fehler."""
        try:
            envelope = self.hub.request(command, args)
        except (device_hub.DeviceError, device_commands.CommandError) as error:
            return ToolResult(success=False, error=str(error))
        if envelope["success"]:
            return ToolResult(success=True, data=_clean_tree(envelope["data"]))
        return ToolResult(success=False, error=clean_text(envelope["error"] or "", 400).strip() or "Das hat nicht geklappt.")


class RemoteSearch(_Remote):
    def find(self, query="", mode="name", file_type="", folder="", count=file_search_tool.DEFAULT_COUNT):
        return self.call("files.find", {"query": _text(query, 300), "mode": _text(mode, 20), "file_type": _text(file_type, 40),
                                        "folder": _text(folder, 100),
                                        "count": _number(count, file_search_tool.DEFAULT_COUNT, 1, file_search_tool.MAX_COUNT)})


class RemoteReader(_Remote):
    def __init__(self, hub, clock=time.monotonic):
        super().__init__(hub)
        self.clock = clock
        self._last = None                      # (Dateiname, Zeitpunkt) der zuletzt gelesenen Datei, fuer den Hinweis an den Router

    def read(self, file="", part=1, question=""):
        result = self.call("files.read", {"file": _text(file, 400), "part": _number(part, 1, 1, 1000), "question": _text(question, 300)})
        data = result.data
        if result.success and isinstance(data, dict) and isinstance(data.get("name"), str) and "choose" not in data:
            self._last = (data["name"], self.clock())
        return result

    def active_name(self):
        """Wie DocumentReader.active_name, aber ohne Rueckfrage an den PC (laeuft bei jeder Chat-Nachricht): gemerkt aus dem letzten Lesen."""
        if self._last is None or self.clock() - self._last[1] > document_tool.ACTIVE_SECONDS:
            return None
        return self._last[0]


class RemoteWriter(_Remote):
    def _args(self, filename, content, folder, mode):
        return {"filename": _text(filename, 300), "content": content if isinstance(content, str) else "",
                "folder": _text(folder, 100), "mode": _text(mode, 40)}

    @staticmethod
    def _too_long(content):
        if isinstance(content, str) and len(content) > device_commands.MAX_NOTE_TEXT:
            return f"Der Text ist zu lang für eine Notiz (höchstens {note_tool.MAX_CONTENT} Zeichen)."
        return None

    def write(self, filename="", content="", folder="", mode="new"):
        problem = self._too_long(content)
        if problem:
            return ToolResult(success=False, error=problem)
        return self.call("notes.write", self._args(filename, content, folder, mode))

    def check(self, filename="", content="", folder="", mode="new"):
        problem = self._too_long(content)
        if problem:
            return problem
        result = self.call("notes.check", self._args(filename, content, folder, mode))
        if not result.success:
            return result.error
        problem = result.data.get("problem") if isinstance(result.data, dict) else None
        return clean_text(problem, 400) if isinstance(problem, str) and problem else None

    def describe(self, filename="", content="", folder="", mode="new"):
        problem = self._too_long(content)
        if problem:
            return [f"Das geht nicht: {problem}"]
        result = self.call("notes.describe", self._args(filename, content, folder, mode))
        if not result.success:
            return [f"Das geht nicht: {result.error}"]
        lines = result.data.get("lines") if isinstance(result.data, dict) else None
        lines = [clean_text(line, 400) for line in lines if isinstance(line, str)][:4] if isinstance(lines, list) else []
        return lines or ["Das geht nicht: Die Antwort vom PC passt nicht."]


MOVE_HINT = ("Ordner gibst du am PC frei, nicht über den Server (aus Sicherheitsgründen): "
             "py pc_agent.py --folders add \"C:\\Pfad\\zum\\Ordner\"")


class RemoteFolders(_Remote):
    """Die freigegebenen Ordner des PCs: der Server liest sie nur."""

    def list(self):
        """[{"path", "exists"}]. Wirft DeviceError, wenn der PC nicht erreichbar ist."""
        return self.hub.request("folders.list")["folders"]

    def add(self, raw):
        raise folders_module.AccessError(MOVE_HINT)

    def remove(self, raw):
        raise folders_module.AccessError(MOVE_HINT.replace("--folders add", "--folders remove"))


def install(hub):
    """Haengt die PC-Werkzeuge als Standard ein. Gibt (search, reader, writer, folders) zurueck."""
    search, reader, writer, shared = RemoteSearch(hub), RemoteReader(hub), RemoteWriter(hub), RemoteFolders(hub)
    file_search_tool.set_default_search(search)
    document_tool.set_default_reader(reader)
    note_tool.set_default_writer(writer)
    folders_module.set_default_list(shared)
    return search, reader, writer, shared
