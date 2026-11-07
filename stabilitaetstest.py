"""Stabilitaetstest (Step 7.2): der echte Server unter Dauerlast, mit Fehlern dazwischen.

Aufruf (im Projektordner):
    py stabilitaetstest.py            # 120 Sekunden
    py stabilitaetstest.py 600        # 10 Minuten
    py stabilitaetstest.py 300 16     # 5 Minuten mit 16 gleichzeitigen "Browsern"

Was geprueft wird:
- Der Server (server.py, unveraendert) bekommt dauernd gemischte Anfragen von mehreren Threads:
  Nachrichten, Hintergrund-Abfragen, Timer, Einstellungen, Widgets, Vorlesen, dazu absichtlich
  kaputte Anfragen (kein JSON, falscher Typ, zu gross, fremder Host, abgebrochene Verbindungen,
  unbekannte Adressen, Pfad-Tricks) und eine Nachricht, bei der die "KI" einen Fehler wirft.
- Remote (Mark 5, R6): dasselbe vom "Handy" aus. Echte Kopplung, Nachrichten und Lesen mit Gerate-Cookie, dazu
  falsche und fehlende Token, verbotene Adressen, falscher Origin/Host, zu lange Nachrichten, falsche Kopplungscodes
  (bis zur Sperre). Nach der Last pruefen eigene Fallgruppen Limits, Sperren, Alle-sperren und Remote-aus.
- Jede Antwort muss zum Fall passen (gueltig = 200, kaputt = 4xx, Fehler = genau 500).
- Gemessen werden Antwortzeiten, Threads, offene Handles und Speicher ueber die Zeit.
- Am Ende muss der Server noch schnell antworten, es darf keine unerwarteten Fehlermeldungen im
  Terminal geben, und Threads und Speicher duerfen nicht dauernd weiter wachsen.

Wie alle Tests: keine echte Datenbank, kein OpenAI, keine Programme. Es kostet nichts.
Der Test ist bewusst NICHT in run_tests.py (dauert zu lange). Ausgabe am Ende:
"STABILITY TEST PASSED" oder die Liste der Abweichungen.
"""

import http.client
import io
import json
import os
import random
import socket
import sys
import tempfile
import threading
import time
import types
from collections import Counter
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "test"))

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 8

# ---- Fakes wie in den anderen Tests (keine Datenbank, kein OpenAI)
for name, attrs in (("dotenv", {"load_dotenv": lambda *a, **k: None}), ("openai", {"OpenAI": object}),
                    ("psycopg", {}), ("psutil", {}), ("requests", {})):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    _inner = types.ModuleType("pycaw.pycaw")
    _inner.AudioUtilities = None
    _inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = _inner

project_stub = types.ModuleType("project")
for fn in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
           "save_message", "get_conversation", "rename_conversation", "create_project",
           "reset_conversation", "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, fn, lambda *a, **k: None)
sys.modules["project"] = project_stub

import remote_auth
import remote_gate
import server
import timer
import widgets
import workspace as workspace_module
import jarvis as jarvis_module
from fake_project_db import FakeProjectDB
from settings_manager import SettingsManager

INJECTED_ERROR_TEXT = "FEHLER-EINSPRITZEN"


class Counter_:
    """Zaehlt, wie oft der Server einen Traceback ins Terminal schreibt."""

    def __init__(self, real):
        self.real = real
        self.text = io.StringIO()
        self.lock = threading.Lock()

    def write(self, data):
        with self.lock:
            self.text.write(data)
        return len(data)

    def flush(self):
        pass

    def tracebacks(self):
        with self.lock:
            return self.text.getvalue().count("Traceback (most recent call last)")

    def dump_tail(self, chars=1500):
        with self.lock:
            return self.text.getvalue()[-chars:]


stderr = Counter_(sys.stderr)
real_stderr = sys.stderr
sys.stderr = stderr

