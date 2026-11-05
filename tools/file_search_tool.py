"""Dateien finden (Mark 5, Step 2.15): nach Name oder Inhalt, nur in den freigegebenen Ordnern.

Der Weg durch die Ordner geht ausschliesslich ueber `FolderList.walk()` (folders.py): Was dort nicht erscheint
(ausserhalb der Freigabe, geschuetzt, versteckt, per Link nach draussen), kann hier nie gefunden werden.

Name: alle Suchwoerter muessen im Dateinamen stehen (Gross-/Kleinschreibung egal).
Inhalt: nur in Textdateien (TEXT_EXTENSIONS, bis 2 MB); alle Suchwoerter muessen irgendwo im Text stehen.
PDF und Word kommen mit 2.16 (Lesen). Das Ergebnis ist eine nummerierte Liste; `listed_file(nummer)` gibt den
Pfad dazu zurueck, damit spaetere Schritte "die zweite Datei" meinen koennen (Pfad wird dort erneut geprueft).

Dateinamen und Textauszuege sind unvertraute Eingabe (untrusted.py): bereinigt, gekuerzt, nie eine Anweisung.
Die Suche ist begrenzt (Dateien, Inhalte, Zeit) und sagt es, wenn sie dadurch unvollstaendig ist.
"""

import os
import re
import threading
import time
from datetime import datetime

import folders as folders_module
from tools.tool_result import ToolResult
from untrusted import clean_text

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".ini", ".cfg",
                   ".yaml", ".yml", ".tex", ".py", ".js", ".css"}
TYPE_WORDS = {
    "pdf": {".pdf"}, "word": {".docx", ".doc"}, "dokument": {".docx", ".doc", ".pdf", ".odt", ".txt"},
    "excel": {".xlsx", ".xls", ".csv"}, "tabelle": {".xlsx", ".xls", ".csv"}, "text": {".txt", ".md"},
    "bild": {".jpg", ".jpeg", ".png", ".gif", ".webp"}, "foto": {".jpg", ".jpeg", ".png"},
    "powerpoint": {".pptx", ".ppt"}, "praesentation": {".pptx", ".ppt"}, "präsentation": {".pptx", ".ppt"},
}
MODES = ("name", "content", "both")
DEFAULT_COUNT = 8
MAX_COUNT = 20
MAX_WORDS = 5
MAX_QUERY = 100
MAX_NAME = 80
MAX_SNIPPET = 160
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES_VISITED = 20000
MAX_CONTENT_FILES = 2000
TIME_LIMIT = 8.0


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
# Woerter, die im Dateinamen dasselbe meinen (deutsch/englisch). Klein, damit die Treffer nachvollziehbar bleiben.
SYNONYM_GROUPS = (
    {"rechnung", "invoice", "receipt", "beleg", "quittung", "bill"},
    {"vertrag", "contract", "agreement"},
    {"lebenslauf", "cv", "resume", "curriculum"},
    {"steuer", "tax"},
    {"bewerbung", "application"},
    {"zeugnis", "certificate", "diploma"},
    {"kuendigung", "termination", "cancellation"},
    {"versicherung", "insurance"},
    {"bestaetigung", "confirmation"},
    {"flug", "flight", "ticket"},
    {"reise", "trip", "travel"},
    {"foto", "photo", "bild", "image", "picture"},
    {"gehalt", "lohn", "salary", "payslip"},
)
_TAGS = re.compile(r"<[^>]{0,200}>")


def _norm(text):
    """Klein geschrieben, Umlaute als ae/oe/ue/ss: "Kündigung" und "Kuendigung" sind gleich."""
    return text.casefold().translate(_UMLAUTS)


def _variants(word):
    """Das Suchwort und seine Synonyme, alle normalisiert."""
    base = _norm(word)
    found = {base}
    for group in SYNONYM_GROUPS:
        if base in group:
            found |= group
    return found


