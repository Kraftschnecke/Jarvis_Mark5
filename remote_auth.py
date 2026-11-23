"""Remote-Geraete (Mark 5, Remote R1): Kopplung, Token, Sperren, Grenzen. Siehe DESIGN_REMOTE.md.

Reine Logik ohne Netz und ohne Server. Wichtig:
- Ein Token wird nur als Hash gespeichert (wie ein Passwort). Das Klartext-Token sieht nur das Handy.
- Ein Kopplungscode gilt 5 Minuten und genau einmal. Er liegt nur im Speicher.
- Nach zu vielen falschen Codes von derselben Quelle ist die Kopplung kurz gesperrt.
- Alles Zeitliche kommt ueber eine Uhr, die sich in Tests ersetzen laesst.
- Vollzugriff (Server-Betrieb, DESIGN_SERVER.md): Ein Geraet mit full=True darf wie der PC selbst arbeiten. Diesen Code gibt es
  nur ueber ``create_pairing(..., full=True)`` (Aufruf im Server-Terminal: ``server_main.py --pair-owner``), nie ueber die Weboberflaeche.
  Der Code liegt zusaetzlich (nur als Hash) in einer Datei neben remote_devices.json, weil das Terminal ein eigener Prozess ist.
"""
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from profiles import OWNER, is_profile_id

DEVICES_FILE = Path(__file__).resolve().parent / "remote_devices.json"
FULL_PENDING_NAME = "remote_pending_full.json"     # neben remote_devices.json: offene Kopplungen mit Vollzugriff (nur Hashes)

PAIRING_TTL = 300                    # Sekunden, die ein Kopplungscode gilt
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"    # ohne I, L, O, 0, 1: nichts, was man verwechseln kann
CODE_LENGTH = 8                                       # 31^8 sind rund 850 Milliarden Moeglichkeiten; dazu die Sperre nach Fehlversuchen
MAX_PENDING = 5                      # so viele offene Kopplungen gleichzeitig
TOKEN_LIFETIME = 90 * 24 * 3600      # wird bei Benutzung verlaengert
LAST_SEEN_WRITE_INTERVAL = 60        # nicht bei jeder Anfrage in die Datei schreiben
MAX_FAILURES = 5                     # falsche Codes ...
FAILURE_WINDOW = 900                 # ... innerhalb dieser Sekunden ...
LOCK_SECONDS = 900                   # ... sperren die Kopplung so lange
MAX_NAME_LENGTH = 40


def make_code():
    """Neuer Kurzcode, z. B. "K7M2-QX9P". secrets ist die Zufallsquelle fuer Passwoerter."""
    letters = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return letters[:4] + "-" + letters[4:]


def normalize_code(code):
    """Was getippt wurde, auf die Grundform: Gross, ohne Strich und Leerzeichen. Alles Unpassende ergibt "" (ungueltig)."""
    if not isinstance(code, str) or len(code) > 64:
        return ""
    letters = "".join(char for char in code.upper() if char.isalnum())
    if len(letters) != CODE_LENGTH or any(char not in CODE_ALPHABET for char in letters):
        return ""
    return letters


def hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def clean_device_name(name, default="Gerät"):
    text = " ".join(str(name or "").split())
    text = "".join(ch for ch in text if ch.isprintable())
    return text[:MAX_NAME_LENGTH].strip() or default


class PairingGuard:
    """Zaehlt falsche Kopplungsversuche je Quelle und sperrt nach zu vielen."""

    def __init__(self, clock=time.time, max_failures=MAX_FAILURES, window=FAILURE_WINDOW, lock_seconds=LOCK_SECONDS):
        self.clock = clock
        self.max_failures = max_failures
        self.window = window
        self.lock_seconds = lock_seconds
        self._failures = {}
        self._locked_until = {}

    def locked(self, source):
        until = self._locked_until.get(source)
        if until is None:
            return False
        if self.clock() >= until:
            del self._locked_until[source]
            self._failures.pop(source, None)
            return False
        return True

    def failure(self, source):
        now = self.clock()
        recent = [t for t in self._failures.get(source, []) if now - t < self.window]
        recent.append(now)
        self._failures[source] = recent
        if len(recent) >= self.max_failures:
            self._locked_until[source] = now + self.lock_seconds

    def success(self, source):
        self._failures.pop(source, None)