fdb = FakeProjectDB()
fdb.install(workspace_module)
fake = object.__new__(jarvis_module.Jarvis)
fake.workspace = workspace_module.Workspace()
fake.pending_project_confirmation = None
work_dir = Path(tempfile.mkdtemp())
fake.settings_manager = SettingsManager(work_dir / "settings.json")
processed = [0]
injected_errors = [0]
count_lock = threading.Lock()


def process_message(message):
    time.sleep(random.uniform(0.005, 0.04))             # "die KI denkt"
    if message == INJECTED_ERROR_TEXT:
        with count_lock:
            injected_errors[0] += 1
        raise RuntimeError("absichtlicher Fehler der Fake-KI")
    with count_lock:
        processed[0] += 1
    return {"status": "response", "content": f"Echo: {message[:50]}"}


REMOTE_HOST = "mein-pc.tailabc.ts.net"
REMOTE_ORIGIN = "https://" + REMOTE_HOST
remote_processed = [0]


def process_remote_message(text, device_name, levels):
    time.sleep(random.uniform(0.005, 0.04))
    if text == INJECTED_ERROR_TEXT:
        with count_lock:
            injected_errors[0] += 1
        raise RuntimeError("absichtlicher Fehler der Fake-KI (remote)")
    with count_lock:
        remote_processed[0] += 1
    return {"status": "response", "content": f"Remote-Echo: {text[:50]}"}


fake.process_message = process_message
fake.process_remote_message = process_remote_message
fake.check_background_results = lambda: []
fake.apply_settings = lambda: None
fake.client = types.SimpleNamespace(audio=types.SimpleNamespace(
    speech=types.SimpleNamespace(create=lambda **kw: types.SimpleNamespace(content=b"ID3-fake"))))


class FakeHockey:
    def get(self, team):
        return {"team": team, "current": None, "next": [], "stale": False}


store = widgets.WidgetStore(work_dir / "widgets.json")
device_store = remote_auth.DeviceStore(work_dir / "remote_devices.json")
gate = remote_gate.RemoteGate(REMOTE_HOST, device_store, fake.settings_manager)
fake.settings_manager.set("remote", "enabled", True)
httpd = server.JarvisServer(("127.0.0.1", 0), fake, widget_store=store, hockey=FakeHockey(), remote=gate)
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()

# ----------------------------------------------------------------------
# Messung von Threads, Handles, Speicher
# ----------------------------------------------------------------------


def process_stats():
    rss = handles = None
    try:
        import psutil
        proc = psutil.Process()
        rss = proc.memory_info().rss / 1e6
        handles = proc.num_handles() if hasattr(proc, "num_handles") else proc.num_fds()
    except Exception:
        try:
            with open("/proc/self/status", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) / 1024
            handles = len(os.listdir("/proc/self/fd"))
        except Exception:
            pass
    return {"threads": threading.active_count(), "rss": rss, "handles": handles}


# ----------------------------------------------------------------------
# Die "Browser"
# ----------------------------------------------------------------------

lock = threading.Lock()
latencies = []
statuses = Counter()
problems = []            # (Fall, erwartet, bekommen)
requests_done = [0]
stop = threading.Event()
slow = []                # Anfragen ueber 5 Sekunden


def raw_request(method, path, body=None, headers=None, host=None, timeout=10):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host or f"localhost:{port}")
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()


