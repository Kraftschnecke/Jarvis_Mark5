"""Web-Oberflaeche fuer J.A.R.V.I.S.

Ein kleiner HTTP-Server nur mit der Python-Standardbibliothek. Er macht zwei
Dinge:

  1. Er liefert die Dateien aus dem Ordner web/ aus (HTML, CSS, JavaScript).
  2. Er stellt eine kleine JSON-Schnittstelle bereit, ueber die die Seite mit
     Jarvis spricht:

       POST /api/message     {"message": "..."}  ->  {"status": ..., "content": ..., "messages": [...]}
                             ("messages" nur, wenn ein Chat-Befehl die offene Konversation geaendert hat)
       POST /api/confirm     {"id": "...", "approve": true|false}  (Antwort auf eine Rueckfrage, Step 4.2)
                             ("/api/message" liefert dann status "confirmation" und ein "confirmation"-Objekt)
       POST /api/plan/confirm {"id": "...", "approve": true|false}  (Plan ausfuehren oder verwerfen, Step 5.3)
       POST /api/plan/abort   {}  (stoppt einen laufenden Plan vor dem naechsten Schritt)
       GET  /api/background?after=<id>  ->  {"messages": [{"id": 3, "text": "..."}], "last": 3}
                             (ohne "after": nur den aktuellen Stand "last" melden)
       GET  /api/alarms      ->  alle Wecker fuer den Kalender; POST /api/alarms/add, /api/alarms/update und /api/alarms/delete (Step 2.11b)
       GET  /api/ringing     ->  was gerade laeutet (Wecker/Timer) und wer den Ton macht (Step 2.11)
       POST /api/ringing/stop ->  ausschalten oder schlummern, auch waehrend Jarvis antwortet
       GET  /api/system      ->  PC-Fakten fuer das Widget "PC Facts" (Step 2.8, lokal gelesen)
       GET  /api/performance ->  CPU, RAM, Laufwerk, Akku, Netzwerk fuer das Widget "Performance"
       GET  /api/timers      ->  {"timers": [{"id", "name", "seconds", "remaining"}]}  (laufende Timer, Step 6b)
       POST /api/speak {"text": "..."}  ->  audio/mpeg  (Sprachausgabe mit der eingestellten Stimme, Step 6b)
       POST /api/timer/cancel {"id": 3}  ->  {"cancelled": true|false}  (einen Timer abbrechen)
       GET  /api/projects    ->  {"projects": [...], "active": {...}}
       GET  /api/settings    ->  {"settings": {...}, "about": {...}}
       GET  /api/actions     ->  {"actions": [{"time", "goal", "details", "decision", "status", "summary"}]}  (Aktionsprotokoll, Step 4.3)
       GET  /api/memories    ->  {"enabled": true, "memories": [{"key", "value", "type"}]}
       POST /api/settings    {"category", "key", "value"}  (nur erlaubte Einstellungen)
       POST /api/memory/...        update, delete (mit Bestaetigung), delete_all (exakter Satz + Anzahl)
       POST /api/project/...       open, new, rename, delete
       POST /api/conversation/...  open, new, rename, reset, delete

Er ist bewusst nur fuer den eigenen Rechner gedacht (127.0.0.1) und hat keine
Anmeldung. Bevor Jarvis ueber das Internet erreichbar sein soll, braucht er
Login, HTTPS und eine Nutzertrennung.

Start:  py server.py
Gastmodus (zum Ausprobieren durch andere, ohne Zugriff auf deinen Rechner):
        py server.py --guest   (siehe guest.py; erlaubt nur /api/message, /api/background, /api/settings)
"""

