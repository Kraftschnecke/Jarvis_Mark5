"""Dokumente lesen (Mark 5, Step 2.16): Text einer Datei aus den freigegebenen Ordnern holen, damit Jarvis sie
zusammenfassen oder Fragen dazu beantworten kann (Fragen: Step 2.17, nutzt dieselben Teile).

Welche Datei: eine Nummer aus der zuletzt genannten Trefferliste (FileSearch.listed_file), ein Pfad oder ein
Dateiname (genau ein Treffer, sonst kommt die nummerierte Auswahl). **Jeder Weg endet in `FolderList.resolve()`**
(folders.py): ausserhalb der Freigabe, geschuetzt (.env, Schluessel, Jarvis-Ordner), Link nach draussen -> abgelehnt,
ohne Rueckfrage. Gelesen wird nie etwas anderes als das, was `resolve()` zurueckgibt.

Formate: Textdateien (TEXT_EXTENSIONS aus file_search_tool), .html (Tags weg), .docx (nur zipfile + Text-Regex, kein
XML-Parser, damit keine Entity-Bomben), .pdf (pypdf, falls installiert; Seiten- und Groessenlimit; Scans ohne Text
werden als solche gemeldet). Alles andere: klare Meldung.

Der Inhalt ist unvertraute Eingabe (untrusted.py): bereinigt, gekuerzt, in Teile (`part`) geschnitten und nie eine
Anweisung. Das Ergebnis steht spaeter im markierten Datenblock des Prompts; dort kann ein Dokument nichts ausloesen.
"""

import html
import logging
import os
import re
import threading
import time
import zipfile

import folders as folders_module
from folders import AccessError
from tools import file_search_tool
from tools.tool_result import ToolResult
from untrusted import clean_text

TEXT_EXTENSIONS = file_search_tool.TEXT_EXTENSIONS
READABLE = sorted(TEXT_EXTENSIONS | {".pdf", ".docx"})
MAX_PART_CHARS = 9000                  # ein Teil fuer das Sprachmodell (Block im Prompt hat 12 000 Zeichen)
MAX_TOTAL_CHARS = 200_000              # mehr merkt sich Jarvis von einer Datei nicht
MAX_TEXT_BYTES = 5 * 1024 * 1024
MAX_BINARY_BYTES = 20 * 1024 * 1024    # pdf/docx
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024  # entpackt
MAX_PDF_PAGES = 40
MAX_NAME = 80
# Das Sprachmodell schreibt bei "Fasse es zusammen" manchmal das Wort selbst in den Parameter: das ist keine Datei
NO_FILE_WORDS = {"es", "sie", "ihn", "das", "dies", "dieses", "diese", "datei", "dokument", "die datei", "das dokument",
                 "diese datei", "dieses dokument", "die letzte", "letzte", "zuletzt", "dieselbe", "it", "this", "that",
                 "none", "null", "-", "n/a", "unbekannt", "leer", "alle"}
MAX_CHOICES = 8
ACTIVE_SECONDS = 30 * 60               # so lange gilt eine gelesene Datei als "die Datei, um die es gerade geht"

WINDOW_CHARS = 1500                  # Abschnitte, aus denen die zur Frage passenden Stellen gewaehlt werden
MAX_QUESTION = 300
MAX_KEYWORDS = 8
STOPWORDS = {
    "und", "oder", "aber", "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "ist", "sind",
    "war", "wird", "wie", "was", "wer", "wann", "wo", "welche", "welcher", "welches", "wieviel", "viel", "viele", "hoch",
    "laut", "steht", "stehen", "gibt", "gab", "hat", "haben", "kann", "muss", "soll", "mit", "von", "vom", "zum", "zur",
    "fuer", "ueber", "auf", "aus", "bei", "nach", "dass", "wenn", "dann", "auch", "noch", "nur", "mir", "mich", "dir",
    "ich", "du", "sie", "wir", "ihr", "es", "im", "in", "an", "am", "um", "zu", "so", "als", "nicht", "kein", "keine",
    "datei", "dokument", "text", "vertrag", "brief", "pdf", "docx", "sagt", "sage", "bitte", "mal", "eigentlich", "genau",
    "the", "what", "how", "when", "who", "where", "which", "does", "this", "that", "with", "for", "and", "are", "was",
}
_TAGS = re.compile(r"<[^>]{0,2000}>")
_SCRIPTS = re.compile(r"(?is)<(script|style|head|svg|noscript)[^>]*>.*?</\1\s*>")
_PARAGRAPH_END = re.compile(r"</w:p\s*>|<w:br\s*/?>|<w:cr\s*/?>")
_TAB = re.compile(r"<w:tab\s*/?>")
_CELL_END = re.compile(r"(?:</w:p\s*>\s*)?</w:tc\s*>")
_ROW_END = re.compile(r"</w:tr\s*>")
_BLOCKS = re.compile(r"(?i)</?(p|div|br|li|tr|h[1-6]|section|article|table|ul|ol)\b[^>]*>")