def full_request(method, path, body=None, headers=None, host=None, timeout=10):
    """Wie raw_request, gibt aber (Status, Header, Text) zurueck."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host or f"localhost:{port}")
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        raw = response.read()
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), raw
    finally:
        conn.close()


def pair_device(name):
    """Kopplung wie am echten Handy: Link-Code am PC erzeugen, auf der Remote-Adresse einloesen, Cookie merken."""
    code = device_store.create_pairing(name)["code"]
    status, headers, raw = full_request("POST", "/api/remote/pair", json.dumps({"code": code}).encode("utf-8"),
                                        {"Content-Type": "application/json", "Origin": REMOTE_ORIGIN}, host=REMOTE_HOST)
    if status != 200:
        raise SystemExit(f"Kopplung fehlgeschlagen ({status}): {raw[:200]!r}")
    return headers["set-cookie"].split(";")[0]


def remote_headers(cookie, origin=REMOTE_ORIGIN, json_body=False):
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if origin:
        headers["Origin"] = origin
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def remote_get(path, cookie, **kw):
    return raw_request("GET", path, None, remote_headers(cookie), host=kw.pop("host", REMOTE_HOST), **kw)


def remote_post(path, payload, cookie, origin=REMOTE_ORIGIN, **kw):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return raw_request("POST", path, body, remote_headers(cookie, origin, json_body=True), host=kw.pop("host", REMOTE_HOST), **kw)


phone_cookie = pair_device("Stabilitaets-iPhone")
limit_cookies = [pair_device(f"Limit-Gerät {i}") for i in range(3)]       # fuer die Fallgruppen nach der Last
revoke_cookies = [pair_device(f"Sperr-Gerät {i}") for i in range(2)]


def post_json(path, payload, **kw):
    return raw_request("POST", path, json.dumps(payload).encode("utf-8"),
                       {"Content-Type": "application/json"}, **kw)


def record(case, expected, got, started):
    elapsed = time.time() - started
    with lock:
        latencies.append(elapsed)
        statuses[got] += 1
        requests_done[0] += 1
        if elapsed > 5:
            slow.append((case, round(elapsed, 1)))
        if got not in expected:
            if len(problems) < 30:
                problems.append((case, sorted(expected), got))


def abort_connection():
    """Eine Verbindung, die mitten in der Anfrage aufgelegt wird (Seite neu geladen o. ae.)."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    kind = random.choice(("half-header", "half-body", "no-data"))
    try:
        if kind == "half-header":
            sock.sendall(b"POST /api/message HTTP/1.1\r\nHost: localhost\r\nContent-Ty")
        elif kind == "half-body":
            sock.sendall(b"POST /api/message HTTP/1.1\r\nHost: localhost:%d\r\nContent-Type: application/json\r\n"
                         b"Content-Length: 500\r\n\r\n{\"message\": \"ab" % port)
        sock.close()
    except OSError:
        pass


