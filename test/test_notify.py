"""Push aufs Handy (notify.py): nur mit Themennamen, nur https, Begrenzung pro Stunde, Fehler werden nie weitergereicht."""

import io
import json
import sys
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import notify

TOPIC = "jarvis-geheim-12345678"

# Themenname: mindestens 16 Zeichen, nur Buchstaben, Ziffern, - und _
assert notify.valid_topic(TOPIC) and notify.valid_topic("a" * 16) and notify.valid_topic("a" * 64) and notify.valid_topic("A_b-9" * 4)
for bad in ("", "kurz", "a" * 15, "a" * 65, "mit leerzeichen drin!!", "slash/slash/slash/", "umlaut-äöü-12345678", None, 5, ["x" * 20]):
    assert not notify.valid_topic(bad), bad

# Server: https; http nur fuer den eigenen Rechner; keine Zugangsdaten/Pfade
for good in ("https://ntfy.sh", "https://ntfy.sh/", "https://push.example.org:8443", "http://localhost:2586", "http://127.0.0.1"):
    assert notify.valid_server(good), good
for bad in ("http://ntfy.sh", "ftp://ntfy.sh", "https://", "https://user:pw@ntfy.sh", "https://:pw@ntfy.sh", "https://ntfy.sh/pfad", "https://ntfy.sh?x=1",
            "https://ntfy.sh#a", "ntfy.sh", "", None, "https://ntfy.sh:abc", "http://localhost.evil.com"):
    assert not notify.valid_server(bad), bad

# Ohne Themennamen oder mit ungueltigem Server: aus, es geht nichts ins Netz
posts = []
def fake_post(url, body, headers):
    posts.append((url, json.loads(body), dict(headers)))
    return 200

for off in (notify.Notifier("", post=fake_post), notify.Notifier("kurz", post=fake_post), notify.Notifier(TOPIC, "http://ntfy.sh", post=fake_post)):
    assert not off.enabled and off.send("T", "Text") is False
assert posts == []

# Senden: JSON mit Themenname, Titel, Text, Prioritaet; Server ohne Schraegstrich am Ende
n = notify.Notifier(TOPIC, "https://ntfy.sh/", post=fake_post)
assert n.enabled and n.send("Jarvis", "Erinnerung: Zahnarzt ä ö ü €", priority="high") is True
url, payload, headers = posts[0]
assert url == "https://ntfy.sh" and payload == {"topic": TOPIC, "title": "Jarvis", "message": "Erinnerung: Zahnarzt ä ö ü €", "priority": 4}
assert headers == {"Content-Type": "application/json; charset=utf-8"}                    # ohne Schluessel kein Authorization
assert n.send("Jarvis", "x", priority="urgent") and posts[-1][1]["priority"] == 5
assert n.send("Jarvis", "x", priority="low") and posts[-1][1]["priority"] == 2
assert n.send("Jarvis", "x") and posts[-1][1]["priority"] == 3
assert n.send("Jarvis", "x", priority="unsinn") and posts[-1][1]["priority"] == 3

# Schluessel (Token): nur sauber geformt, als Bearer
tok = notify.Notifier(TOPIC, post=fake_post, token="tk_abc123")
assert tok.send("T", "x") and posts[-1][2]["Authorization"] == "Bearer tk_abc123"
assert notify.Notifier(TOPIC, post=fake_post, token="tk abc\r\nX: y").token == "" and notify.Notifier(TOPIC, post=fake_post, token=5).token == ""

# Titel/Text: gekuerzt, Steuerzeichen raus, leerer Text wird nicht gesendet, leerer Titel -> "Jarvis"
posts.clear()
n = notify.Notifier(TOPIC, post=fake_post)
assert n.send("T" * 200, "a" * 900 + "\x00\x1b") and len(posts[0][1]["title"]) == notify.MAX_TITLE and len(posts[0][1]["message"]) == notify.MAX_TEXT
assert "\x00" not in posts[0][1]["message"] and "\x1b" not in posts[0][1]["message"]
assert n.send("", "Hallo\nZeile 2") and posts[1][1]["title"] == "Jarvis" and posts[1][1]["message"] == "Hallo\nZeile 2"
before = len(posts)
assert n.send("T", "") is False and n.send("T", "   \x00  ") is False and n.send("T", None) is False and len(posts) == before