def _words(text):
    return [w for w in re.split(r"\s+", clean_text(text, MAX_QUERY).casefold().strip()) if w][:MAX_WORDS]


def _extensions(file_type):
    """".pdf", "pdf", "Word", "Bilder" -> Menge von Endungen. Leer/unbekannt -> None (= jede) oder die Endung selbst."""
    if not isinstance(file_type, str):
        return None
    text = clean_text(file_type, 30).strip().casefold().lstrip("*.").rstrip("s") if file_type.strip().casefold().endswith("s") \
        and file_type.strip().casefold().lstrip("*.") not in TYPE_WORDS else clean_text(file_type, 30).strip().casefold().lstrip("*.")
    if text in ("", "alle", "egal", "none", "null", "-", "beliebig", "datei", "dateien"):
        return None
    if text in TYPE_WORDS:
        return TYPE_WORDS[text]
    return {"." + text} if re.fullmatch(r"[a-z0-9]{1,6}", text) else None


def _size_text(size):
    if size < 1024:
        return f"{size} Byte"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


def _snippet(text, word):
    index = text.casefold().find(word)
    if index < 0:
        return ""
    piece = text[max(0, index - 60):index + 100]
    return clean_text(" ".join(_TAGS.sub(" ", piece).split()), MAX_SNIPPET)