def one_request(rng, number):
    """Eine zufaellige Anfrage. Gibt (Fall, erlaubte Status, Funktion) zurueck."""
    if rng.random() < 0.3:
        return remote_case(rng, number)
    pick = rng.random()
    if pick < 0.28:
        return "message", {200}, lambda: post_json("/api/message", {"message": f"Hallo {number}"})
    if pick < 0.30:
        return "message-fehler", {500}, lambda: post_json("/api/message", {"message": INJECTED_ERROR_TEXT})
    if pick < 0.42:
        return "background", {200}, lambda: raw_request("GET", "/api/background?after=0")
    if pick < 0.46:
        return "timers", {200}, lambda: raw_request("GET", "/api/timers")
    if pick < 0.50:
        return "settings", {200}, lambda: raw_request("GET", "/api/settings")
    if pick < 0.54:
        return "widgets-lesen", {200}, lambda: raw_request("GET", "/api/widgets")
    if pick < 0.56:
        return "hockey", {200}, lambda: raw_request("GET", "/api/hockey")
    if pick < 0.59:
        return "statisch", {200}, lambda: raw_request("GET", rng.choice(["/", "/app.js", "/style.css", "/voice.js"]))
    if pick < 0.62:
        return "notiz", {200}, lambda: post_json("/api/widgets/notes", {"text": "n" * rng.randint(0, 3000)})
    if pick < 0.65:
        return "ziele", {200}, lambda: post_json("/api/widgets/goals", {"items": [
            {"text": f"Ziel {i}", "done": i % 2 == 0, "daily": i % 3 == 0} for i in range(rng.randint(0, 10))]})
    if pick < 0.68:
        def add_event_and_clean_up():
            # Das Limit (500 Termine) soll den Test nicht verfaelschen: eigene Termine gleich wieder loeschen.
            status = post_json("/api/widgets/events", {
                "title": f"Termin {number}", "date": time.strftime("%Y-%m-%d"), "time": "10:00"})
            for event in store.events_on(time.strftime("%Y-%m-%d")):
                if event.get("title") == f"Termin {number}":
                    try:
                        store.delete_event(event["id"])
                    except ValueError:
                        pass
            return status
        return "termin", {200}, add_event_and_clean_up
    if pick < 0.70:
        return "termin-loeschen-unbekannt", {400}, lambda: post_json("/api/widgets/events/delete", {"id": "gibtsnicht"})
    if pick < 0.73:
        return "einstellung", {200}, lambda: post_json("/api/settings", {
            "category": "appearance", "key": "font_size", "value": rng.randint(11, 20)})
    if pick < 0.75:
        return "einstellung-ungueltig", {400}, lambda: post_json("/api/settings", {
            "category": "appearance", "key": "font_size", "value": 999})
    if pick < 0.78:
        return "vorlesen", {200}, lambda: post_json("/api/speak", {"text": "Guten Tag, Sir."})
    if pick < 0.80:
        return "kein-json", {400}, lambda: raw_request("POST", "/api/message", b"{kaputt", {"Content-Type": "application/json"})
    if pick < 0.82:
        return "falscher-typ", {415}, lambda: raw_request("POST", "/api/message", b"message=hallo",
                                                          {"Content-Type": "application/x-www-form-urlencoded"})
    if pick < 0.84:
        return "zu-gross", {400}, lambda: raw_request("POST", "/api/message", b"x" * (server.MAX_BODY_BYTES + 10),
                                                      {"Content-Type": "application/json"})
    if pick < 0.86:
        return "fremder-host", {403}, lambda: raw_request("GET", "/api/settings", host="evil.example")
    if pick < 0.88:
        return "fremder-origin", {403}, lambda: raw_request("POST", "/api/message", b'{"message":"x"}',
                                                            {"Content-Type": "application/json", "Origin": "https://evil.example"})
    if pick < 0.90:
        return "unbekannt", {404}, lambda: raw_request("GET", rng.choice(["/api/gibtsnicht", "/nix.html", "/../server.py", "/..%2f.env", "/.env"]))
    if pick < 0.92:
        return "falsche-methode", {501, 405}, lambda: raw_request("DELETE", "/api/message")
    if pick < 0.94:
        return "timer-abbrechen-ungueltig", {400}, lambda: post_json("/api/timer/cancel", {"id": "x"})
    if pick < 0.96:
        return "plan-abbrechen", {200}, lambda: post_json("/api/plan/abort", {})
    if pick < 0.98:
        return "abbruch", {None}, lambda: (abort_connection(), None)[1]
    return "unicode", {200}, lambda: post_json("/api/message", {"message": "Ünïcödé ✓ 🏒 " + "ß" * rng.randint(1, 200)})


