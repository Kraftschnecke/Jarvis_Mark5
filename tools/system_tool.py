"""Rechner-Grundfunktionen (Mark 5, Step 2.23): Ton stumm, Bildschirm sperren, Desktop zeigen, Helligkeit.

Nur diese fuenf festen Befehle, nur unter Windows, ohne Konto und ohne Netz:
  mute          die Stummtaste (Umschalter: stumm an/aus)
  lock          den Bildschirm sperren (wie Windows+L; danach braucht es dein Passwort)
  show_desktop  alle Fenster minimieren bzw. zurueckholen (wie Windows+D)
  brightness_*  Helligkeit setzen/heller/dunkler (nur Bildschirme, die Windows selbst dimmen kann, meist Laptops)
Jarvis kann damit nichts oeffnen, schliessen oder loeschen und keine beliebige Taste druecken. Alle Befehle sind
beim Risiko "confirm" (siehe risk.py). Helligkeit geht ueber ein FEST eingebautes PowerShell-Skript, in das nur eine
gepruefte ganze Zahl eingesetzt wird; Text vom Nutzer oder Modell gelangt nie in einen Befehl.
"""

import re
import subprocess
import sys

from tools.tool_result import ToolResult

VK_VOLUME_MUTE = 0xAD
VK_LWIN = 0x5B
VK_D = 0x44
KEYEVENTF_KEYUP = 0x0002
STEP = 20
MIN_BRIGHTNESS = 5
POWERSHELL_TIMEOUT = 15

COMMANDS = ("mute", "lock", "show_desktop", "brightness_set", "brightness_up", "brightness_down")

ALIASES = {
    "mute": "mute", "unmute": "mute", "stumm": "mute", "stummschalten": "mute", "ton aus": "mute", "ton an": "mute",
    "lock": "lock", "sperren": "lock", "bildschirm sperren": "lock", "computer sperren": "lock", "lock screen": "lock",
    "show desktop": "show_desktop", "desktop": "show_desktop", "desktop zeigen": "show_desktop",
    "fenster minimieren": "show_desktop", "alle fenster minimieren": "show_desktop", "minimize": "show_desktop",
    "brightness": "brightness_set", "helligkeit": "brightness_set", "set brightness": "brightness_set",
    "heller": "brightness_up", "brighter": "brightness_up", "brightness up": "brightness_up",
    "dunkler": "brightness_down", "dimmer": "brightness_down", "dim": "brightness_down", "brightness down": "brightness_down",
}

DONE = {
    "mute": "Stummtaste gedrückt",
    "lock": "Bildschirm gesperrt",
    "show_desktop": "Alle Fenster minimiert (Windows+D)",
}

_GET = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness"


def normalize_command(raw):
    """Gibt den festen Befehlsnamen zurueck oder None."""
    if not isinstance(raw, str):
        return None
    word = " ".join(raw.strip().casefold().replace("_", " ").split())
    key = word.replace(" ", "_")
    if key in COMMANDS:
        return key
    return ALIASES.get(word)


def parse_percent(value):
    """Ganze Zahl 0 bis 100 aus '50', '50%', 50, 50.0; sonst None. Wahrheitswerte zaehlen nicht."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = value
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d{1,3})(?:[.,]0+)?\s*(?:%|prozent|percent)?\s*", value, re.IGNORECASE)
        if not match:
            return None
        number = int(match.group(1))
    else:
        return None
    if number != int(number) or not 0 <= number <= 100:
        return None
    return int(number)


def _press(keys):
    """Drueckt Tasten gleichzeitig und loest sie (nur Windows). Wird in Tests ersetzt."""
    import ctypes
    user32 = ctypes.windll.user32
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


def _lock():
    """Sperrt den Bildschirm (nur Windows). Wird in Tests ersetzt."""
    import ctypes
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows hat das Sperren abgelehnt")


def _powershell(script):
    """Fuehrt ein FESTES Skript aus und gibt die Ausgabe zurueck. Wird in Tests ersetzt."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Als Bytes holen und selbst lesen: Fehlertexte von PowerShell kommen je nach Windows-Sprache in der DOS-Zeichentabelle
    # (z. B. "Zugriff verweigert" mit Umlaut), und das Lesen als cp1252 wuerde einen Fehler im Lese-Thread ausloesen.
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                          timeout=POWERSHELL_TIMEOUT, creationflags=flags)
    if done.returncode != 0:
        raise OSError("PowerShell meldet einen Fehler")
    return (done.stdout or b"").decode("utf-8", errors="replace")


