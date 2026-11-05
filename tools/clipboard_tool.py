"""Zwischenablage lesen (Mark 5, Step 2.24). NUR LESEN, nur Text, nur unter Windows.

Was dieses Werkzeug tut: den Text lesen, der gerade in der Windows-Zwischenablage liegt, damit Jarvis ihn zusammenfassen,
uebersetzen oder eine Frage dazu beantworten kann ("Fasse zusammen, was in meiner Zwischenablage steht").
Was es NICHT tut: in die Zwischenablage schreiben, sie leeren, Bilder oder Dateien lesen. Es gibt in diesem Modul keinen
Schreibweg. Gelesen wird erst nach deinem "Ja" und nur der Text, hoechstens MAX_TEXT Zeichen. Die Rueckfrage zeigt den Inhalt
absichtlich NICHT (dort koennte ein kopiertes Passwort stehen); sie sagt nur, dass der Text an OpenAI geht.
Der Inhalt stammt aus beliebigen Quellen (Webseiten, Mails) und ist unvertraut: gesaeubert, gekuerzt, nur als Daten an das
Sprachmodell. Er wird nicht gespeichert.
"""

import sys
import time

from tools.tool_result import ToolResult
from untrusted import clean_text

CF_UNICODETEXT = 13
MAX_TEXT = 9000              # Zeichen, die zum Sprachmodell gehen
MAX_READ = 400000            # Zeichen, die hoechstens aus der Zwischenablage geholt werden
MAX_QUESTION = 300
OPEN_TRIES = 6               # die Zwischenablage kann kurz von einem anderen Programm gehalten werden


def _read_text():
    """Gibt den Text der Zwischenablage zurueck, oder None wenn dort kein Text liegt (nur Windows). Wird in Tests ersetzt."""
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.CloseClipboard.argtypes, user32.CloseClipboard.restype = [], wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes, user32.IsClipboardFormatAvailable.restype = [wintypes.UINT], wintypes.BOOL
    user32.GetClipboardData.argtypes, user32.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes, kernel32.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
    kernel32.GlobalSize.argtypes, kernel32.GlobalSize.restype = [wintypes.HGLOBAL], ctypes.c_size_t

    for attempt in range(OPEN_TRIES):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("Die Zwischenablage wird gerade von einem anderen Programm benutzt.")

    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError("Der Inhalt der Zwischenablage ließ sich nicht öffnen.")
        try:
            length = min(kernel32.GlobalSize(handle) // 2, MAX_READ)
            return ctypes.wstring_at(pointer, length).split("\x00", 1)[0]
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_clipboard(question=""):
    if not sys.platform.startswith("win"):
        return ToolResult(success=False, error="Die Zwischenablage kann Jarvis nur unter Windows lesen.")

    try:
        raw = _read_text()
    except Exception as error:
        return ToolResult(success=False, error=f"Die Zwischenablage ließ sich nicht lesen ({error}).")

    if raw is None:
        return ToolResult(success=True, data={"info": "In der Zwischenablage liegt kein Text (vielleicht ein Bild oder eine Datei)."})

    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ToolResult(success=True, data={"info": "Die Zwischenablage ist leer."})

    data = {"characters": len(text), "text": clean_text(text[:MAX_TEXT], MAX_TEXT + 40)}
    if len(text) > MAX_TEXT:
        data["cut"] = True
    asked = clean_text(question, MAX_QUESTION).strip() if isinstance(question, str) else ""
    if asked:
        data["question"] = asked
    return ToolResult(success=True, data=data)


def describe(question=""):
    """Zeilen fuer die Rueckfrage (ohne den Inhalt)."""
    return ["Der Text, der gerade in deiner Zwischenablage liegt",
            "Er geht zum Auswerten an OpenAI. Nichts wird verändert, gespeichert oder in die Zwischenablage geschrieben."]