def remote_case(rng, number):
    """Eine zufaellige Anfrage vom "Handy" (ueber den Remote-Namen)."""
    pick = rng.random()
    if pick < 0.30:
        return "remote-nachricht", {200}, lambda: remote_post("/api/message", {"message": f"Hallo vom Handy {number}"}, phone_cookie)
    if pick < 0.32:
        return "remote-nachricht-fehler", {500}, lambda: remote_post("/api/message", {"message": INJECTED_ERROR_TEXT}, phone_cookie)
    if pick < 0.52:
        path = rng.choice(["/api/timers", "/api/background?after=0", "/api/widgets", "/api/projects", "/api/sync",
                           "/api/ringing", "/api/focus", "/api/alarms", "/api/settings", "/api/remote/whoami"])
        return "remote-lesen", {200}, lambda: remote_get(path, phone_cookie)
    if pick < 0.56:
        return "remote-statisch", {200}, lambda: remote_get(rng.choice(["/", "/app.js", "/style.css", "/sync.js", "/remote_mode.js"]), phone_cookie)
    if pick < 0.60:
        return "remote-kopplungsseite", {200}, lambda: raw_request("GET", rng.choice(["/pair", "/manifest.webmanifest", "/sw.js"]), host=REMOTE_HOST)
    if pick < 0.66:
        bad = rng.choice(["jarvis_device=falsch", "jarvis_device=", "jarvis_device=abc.def", "x=1", "jarvis_device=" + phone_cookie.split("=", 1)[1] + "x",
                          "jarvis_device=" + "a" * 3000])
        return "remote-falsches-token", {401}, lambda: remote_get("/api/timers", bad)
    if pick < 0.70:
        return "remote-ohne-token", {401}, lambda: remote_get(rng.choice(["/api/timers", "/", "/app.js", "/api/settings"]), None)
    if pick < 0.78:
        path = rng.choice(["/api/actions", "/api/memories", "/api/folders", "/api/remote/state", "/api/system", "/api/performance", "/api/hockey", "/api/nichts"])
        return "remote-verboten-lesen", {403}, lambda: remote_get(path, phone_cookie)
    if pick < 0.84:
        path = rng.choice(["/api/settings", "/api/confirm", "/api/plan/confirm", "/api/memory/delete_all", "/api/folders/add", "/api/widgets/events",
                           "/api/project/delete", "/api/conversation/reset", "/api/remote/pair_link", "/api/remote/revoke_all", "/api/briefing/auto"])
        return "remote-verboten-schreiben", {403}, lambda: remote_post(path, {"category": "remote", "key": "enabled", "value": False, "id": "x", "text": "x"}, phone_cookie)
    if pick < 0.88:
        origin = rng.choice([None, "https://evil.example", "http://localhost:%d" % port, "http://" + REMOTE_HOST, REMOTE_ORIGIN + ".evil.example"])
        return "remote-falscher-origin", {403}, lambda: remote_post("/api/message", {"message": "x"}, phone_cookie, origin=origin)
    if pick < 0.91:
        host = rng.choice(["evil.example", REMOTE_HOST + ".evil.example", "x" + REMOTE_HOST, "localhost.evil.example"])
        return "remote-falscher-host", {403}, lambda: remote_get("/api/timers", phone_cookie, host=host)
    if pick < 0.94:
        return "remote-nachricht-ungueltig", {400}, lambda: remote_post("/api/message", rng.choice([
            {"message": "x" * 1001}, {"message": ""}, {"message": "   "}, {"message": 5}, {"nichts": 1}, b"{kaputt"]), phone_cookie)
    if pick < 0.955:
        # Ziele, Listen, gemeinsame Notiz und die eigene Notiz des Handys (Stufe Alltag), gueltig und zu lang
        kind = rng.choice(["goals", "lists", "notes", "device_note", "notes-lang", "device_note-lang"])
        bodies = {
            "goals": ("/api/widgets/goals", {"items": [{"text": f"Ziel {number}", "done": bool(number % 2), "daily": False}]}, {200}),
            "lists": ("/api/widgets/lists", {"lists": [{"name": "Einkauf", "items": [{"text": f"Eier {number}", "done": False}]}]}, {200}),
            "notes": ("/api/widgets/notes", {"text": "n" * rng.randint(0, 500)}, {200}),
            "device_note": ("/api/widgets/device_note", {"text": "h" * rng.randint(0, 500)}, {200}),
            "notes-lang": ("/api/widgets/notes", {"text": "x" * 5001}, {400}),
            "device_note-lang": ("/api/widgets/device_note", {"text": "x" * 5001}, {400}),
        }
        path, body, expected = bodies[kind]
        return "remote-widgets-" + kind, expected, lambda: remote_post(path, body, phone_cookie)
    if pick < 0.97:
        return "remote-kopplung-falsch", {400, 429}, lambda: remote_post("/api/remote/pair", {"code": f"falsch{number}{rng.randint(0, 10**6)}"}, None)
    return "remote-nachricht-unicode", {200}, lambda: remote_post("/api/message", {"message": "Ünïcödé ✓ 🏒 " + "ß" * rng.randint(1, 200)}, phone_cookie)


