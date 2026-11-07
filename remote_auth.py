"""Remote-Geraete (Mark 5, Remote R1): Kopplung, Token, Sperren, Grenzen. Siehe DESIGN_REMOTE.md.

Reine Logik ohne Netz und ohne Server. Wichtig:
- Ein Token wird nur als Hash gespeichert (wie ein Passwort). Das Klartext-Token sieht nur das Handy.
- Ein Kopplungscode gilt 5 Minuten und genau einmal. Er liegt nur im Speicher.
- Nach zu vielen falschen Codes von derselben Quelle ist die Kopplung kurz gesperrt.
- Alles Zeitliche kommt ueber eine Uhr, die sich in Tests ersetzen laesst.
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

DEVICES_FILE = Path(__file__).resolve().parent / "remote_devices.json"

PAIRING_TTL = 300                    # Sekunden, die ein Kopplungslink gilt
MAX_PENDING = 5                      # so viele offene Kopplungen gleichzeitig
TOKEN_LIFETIME = 90 * 24 * 3600      # wird bei Benutzung verlaengert
LAST_SEEN_WRITE_INTERVAL = 60        # nicht bei jeder Anfrage in die Datei schreiben
MAX_FAILURES = 5                     # falsche Codes ...
FAILURE_WINDOW = 900                 # ... innerhalb dieser Sekunden ...
LOCK_SECONDS = 900                   # ... sperren die Kopplung so lange
MAX_NAME_LENGTH = 40


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
    def __init__(self, path=DEVICES_FILE, clock=time.time, secret_factory=secrets.token_urlsafe, guard=None):
        self.path = Path(path)
        self.clock = clock
        self.secret_factory = secret_factory
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
                })
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
    def create_pairing(self, name):
        """Neuer Kopplungscode fuer ein Geraet. Gibt {"code", "expires", "name"} zurueck."""
        with self._lock:
            now = self.clock()
            self._pending = {h: p for h, p in self._pending.items() if p["expires"] > now}
            while len(self._pending) >= MAX_PENDING:
                oldest = min(self._pending, key=lambda h: self._pending[h]["expires"])
                del self._pending[oldest]
            code = self.secret_factory(24)
            expires = now + PAIRING_TTL
            device_name = clean_device_name(name)
            self._pending[hash_token(code)] = {"name": device_name, "expires": expires}
            return {"code": code, "expires": expires, "name": device_name}

    def redeem(self, code, source=""):
        """Tauscht einen Kopplungscode gegen ein Token. Gibt (status, token, geraet) zurueck.

        status: "ok", "invalid" (falsch, abgelaufen oder schon benutzt) oder "locked" (zu viele Fehlversuche).
        """
        with self._lock:
            if self.guard.locked(source):
                return "locked", None, None
            now = self.clock()
            entry = self._pending.pop(hash_token(code), None) if isinstance(code, str) and code else None
            if entry is None or entry["expires"] <= now:
                self.guard.failure(source)
                return "invalid", None, None
            self.guard.success(source)
            device_id = secrets.token_hex(4)
            token = f"{device_id}.{self.secret_factory(32)}"
            device = {"id": device_id, "name": entry["name"], "token_hash": hash_token(token), "created": now,
                      "last_seen": now, "expires": now + TOKEN_LIFETIME, "revoked": False}
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
    return {key: device[key] for key in ("id", "name", "created", "last_seen", "expires", "revoked")}