def _tidy(text):
    """Zeilen putzen, Leerraum zusammenfassen, hoechstens eine Leerzeile am Stueck."""
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if b"\x00" in raw[:4096]:
        return None                                    # keine Textdatei
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_text_file(path, suffix):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_TEXT_BYTES)
    text = _decode(raw)
    if text is None:
        raise ValueError("Das ist keine Textdatei (Binärdaten).")
    if suffix in (".html", ".htm"):
        text = html.unescape(_TAGS.sub(" ", _BLOCKS.sub("\n", _SCRIPTS.sub(" ", text))))
    return text


def _read_docx(path):
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise ValueError("Das Word-Dokument ist zu groß.")
            with archive.open(info) as stream:
                xml = stream.read(MAX_DOCX_XML_BYTES + 1).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise ValueError("Das Word-Dokument konnte ich nicht öffnen (beschädigt oder kein .docx).") from error
    xml = _PARAGRAPH_END.sub("\n", _ROW_END.sub("\n", _CELL_END.sub("\t", _TAB.sub("\t", xml))))
    return html.unescape(_TAGS.sub("", xml))


def _read_pdf(path):
    try:
        import pypdf
        logging.getLogger("pypdf").setLevel(logging.ERROR)     # kaputte Dateien nicht in die Konsole schreiben
    except ImportError as error:
        raise ValueError("Zum Lesen von PDFs fehlt das Paket pypdf. Installiere es mit: py -m pip install pypdf") from error
    try:
        reader = pypdf.PdfReader(path)
        if getattr(reader, "is_encrypted", False):
            raise ValueError("Diese PDF ist passwortgeschützt, die kann ich nicht lesen.")
        pages = reader.pages
        total_pages = len(pages)
        parts = []
        size = 0
        for number in range(min(total_pages, MAX_PDF_PAGES)):
            page_text = pages[number].extract_text() or ""
            parts.append(page_text)
            size += len(page_text)
            if size >= MAX_TOTAL_CHARS:
                break
    except ValueError:
        raise
    except Exception as error:                          # pypdf wirft je nach Schaden viele Arten
        raise ValueError("Diese PDF konnte ich nicht lesen (beschädigt oder ungewöhnlich aufgebaut).") from error
    return "\n\n".join(parts), total_pages, len(parts)


def _norm(text):
    return text.casefold().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))


def question_keywords(question):
    """Die wichtigen Woerter der Frage (ohne Fuellwoerter), auf 6 Zeichen gekuerzt, damit Beugungen mitzaehlen."""
    found = []
    for word in re.findall(r"[0-9a-zA-Z]{3,}", _norm(question)):
        base = re.sub(r"(es|en|e|s|n)$", "", word)             # "Vertrags", "Texte" zaehlen wie "Vertrag", "Text"
        if word in STOPWORDS or base in STOPWORDS:
            continue
        stem = word[:6]
        if stem not in found:
            found.append(stem)
    return found[:MAX_KEYWORDS]


def _windows(text):
    """Text in Abschnitte von etwa WINDOW_CHARS Zeichen, an Absatzgrenzen."""
    windows, current = [], ""
    for block in re.split(r"\n{2,}", text):
        while len(block) > WINDOW_CHARS:                       # sehr langer Absatz: hart teilen
            cut = block.rfind(" ", 0, WINDOW_CHARS)
            cut = cut if cut > WINDOW_CHARS // 2 else WINDOW_CHARS
            windows.append(block[:cut])
            block = block[cut:].lstrip()
        if current and len(current) + len(block) + 2 > WINDOW_CHARS:
            windows.append(current)
            current = ""
        current = f"{current}\n\n{block}" if current else block
    if current:
        windows.append(current)
    return windows


