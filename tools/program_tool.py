import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

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


# ---- Installierte Programme aus dem Startmenue (Get-StartApps): damit "Apple Music" & Co. ohne Eintrag in programs.json gehen.
# Gestartet wird ueber "shell:AppsFolder\\<AppID>" (das gleiche, was ein Klick im Startmenue tut; geht auch bei Store-Apps).
# Nicht dabei: Eingabeaufforderung, PowerShell, Terminal, Registrierungs-Editor und Deinstallationsprogramme.
START_APPS_TTL = 300          # Sekunden, die die Liste gemerkt wird
START_APPS_RETRY = 20         # so frueh darf ein Fehltreffer die Liste neu lesen (z. B. nach einer Installation)
START_APPS_TIMEOUT = 25
MAX_START_APPS = 600
APP_PREFIX = "shell:AppsFolder\\"
_APPID = re.compile(r"[A-Za-z0-9._!{}()\\ :-]{1,300}")
_BLOCKED = ("powershell", "cmd.exe", "eingabeaufforderung", "command prompt", "terminal", "regedit", "registrierungs", "registry editor",
            "uninstall", "deinstall", "windows.systemcontrol", "wscript", "cscript", "mshta")
_start_apps_cache = {"time": None, "apps": {}}


def _read_start_apps():
    """Liest (Name, AppID) aus dem Startmenue (nur Windows). Wird in Tests ersetzt."""
    if not sys.platform.startswith("win"):
        return []
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=START_APPS_TIMEOUT,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        return []
    data = json.loads((done.stdout or b"").decode("utf-8", errors="ignore").strip() or "[]")
    if isinstance(data, dict):
        data = [data]
    return [(item.get("Name"), item.get("AppID")) for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _usable_app(name, app_id):
    if not isinstance(name, str) or not isinstance(app_id, str):
        return False
    name, app_id = name.strip(), app_id.strip()
    if not 1 <= len(name) <= 100 or not _APPID.fullmatch(app_id):
        return False
    low = (name + " " + app_id).casefold()
    return not any(word in low for word in _BLOCKED)


def start_apps(force=False, clock=time.monotonic):
    """{name klein: "shell:AppsFolder\\AppID"} der installierten Programme. Fehler beim Lesen: leere Liste, kein Absturz."""
    now = clock()
    cached = _start_apps_cache
    if not force and cached["time"] is not None and now - cached["time"] < START_APPS_TTL:
        return cached["apps"]
    try:
        raw = _read_start_apps()
    except Exception:
        raw = []
    apps = {}
    for name, app_id in raw[:MAX_START_APPS]:
        if _usable_app(name, app_id):
            apps.setdefault(" ".join(name.split()).casefold(), APP_PREFIX + app_id.strip())
    cached["time"], cached["apps"] = now, apps
    return apps


def _from_start_apps(name, clock=time.monotonic):
    """Treffer im Startmenue: genau ein Name, sonst eindeutiger Teilname, sonst ValueError mit Auswahl; None = nichts gefunden."""
    name = " ".join(str(name).split())
    if any(word in name for word in _BLOCKED) or name in ("cmd", "ps", "pwsh", "shell"):
        return None                                      # Kommandozeilen nie ueber den Namen anbieten
    for attempt in (0, 1):
        apps = start_apps(force=attempt == 1, clock=clock)
        if name in apps:
            return apps[name]
        if len(name) >= MIN_PARTIAL_MATCH_LENGTH:
            matches = sorted(key for key in apps if name in key)
            if len(matches) == 1:
                return apps[matches[0]]
            if len(matches) > 1:
                starting = [key for key in matches if key.startswith(name)]
                if len(starting) == 1:
                    return apps[starting[0]]
                raise ValueError(f"Mehrere Programme passen zu '{name}': {', '.join(matches[:6])}")
        age = clock() - (_start_apps_cache["time"] or 0)
        if attempt == 0 and age < START_APPS_RETRY:
            break                                        # gerade erst gelesen: nicht nochmal
    return None


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

    found = _from_start_apps(name)       # zuletzt: installierte Programme aus dem Startmenue

    if found:
        return found

    raise FileNotFoundError(
        f"Program not found: {program}. "
        f"Es steht weder im Startmenü noch in programs.json."
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

    Freigegeben ist, was in programs.json steht, ein eingebautes
    Windows-Programm ist oder im Startmenue installiert ist (ohne Shells,
    Registry-Editor und Deinstallationsprogramme). Diese Pruefung steckt bewusst hier und nicht nur
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
                + list(start_apps().values())
            )
        }
    except ValueError as error:
        return ToolResult(success=False, error=str(error))

    if not isinstance(target, str) or _normalize(target) not in allowed:
        return ToolResult(
            success=False,
            error=(
                "Dieses Programm ist nicht freigegeben. "
                "Es muss im Startmenü installiert oder in programs.json eingetragen sein."
            )
        )

    try:
        os.startfile(target)
        return ToolResult(success=True, data=target)
    except Exception as error:
        return ToolResult(success=False, error=str(error))
