"""Freigegebene Ordner (Mark 5, Step 2.14): Jarvis liest Dateien nur in Ordnern, die der Besitzer eingetragen hat.

Die Liste steht in folders.json (nicht in Git) und wird nur in den Einstellungen gepflegt: Es gibt bewusst KEINE
Aufgabe im Chat, die einen Ordner hinzufuegt, sonst koennte ein Dokument oder eine Webseite Jarvis dazu bringen,
die Freigabe zu erweitern. Alle spaeteren Datei-Faehigkeiten (Suchen, Lesen, Notizen schreiben) holen sich ihren
Pfad ueber `FolderList.resolve()`: Das ist die einzige Stelle, die entscheidet, ob ein Pfad erlaubt ist.

Was `resolve()` prueft:
  - der Pfad wird mit realpath aufgeloest (".." und Symlinks/Junctions werden verfolgt): Was am Ende ausserhalb
    der Freigabe landet, wird abgelehnt, auch wenn der Name innerhalb liegt;
  - "gleicher Anfang" reicht nicht ("docs2" liegt nicht in "docs"); verglichen wird Pfadteil fuer Pfadteil;
  - unter Windows: keine Datenstroeme ("datei.txt:strom"), keine Geraetenamen (CON, NUL, ...), keine
    Netzwerkpfade (\\\\server\\freigabe) und keine Adressen (https://...);
  - geschuetzt bleibt auch innerhalb einer Freigabe: Jarvis' eigener Ordner (.env, settings.json), .ssh, .aws,
    .gnupg, .git, Schluesseldateien (*.pem, *.key, ...) und .env-Dateien.
Ein abgelehnter Pfad wird ohne Rueckfrage abgelehnt, und die Meldung verraet nicht, ob er existiert.
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path

from config import FOLDERS_FILE

MAX_FOLDERS = 10
MAX_PATH_LENGTH = 400
PROJECT_DIR = Path(__file__).resolve().parent

_IS_WINDOWS = os.name == "nt"
_normcase = os.path.normcase                       # Windows: Gross-/Kleinschreibung egal (in Tests ersetzbar)
_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(//|\\\\)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DEVICE_NAMES = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
SENSITIVE_DIRS = {".ssh", ".aws", ".gnupg", ".git", ".azure", ".kube", ".docker"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".kdbx", ".ppk"}
SENSITIVE_PREFIXES = (".env", "id_rsa", "id_ed25519", "id_ecdsa")
SKIP_DIRS = {"node_modules", "__pycache__", "$recycle.bin", "system volume information", "venv", "site-packages"}


class AccessError(ValueError):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen darf."""


def _real(path):
    return os.path.realpath(path)


def _same_or_inside(child, root):
    """Pfadteil fuer Pfadteil: /a/docs2 liegt nicht in /a/docs."""
    child, root = _normcase(child), _normcase(root)
    try:
        return os.path.commonpath([child, root]) == root
    except ValueError:                              # verschiedene Laufwerke
        return False


def _is_protected(real_path, project_dir):
    if _same_or_inside(real_path, _real(project_dir)):
        return True
    parts = [p.casefold() for p in Path(real_path).parts]
    if any(p in SENSITIVE_DIRS for p in parts):
        return True
    name = Path(real_path).name.casefold()
    return name.startswith(SENSITIVE_PREFIXES) or Path(name).suffix in SENSITIVE_SUFFIXES


def _basic_checks(raw, what):
    """Gemeinsame Pruefung fuer Ordner und Dateipfade: Text, keine Adresse, kein Netzwerkpfad, Windows-Fallen."""
    if not isinstance(raw, str) or not raw.strip():
        raise AccessError(f"Es wurde kein {what} angegeben.")
    text = raw.strip()
    if len(text) > MAX_PATH_LENGTH or _CONTROL.search(text):
        raise AccessError(f"Dieser {what} ist nicht gültig.")
    if _URI.match(text) or text.startswith(("\\\\", "//")):
        raise AccessError("Ich lese nur lokale Ordner und Dateien, keine Web- oder Netzwerkadressen.")
    if _IS_WINDOWS:
        if ":" in text[2:] or (len(text) > 1 and text[1] == ":" and not text[0].isalpha()):
            raise AccessError(f"Dieser {what} ist nicht gültig (Datenströme mit „:“ sind nicht erlaubt).")
        for part in re.split(r"[\\/]+", text):
            stem = part.rstrip(" .").split(".")[0].casefold()
            if stem in _DEVICE_NAMES:
                raise AccessError(f"Dieser {what} ist nicht gültig (reservierter Name).")
    return text