class DeviceStore:
    def __init__(self, path=DEVICES_FILE, clock=time.time, secret_factory=secrets.token_urlsafe, guard=None, code_factory=make_code):
        self.path = Path(path)
        self.clock = clock
        self.secret_factory = secret_factory
        self.code_factory = code_factory
        self.guard = guard or PairingGuard(clock)
        self._lock = threading.Lock()
        self._pending = {}                 # Code-Hash -> {"name", "expires"}
        self._devices = self._load()

    # --- Datei ---------------------------------------------------------
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            self._set_aside_broken_file()
            return []
        devices = []
        for item in data.get("devices", []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("token_hash"), str):
                devices.append({
                    "id": item["id"], "name": clean_device_name(item.get("name")),
                    "token_hash": item["token_hash"], "created": _number(item.get("created")),
                    "last_seen": _number(item.get("last_seen")), "expires": _number(item.get("expires")),
                    "revoked": item.get("revoked") is True,
                    # Aeltere Geraete haben keinen Bereich und gehoeren dem Besitzer; Unsinn in der Datei zaehlt nie als Gast
                    "profile": item["profile"] if is_profile_id(item.get("profile")) else OWNER,
                })
                # Vollzugriff nur fuer Geraete des Besitzers; Unsinn oder ein Gast-Geraet mit "full" in der Datei zaehlt nie
                devices[-1]["full"] = item.get("full") is True and devices[-1]["profile"] == OWNER
        return devices

    def _set_aside_broken_file(self):
        try:
            os.replace(self.path, self.path.with_suffix(self.path.suffix + ".defekt"))
        except OSError:
            pass

    def _save(self):
        payload = json.dumps({"version": 1, "devices": self._devices}, ensure_ascii=False, indent=2)
        handle, temp_path = tempfile.mkstemp(dir=str(self.path.parent), prefix=".remote_", suffix=".tmp")
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

    # --- Kopplung -------------------------------------------------------
    def create_pairing(self, name, profile=OWNER, full=False):
        """Neuer Kopplungscode fuer ein Geraet des Besitzers oder eines Gast-Bereichs. Gibt {"code", "expires", "name", "profile", "full"} zurueck.

        ``full=True`` (Vollzugriff wie am PC) gibt es nur fuer den Besitzer und wird nur vom Server-Terminal aus verlangt."""
        if profile != OWNER and not is_profile_id(profile):
            raise ValueError("Ungültiger Bereich.")
        if full and profile != OWNER:
            raise ValueError("Vollzugriff gibt es nur für den Besitzer.")
        with self._lock:
            now = self.clock()
            self._pending = {h: p for h, p in self._pending.items() if p["expires"] > now}
            while len(self._pending) >= MAX_PENDING:
                oldest = min(self._pending, key=lambda h: self._pending[h]["expires"])
                del self._pending[oldest]
            code = self.code_factory()
            while normalize_code(code) == "" or hash_token(normalize_code(code)) in self._pending:
                code = self.code_factory()       # ungueltig oder schon vergeben: neu wuerfeln
            expires = now + PAIRING_TTL
            device_name = clean_device_name(name)
            code_hash = hash_token(normalize_code(code))
            self._pending[code_hash] = {"name": device_name, "expires": expires, "profile": profile, "full": full}
            if full:
                self._write_full_pending(code_hash, {"name": device_name, "expires": expires})
            return {"code": code, "expires": expires, "name": device_name, "profile": profile, "full": full}

    # --- offene Kopplungen mit Vollzugriff in einer Datei (das Server-Terminal ist ein eigener Prozess) ---------
    def _full_pending_path(self):
        return self.path.with_name(FULL_PENDING_NAME)

    def _read_full_pending(self):
        try:
            data = json.loads(self._full_pending_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        now = self.clock()
        result = {}
        for code_hash, entry in (data.items() if isinstance(data, dict) else []):
            if (isinstance(code_hash, str) and isinstance(entry, dict) and isinstance(entry.get("name"), str)
                    and isinstance(entry.get("expires"), (int, float)) and not isinstance(entry["expires"], bool) and entry["expires"] > now):
                result[code_hash] = {"name": clean_device_name(entry["name"]), "expires": float(entry["expires"])}
        return result

    def _store_full_pending(self, entries):
        path = self._full_pending_path()
        if not entries:
            try:
                path.unlink()
            except OSError:
                pass
            return
        handle, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".pending_", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(entries, file)
            try:
                os.chmod(temp_path, 0o600)           # nur der Besitzer des Servers darf die Datei lesen
            except OSError:
                pass
            os.replace(temp_path, path)
        except OSError:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _write_full_pending(self, code_hash, entry):
        entries = self._read_full_pending()
        entries[code_hash] = entry
        while len(entries) > MAX_PENDING:
            del entries[min(entries, key=lambda h: entries[h]["expires"])]
        self._store_full_pending(entries)

    def _take_full_pending(self, code_hash):
        """Ein offener Vollzugriff-Code aus der Datei (und dort gleich verbraucht), sonst None."""
        entries = self._read_full_pending()
        entry = entries.pop(code_hash, None)
        if entry is not None or not entries:
            self._store_full_pending(entries)
        return entry

    def redeem(self, code, source=""):
        """Tauscht einen Kopplungscode gegen ein Token. Gibt (status, token, geraet) zurueck.

        status: "ok", "invalid" (falsch, abgelaufen oder schon benutzt) oder "locked" (zu viele Fehlversuche).
        """
        with self._lock:
            if self.guard.locked(source):
                return "locked", None, None
            now = self.clock()
            canonical = normalize_code(code)
            entry = self._pending.pop(hash_token(canonical), None) if canonical else None
            if entry is None and canonical:
                found = self._take_full_pending(hash_token(canonical))         # im Server-Terminal erzeugt
                entry = dict(found, profile=OWNER, full=True) if found is not None else None
            elif entry is not None and entry.get("full"):
                if self._take_full_pending(hash_token(canonical)) is None:     # die Datei-Kopie ist die Wahrheit: schon anderswo benutzt
                    entry = None
            if entry is None or entry["expires"] <= now:
                self.guard.failure(source)
                return "invalid", None, None
            self.guard.success(source)
            device_id = secrets.token_hex(4)
            token = f"{device_id}.{self.secret_factory(32)}"
            device = {"id": device_id, "name": entry["name"], "token_hash": hash_token(token), "created": now,
                      "last_seen": now, "expires": now + TOKEN_LIFETIME, "revoked": False, "profile": entry["profile"],
                      "full": entry.get("full") is True}
            self._devices.append(device)
            try:
                self._save()
            except OSError:
                self._devices.remove(device)        # nicht gespeichert = nicht gekoppelt
                raise
            return "ok", token, _public(device)

    def pending_count(self):
        with self._lock:
            now = self.clock()
            return sum(1 for p in self._pending.values() if p["expires"] > now)

    # --- Anmeldung mit Token ---------------------------------------------
    def authenticate(self, token):
        """Das Geraet zu einem gueltigen Token, sonst None. Verlaengert die Laufzeit bei Benutzung."""
        if not isinstance(token, str) or "." not in token or len(token) > 200:
            return None
        device_id = token.split(".", 1)[0]
        with self._lock:
            device = next((d for d in self._devices if d["id"] == device_id), None)
            expected = device["token_hash"] if device else hash_token("kein-geraet")
            matches = hmac.compare_digest(expected, hash_token(token))
            now = self.clock()
            if device is None or not matches or device["revoked"] or device["expires"] <= now:
                return None
            if now - device["last_seen"] >= LAST_SEEN_WRITE_INTERVAL:
                device["last_seen"] = now
                device["expires"] = now + TOKEN_LIFETIME
                try:
                    self._save()
                except OSError:
                    pass            # eine volle Platte darf die Anmeldung nicht verhindern
            return _public(device)

    # --- Verwaltung (nur am PC) -------------------------------------------
    def devices(self):
        with self._lock:
            return [_public(d) for d in self._devices]

    def revoke(self, device_id):
        with self._lock:
            for device in self._devices:
                if device["id"] == device_id and not device["revoked"]:
                    device["revoked"] = True
                    self._save()
                    return True
            return False

    def restore(self, device_id):
        """Ein gesperrtes Geraet wieder freigeben (nur am PC). Der alte Token gilt wieder, die Laufzeit beginnt neu."""
        with self._lock:
            for device in self._devices:
                if device["id"] == device_id and device["revoked"]:
                    device["revoked"] = False
                    device["expires"] = max(device["expires"], self.clock() + TOKEN_LIFETIME)
                    self._save()
                    return True
            return False

    def remove_profile_devices(self, profile):
        """Alle Geraete eines Gast-Bereichs entfernen (Token weg, Eintrag weg) und seine offenen Kopplungen verwerfen. Gibt die Zahl zurueck."""
        if profile == OWNER:
            return 0
        with self._lock:
            before = len(self._devices)
            self._devices = [d for d in self._devices if d["profile"] != profile]
            self._pending = {h: p for h, p in self._pending.items() if p.get("profile") != profile}
            removed = before - len(self._devices)
            if removed:
                self._save()
            return removed

    def revoke_all(self):
        with self._lock:
            count = 0
            for device in self._devices:
                if not device["revoked"]:
                    device["revoked"] = True
                    count += 1
            self._pending.clear()
            if count:
                self._save()
            return count

    def forget(self, device_id):
        """Eintrag ganz entfernen (nur sinnvoll fuer schon gesperrte Geraete)."""
        with self._lock:
            before = len(self._devices)
            self._devices = [d for d in self._devices if d["id"] != device_id]
            if len(self._devices) != before:
                self._save()
                return True
            return False


class UsageLimits:
    """Optionale Grenzen (DESIGN_REMOTE.md, Abschnitt 6). 0 = unbegrenzt, so ist es voreingestellt."""

    def __init__(self, max_messages=0, window=600, max_daily=0, clock=time.time):
        self.max_messages = max_messages
        self.window = window
        self.max_daily = max_daily
        self.clock = clock
        self._lock = threading.Lock()
        self._messages = {}
        self._day = None
        self._daily = 0

    def allow_message(self, device_id):
        """Zaehlt eine Nachricht und sagt, ob sie erlaubt ist."""
        if self.max_messages <= 0:
            return True
        with self._lock:
            now = self.clock()
            queue = self._messages.setdefault(device_id, deque())
            while queue and now - queue[0] >= self.window:
                queue.popleft()
            if len(queue) >= self.max_messages:
                return False
            queue.append(now)
            return True

    def allow_ai_call(self):
        """Zaehlt einen KI-Aufruf ueber Remote und sagt, ob er heute noch erlaubt ist."""
        if self.max_daily <= 0:
            return True
        with self._lock:
            today = datetime.fromtimestamp(self.clock()).date()
            if today != self._day:
                self._day, self._daily = today, 0
            if self._daily >= self.max_daily:
                return False
            self._daily += 1
            return True


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _public(device):
    """Ohne Hash: das ist alles, was die Seite je zu sehen bekommt."""
    return {key: device[key] for key in ("id", "name", "created", "last_seen", "expires", "revoked", "profile", "full")}