def worker(seed):
    rng = random.Random(seed)
    number = 0
    while not stop.is_set():
        number += 1
        case, expected, call = one_request(rng, number)
        started = time.time()
        try:
            got = call()
        except Exception as error:                          # keine Antwort / Verbindungsfehler
            got = f"Fehler: {type(error).__name__}"
        record(case, expected, got, started)
        time.sleep(rng.uniform(0, 0.02))


def timer_worker():
    """Echte Timer starten und abbrechen, damit Hintergrundmeldungen entstehen."""
    rng = random.Random(7)
    while not stop.is_set():
        try:
            t = timer.start_timer(rng.choice([1, 1, 2]), f"T{rng.randint(1, 5)}")
            if rng.random() < 0.4:
                timer.cancel_timer_by_id(t.id)
        except Exception:
            pass                                             # z.B. zu viele Timer: erlaubt
        time.sleep(rng.uniform(0.2, 0.6))


# ----------------------------------------------------------------------
# Ablauf
# ----------------------------------------------------------------------

print(f"Stabilitaetstest: {DURATION:.0f} Sekunden, {WORKERS} gleichzeitige Clients, Port {port}", file=real_stderr)
baseline = process_stats()
samples = []
threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(WORKERS)]
threads.append(threading.Thread(target=timer_worker, daemon=True))
started_at = time.time()
for t in threads:
    t.start()

next_print = started_at + 10
while time.time() - started_at < DURATION:
    time.sleep(1)
    stats = process_stats()
    stats["t"] = time.time() - started_at
    samples.append(stats)
    if time.time() >= next_print:
        next_print += 10
        with lock:
            n = requests_done[0]
        print(f"  {stats['t']:5.0f} s  Anfragen {n:6d}  Threads {stats['threads']:3d}  "
              f"Handles {stats['handles']}  Speicher {stats['rss'] if stats['rss'] is None else round(stats['rss'], 1)} MB",
              file=real_stderr)

stop.set()
for t in threads:
    t.join(timeout=15)
time.sleep(3)                                                # Handler-Threads auslaufen lassen
end = process_stats()

# Nach der Last: der Server antwortet noch, schnell und richtig
health = []
for _ in range(20):
    t0 = time.time()
    code = raw_request("GET", "/api/settings")
    health.append((code, time.time() - t0))
tail_time = time.time() - started_at

# ----------------------------------------------------------------------
# Remote nach der Last: Limits, Sperren, Schalter (jede Gruppe mit eigenem Geraet)
# ----------------------------------------------------------------------
remote_checks = []


def check(name, got, expected):
    remote_checks.append((name, got, expected))


def message_status(cookie):
    return remote_post("/api/message", {"message": "Limit-Test"}, cookie)


remote_settings = fake.settings_manager
# 0) Waehrend der Last wurden falsche Kopplungscodes geschickt: die Sperre gilt jetzt auch fuer einen richtigen Code
locked_code = device_store.create_pairing("Sollte-gesperrt-sein")["code"]
check("Kopplung nach vielen Fehlversuchen gesperrt", remote_post("/api/remote/pair", {"code": locked_code}, None), 429)
check("Gekoppeltes Geraet trotz Kopplungssperre weiter ok", message_status(phone_cookie), 200)
device_store.guard._locked_until.clear()
device_store.guard._failures.clear()
check("Nach Ende der Sperre klappt der richtige Code", remote_post("/api/remote/pair", {"code": locked_code}, None), 200)