class FolderList:
    def __init__(self, path=FOLDERS_FILE, project_dir=PROJECT_DIR, home=None, system_dirs=None):
        self.path = Path(path)
        self.project_dir = Path(project_dir)
        self._home = home
        self._system_dirs = system_dirs
        self._lock = threading.Lock()

    # --- Ablage --------------------------------------------------------
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("folders") if isinstance(data, dict) else None
        return [p for p in items if isinstance(p, str)][:MAX_FOLDERS] if isinstance(items, list) else []

    def _save(self, folders):
        handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"folders": folders}, stream, ensure_ascii=False, indent=2)
            os.replace(temp, self.path)
        except OSError as error:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise AccessError("Die Liste konnte nicht gespeichert werden.") from error

    # --- Ordner pruefen ------------------------------------------------
    def _too_broad(self, real):
        home = _real(self._home if self._home is not None else os.path.expanduser("~"))
        if Path(real).parent == Path(real):                  # Wurzel eines Laufwerks
            return "Ein ganzes Laufwerk ist zu groß. Nimm einen Ordner darin, zum Beispiel Dokumente."
        if _same_or_inside(home, real):
            return "Dein ganzer Benutzerordner (oder ein Ordner darüber) ist zu groß. Nimm einen Unterordner wie Dokumente."
        system = self._system_dirs if self._system_dirs is not None else self._default_system_dirs()
        if any(_same_or_inside(real, _real(d)) or _same_or_inside(_real(d), real) for d in system):
            return "Systemordner gebe ich nicht frei."
        return None

    @staticmethod
    def _default_system_dirs():
        if _IS_WINDOWS:
            names = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")
            return [os.environ[n] for n in names if os.environ.get(n)]
        return ["/etc", "/usr", "/bin", "/sbin", "/lib", "/var", "/proc", "/sys", "/dev", "/boot", "/root"]

    def validate_folder(self, raw):
        """Prueft einen Ordner fuer die Freigabe. Gibt den aufgeloesten Pfad zurueck oder wirft AccessError."""
        text = _basic_checks(raw, "Ordner")
        expanded = os.path.expanduser(text)
        if not os.path.isabs(expanded):
            raise AccessError("Bitte den vollständigen Pfad angeben, zum Beispiel C:\\Users\\du\\Documents.")
        real = _real(expanded)
        if not os.path.isdir(real):
            raise AccessError("Diesen Ordner gibt es nicht (oder es ist eine Datei).")
        if _is_protected(real, self.project_dir):
            raise AccessError("Dieser Ordner ist geschützt (Jarvis' eigener Ordner, Schlüssel und Zugangsdaten).")
        problem = self._too_broad(real)
        if problem:
            raise AccessError(problem)
        return real

    # --- Liste pflegen -------------------------------------------------
    def add(self, raw):
        real = self.validate_folder(raw)
        with self._lock:
            folders = self._load()
            if any(_normcase(_real(f)) == _normcase(real) for f in folders):
                raise AccessError("Dieser Ordner ist schon freigegeben.")
            if len(folders) >= MAX_FOLDERS:
                raise AccessError(f"Es sind höchstens {MAX_FOLDERS} Ordner möglich. Entferne zuerst einen.")
            folders.append(real)
            self._save(folders)
        return self.list()

    def remove(self, raw):
        if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_PATH_LENGTH:
            raise AccessError("Es wurde kein Ordner angegeben.")
        wanted = _normcase(raw.strip())
        with self._lock:
            folders = self._load()
            keep = [f for f in folders if _normcase(f) != wanted and _normcase(_real(f)) != _normcase(_real(raw.strip()))]
            if len(keep) == len(folders):
                raise AccessError("Dieser Ordner ist nicht in der Liste.")
            self._save(keep)
        return self.list()

    def list(self):
        """Fuer die Anzeige: [{"path", "exists"}]."""
        with self._lock:
            folders = self._load()
        return [{"path": f, "exists": os.path.isdir(f)} for f in folders]

    def roots(self):
        """Die Ordner, die jetzt wirklich gelten: noch vorhanden und weiterhin erlaubt (neu aufgeloest)."""
        roots = []
        with self._lock:
            folders = self._load()
        for folder in folders:
            try:
                roots.append(self.validate_folder(folder))
            except AccessError:
                continue                            # geloescht, ersetzt oder inzwischen nicht mehr erlaubt
        return roots

    def walk(self, should_stop=None):
        """Alle Dateien, die Jarvis sehen darf: Generator von (aufgeloester Pfad, Freigabe, relativer Pfad).

        Gleiche Regeln wie `resolve()`: Jede Datei und jeder Unterordner wird aufgeloest und muss in derselben
        Freigabe bleiben (Symlinks/Junctions nach draussen werden uebersprungen, nicht betreten); geschuetzte
        Dateien und Ordner fehlen; versteckte Eintraege (Name beginnt mit ".") und Muell-/Bibliotheksordner auch.
        Dieselbe Datei kommt nur einmal. `should_stop()` kann die Suche zwischendurch beenden.
        """
        seen = set()
        for root in self.roots():
            for current, dirs, files in os.walk(root, followlinks=False, onerror=lambda error: None):
                if should_stop is not None and should_stop():
                    return
                keep = []
                for name in dirs:
                    if name.startswith(".") or name.casefold() in SKIP_DIRS:
                        continue
                    real = _real(os.path.join(current, name))
                    if _same_or_inside(real, root) and not _is_protected(real, self.project_dir):
                        keep.append(name)
                dirs[:] = keep
                for name in files:
                    if name.startswith("."):
                        continue
                    if should_stop is not None and should_stop():
                        return
                    real = _real(os.path.join(current, name))
                    key = _normcase(real)
                    if key in seen or not _same_or_inside(real, root) or _is_protected(real, self.project_dir):
                        continue
                    seen.add(key)
                    yield real, root, os.path.relpath(real, root)

    # --- Der Zugriff ---------------------------------------------------
    def resolve(self, raw, must_exist=True):
        """Der einzige Weg zu einem lesbaren Pfad: gibt den aufgeloesten Pfad (str) zurueck oder wirft AccessError.

        Absolute Pfade muessen in einer Freigabe liegen. Relative Pfade ("Notizen/liste.txt") werden der Reihe nach
        in jedem freigegebenen Ordner gesucht. must_exist=False erlaubt einen noch nicht vorhandenen Pfad
        (zum Schreiben), er muss trotzdem innerhalb liegen und sein Elternordner muss existieren.
        """
        text = _basic_checks(raw, "Pfad")
        roots = self.roots()
        if not roots:
            raise AccessError("Es ist noch kein Ordner freigegeben. Trage Ordner in den Einstellungen unter „Folders“ ein.")
        expanded = os.path.expanduser(text)
        candidates = [expanded] if os.path.isabs(expanded) else [os.path.join(root, expanded) for root in roots]
        refused = AccessError("Dieser Pfad liegt nicht in einem freigegebenen Ordner.")
        for candidate in candidates:
            real = _real(candidate)
            if not any(_same_or_inside(real, root) for root in roots):
                continue
            if _is_protected(real, self.project_dir):
                raise AccessError("Diese Datei ist geschützt (Schlüssel und Zugangsdaten lese ich nie).")
            if os.path.exists(real) or (not must_exist and os.path.isdir(os.path.dirname(real))):
                return real
            refused = AccessError("Diese Datei oder diesen Ordner gibt es nicht.")
        raise refused


_default = None


def default_list():
    global _default
    if _default is None:
        _default = FolderList()
    return _default


def set_default_list(folder_list):
    global _default
    _default = folder_list
