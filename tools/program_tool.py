import json
import os
import platform
import shutil

from config import PROGRAMS_FILE
from tools.tool_result import ToolResult

# Eingebaute Windows-Programme. Alles andere muss in programs.json stehen.
PROGRAM_ALIASES = {
    "notepad": "notepad.exe",
    "editor": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "vs code": "code",
    "visual studio code": "code",
    "vscode": "code",
    "visualcode": "code"
}

# Erst ab dieser Laenge darf ein Name nur teilweise passen
# ("rainbow" findet "rainbow six siege", "s" findet nichts).
MIN_PARTIAL_MATCH_LENGTH = 3


def load_registered_programs():
    """Liest die Freigabeliste (Name -> Pfad oder URI wie steam://...).

    Fehlt die Datei, ist die Liste leer. Ist sie kaputt, gibt es einen
    verstaendlichen Fehler statt eines Absturzes.
    """
    try:
        text = PROGRAMS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ValueError(f"programs.json konnte nicht gelesen werden: {error}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"programs.json ist kein gueltiges JSON ({error}). "
            f"Tipp: Pfade mit / statt \\ schreiben, z.B. C:/Games/spiel.exe"
        )

    if not isinstance(data, dict):
        raise ValueError(
            "programs.json muss ein Objekt sein: {\"name\": \"pfad\"}"
        )

    return {
        str(name).strip().lower(): str(target).strip()
        for name, target in data.items()
        if str(name).strip() and str(target).strip()
    }


def _normalize(target):
    return os.path.normcase(os.path.normpath(target))


def _builtin_programs():
    """Eingebaute Programme, die es auf diesem Rechner wirklich gibt."""
    found = {}

    for alias, executable in PROGRAM_ALIASES.items():
        path = shutil.which(executable)

        if path:
            found[alias] = path

    return found


def find_program_windows(program):
    name = str(program).strip().lower()

    if not name:
        raise FileNotFoundError("Es wurde kein Programmname angegeben.")

    registered = load_registered_programs()

    if name in registered:
        return registered[name]

    if name in PROGRAM_ALIASES:
        path = shutil.which(PROGRAM_ALIASES[name])

        if path:
            return path

    if len(name) >= MIN_PARTIAL_MATCH_LENGTH:
        matches = sorted(key for key in registered if name in key)

        if len(matches) == 1:
            return registered[matches[0]]

        if len(matches) > 1:
            raise ValueError(
                f"Mehrere Programme passen zu '{program}': "
                f"{', '.join(matches)}"
            )

    raise FileNotFoundError(
        f"Program not found: {program}. "
        f"Es muss in programs.json freigegeben sein."
    )


_remote = None


def set_remote(remote):
    """Server-Betrieb (S6, G6): Programme suchen und starten am PC-Agent; dort gilt die programs.json des PCs. None = dieser Rechner."""
    global _remote
    _remote = remote


def find_program(program):
    if _remote is not None:
        return _remote.call("programs.find", {"program": program[:100] if isinstance(program, str) else ""})
    system = platform.system()

    if system == "Windows":
        try:
            return ToolResult(
                success=True,
                data=find_program_windows(program)
            )
        except (FileNotFoundError, ValueError) as error:
            return ToolResult(
                success=False,
                error=str(error)
            )
    return ToolResult(
        success=False,
        error=f"Unsupported operating system: {system}"
    )


def launch_program(target):
    """Startet ein Programm, aber nur, wenn es freigegeben ist.

    Freigegeben ist, was in programs.json steht oder ein eingebautes
    Windows-Programm ist. Diese Pruefung steckt bewusst hier und nicht nur
    im Task: Egal welchen Pfad das Sprachmodell vorschlaegt, es startet
    nichts, was du nicht freigegeben hast.
    """
    if _remote is not None:
        return _remote.call("programs.launch", {"target": target[:500] if isinstance(target, str) else ""})

    try:
        allowed = {
            _normalize(path)
            for path in (
                list(load_registered_programs().values())
                + list(_builtin_programs().values())
            )
        }
    except ValueError as error:
        return ToolResult(success=False, error=str(error))

    if not isinstance(target, str) or _normalize(target) not in allowed:
        return ToolResult(
            success=False,
            error=(
                "Dieses Programm ist nicht freigegeben. "
                "Trage es in programs.json ein, wenn ich es starten soll."
            )
        )

    try:
        os.startfile(target)
        return ToolResult(success=True, data=target)
    except Exception as error:
        return ToolResult(success=False, error=str(error))