def passages_for_question(text, question, budget=MAX_PART_CHARS):
    """Die Stellen eines langen Textes, die zur Frage passen (beste zuerst gewaehlt, im Text in Reihenfolge).

    Gibt (Auszug, gefunden) zurueck; gefunden=False: kein Abschnitt enthaelt ein Wort der Frage (dann der Anfang).
    Der erste Abschnitt kommt als Zusammenhang dazu, wenn Platz ist.
    """
    keywords = question_keywords(question)
    windows = _windows(text)
    scored = []
    for index, window in enumerate(windows):
        lowered = _norm(window)
        hits = [lowered.count(k) for k in keywords]
        score = 10 * sum(1 for h in hits if h) + sum(min(h, 5) for h in hits)
        if score:
            scored.append((score, index))
    if not scored:
        return text[:budget], False
    chosen, used = [], 0
    for score, index in sorted(scored, key=lambda item: (-item[0], item[1])):
        if used + len(windows[index]) > budget and chosen:
            continue
        chosen.append(index)
        used += len(windows[index])
    if 0 not in chosen and used + len(windows[0]) <= budget:
        chosen.append(0)
    chosen.sort()
    pieces, previous = [], None
    for index in chosen:
        if previous is not None and index != previous + 1:
            pieces.append("[…]")
        pieces.append(windows[index])
        previous = index
    return "\n\n".join(pieces)[:budget], True