# Begrenzung: 30 pro Stunde, danach verworfen (eine Warnung), nach einer Stunde geht es wieder
class Clock:
    now = 1000.0
    def __call__(self):
        return self.now
clock = Clock()
posts.clear()
limited = notify.Notifier(TOPIC, post=fake_post, clock=clock)
for i in range(notify.MAX_PER_HOUR):
    assert limited.send("T", f"Nr {i}") is True
out = io.StringIO()
with redirect_stdout(out):
    assert limited.send("T", "zu viel") is False and limited.send("T", "noch mehr") is False
assert len(posts) == notify.MAX_PER_HOUR and out.getvalue().count("[PUSH]") == 1, out.getvalue()
clock.now += 3599
assert limited.send("T", "noch nicht") is False
clock.now += 1
assert limited.send("T", "wieder") is True and len(posts) == notify.MAX_PER_HOUR + 1
out = io.StringIO()
with redirect_stdout(out):
    for _ in range(notify.MAX_PER_HOUR - 1):
        assert limited.send("T", "x") is True
    assert limited.send("T", "wieder zu viel") is False
assert out.getvalue().count("[PUSH]") == 1, out.getvalue()                                # nach der Pause gibt es die Warnung erneut
# eine abgelehnte (leere) Nachricht verbraucht kein Kontingent
fresh = notify.Notifier(TOPIC, post=fake_post, clock=clock)
posts.clear()
for _ in range(100):
    fresh.send("T", "")
assert all(fresh.send("T", "x") for _ in range(notify.MAX_PER_HOUR))

# Fehler werden nie weitergereicht und verraten weder Themenname noch Schluessel
def broken(url, body, headers):
    raise ConnectionError(f"kein Netz zu {url} {TOPIC} tk_geheim")
def http_error(url, body, headers):
    raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
def bad_status(url, body, headers):
    return 500
for fn in (broken, http_error, bad_status):
    out = io.StringIO()
    with redirect_stdout(out):
        assert notify.Notifier(TOPIC, post=fn, token="tk_geheim").send("T", "x") is False
    assert TOPIC not in out.getvalue() and "tk_geheim" not in out.getvalue() and "ntfy.sh" not in out.getvalue(), out.getvalue()
    assert ("429" in out.getvalue()) == (fn is http_error) and ("ConnectionError" in out.getvalue()) == (fn is broken), out.getvalue()
assert notify.Notifier(TOPIC, post=lambda *a: 299).send("T", "x") is True and notify.Notifier(TOPIC, post=lambda *a: 300).send("T", "x") is False
assert notify.Notifier(TOPIC, post=lambda *a: 199).send("T", "x") is False and notify.Notifier(TOPIC, post=lambda *a: 200).send("T", "x") is True
assert notify.Notifier(TOPIC, post=lambda *a: None).send("T", "x") is False
assert notify.Notifier(TOPIC, post=lambda *a: True).send("T", "x") is False             # True ist kein Statuscode

# echter Weg: Anfrage an einen lokalen Mini-Server
import http.server
import threading
got = {}
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        got["auth"] = self.headers.get("Authorization")
        got["type"] = self.headers.get("Content-Type")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")
    def log_message(self, *a):
        pass
srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
real = notify.Notifier(TOPIC, f"http://127.0.0.1:{srv.server_address[1]}", token="tk_1")
assert real.send("Jarvis", "Test ä", priority="high") is True
assert got["body"]["message"] == "Test ä" and got["body"]["topic"] == TOPIC and got["auth"] == "Bearer tk_1" and got["type"].startswith("application/json"), got
srv.shutdown()
with redirect_stdout(io.StringIO()):
    assert notify.Notifier(TOPIC, "http://127.0.0.1:1").send("T", "x") is False         # nichts erreichbar: False statt Fehler

# Standard-Notifier: aus der Konfiguration, austauschbar
import config
assert config.NTFY_SERVER == "https://ntfy.sh" or config.NTFY_SERVER
notify.set_default_notifier(None)
assert isinstance(notify.default_notifier(), notify.Notifier) and notify.default_notifier() is notify.default_notifier()
fake = notify.Notifier(TOPIC, post=fake_post)
notify.set_default_notifier(fake)
assert notify.default_notifier() is fake
assert notify.from_config().enabled == bool(notify.valid_topic(config.NTFY_TOPIC) and notify.valid_server(config.NTFY_SERVER))
notify.set_default_notifier(None)

print("ALL TESTS PASSED")
