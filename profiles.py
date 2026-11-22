"""Bereiche (Mark 5, Schritt C1): getrennte Daten fuer Gaeste, die Jarvis ueber Remote testen. Siehe DESIGN_CLIENT.md.

Der Besitzer ("owner") ist kein gespeicherter Bereich: Er hat alles wie bisher. Ein Gast-Bereich hat einen Namen,
eigene Limits (die der Besitzer einstellt) und einen eigenen Ordner `profiles/<id>/` fuer seine Daten (kommt in C2).
Reine Logik ohne Netz. Die Ordnerpfade entstehen nur aus einer geprueften Nummer, nie aus Eingaben.
"""
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path

OWNER = "owner"
PROFILES_FILE = Path(__file__).resolve().parent / "profiles.json"
PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

MAX_PROFILES = 5
MAX_NAME_LENGTH = 30
ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")
DEFAULT_LIMITS = {"ai_per_day": 100, "messages_per_10min": 20}       # 0 = unbegrenzt
MAX_LIMIT = 100000


class ProfileError(ValueError):
    """Eine Eingabe des Besitzers ist ungueltig (die Meldung steht fuer ihn da)."""


def clean_profile_name(name):
    if not isinstance(name, str):
        return ""
    text = " ".join(name.split())
    return "".join(ch for ch in text if ch.isprintable())[:MAX_NAME_LENGTH].strip()