class DocumentReader:
    def __init__(self, folder_list=None, search=None, clock=time.monotonic):
        self._folders = folder_list
        self._search = search
        self.clock = clock
        self._lock = threading.Lock()
        self._last_path = None
        self._last_time = None
        self._seq_at_read = 0

    @property
    def folders(self):
        return self._folders if self._folders is not None else folders_module.default_list()

    @property
    def search(self):
        return self._search if self._search is not None else file_search_tool.default_search()

    def active_name(self):
        """Name der Datei, die gerade gelesen wurde und um die es vermutlich weitergeht (sonst None).

        Der Router bekommt ihn als Hinweis, damit Folgefragen ohne Dateinamen ("Wie hoch ist die Kaution?") bei der
        Datei bleiben. Nach ACTIVE_SECONDS oder wenn die Datei verschwunden ist, gilt sie nicht mehr.
        """
        with self._lock:
            path, stamp = self._last_path, self._last_time
        if path is None or stamp is None or self.clock() - stamp > ACTIVE_SECONDS or not os.path.isfile(path):
            return None
        return os.path.basename(path)

    # --- Welche Datei? -------------------------------------------------
    def _pick(self, file):
        """Gibt (Pfad, Auswahl-Ergebnis) zurueck: entweder ein Pfad oder ein fertiges ToolResult (Rueckfrage/Fehler)."""
        text = clean_text(file, 400).strip() if isinstance(file, str) else (str(file) if isinstance(file, int) and not isinstance(file, bool) else "")
        if not text:
            return None, ToolResult(success=False, error="Welche Datei soll ich lesen? Nenne den Namen oder die Nummer aus der Trefferliste.")
        if re.fullmatch(r"\d{1,3}", text):
            path = self.search.listed_file(text)
            if path is None:
                return None, ToolResult(success=False, error="Diese Nummer kenne ich nicht. Lass mich zuerst nach der Datei suchen.")
            return path, None
        if os.path.isabs(os.path.expanduser(text)) or "/" in text or "\\" in text:
            return text, None                           # Pfad: wird gleich von resolve() geprueft
        found = self.search.find(text, mode="name", count=MAX_CHOICES)
        if not found.success:
            return None, found
        files = found.data["files"]
        if not files:
            return None, ToolResult(success=False, error="Eine Datei mit diesem Namen habe ich in den freigegebenen Ordnern nicht gefunden.")
        exact = [f for f in files if f["name"].casefold() == text.casefold()]
        chosen = exact if len(exact) == 1 else files
        if len(chosen) == 1:
            return self.search.listed_file(chosen[0]["number"]), None
        return None, ToolResult(success=True, data={
            "choose": files, "total_matches": found.data["total_matches"],
            "info": "Mehrere Dateien passen. Frage, welche gemeint ist (Nummer reicht)."})

    # --- Lesen ---------------------------------------------------------
    def read(self, file="", part=1, question=""):
        try:
            number = max(1, min(1000, int(str(part).strip())))
        except (TypeError, ValueError):
            number = 1

        raw_file = file
        if not (isinstance(file, (str, int)) and str(file).strip()) or str(file).strip().casefold().rstrip(".!?") in NO_FILE_WORDS:
            with self._lock:
                last = self._last_path
                seq_at_read = self._seq_at_read
            listing = [i for i in self.search.last_listing() if os.path.exists(i["path"])]    # Gelöschtes zählt nicht
            if last is not None and self.search.sequence == seq_at_read:
                raw_file = last                             # seit dem Lesen nicht neu gesucht: die Datei, um die es geht
            elif number == 1 and len(listing) == 1:
                raw_file = listing[0]["path"]               # "Fass es zusammen" nach genau einem Treffer
            elif number == 1 and len(listing) > 1 and (last is None or last not in [i["path"] for i in listing]):
                return ToolResult(success=True, data={
                    "choose": [{"number": i["number"], "name": os.path.basename(i["path"])} for i in listing],
                    "info": "Mehrere Dateien stehen zur Auswahl. Frage, welche gemeint ist (Nummer reicht)."})
            elif last is not None:
                raw_file = last
            else:
                return ToolResult(success=False, error="Welche Datei soll ich lesen? Nenne den Namen oder die Nummer aus der Trefferliste.")
        path, outcome = self._pick(raw_file)
        if outcome is not None:
            return outcome

        try:
            real = self.folders.resolve(path)
        except AccessError as error:
            return ToolResult(success=False, error=str(error))
        if not os.path.isfile(real):
            return ToolResult(success=False, error="Das ist keine Datei.")

        name = os.path.basename(real)
        suffix = os.path.splitext(name)[1].casefold()
        if suffix not in READABLE:
            return ToolResult(success=False, error=f"Dieses Dateiformat ({suffix or 'ohne Endung'}) kann ich noch nicht lesen. "
                                                   f"Lesbar sind: {', '.join(e.lstrip('.') for e in READABLE)}.")
        try:
            size = os.path.getsize(real)
        except OSError:
            return ToolResult(success=False, error="Die Datei konnte ich nicht lesen.")
        if suffix in (".pdf", ".docx") and size > MAX_BINARY_BYTES:
            return ToolResult(success=False, error="Die Datei ist zu groß (über 20 MB).")

        pages = None
        pages_read = None
        try:
            if suffix == ".pdf":
                text, pages, pages_read = _read_pdf(real)
            elif suffix == ".docx":
                text = _read_docx(real)
            else:
                text = _read_text_file(real, suffix)
        except ValueError as error:
            return ToolResult(success=False, error=str(error))
        except OSError:
            return ToolResult(success=False, error="Die Datei konnte ich nicht lesen.")

        text = clean_text(_tidy(text), MAX_TOTAL_CHARS + 100)
        with self._lock:
            self._last_path = real
            self._last_time = self.clock()
            self._seq_at_read = self.search.sequence
        if not text:
            hint = " (vermutlich ein Scan oder nur Bilder: Text erkennen kann ich nicht)" if suffix == ".pdf" else ""
            return ToolResult(success=True, data={"name": clean_text(name, MAX_NAME), "info": f"In der Datei steht kein lesbarer Text{hint}."})

        parts = (len(text) + MAX_PART_CHARS - 1) // MAX_PART_CHARS
        asked = clean_text(question, MAX_QUESTION).strip() if isinstance(question, str) else ""
        if asked and parts > 1 and number == 1 and question_keywords(asked):
            excerpt, matched = passages_for_question(text, asked)
            data = {"name": clean_text(name, MAX_NAME), "type": suffix.lstrip("."), "characters": len(text),
                    "parts": parts, "text": excerpt, "excerpts_for_question": matched}
            if pages is not None:
                data["pages"] = pages
                if pages_read < pages:
                    data["pages_read"] = pages_read
            if matched:
                data["note"] = "Die Datei ist lang: Ich habe nur die Stellen herausgesucht, die zur Frage passen."
            else:
                data["note"] = "Zur Frage habe ich keine passende Stelle gefunden; das ist nur der Anfang der Datei."
            if text.endswith("[... gekuerzt]") or (pages_read is not None and pages_read < pages):
                data["cut"] = "Die Datei ist sehr lang; ich habe nur den Anfang gelesen."
            return ToolResult(success=True, data=data)
        if number > parts:
            return ToolResult(success=False, error=f"Die Datei hat nur {parts} Teil(e).")
        chunk = text[(number - 1) * MAX_PART_CHARS:number * MAX_PART_CHARS]

        data = {"name": clean_text(name, MAX_NAME), "type": suffix.lstrip("."), "part": number, "parts": parts,
                "characters": len(text), "text": chunk}
        if pages is not None:
            data["pages"] = pages
            if pages_read < pages:
                data["pages_read"] = pages_read
        if parts > number:
            data["more"] = f"Es folgt noch Teil {number + 1} von {parts}; zum Weiterlesen: dieselbe Datei, Teil {number + 1}."
        if text.endswith("[... gekuerzt]") or (pages_read is not None and pages_read < pages):
            data["cut"] = "Die Datei ist sehr lang; ich habe nur den Anfang gelesen."
        return ToolResult(success=True, data=data)


_default = None


def default_reader():
    global _default
    if _default is None:
        _default = DocumentReader()
    return _default


def set_default_reader(reader):
    global _default
    _default = reader
