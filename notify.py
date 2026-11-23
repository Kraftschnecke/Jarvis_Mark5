"""Push aufs Handy (Mark 5, Server S3): kleine Nachrichten ueber ntfy.

ntfy ist eine kostenlose App (iPhone/Android). Jarvis schickt eine Web-Anfrage an einen "Themennamen"; wer die App auf genau
diesen Namen abonniert hat, bekommt die Nachricht. Der Themenname ist das Passwort: wer ihn kennt, kann mitlesen und
Nachrichten schicken. Deshalb: lang und zufaellig (mindestens 16 Zeichen) und nirgends weitergeben.

Sicherheit:
  - Ohne Themennamen ist alles aus (Voreinstellung): es geht nichts ins Netz.
  - Nur https (Ausnahme: der eigene Rechner, damit sich ein eigener ntfy-Server testen laesst).
  - Hoechstens MAX_PER_HOUR Nachrichten pro Stunde: ein Fehler (Schleife) kann das Handy nicht zumuellen.
  - Ein Fehler beim Senden wird nie weitergereicht und steht nie mit Themennamen oder Schluessel im Terminal.
  - Gesendet wird nur Text, den Jarvis selbst gebaut hat (Erinnerung, Wecker, Hinweis), nie Schluessel oder Dateien.
"""

import json
import re
import time
import urllib.error
import urllib.request
from collections import deque
from urllib.parse import urlparse

DEFAULT_SERVER = "https://ntfy.sh"
MIN_TOPIC_LENGTH = 16
MAX_TITLE = 60
MAX_TEXT = 500
MAX_PER_HOUR = 30
TIMEOUT_SECONDS = 10
PRIORITIES = {"low": 2, "default": 3, "high": 4, "urgent": 5}
_TOPIC = re.compile(r"[A-Za-z0-9_-]+")
_LOCAL_HOSTS = ("localhost", "127.0.0.1")


def valid_topic(topic):
    return isinstance(topic, str) and len(topic) >= MIN_TOPIC_LENGTH and len(topic) <= 64 and _TOPIC.fullmatch(topic) is not None


def valid_server(server):
    """https://… (oder http nur fuer den eigenen Rechner), ohne Zugangsdaten und ohne Pfad."""
    try:
        parts = urlparse(server)
        host = parts.hostname
        parts.port                                      # wirft bei ungueltigem Port
    except (ValueError, AttributeError):
        return False
    if not host or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and host in _LOCAL_HOSTS)


def _clean(text, limit):
    text = "".join(ch if ch.isprintable() or ch == "\n" else " " for ch in str(text or "")).strip()
    return text[:limit]


class Notifier:
    def __init__(self, topic="", server=DEFAULT_SERVER, token="", post=None, clock=time.monotonic):
        self.topic = topic if valid_topic(topic) else ""
        self.server = server.rstrip("/") if valid_server(server) else ""
        self.token = token if isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", token or "") else ""
        self.post = post or self._post
        self.clock = clock
        self._sent = deque()
        self._warned = False

    @property
    def enabled(self):
        return bool(self.topic and self.server)

    def _post(self, url, body, headers):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:
            return answer.status

    def _allowed(self):
        now = self.clock()
        while self._sent and now - self._sent[0] >= 3600:
            self._sent.popleft()
        if len(self._sent) >= MAX_PER_HOUR:
            if not self._warned:
                print(f"[PUSH] Mehr als {MAX_PER_HOUR} Nachrichten in einer Stunde: weitere werden verworfen.")
                self._warned = True
            return False
        self._warned = False
        self._sent.append(now)
        return True

    def send(self, title, text, priority="default"):
        """Schickt eine Nachricht. True nur, wenn ntfy sie angenommen hat. Wirft nie."""
        if not self.enabled:
            return False
        message = _clean(text, MAX_TEXT)
        if not message or not self._allowed():
            return False
        payload = {"topic": self.topic, "title": _clean(title, MAX_TITLE) or "Jarvis", "message": message,
                   "priority": PRIORITIES.get(priority, PRIORITIES["default"])}
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            status = self.post(self.server, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers)
        except urllib.error.HTTPError as error:
            print(f"[PUSH] ntfy hat abgelehnt (HTTP {error.code}).")
            return False
        except Exception as error:
            print(f"[PUSH] Senden fehlgeschlagen: {type(error).__name__}")
            return False
        return isinstance(status, int) and 200 <= status < 300


def from_config():
    import config
    return Notifier(config.NTFY_TOPIC, config.NTFY_SERVER or DEFAULT_SERVER, config.NTFY_TOKEN)


_default = None


def default_notifier():
    global _default
    if _default is None:
        _default = from_config()
    return _default


def set_default_notifier(notifier):
    """Nur fuer Tests."""
    global _default
    _default = notifier