# 1) Nachrichtenlimit je Geraet: 3 erlaubt, dann 429; ein anderes Geraet ist nicht betroffen
remote_settings.set("remote", "max_messages", 3)
check("Limit: erste drei Nachrichten", [message_status(limit_cookies[0]) for _ in range(3)], [200, 200, 200])
check("Limit: vierte und fuenfte Nachricht", [message_status(limit_cookies[0]) for _ in range(2)], [429, 429])
check("Limit: anderes Geraet", message_status(limit_cookies[1]), 200)
check("Limit: Lesen ist nicht begrenzt", remote_get("/api/timers", limit_cookies[0]), 200)
remote_settings.set("remote", "max_messages", 0)
check("Limit 0 = unbegrenzt", [message_status(limit_cookies[0]) for _ in range(5)], [200] * 5)

# 2) KI-Aufrufe pro Tag fuer alle Geraete zusammen
gate.limits._day = None
gate.limits._daily = 0
remote_settings.set("remote", "max_ai_per_day", 2)
check("Tageslimit: zwei Nachrichten", [message_status(limit_cookies[2]), message_status(limit_cookies[1])], [200, 200])
check("Tageslimit: dritte, egal von welchem Geraet", [message_status(limit_cookies[2]), message_status(phone_cookie)], [429, 429])
remote_settings.set("remote", "max_ai_per_day", 0)
check("Tageslimit 0 = unbegrenzt", message_status(phone_cookie), 200)

# 3) Sperren wirkt sofort, nur fuer dieses Geraet
sperr_id = revoke_cookies[0].split("=", 1)[1].split(".", 1)[0]
check("Vor dem Sperren", remote_get("/api/timers", revoke_cookies[0]), 200)
device_store.revoke(sperr_id)
check("Gesperrtes Geraet", [remote_get("/api/timers", revoke_cookies[0]), message_status(revoke_cookies[0])], [401, 401])
check("Anderes Geraet nicht betroffen", remote_get("/api/timers", revoke_cookies[1]), 200)

# 4) Remote aus: auch gekoppelte Geraete kommen nicht rein, der PC schon
remote_settings.set("remote", "enabled", False)
check("Remote aus: Handy", [remote_get("/api/timers", phone_cookie), message_status(phone_cookie), raw_request("GET", "/pair", host=REMOTE_HOST)], [403, 403, 403])
check("Remote aus: PC", raw_request("GET", "/api/timers"), 200)
remote_settings.set("remote", "enabled", True)
check("Remote wieder an", remote_get("/api/timers", phone_cookie), 200)

# 5) Alle Geraete sperren
device_store.revoke_all()
check("Alle gesperrt", [remote_get("/api/timers", phone_cookie), remote_get("/api/timers", limit_cookies[0]), remote_get("/api/timers", revoke_cookies[1])], [401, 401, 401])
check("PC nach Alle-sperren", [raw_request("GET", "/api/timers"), raw_request("GET", "/api/settings")], [200, 200])

# 6) Das Geraete-File enthaelt keine Token im Klartext
saved = (work_dir / "remote_devices.json").read_text(encoding="utf-8")
for cookie in [phone_cookie] + limit_cookies + revoke_cookies:
    check("Kein Token im Klartext gespeichert", cookie.split("=", 1)[1].split(".", 1)[1] in saved, False)

sys.stderr = real_stderr

# ----------------------------------------------------------------------
# Auswertung
# ----------------------------------------------------------------------

lat = sorted(latencies)


def pct(p):
    return lat[min(len(lat) - 1, int(len(lat) * p))] * 1000 if lat else 0.0


warm = [s for s in samples if s["t"] >= DURATION * 0.2 and s["rss"] is not None]
rss_growth = (samples[-1]["rss"] - warm[0]["rss"]) if warm and samples and samples[-1]["rss"] is not None else None
peak_threads = max((s["threads"] for s in samples), default=0)
peak_handles = max((s["handles"] for s in samples if s["handles"] is not None), default=None)