def clean_limit(value):
    """Ganze Zahl von 0 bis MAX_LIMIT, sonst ProfileError. Wahrheitswerte und Kommazahlen zaehlen nicht."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > MAX_LIMIT:
        raise ProfileError(f"Ein Limit ist eine ganze Zahl von 0 bis {MAX_LIMIT} (0 = unbegrenzt).")
    return value


def is_profile_id(value):
    return isinstance(value, str) and ID_PATTERN.match(value) is not None


class ProfileStore:
    def __init__(self, path=PROFILES_FILE, data_dir=PROFILES_DIR, clock=time.time, id_factory=None):
        self.path = Path(path)
        self.data_dir = Path(data_dir)
        self.clock = clock
        self.id_factory = id_factory or (lambda: secrets.token_hex(4))
        self._lock = threading.Lock()
        self._profiles = self._load()
        self._epochs = {}          # wird bei "Zaehler zuruecksetzen" erhoeht: die Gast-Seite leert dann auch ihr 10-Minuten-Fenster

    # --- Datei ---------------------------------------------------------
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            try:
                os.replace(self.path, self.path.with_suffix(self.path.suffix + ".defekt"))
            except OSError:
                pass
            return []
        profiles = []
        seen = set()
        for item in data.get("profiles", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict) or not is_profile_id(item.get("id")) or item["id"] in seen:
                continue
            name = clean_profile_name(item.get("name"))
            if not name:
                continue
            limits = dict(DEFAULT_LIMITS)
            stored = item.get("limits") if isinstance(item.get("limits"), dict) else {}
            for key in DEFAULT_LIMITS:
                try:
                    limits[key] = clean_limit(stored[key]) if key in stored else limits[key]
                except ProfileError:
                    pass
            created = item.get("created")
            profiles.append({"id": item["id"], "name": name, "limits": limits,
                             "created": float(created) if isinstance(created, (int, float)) and not isinstance(created, bool) else 0.0})
            seen.add(item["id"])
        return profiles

    def _save(self):
        payload = json.dumps({"version": 1, "profiles": self._profiles}, ensure_ascii=False, indent=2)
        handle, temp_path = tempfile.mkstemp(dir=str(self.path.parent), prefix=".profiles_", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(payload)
            os.replace(temp_path, self.path)
        except OSError:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    # --- Lesen -----------------------------------------------------------
    def list(self):
        with self._lock:
            return [_copy(p) for p in self._profiles]

    def get(self, profile_id):
        with self._lock:
            return next((_copy(p) for p in self._profiles if p["id"] == profile_id), None)

    def exists(self, profile_id):
        """True fuer den Besitzer und fuer jeden angelegten Bereich."""
        return profile_id == OWNER or self.get(profile_id) is not None

    def path_for(self, profile_id):
        """Der Datenordner eines Bereichs. Nur fuer angelegte Bereiche, sonst ProfileError. Wird nicht angelegt."""
        if self.get(profile_id) is None:
            raise ProfileError("Diesen Bereich gibt es nicht.")
        return self.data_dir / profile_id

    # --- Aendern (nur der Besitzer am PC) ------------------------------------
    def create(self, name):
        cleaned = clean_profile_name(name)
        if not cleaned:
            raise ProfileError("Bitte einen Namen für den Bereich angeben.")
        with self._lock:
            if len(self._profiles) >= MAX_PROFILES:
                raise ProfileError(f"Höchstens {MAX_PROFILES} Gast-Bereiche.")
            if any(p["name"].casefold() == cleaned.casefold() for p in self._profiles):
                raise ProfileError(f"Einen Bereich „{cleaned}“ gibt es schon.")
            profile_id = self.id_factory()
            while any(p["id"] == profile_id for p in self._profiles):
                profile_id = self.id_factory()
            profile = {"id": profile_id, "name": cleaned, "limits": dict(DEFAULT_LIMITS), "created": self.clock()}
            self._profiles.append(profile)
            try:
                self._save()
            except OSError:
                self._profiles.remove(profile)
                raise
            return _copy(profile)

    def set_limits(self, profile_id, **limits):
        """Limits setzen (ai_per_day, messages_per_10min). Unbekannte Namen und ungueltige Werte werden abgelehnt, nichts wird halb geaendert."""
        checked = {}
        for key, value in limits.items():
            if key not in DEFAULT_LIMITS:
                raise ProfileError("Unbekanntes Limit.")
            checked[key] = clean_limit(value)
        with self._lock:
            profile = next((p for p in self._profiles if p["id"] == profile_id), None)
            if profile is None:
                raise KeyError(profile_id)
            before = dict(profile["limits"])
            profile["limits"].update(checked)
            try:
                self._save()
            except OSError:
                profile["limits"] = before
                raise
            return _copy(profile)

    def delete(self, profile_id):
        """Bereich und alle seine Daten entfernen. False, wenn es ihn nicht gibt."""
        with self._lock:
            profile = next((p for p in self._profiles if p["id"] == profile_id), None)
            if profile is None:
                return False
            self._profiles.remove(profile)
            try:
                self._save()
            except OSError:
                self._profiles.append(profile)
                raise
        self._remove_data(profile_id)
        return True

    def reset_data(self, profile_id):
        """Alle Daten eines Bereichs loeschen, den Bereich selbst behalten (sauberer Neustart fuer den naechsten Testlauf)."""
        if self.get(profile_id) is None:
            return False
        self._remove_data(profile_id)
        self._bump(profile_id)
        return True

    def reset_usage(self, profile_id):
        """Nur die Zaehler (KI-Aufrufe heute, Nachrichten in den letzten 10 Minuten) auf null: der Gast kann sofort weitertesten."""
        if self.get(profile_id) is None:
            return False
        try:
            (self.data_dir / profile_id / "usage.json").unlink()
        except FileNotFoundError:
            pass
        self._bump(profile_id)
        return True

    def epoch(self, profile_id):
        with self._lock:
            return self._epochs.get(profile_id, 0)

    def _bump(self, profile_id):
        with self._lock:
            self._epochs[profile_id] = self._epochs.get(profile_id, 0) + 1

    def _remove_data(self, profile_id):
        if not is_profile_id(profile_id):
            return
        target = self.data_dir / profile_id
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)


def _copy(profile):
    return {"id": profile["id"], "name": profile["name"], "created": profile["created"], "limits": dict(profile["limits"])}