def _current_brightness():
    text = _powershell(_GET).strip()
    if not re.fullmatch(r"\d{1,3}", text):
        raise OSError("keine Helligkeit gemeldet")
    return int(text)


def _set_brightness(level):
    level = int(level)                                            # nur eine ganze Zahl kommt je in das Skript
    if not MIN_BRIGHTNESS <= level <= 100:
        raise ValueError("Helligkeit ausserhalb des erlaubten Bereichs")
    _powershell(f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})")


NO_BRIGHTNESS = ("Die Helligkeit lässt sich bei diesem Bildschirm nicht von Windows aus ändern "
                 "(bei externen Monitoren geht das meist nur an der Monitortaste).")


def _brightness(name, value):
    try:
        if name == "brightness_set":
            level = parse_percent(value)
            if level is None:
                return ToolResult(success=False, error="Auf wie viel Prozent? Nenne eine Zahl von 0 bis 100.")
        else:
            current = _current_brightness()
            step = parse_percent(value) if str(value or "").strip() else STEP
            level = current + (step or STEP) * (1 if name == "brightness_up" else -1)
        level = max(MIN_BRIGHTNESS, min(100, level))
        _set_brightness(level)
    except (OSError, subprocess.SubprocessError):
        return ToolResult(success=False, error=NO_BRIGHTNESS)
    data = {"command": name, "done": f"Helligkeit auf {level} Prozent gestellt", "brightness": level}
    if level == MIN_BRIGHTNESS:
        data["note"] = f"Weiter als {MIN_BRIGHTNESS} Prozent dimmt Jarvis nicht, damit der Bildschirm nicht schwarz wird."
    return ToolResult(success=True, data=data)


def system_control(command, value=""):
    name = normalize_command(command)
    if name is None:
        return ToolResult(success=False, error="Das verstehe ich nicht als Rechnerbefehl. Möglich sind: stumm, Bildschirm sperren, "
                                               "Desktop zeigen (Fenster minimieren), Helligkeit setzen, heller, dunkler.")
    if not sys.platform.startswith("win"):
        return ToolResult(success=False, error="Diese Befehle funktionieren nur unter Windows.")
    if name.startswith("brightness"):
        return _brightness(name, value)
    try:
        if name == "mute":
            _press((VK_VOLUME_MUTE,))
        elif name == "show_desktop":
            _press((VK_LWIN, VK_D))
        else:
            _lock()
    except Exception as error:
        return ToolResult(success=False, error=f"Der Befehl ließ sich nicht ausführen: {error}")
    data = {"command": name, "done": DONE[name]}
    if name == "mute":
        data["note"] = "Stumm ist bei Windows ein Umschalter: War der Ton an, ist er jetzt aus, sonst wieder an. Jarvis kann nicht sehen, was gerade gilt."
    if name == "show_desktop":
        data["note"] = "Derselbe Befehl bringt die Fenster auch wieder zurück."
    return ToolResult(success=True, data=data)


def describe(command, value=""):
    """Zeilen fuer die Rueckfrage."""
    name = normalize_command(command)
    text = {
        "mute": "Ton stumm schalten bzw. wieder einschalten",
        "lock": "Den Bildschirm sperren; zum Entsperren brauchst du dein Passwort",
        "show_desktop": "Alle Fenster minimieren (Windows+D)",
        "brightness_up": f"Bildschirm um {STEP} Prozent heller",
        "brightness_down": f"Bildschirm um {STEP} Prozent dunkler",
    }.get(name)
    if name == "brightness_set":
        level = parse_percent(value)
        text = f"Helligkeit auf {level} Prozent" if level is not None else "Helligkeit ändern"
    return [text or "Rechnerbefehl", "Nichts wird geschlossen oder gelöscht."]
