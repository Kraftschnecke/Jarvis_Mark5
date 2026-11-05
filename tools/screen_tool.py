"""Bildschirm ansehen (Mark 5, Step 2.25). Ein Bild aufnehmen, damit Jarvis beschreiben kann, was zu sehen ist.

Ablauf: Nach deinem "Ja" wird der HAUPTBILDSCHIRM einmal aufgenommen, auf hoechstens MAX_WIDTH Pixel Breite verkleinert und als
PNG im Arbeitsspeicher an das Ergebnis gehaengt. brain.respond_to_task schickt es zusammen mit deiner Frage an das Sprachmodell
und wirft es danach weg. Das Bild wird nie auf die Festplatte geschrieben, nie in der Datenbank, im Protokoll oder im
Gespraech gespeichert und steht nicht im Text des Ergebnisses (Schluessel mit "_" am Anfang werden nie als Text ausgegeben).
Es gibt keine Dauerbeobachtung: eine Aufnahme pro Ja.

Die Aufnahme laeuft ueber ein FEST eingebautes PowerShell-Skript (System.Drawing, kein Text vom Nutzer oder Modell darin).
Was auf dem Bildschirm steht, ist unvertraut: Text im Bild kann Anweisungen enthalten (siehe Prompt-Regel in brain.py).
Nur Windows. Nur der Hauptbildschirm; weitere Monitore werden nicht aufgenommen.
"""

import base64
import re
import subprocess
import sys

from tools.tool_result import ToolResult
from untrusted import clean_text

MAX_WIDTH = 1600
MAX_BYTES = 6_000_000          # so gross darf das PNG hoechstens sein
MAX_QUESTION = 300
CAPTURE_TIMEOUT = 30
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IMAGE_KEY = "_image_png_base64"

_SCRIPT = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class JarvisDpi {{ [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }}'
[void][JarvisDpi]::SetProcessDPIAware()
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$g.Dispose()
if ($bmp.Width -gt {MAX_WIDTH}) {{
  $h = [int]($bmp.Height * {MAX_WIDTH} / $bmp.Width)
  $small = New-Object System.Drawing.Bitmap $bmp, {MAX_WIDTH}, $h
  $bmp.Dispose()
  $bmp = $small
}}
$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
[Convert]::ToBase64String($ms.ToArray())
"""


def _capture():
    """Nimmt den Hauptbildschirm auf und gibt das PNG als Base64-Text zurueck (nur Windows). Wird in Tests ersetzt."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")      # -EncodedCommand: keine Probleme mit Anfuehrungszeichen
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], capture_output=True,
                          timeout=CAPTURE_TIMEOUT, creationflags=flags)
    if done.returncode != 0:
        raise OSError("PowerShell meldet einen Fehler")
    return (done.stdout or b"").decode("ascii", errors="ignore").strip()


def _valid_png(text):
    """True, wenn ``text`` Base64 eines PNG in erlaubter Groesse ist."""
    if not isinstance(text, str) or not text or len(text) > MAX_BYTES * 4 // 3 + 8 or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", text):
        return False
    try:
        raw = base64.b64decode(text, validate=True)
    except ValueError:
        return False
    return raw.startswith(PNG_SIGNATURE) and len(raw) <= MAX_BYTES


def describe_screen(question=""):
    """Nimmt den Bildschirm auf. Das Bild steckt unter IMAGE_KEY im Ergebnis; den Rest uebernimmt brain.respond_to_task."""
    if not sys.platform.startswith("win"):
        return ToolResult(success=False, error="Den Bildschirm kann Jarvis nur unter Windows ansehen.")

    try:
        image = _capture()
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Die Bildschirmaufnahme hat zu lange gedauert.")
    except Exception:
        return ToolResult(success=False, error="Die Bildschirmaufnahme hat nicht geklappt.")

    if not _valid_png(image):
        return ToolResult(success=False, error="Die Bildschirmaufnahme hat kein brauchbares Bild geliefert.")

    data = {IMAGE_KEY: image, "image": "Eine Aufnahme des Hauptbildschirms ist dem Auftrag als Bild beigefügt."}
    asked = clean_text(question, MAX_QUESTION).strip() if isinstance(question, str) else ""
    if asked:
        data["question"] = asked
    return ToolResult(success=True, data=data)


def describe(question=""):
    """Zeilen fuer die Rueckfrage."""
    return [f"Ein Bild deines Hauptbildschirms (auf höchstens {MAX_WIDTH} Pixel Breite verkleinert)",
            "Es geht nur zum Beantworten an OpenAI und wird nicht gespeichert. Alles, was gerade sichtbar ist (auch Passwörter, Mails, Nachrichten), ist im Bild.",
            "Schließe vorher, was nicht dabei sein soll."]