class FileSearch:
    def __init__(self, folder_list=None, clock=time.monotonic):
        self._folders = folder_list
        self.clock = clock
        self._lock = threading.Lock()
        self._last = []                 # [{"number", "path"}] der zuletzt genannten Treffer
        self._sequence = 0              # zaehlt die Suchen: so erkennt das Lesen, ob die Liste neuer ist als die gelesene Datei

    @property
    def folders(self):
        return self._folders if self._folders is not None else folders_module.default_list()

    def find(self, query="", mode="name", file_type="", folder="", count=DEFAULT_COUNT):
        words = _words(query) if isinstance(query, str) else []
        mode = mode.strip().casefold() if isinstance(mode, str) and mode.strip().casefold() in MODES else "name"
        extensions = _extensions(file_type)
        where = clean_text(folder, 60).strip().casefold() if isinstance(folder, str) else ""
        if where in ("", "alle", "alles", "egal", "none", "null", "-"):
            where = ""
        try:
            limit = max(1, min(MAX_COUNT, int(str(count).strip())))
        except (TypeError, ValueError):
            limit = DEFAULT_COUNT

        if not words and extensions is None and not where:
            return ToolResult(success=False, error="Wonach soll ich suchen? Nenne einen Teil des Dateinamens, ein Stichwort aus dem Inhalt oder einen Dateityp.")
        if not self.folders.roots():
            return ToolResult(success=False, error="Es ist noch kein Ordner freigegeben. Trage Ordner in den Einstellungen unter „Folders“ ein.")

        started = self.clock()
        stats = {"visited": 0, "content_read": 0}
        stop_reason = []

        def should_stop():
            if self.clock() - started > TIME_LIMIT:
                stop_reason.append("Zeit")
            elif stats["visited"] >= MAX_FILES_VISITED:
                stop_reason.append("Dateien")
            return bool(stop_reason)

        variants = {w: _variants(w) for w in words}

        def scan(scan_mode):
            hits = []
            stats["visited"] = 0
            for real, root, relative in self.folders.walk(should_stop):
                stats["visited"] += 1
                name = os.path.basename(real)
                normalized_name = _norm(name)
                suffix = os.path.splitext(name)[1].casefold()
                location = os.path.join(os.path.basename(root), os.path.dirname(relative)).rstrip("\\/")
                if where and where not in location.casefold():
                    continue
                if extensions is not None and suffix not in extensions:
                    continue

                by_name = bool(words) and all(any(v in normalized_name for v in variants[w]) for w in words)
                snippet = ""
                by_content = False
                if words and not by_name and scan_mode in ("content", "both") and suffix in TEXT_EXTENSIONS \
                        and stats["content_read"] < MAX_CONTENT_FILES:
                    text = self._read_text(real)
                    if text is not None:
                        stats["content_read"] += 1
                        lowered = text.casefold()
                        if all(w in lowered for w in words):
                            by_content, snippet = True, _snippet(text, words[0])
                if words:
                    if not ((scan_mode in ("name", "both") and by_name) or by_content):
                        if not (scan_mode == "content" and by_name and suffix not in TEXT_EXTENSIONS):
                            continue
                try:
                    info = os.stat(real)
                except OSError:
                    continue
                hits.append({"path": real, "name": name, "location": location, "size": info.st_size, "mtime": info.st_mtime,
                             "match": "name" if by_name else "content", "snippet": snippet})

            return hits

        hits = scan(mode)
        fallback = False
        if not hits and mode == "name" and words and not stop_reason:
            hits, fallback = scan("both"), True               # im Namen nichts: auch in Textinhalten suchen

        hits.sort(key=lambda h: (0 if h["match"] == "name" else 1, -h["mtime"]))
        shown = hits[:limit]
        with self._lock:
            self._last = [{"number": n, "path": h["path"]} for n, h in enumerate(shown, start=1)]
            self._sequence += 1

        files = []
        for number, h in enumerate(shown, start=1):
            entry = {"number": number, "name": clean_text(h["name"], MAX_NAME), "folder": clean_text(h["location"], 120),
                     "size": _size_text(h["size"]), "modified": datetime.fromtimestamp(h["mtime"]).strftime("%d.%m.%Y"),
                     "found_in": "Name" if h["match"] == "name" else "Inhalt"}
            if h["snippet"]:
                entry["excerpt"] = h["snippet"]
            files.append(entry)

        data = {"files": files, "total_matches": len(hits), "searched_files": stats["visited"]}
        if stop_reason:
            data["incomplete"] = "Die Suche wurde abgebrochen (" + ("zu lange" if stop_reason[0] == "Zeit" else "zu viele Dateien") + "): Es können weitere Treffer fehlen."
        if fallback:
            data["also_searched_content"] = "Im Dateinamen gab es keinen Treffer, deshalb habe ich auch den Inhalt der Textdateien durchsucht."
        if (mode in ("content", "both") or fallback) and words:
            data["content_note"] = "Inhalte durchsuche ich nur in Textdateien (txt, md, csv, json, html, …); PDF und Word noch nicht."
        if not files:
            data["info"] = "Dazu habe ich in den freigegebenen Ordnern nichts gefunden."
        elif len(hits) > len(shown):
            data["more"] = f"Es gibt {len(hits) - len(shown)} weitere Treffer; mit einem genaueren Suchwort wird die Liste kürzer."
        return ToolResult(success=True, data=data)

    @staticmethod
    def _read_text(path):
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                return None
            with open(path, "rb") as stream:
                raw = stream.read(MAX_FILE_BYTES)
        except OSError:
            return None
        if b"\x00" in raw[:2048]:                       # Binaerdatei mit Textendung
            return None
        return raw.decode("utf-8", errors="replace")

    @property
    def sequence(self):
        with self._lock:
            return self._sequence

    def last_listing(self):
        """Pfade der zuletzt genannten Treffer (Nummer, Pfad) fuer "fass es zusammen" ohne Nennung einer Datei."""
        with self._lock:
            return [dict(item) for item in self._last]

    def listed_file(self, number):
        """Pfad der Datei mit dieser Nummer aus der letzten Trefferliste oder None. (Spaetere Schritte pruefen ihn erneut.)"""
        try:
            wanted = int(str(number).strip())
        except (TypeError, ValueError):
            return None
        with self._lock:
            return next((i["path"] for i in self._last if i["number"] == wanted), None)


_default = None


def default_search():
    global _default
    if _default is None:
        _default = FileSearch()
    return _default


def set_default_search(search):
    global _default
    _default = search