print()
print(f"Dauer {tail_time:.0f} s, Anfragen {len(lat)}, davon Nachrichten verarbeitet {processed[0]}, "
      f"absichtliche Fehler {injected_errors[0]}")
print(f"Antwortzeit: Median {pct(0.5):.0f} ms, 95% {pct(0.95):.0f} ms, 99% {pct(0.99):.0f} ms, laengste {pct(1.0):.0f} ms")
print("Status:", dict(sorted(((str(k), v) for k, v in statuses.items()))))
print(f"Remote: Nachrichten verarbeitet {remote_processed[0]}, Pruefungen nach der Last {len(remote_checks)}")
print(f"Threads: Start {baseline['threads']}, Spitze {peak_threads}, Ende {end['threads']}")
if end["handles"] is not None:
    print(f"Handles: Start {baseline['handles']}, Spitze {peak_handles}, Ende {end['handles']}")
if rss_growth is not None:
    print(f"Speicher: Start {baseline['rss']:.0f} MB, Ende {end['rss']:.0f} MB, "
          f"Zuwachs nach dem Warmlaufen {rss_growth:+.1f} MB")

failures = []
unexpected = [p for p in problems]
if unexpected:
    failures.append(f"{len(unexpected)}+ Antworten passten nicht zum Fall, erste: {unexpected[:5]}")
for name, got, expected in remote_checks:
    if got != expected:
        failures.append(f"Remote-Pruefung \"{name}\": bekommen {got}, erwartet {expected}")
if remote_processed[0] == 0:
    failures.append("Remote: keine einzige Nachricht vom Handy wurde verarbeitet")
if slow:
    failures.append(f"{len(slow)} Anfragen dauerten ueber 5 Sekunden: {slow[:5]}")
real_tracebacks = stderr.tracebacks()
if real_tracebacks != injected_errors[0]:
    failures.append(f"Tracebacks im Terminal: {real_tracebacks}, erwartet (absichtliche Fehler): {injected_errors[0]}\n"
                    f"{stderr.dump_tail()}")
if any(code != 200 for code, _ in health) or max(t for _, t in health) > 1.0:
    failures.append(f"Nach der Last antwortet der Server nicht sauber: {health[:5]}")
if end["threads"] > baseline["threads"] + WORKERS + 6:
    failures.append(f"Threads wachsen: Start {baseline['threads']}, Ende {end['threads']}")
# Handles: unter Windows entstehen beim Start einmalig viele (Module, Sockets). Ein Leck zeigt sich als Trend
# waehrend der Last: Mittel des letzten Viertels gegen Mittel des zweiten Viertels (nach dem Warmlaufen).
_h = [s["handles"] for s in samples if s["handles"] is not None]
if len(_h) >= 8:
    _q = len(_h) // 4
    _early = sum(_h[_q:2 * _q]) / _q
    _late = sum(_h[-_q:]) / _q
    if _late > _early + 40:
        failures.append(f"Handles wachsen waehrend der Last: {_early:.0f} -> {_late:.0f}")
if end["handles"] is not None and baseline["handles"] is not None and end["handles"] > baseline["handles"] + 150:
    failures.append(f"Handles nach der Last weit ueber dem Start: Start {baseline['handles']}, Ende {end['handles']}")
if rss_growth is not None and rss_growth > 60:
    failures.append(f"Speicher waechst nach dem Warmlaufen um {rss_growth:.0f} MB")
if len(lat) < DURATION * 10:
    failures.append(f"Verdaechtig wenige Anfragen ({len(lat)}): der Server war zu langsam")
if pct(0.95) > 1500:
    failures.append(f"95%-Antwortzeit {pct(0.95):.0f} ms ist zu hoch")

print()
if failures:
    print("STABILITY TEST FAILED")
    for item in failures:
        print(" -", item)
    sys.exit(1)
print("STABILITY TEST PASSED")
