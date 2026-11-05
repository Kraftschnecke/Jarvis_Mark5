"""Musiksteuerung ueber die Medientasten von Windows (Mark 5, Step 2.21).

Das ist dieselbe Taste wie auf der Tastatur: Play/Pause, Naechster Titel, Vorheriger Titel.
Sie wirkt auf das Programm, das Windows gerade als "aktiven Player" fuehrt (Spotify, Browser, VLC ...).
Es braucht kein Konto, kein Passwort und kein Netz. Jarvis kann damit nichts oeffnen und keinen
bestimmten Titel waehlen: Er drueckt nur die Taste.

Wichtig: "Play" und "Pause" sind bei Windows EINE Taste (Umschalter). Jarvis kann nicht wissen,
ob gerade etwas spielt, und sagt das auch so.
"""

import sys

from tools.tool_result import ToolResult

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

# Erlaubte Befehle -> (Taste, Beschreibung fuer die Antwort). Mehr gibt es nicht.
COMMANDS = {
    "play_pause": (VK_MEDIA_PLAY_PAUSE, "Play/Pause gedrückt"),
    "next": (VK_MEDIA_NEXT_TRACK, "nächster Titel"),
    "previous": (VK_MEDIA_PREV_TRACK, "vorheriger Titel"),
}

# Woerter, die das Sprachmodell statt der festen Namen schreiben kann
ALIASES = {
    "play": "play_pause", "pause": "play_pause", "toggle": "play_pause", "playpause": "play_pause",
    "play/pause": "play_pause", "play-pause": "play_pause", "resume": "play_pause", "stop": "play_pause",
    "weiter": "play_pause", "pausieren": "play_pause", "abspielen": "play_pause", "start": "play_pause",
    "next": "next", "skip": "next", "naechster": "next", "nächster": "next", "vor": "next", "next track": "next",
    "previous": "previous", "prev": "previous", "back": "previous", "zurueck": "previous", "zurück": "previous",
    "vorheriger": "previous", "previous track": "previous",
}


def normalize_command(raw):
    """Gibt den festen Befehlsnamen zurueck oder None."""
    if not isinstance(raw, str):
        return None
    word = raw.strip().casefold().replace("_", " ").replace("  ", " ")
    key = word.replace(" ", "_")
    if key in COMMANDS:
        return key
    return ALIASES.get(word) or ALIASES.get(key)


def _press(virtual_key):
    """Drueckt und loest eine Taste (nur Windows). Wird in Tests ersetzt."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)


def media_control(command):
    name = normalize_command(command)

    if name is None:
        return ToolResult(
            success=False,
            error="Das verstehe ich nicht als Musikbefehl. Möglich sind: abspielen/pausieren, nächster Titel, vorheriger Titel."
        )

    if not sys.platform.startswith("win"):
        return ToolResult(success=False, error="Die Musiksteuerung funktioniert nur unter Windows.")

    key, description = COMMANDS[name]

    try:
        _press(key)
    except Exception as error:
        return ToolResult(success=False, error=f"Die Medientaste ließ sich nicht senden: {error}")

    data = {"command": name, "done": description}
    if name == "play_pause":
        data["note"] = "Play und Pause sind bei Windows dieselbe Taste: War Musik an, ist sie jetzt pausiert, sonst läuft sie. Jarvis kann nicht sehen, was gerade spielt."

    return ToolResult(success=True, data=data)