import json
import platform
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import abilities
import action_log
import speech
import timer
import reminders
import ringing
import widgets
from tools import news_tool, system_status_tool, weather_tool
from config import SERVER_HOST, SERVER_PORT, VERSION
from memory import MAX_VALUE_LENGTH, VALID_TYPES
from personality import get_address, is_valid_address
from settings_manager import SettingsManager
from workspace import WorkspaceError

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_BODY_BYTES = 64 * 1024
# Bis zu dieser Groesse wird ein Body immer gelesen, auch wenn die Anfrage
# abgelehnt wird. Sonst bricht der Server die Verbindung ab, waehrend der
# Browser noch sendet, und der Browser sieht keine Antwort (Windows: WinError 10053).
MAX_DRAIN_BYTES = 1024 * 1024

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _is_int(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


ACCENT_COLORS = ("J.A.R.V.I.S. Blue", "British Racing Green")

# Nur diese Einstellungen duerfen ueber die Seite geaendert werden, und nur
# mit gueltigen Werten. Alles andere in settings.json bleibt unangetastet.
EDITABLE_SETTINGS = {
    ("appearance", "theme"): lambda v: v in ("Dark", "Light", "System"),
    ("appearance", "font_size"): lambda v: _is_int(v, 11, 20),
    ("appearance", "accent_color"): lambda v: v in ACCENT_COLORS,
    ("jarvis", "address"): is_valid_address,
    ("jarvis", "home_place"): lambda v: isinstance(v, str) and v == v.strip() and len(v) <= 60 and v.isprintable(),
    ("memory", "enabled"): lambda v: isinstance(v, bool),
    ("voice", "output"): lambda v: isinstance(v, bool),
    ("voice", "speed"): lambda v: v in SettingsManager.CHOICES[("voice", "speed")],
    ("voice", "engine"): lambda v: v in SettingsManager.CHOICES[("voice", "engine")],
    ("voice", "voice"): lambda v: v in SettingsManager.CHOICES[("voice", "voice")],
    ("voice", "input_language"): lambda v: v in SettingsManager.CHOICES[("voice", "input_language")],
    ("voice", "input"): lambda v: isinstance(v, bool),
    ("voice", "wake_word"): lambda v: isinstance(v, bool),
    ("widgets", "top"): lambda v: v in SettingsManager.CHOICES[("widgets", "top")],
    ("widgets", "middle"): lambda v: v in SettingsManager.CHOICES[("widgets", "middle")],
    ("widgets", "bottom"): lambda v: v in SettingsManager.CHOICES[("widgets", "bottom")],
    ("widgets", "fourth"): lambda v: v in SettingsManager.CHOICES[("widgets", "fourth")],
    ("widgets", "fifth"): lambda v: v in SettingsManager.CHOICES[("widgets", "fifth")],
}
EDITABLE_SETTINGS[("alarm", "sound")] = lambda v: v in SettingsManager.CHOICES[("alarm", "sound")]
EDITABLE_SETTINGS[("alarm", "ring_timers")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("alarm", "briefing")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("alarm", "max_minutes")] = lambda v: _is_int(v, 1, 60)
EDITABLE_SETTINGS[("alarm", "snooze_minutes")] = lambda v: _is_int(v, 1, 60)
# Schalter fuer Faehigkeiten: eine Zeile je Eintrag in abilities.ABILITIES
EDITABLE_SETTINGS[("limits", "ai_calls_per_day")] = lambda v: _is_int(v, 0, 100000)
EDITABLE_SETTINGS[("limits", "speech_calls_per_day")] = lambda v: _is_int(v, 0, 100000)
for _feed_id in news_tool.FEEDS:
    EDITABLE_SETTINGS[("news", _feed_id)] = lambda v: isinstance(v, bool)
for _ability in abilities.ABILITIES:
    EDITABLE_SETTINGS[("abilities", _ability.id)] = lambda v: isinstance(v, bool)


def settings_state(jarvis):
    return {
        "guest": bool(getattr(jarvis, "guest", False)),
        "settings": jarvis.settings_manager.get_all(),
        "abilities": abilities.describe_all(jarvis.settings_manager),
        "usage": jarvis.cost_counter.snapshot() if getattr(jarvis, "cost_counter", None) else None,
        "about": {
            "version": VERSION,
            "system": (
                f"Python {sys.version_info.major}.{sys.version_info.minor}"
                f".{sys.version_info.micro} · {platform.system()} {platform.release()}"
            ),
        },
    }


# Diesen Satz muss man exakt eintippen, um ALLE Erinnerungen zu loeschen.
DELETE_ALL_PHRASE = "ALLE ERINNERUNGEN LÖSCHEN"


def memories_state(jarvis):
    return {
        "enabled": bool(jarvis.memory_enabled()),
        "memories": jarvis.memory.list_all(),
        "delete_all_phrase": DELETE_ALL_PHRASE,
        "max_value_length": MAX_VALUE_LENGTH,
    }


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def get_text(data, key):
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Ungueltige Anfrage")

    return value.strip()


def get_id(data, key):
    value = data.get(key)

    # bool ist in Python auch ein int: True waere sonst die ID 1
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(400, "Ungueltige Anfrage")

    return value


def sidebar_state(jarvis, **extra):
    """Antwort fuer alle Aktionen der Seitenleiste: neuer Stand + Zusatz."""
    state = {
        "projects": jarvis.get_tree(),
        "active": jarvis.get_active()
    }
    state.update(extra)
    return state


def conversation_changed(jarvis, before):
    """Hat sich die offene Konversation durch eine Nachricht veraendert?

    Eine normale Nachricht haengt nur etwas an dieselbe Liste an. Anders ist
    es, wenn eine andere Konversation aktiv wurde, die Liste ersetzt wurde
    (Konversation neu geladen) oder kleiner geworden ist (Reset).
    """
    active, messages, count = before
    conversation = jarvis.conversation

    return (
        jarvis.get_active() != active
        or conversation.messages is not messages
        or len(conversation.messages) < count
    )


def api_post(jarvis, path, data):
    """Fuehrt eine POST-Aktion aus. Gibt das Antwort-Dict zurueck."""
    if path == "/api/message":
        conversation = jarvis.conversation
        before = (jarvis.get_active(), conversation.messages, len(conversation.messages))

        response = jarvis.process_message(get_text(data, "message"))

        result = {
            "status": response["status"],
            "content": response["content"]
        }

        # Aktion mit Rueckfrage: Der Browser zeigt Ja/Nein-Knoepfe
        if response.get("status") == "confirmation":
            result["confirmation"] = response["confirmation"]

        # Plan zur Freigabe (Step 5.3): Der Browser zeigt Ausfuehren/Abbrechen
        if response.get("status") == "plan":
            result["plan"] = response["plan"]

        # Chat-Befehle ("Oeffne Projekt X", "Reset", ...) koennen die offene
        # Konversation wechseln oder leeren. Dann bekommt der Browser den neuen
        # Verlauf mit, sonst zeigt das Chatfenster noch den alten.
        if conversation_changed(jarvis, before):
            result["messages"] = [
                dict(message) for message in jarvis.conversation.messages
            ]

        return result

    if path == "/api/confirm":
        # Antwort auf eine Rueckfrage (Step 4.2). Nur "approve": true fuehrt aus,
        # alles andere (fehlt, "true" als Text, 1, ...) zaehlt als Nein.
        response = jarvis.confirm_action(
            get_text(data, "id"), data.get("approve") is True
        )

        return {"status": response["status"], "content": response["content"]}

    if path == "/api/plan/confirm":
        # Wie /api/confirm: nur "approve": true fuehrt den Plan aus
        response = jarvis.confirm_plan(
            get_text(data, "id"), data.get("approve") is True
        )

        return {"status": response["status"], "content": response["content"]}

    if path == "/api/settings":
        category = get_text(data, "category")
        key = get_text(data, "key")
        is_valid = EDITABLE_SETTINGS.get((category, key))

        if is_valid is None or "value" not in data or not is_valid(data["value"]):
            raise ApiError(400, "Diese Einstellung kann so nicht geaendert werden.")

        jarvis.settings_manager.set(category, key, data["value"])
        jarvis.apply_settings()
        return settings_state(jarvis)

    if path == "/api/memory/update":
        key = get_text(data, "key")
        value = get_text(data, "value")
        memory_type = data.get("type")

        if memory_type not in VALID_TYPES:
            raise ApiError(400, "Ungueltiger Typ.")

        if len(value) > MAX_VALUE_LENGTH:
            raise ApiError(
                400, f"Der Wert ist zu lang (höchstens {MAX_VALUE_LENGTH} Zeichen)."
            )

        if not jarvis.memory.update(key, value, memory_type):
            raise ApiError(404, "Diesen Eintrag gibt es nicht mehr.")

        return memories_state(jarvis)

    if path == "/api/memory/delete":
        key = get_text(data, "key")

        # Ohne ausdrueckliche Bestaetigung wird nichts geloescht
        if data.get("confirm") is not True:
            raise ApiError(400, "Löschen braucht eine Bestätigung.")

        if not jarvis.memory.delete(key):
            raise ApiError(404, "Diesen Eintrag gibt es nicht mehr.")

        return memories_state(jarvis)

    if path == "/api/memory/delete_all":
        # Zwei Sicherungen: der exakte Satz UND die Anzahl, die der Nutzer
        # gesehen hat. Hat sich inzwischen etwas geaendert, wird nichts geloescht.
        if data.get("confirm_text") != DELETE_ALL_PHRASE:
            raise ApiError(400, "Der Bestätigungssatz stimmt nicht.")

        count = data.get("count")

        if not isinstance(count, int) or isinstance(count, bool):
            raise ApiError(400, "Ungueltige Anfrage")

        if count != len(jarvis.memory.list_all()):
            raise ApiError(
                409, "Die Liste hat sich geändert. Bitte neu laden und noch einmal prüfen."
            )

        jarvis.memory.delete_all()
        return memories_state(jarvis)

    if path == "/api/project/new":
        jarvis.add_project(get_text(data, "name"))
        return sidebar_state(jarvis)

    if path == "/api/project/open":
        jarvis.select_project(get_id(data, "project_id"))
        return sidebar_state(jarvis)

    if path == "/api/project/rename":
        jarvis.rename_project_by_id(
            get_id(data, "project_id"), get_text(data, "name")
        )
        return sidebar_state(jarvis)

    if path == "/api/project/delete":
        jarvis.delete_project_by_id(get_id(data, "project_id"))
        return sidebar_state(jarvis)

    if path == "/api/conversation/open":
        messages = jarvis.select_conversation(
            get_id(data, "project_id"), get_id(data, "conversation_id")
        )
        return sidebar_state(jarvis, messages=messages)

    if path == "/api/conversation/new":
        project_id = data.get("project_id")

        if project_id is not None:
            project_id = get_id(data, "project_id")

        jarvis.add_conversation(get_text(data, "title"), project_id)
        return sidebar_state(jarvis, messages=[])

    if path == "/api/conversation/rename":
        jarvis.rename_conversation_by_id(
            get_id(data, "project_id"),
            get_id(data, "conversation_id"),
            get_text(data, "title")
        )
        return sidebar_state(jarvis)

    if path == "/api/conversation/reset":
        jarvis.reset_conversation_by_id(
            get_id(data, "project_id"), get_id(data, "conversation_id")
        )
        return sidebar_state(jarvis)

    if path == "/api/conversation/delete":
        jarvis.delete_conversation_by_id(
            get_id(data, "project_id"), get_id(data, "conversation_id")
        )
        return sidebar_state(jarvis)

    raise ApiError(404, "Unbekannte Adresse")


class BackgroundFeed:
    """Sammelt Meldungen aus dem Hintergrund (z.B. Timer) fuer alle Browser-Tabs.

    Jarvis gibt jede Meldung nur einmal heraus. Wuerde jeder Tab direkt dort
    nachfragen, bekaeme nur ein zufaelliger Tab die Meldung (z.B. ein altes,
    vergessenes Fenster). Hier bekommt jede Meldung eine laufende Nummer, und
    jeder Tab fragt "alles nach Nummer X".
    """

    MAX_KEPT = 100

    def __init__(self):
        self.lock = threading.Lock()
        self.items = []   # [(id, text)]
        self.last = 0

    def collect(self, jarvis):
        with self.lock:
            for text in jarvis.check_background_results():
                self.last += 1
                self.items.append((self.last, text))

            del self.items[:-self.MAX_KEPT]

    def since(self, after):
        with self.lock:
            return self.last, [
                {"id": item_id, "text": text}
                for item_id, text in self.items
                if item_id > after
            ]


GUEST_DENIED = {"error": "Im Gastmodus nicht verfügbar."}


class JarvisServer(ThreadingHTTPServer):
    daemon_threads = True
    # Die Standard-Warteschlange fasst nur 5 neue Verbindungen. Die Seite fragt
    # jede Sekunde Hintergrund und Timer ab, ein Test schickt viele Anfragen
    # kurz hintereinander: auf Windows kann sonst eine Verbindung ins Leere laufen.
    request_queue_size = 128

    def __init__(self, address, jarvis, guest=False, widget_store=None, hockey=None, weather=None, monitor=None):
        super().__init__(address, JarvisHandler)
        self.jarvis = jarvis
        self.guest = guest
        self.widget_store = widget_store or widgets.default_store()
        self.hockey = hockey or widgets.HockeyFeed()
        self.weather = weather or weather_tool.default_service()
        self.monitor = monitor or system_status_tool.PerformanceMonitor()
        self.feed = BackgroundFeed()
        # Jarvis ist nicht fuer mehrere gleichzeitige Nachrichten gebaut.
        self.message_lock = threading.Lock()


class JarvisHandler(BaseHTTPRequestHandler):
    server_version = "Jarvis"

    # --- Hilfen ---------------------------------------------------------

    def log_message(self, format, *args):
        pass  # keine Zeile pro Anfrage im Terminal

    def handle_one_request(self):
        """Bricht der Browser eine Anfrage ab (Seite neu geladen, Stopp beim Vorlesen,
        naechster Satz vorgeladen), ist das kein Fehler: keine Meldung im Terminal."""
        try:
            super().handle_one_request()
        except ConnectionError:
            self.close_connection = True

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def guest_get(self, path):
        """Gastmodus: nur Einstellungen (Standardwerte) und eine leere Hintergrund-Liste."""
        if path == "/api/settings":
            return self.send_json(200, settings_state(self.server.jarvis))

        if path == "/api/background":
            return self.send_json(200, {"messages": [], "last": 0})

        return self.send_json(403, GUEST_DENIED)

    def handle_speak(self, data):
        jarvis = self.server.jarvis
        text = data.get("text")

        try:
            audio = speech.synthesize(
                getattr(jarvis, "client", None),
                text,
                jarvis.settings_manager.get("voice", "voice", speech.DEFAULT_VOICE),
            )
        except speech.SpeechError as error:
            return self.send_json(400 if not isinstance(text, str) or not text.strip() else 502,
                                  {"error": str(error)})

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)

    def host_allowed(self):
        """Nur Anfragen an localhost zulassen (Schutz vor DNS-Rebinding)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("localhost", "127.0.0.1", "[::1]")

    def origin_allowed(self):
        """Eine fremde Webseite darf Jarvis nicht fernsteuern."""
        origin = self.headers.get("Origin")

        if origin is None:
            return True

        return urlparse(origin).hostname in ("localhost", "127.0.0.1", "::1")

    # --- Anfragen -------------------------------------------------------

    def do_GET(self):
        if not self.host_allowed():
            return self.send_json(403, {"error": "Host nicht erlaubt"})

        path = urlparse(self.path).path

        if self.server.guest and path.startswith("/api/"):
            return self.guest_get(path)

        if path == "/api/timers":
            return self.send_json(200, {"timers": timer.list_timers()})

        if path == "/api/ringing":
            return self.send_json(200, ringing.default_ringer().state())

        if path == "/api/alarms":
            return self.send_json(200, {"alarms": reminders.default_store().alarms_overview()})

        if path == "/api/background":
            feed = self.server.feed
            feed.collect(self.server.jarvis)

            after = parse_qs(urlparse(self.path).query).get("after")

            # Ohne "after" (neuer Tab): nur den aktuellen Stand melden, nichts
            # Altes nachliefern.
            if after is None:
                return self.send_json(200, {"messages": [], "last": feed.since(0)[0]})

            try:
                after = int(after[0])
            except ValueError:
                return self.send_json(400, {"error": "Ungueltige Anfrage"})

            last, messages = feed.since(after)
            return self.send_json(200, {"messages": messages, "last": last})

        if path == "/api/settings":
            return self.send_json(200, settings_state(self.server.jarvis))

        # Seitenleiste: Notizen und Ziele (lokale Datei), Spielplan (Server holt ihn selbst)
        if path == "/api/widgets":
            return self.send_json(200, self.server.widget_store.get())

        if path == "/api/hockey":
            team = self.server.jarvis.settings_manager.get("widgets", "bottom")
            if team not in widgets.TEAMS:
                return self.send_json(200, {"team": None})
            try:
                return self.send_json(200, self.server.hockey.get(team))
            except widgets.HockeyError as error:
                return self.send_json(502, {"error": str(error)})

        # PC-Fakten und Leistungsdaten fuer die Widgets (lokal gelesen, kein Internet)
        if path == "/api/system":
            try:
                return self.send_json(200, system_status_tool.facts())
            except Exception:
                return self.send_json(502, {"error": "Die Systemdaten konnten nicht gelesen werden."})

        if path == "/api/performance":
            try:
                return self.send_json(200, self.server.monitor.sample())
            except Exception:
                return self.send_json(502, {"error": "Die Leistungsdaten konnten nicht gelesen werden."})

        if path == "/api/weather":
            # Kurzer Satz fuer den Startbericht. Nie ein Fehler: ohne Wetter faellt der Satz einfach weg.
            summary = None
            if abilities.task_enabled("GET_WEATHER", self.server.jarvis.settings_manager):
                try:
                    summary = self.server.weather.summary()
                except Exception:
                    summary = None
            return self.send_json(200, {"summary": summary})

        if path == "/api/memories":
            try:
                return self.send_json(200, memories_state(self.server.jarvis))
            except ConnectionError:
                raise            # Browser hat aufgelegt: kein Fehler von Jarvis
            except Exception:
                traceback.print_exc()
                return self.send_json(500, {"error": "Das Gedaechtnis konnte nicht geladen werden."})

        if path == "/api/actions":
            try:
                return self.send_json(200, {"actions": action_log.recent(100)})
            except ConnectionError:
                raise            # Browser hat aufgelegt: kein Fehler von Jarvis
            except Exception:
                traceback.print_exc()
                return self.send_json(500, {"error": "Das Aktionsprotokoll konnte nicht geladen werden."})

        if path == "/api/projects":
            try:
                return self.send_json(200, sidebar_state(self.server.jarvis))
            except ConnectionError:
                raise            # Browser hat aufgelegt: kein Fehler von Jarvis
            except Exception:
                traceback.print_exc()
                return self.send_json(500, {"error": "Projekte konnten nicht geladen werden."})

        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Unbekannte Adresse"})

        self.send_static(path)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1

        raw = b""

        if 0 < length <= MAX_DRAIN_BYTES:
            raw = self.rfile.read(length)
        elif length > MAX_DRAIN_BYTES:
            self.close_connection = True

        if not self.host_allowed() or not self.origin_allowed():
            return self.send_json(403, {"error": "Nicht erlaubt"})

        path = urlparse(self.path).path

        if not path.startswith("/api/"):
            return self.send_json(404, {"error": "Unbekannte Adresse"})

        # Nur JSON: ein fremdes Formular kann diesen Typ nicht ohne
        # Vorab-Pruefung des Browsers senden.
        content_type = (self.headers.get("Content-Type") or "").split(";")[0]

        if content_type.strip() != "application/json":
            return self.send_json(415, {"error": "Nur application/json"})

        if length <= 0 or length > MAX_BODY_BYTES:
            return self.send_json(400, {"error": "Ungueltige Laenge"})

        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self.send_json(400, {"error": "Ungueltige Anfrage"})

        if not isinstance(data, dict):
            return self.send_json(400, {"error": "Ungueltige Anfrage"})

        if self.server.guest and path != "/api/message":
            return self.send_json(403, GUEST_DENIED)

        try:
            # Alles, was den Zustand von Jarvis aendert, laeuft nacheinander.
            # So wechselt niemand die Konversation, waehrend eine Antwort
            # noch in die alte gespeichert wird.
            # Stopp fuer einen laufenden Plan: bewusst OHNE message_lock, denn der
            # laufende Plan haelt ihn. Es wird nur ein Merker gesetzt.
            if self.server.guest:
                # Nur Nachrichten, und nur an den Gast-Jarvis (guest.py)
                with self.server.message_lock:
                    response = self.server.jarvis.process_message(get_text(data, "message"))
                return self.send_json(200, {"status": "response", "content": response["content"]})

            if path == "/api/plan/abort":
                return self.send_json(200, {"aborted": bool(self.server.jarvis.abort_plan())})

            # Sprachausgabe: Text rein, MP3 raus. Ohne message_lock, damit Jarvis
            # beim Vorlesen nicht auf die naechste Nachricht warten muss.
            if path == "/api/speak":
                return self.handle_speak(data)

            # Notizen und Ziele speichern: kleine lokale Datei, braucht den message_lock nicht
            if path in ("/api/widgets/notes", "/api/widgets/goals", "/api/widgets/events",
                        "/api/widgets/events/delete", "/api/widgets/events/delete_series"):
                store = self.server.widget_store
                try:
                    if path.endswith("notes"):
                        store.set_notes(data.get("text"))
                    elif path.endswith("goals"):
                        store.set_goals(data.get("items"))
                    elif path.endswith("delete"):
                        store.delete_event(data.get("id"))
                    elif path.endswith("delete_series"):
                        store.delete_series(data.get("series"))
                    else:
                        store.add_event(data.get("title"), data.get("date"), data.get("time", ""))
                except ValueError as error:
                    return self.send_json(400, {"error": str(error)})
                return self.send_json(200, self.server.widget_store.get())

            # Wecker im Kalender anlegen: Tag aus dem Kalender, Wiederholung wie beim Chat (recurrence.py)
            if path == "/api/alarms/add":
                fields = {key: data.get(key) for key in ("time", "label", "date", "repeat", "until")}
                if any(value is not None and not isinstance(value, str) for value in fields.values()) \
                        or not isinstance(data.get("briefing", False), bool):
                    return self.send_json(400, {"error": "Ungültige Angaben."})
                store = reminders.default_store()
                try:
                    store.add(fields["label"], fields["date"] or "", fields["time"], fields["repeat"] or None,
                              None, None, fields["until"] or None, kind="alarm", briefing=data.get("briefing", False))
                except reminders.ReminderError as error:
                    return self.send_json(400, {"error": str(error)})
                return self.send_json(200, {"alarms": store.alarms_overview()})

            # Wecker im Kalender aendern oder loeschen: kleine lokale Datei, braucht den message_lock nicht
            if path in ("/api/alarms/delete", "/api/alarms/update"):
                alarm_id = data.get("id")
                if not isinstance(alarm_id, str) or not alarm_id or len(alarm_id) > 40:
                    return self.send_json(400, {"error": "Ungültiger Wecker."})
                store = reminders.default_store()
                try:
                    if path.endswith("delete"):
                        store.delete_alarm(alarm_id)
                    else:
                        store.update_alarm(alarm_id, time=data.get("time"), label=data.get("label"),
                                           briefing=data.get("briefing"), day=data.get("date"))
                except reminders.ReminderError as error:
                    return self.send_json(400, {"error": str(error)})
                return self.send_json(200, {"alarms": store.alarms_overview()})

            # Wecker/Timer ausschalten oder schlummern: soll sofort gehen, auch waehrend Jarvis antwortet
            if path == "/api/ringing/stop":
                ring_id = data.get("id")
                if ring_id is not None and (isinstance(ring_id, bool) or not isinstance(ring_id, int)):
                    return self.send_json(400, {"error": "Ungültige Nummer."})
                ringer = ringing.default_ringer()
                address = get_address()
                if data.get("snooze") is True:
                    stopped, minutes = ringer.snooze(data.get("minutes"), which=ring_id)
                    reply = ringing.snooze_message(minutes, address) if stopped else ""
                else:
                    stopped = ringer.stop(which=ring_id)
                    reply = ringing.stop_message(stopped, address, ringer) if stopped else ""
                return self.send_json(200, {"stopped": [r["label"] for r in stopped], "reply": reply, "state": ringer.state()})

            # Timer abbrechen: harmlos und soll auch gehen, waehrend Jarvis antwortet
            if path == "/api/timer/cancel":
                timer_id = data.get("id")
                if isinstance(timer_id, bool) or not isinstance(timer_id, int):
                    return self.send_json(400, {"error": "Ungültige Timer-Nummer."})
                return self.send_json(200, {"cancelled": timer.cancel_timer_by_id(timer_id)})

            with self.server.message_lock:
                result = api_post(self.server.jarvis, path, data)
        except ApiError as error:
            return self.send_json(error.status, {"error": str(error)})
        except WorkspaceError as error:
            return self.send_json(400, {"error": str(error)})
        except ConnectionError:
            raise            # Browser hat aufgelegt: kein Fehler von Jarvis (siehe handle_one_request)
        except ConnectionError:
            raise            # Browser hat aufgelegt: kein Fehler von Jarvis
        except Exception:
            traceback.print_exc()
            return self.send_json(500, {"error": "Interner Fehler. Details im Terminal."})

        self.send_json(200, result)

    def send_static(self, url_path):
        if url_path == "/":
            url_path = "/index.html"

        # Nur Dateien innerhalb von web/ ausliefern (kein "../")
        target = (WEB_DIR / url_path.lstrip("/")).resolve()

        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            return self.send_json(404, {"error": "Nicht gefunden"})

        body = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Weboberflaeche")
    parser.add_argument("--guest", action="store_true",
                        help="Gastmodus: nur plaudern, Uhrzeit, Datum, Rechnen, Websuche (siehe guest.py)")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Port (Standard aus config.py)")
    args = parser.parse_args(argv)

    if args.guest:
        # Bewusst KEIN Jarvis-Objekt: keine Datenbank, kein Gedaechtnis, keine Projekte.
        from openai import OpenAI
        from config import OPENAI_TIMEOUT
        import cost_guard
        from guest import GUEST_AI_CALLS_PER_DAY, GuestJarvis

        counter = cost_guard.UsageCounter("usage_guest.json", lambda: {"ai": GUEST_AI_CALLS_PER_DAY, "speech": 1})
        jarvis = GuestJarvis(cost_guard.guard(OpenAI(timeout=OPENAI_TIMEOUT), counter))
    else:
        from jarvis import Jarvis

        jarvis = Jarvis()
        reminders.start_scheduler()         # Erinnerungen (Step 2.9): nur im normalen Modus, nie im Gastmodus
        ringing.start_ticker()              # beendet zu lange laeutende Wecker/Timer (Step 2.11)

    server = JarvisServer((SERVER_HOST, args.port), jarvis, guest=args.guest)
    url = f"http://localhost:{server.server_address[1]}"

    print(f"J.A.R.V.I.S. {'(GASTMODUS) ' if args.guest else ''}laeuft auf {url}  (beenden mit Strg+C)")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nJ.A.R.V.I.S.: Shutting down, {get_address()}")
    finally:
        reminders.stop_scheduler()
        ringing.stop_ticker()               # Ton aus, wenn der Server endet
        server.server_close()


if __name__ == "__main__":
    main()
