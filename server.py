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
       POST /api/hints -> faellige proaktive Hinweise: {"hints": [{"kind", "text"}]} (Step 2.29, nur Anzeige)
       POST /api/goals/evening -> Abendfrage zu offenen Zielen: {"text": ...} oder null (Step 2.28)
       POST /api/briefing/auto -> Tagesbriefing beim ersten Start des Tages: {"text": ...} oder null (Step 2.12)
       GET  /api/gym         ->  Gym-Plan: heutiges Training mit Zielen und der ganze Wochenplan; POST /api/gym/plan (nur PC), /api/gym/log, /api/gym/clear
       GET  /api/folders     ->  freigegebene Ordner; POST /api/folders/add und /api/folders/remove pflegen sie (Step 2.14)
       GET  /api/focus       ->  laufende Fokus-Sitzung (Phase, Runde, Restzeit); POST /api/focus/stop beendet sie (Step 2.13)
       GET  /api/ringing     ->  was gerade laeutet (Wecker/Timer) und wer den Ton macht (Step 2.11)
       POST /api/ringing/stop ->  ausschalten oder schlummern, auch waehrend Jarvis antwortet
       GET  /api/system      ->  PC-Fakten fuer das Widget "PC Facts" (Step 2.8, lokal gelesen)
       GET  /api/performance ->  CPU, RAM, Laufwerk, Akku, Netzwerk fuer das Widget "Performance"
       GET  /api/reminders   ->  {"reminders": [{"id", "text", "due", "repeat"}]}  (naechste Erinnerungen, nur lesen; Willkommensseite)
       GET  /api/news        ->  {"items": [{"title", "source", "summary", "url", "published"}]}  (Schlagzeilen, nur lesen; Willkommensseite)
       GET  /api/briefing    ->  {"text": "..."}  (Tagesbriefing zum Lesen, ohne den Tagesmerker zu setzen; Willkommensseite)
       GET  /api/pc_lage     ->  {"pc_lage": {"now", "drives", "programs", "autostart", "assessment"}}  (SSD/HDD, Last, Verbraucher, Ampel mit Tipps; nur am PC; Willkommensseite)
       POST /api/media {"action": "play_pause"|"next"|"previous"}  ->  Medientaste (nur am PC); POST /api/volume {"percent": 0-100}  (nur am PC)
       GET  /api/timers      ->  {"timers": [{"id", "name", "seconds", "remaining"}]}  (laufende Timer, Step 6b)
       POST /api/speak {"text": "..."}  ->  audio/mpeg  (Sprachausgabe mit der eingestellten Stimme, Step 6b)
       POST /api/timer/cancel {"id": 3}  ->  {"cancelled": true|false}  (einen Timer abbrechen)
       GET  /api/projects    ->  {"projects": [...], "active": {...}}
       GET  /api/remote/state ->  Remote-Verwaltung am PC: Schalter, Stufen, Geraete (R4); POST /api/remote/pair_link, /revoke, /restore, /revoke_all, /forget, /profile_add, /profile_limits, /profile_delete, /profile_reset, /profile_reset_usage
       GET  /api/sync?known=<v> ->  Live-Abgleich: {"version", "active"} und bei neuem Stand "messages" + "projects" (R2b)
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

import hashlib
import json
import platform
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import abilities
import action_log
import calendar_sync
import device_commands
import device_hub
import device_page
import speech
import tester as tester_module
import timer
import reminders
import focus
import gym
import folders
import profiles as profile_module
import remote_policy
import ringing
import widgets
from tools import media_tool, news_tool, pc_health, system_status_tool, volume_tool, weather_tool
from config import REMOTE_HOST, SERVER_HOST, SERVER_PORT, VERSION
from memory import MAX_VALUE_LENGTH, VALID_TYPES
from personality import get_address, is_valid_address
from profiles import OWNER
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
    ".webmanifest": "application/manifest+json; charset=utf-8",
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
EDITABLE_SETTINGS[("focus", "work_minutes")] = lambda v: _is_int(v, 1, 120)
EDITABLE_SETTINGS[("focus", "break_minutes")] = lambda v: _is_int(v, 1, 60)
EDITABLE_SETTINGS[("focus", "long_break_minutes")] = lambda v: _is_int(v, 1, 60)
EDITABLE_SETTINGS[("focus", "rounds")] = lambda v: _is_int(v, 1, 12)
EDITABLE_SETTINGS[("briefing", "auto")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("briefing", "news")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("hints", "appointments")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("hints", "appointment_minutes")] = lambda v: _is_int(v, 5, 120)
EDITABLE_SETTINGS[("hints", "weather")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("hints", "weather_hour")] = lambda v: _is_int(v, 15, 23)
EDITABLE_SETTINGS[("hints", "pc")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("goals", "evening")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("goals", "evening_hour")] = lambda v: _is_int(v, 17, 23)
# Zugriff vom Handy (Remote): nur am PC aenderbar, das Handy hat keinen Zugriff auf /api/settings (remote_policy.py)
EDITABLE_SETTINGS[("remote", "enabled")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("remote", "info")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("remote", "daily")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("remote", "pc")] = lambda v: isinstance(v, bool)
EDITABLE_SETTINGS[("remote", "max_messages")] = lambda v: _is_int(v, 0, 1000)
EDITABLE_SETTINGS[("remote", "max_ai_per_day")] = lambda v: _is_int(v, 0, 100000)
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


def agent_status(srv):
    """Ist der PC-Agent verbunden (S6)? {"online", "name"}; ohne Remote gibt es keinen Agent."""
    gate = srv.remote
    device_id = srv.hub.online_device() if gate is not None else None
    name = next((d["name"] for d in gate.store.devices() if d["id"] == device_id), "") if device_id else ""
    return {"online": device_id is not None, "name": name}


def agent_ping(srv):
    """Verbindungstest: ein "ping" an den PC-Agent. Immer 200; bei Fehlern steht der Grund in "error"."""
    try:
        result = srv.hub.request("ping")
    except (device_hub.DeviceOffline, device_hub.DeviceTimeout, device_hub.DeviceFailed) as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "result": result}


def remote_panel_state(gate, now=None):
    """Die Remote-Verwaltung am PC (R4): was die Einstellungsseite zeigt. Nie Hashes oder Codes."""
    now = time.time() if now is None else now

    if gate is None:
        return {"available": False, "host": "", "enabled": False, "active": False,
                "levels": dict(remote_policy.DEFAULT_LEVELS), "devices": [], "pending": 0, "profiles": []}

    profiles = gate.profiles.list() if gate.profiles is not None else []
    names = {p["id"]: p["name"] for p in profiles}
    all_devices = sorted(gate.store.devices(), key=lambda d: d["created"], reverse=True)

    devices = [
        {"id": d["id"], "name": d["name"], "created": d["created"], "last_seen": d["last_seen"],
         "revoked": bool(d["revoked"]), "expired": d["expires"] <= now,
         "profile": d["profile"], "profile_name": names.get(d["profile"], "") if d["profile"] != OWNER else "",
         "agent": bool(d.get("agent"))}
        for d in all_devices
    ]
    profile_list = [
        {"id": p["id"], "name": p["name"], "limits": p["limits"],
         "devices": sum(1 for d in all_devices if d["profile"] == p["id"] and not d["revoked"])}
        for p in profiles
    ]

    return {
        "available": bool(gate.host),
        "host": gate.host,
        "enabled": gate.settings.get("remote", "enabled", False) is True,
        "active": gate.active(),
        "levels": gate.levels(),
        "devices": devices,
        "pending": gate.store.pending_count(),
        "profiles": profile_list,
    }


def remote_admin_post(gate, path, data, own_id=None):
    """Remote-Verwaltung am PC: Koppel-Link erzeugen, Geraete sperren oder entfernen. Gibt (Status, Antwort) zurueck."""
    if gate is None:
        return 404, {"error": "Remote ist nicht eingerichtet."}

    if path == "/api/remote/pair_link":
        if not gate.host:
            return 400, {"error": "Der Remote-Name fehlt: Trage JARVIS_REMOTE_HOST in die .env ein."}

        if not gate.active():
            return 400, {"error": "Remote ist ausgeschaltet. Schalte es zuerst ein."}

        name = data.get("name")

        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
            return 400, {"error": "Bitte einen Namen für das Gerät angeben (höchstens 40 Zeichen)."}

        profile = data.get("profile", OWNER)

        if not isinstance(profile, str) or not profile or len(profile) > 64:
            return 400, {"error": "Ungültiger Bereich."}

        if profile != OWNER and (gate.profiles is None or gate.profiles.get(profile) is None):
            return 400, {"error": "Diesen Gast-Bereich gibt es nicht."}

        pairing = gate.store.create_pairing(name, profile)

        return 200, {
            "link": f"https://{gate.host}/pair#{pairing['code']}",
            "code": pairing["code"],
            "profile": profile,
            "name": pairing["name"],
            "expires_in": max(0, int(pairing["expires"] - gate.store.clock())),
            "state": remote_panel_state(gate),
        }

    if path == "/api/remote/revoke_all":
        count = gate.store.revoke_all(keep=own_id)          # das Geraet, an dem du sitzt, bleibt (sonst sperrst du dich aus)
        return 200, {"revoked": count, "state": remote_panel_state(gate)}

    if path in PROFILE_PATHS:
        return remote_profile_post(gate, path, data)

    device_id = data.get("id")

    if not isinstance(device_id, str) or not device_id or len(device_id) > 64:
        return 400, {"error": "Ungültige Anfrage"}

    if own_id is not None and device_id == own_id and path in ("/api/remote/revoke", "/api/remote/forget"):
        return 400, {"error": "Das ist dieses Gerät. Sperrst oder entfernst du es, bist du ausgesperrt."}

    actions = {"/api/remote/revoke": gate.store.revoke, "/api/remote/restore": gate.store.restore, "/api/remote/forget": gate.store.forget}
    done = actions[path](device_id)

    if not done:
        return 404, {"error": "Gerät nicht gefunden."}

    return 200, {"state": remote_panel_state(gate)}


PROFILE_PATHS = ("/api/remote/profile_add", "/api/remote/profile_limits", "/api/remote/profile_delete",
                 "/api/remote/profile_reset", "/api/remote/profile_reset_usage")


def remote_profile_post(gate, path, data):
    """Gast-Bereiche verwalten (C1): anlegen, Limits, zuruecksetzen, loeschen. Nur am PC."""
    if gate.profiles is None:
        return 404, {"error": "Gast-Bereiche sind nicht eingerichtet."}

    try:
        if path == "/api/remote/profile_add":
            created = gate.profiles.create(data.get("name"))
            return 200, {"profile": created["id"], "state": remote_panel_state(gate)}

        profile_id = data.get("id")

        if not isinstance(profile_id, str) or not profile_module.is_profile_id(profile_id):
            return 400, {"error": "Ungültige Anfrage"}

        if path == "/api/remote/profile_limits":
            limits = {key: data[key] for key in profile_module.DEFAULT_LIMITS if key in data}
            if not limits:
                return 400, {"error": "Kein Limit angegeben."}
            gate.profiles.set_limits(profile_id, **limits)
        elif path == "/api/remote/profile_reset":
            if not gate.profiles.reset_data(profile_id):
                return 404, {"error": "Bereich nicht gefunden."}
        elif path == "/api/remote/profile_reset_usage":
            if not gate.profiles.reset_usage(profile_id):
                return 404, {"error": "Bereich nicht gefunden."}
        else:
            if gate.profiles.get(profile_id) is None:
                return 404, {"error": "Bereich nicht gefunden."}
            gate.store.remove_profile_devices(profile_id)      # erst die Geraete (kein Zugriff mehr), dann der Bereich mit seinen Daten
            gate.profiles.delete(profile_id)
    except profile_module.ProfileError as error:
        return 400, {"error": str(error)}
    except KeyError:
        return 404, {"error": "Bereich nicht gefunden."}

    return 200, {"state": remote_panel_state(gate)}


def sync_state(jarvis, known=""):
    """Live-Abgleich (R2b): Stand der offenen Konversation als kurzer Fingerabdruck.

    PC und Handy fragen alle paar Sekunden nach. Ist der Fingerabdruck anders als
    der, den die Seite kennt, kommen Verlauf und Seitenleiste gleich mit, sonst nur
    die Version. Gelesen wird ohne message_lock: eine halbfertige Antwort steht
    erst in der Liste, wenn sie fertig ist.
    """
    active = jarvis.get_active()
    messages = [dict(message) for message in list(jarvis.conversation.messages)]

    raw = json.dumps([active, messages], sort_keys=True, default=str, ensure_ascii=False)
    version = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    state = {"version": version, "active": active}

    if known != version:
        state["messages"] = messages
        state["projects"] = jarvis.get_tree()

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

    def add(self, text):
        """Eine fertige Meldung (z. B. ein Hinweis) hinzufuegen; alle Seiten holen sie mit ab."""
        with self.lock:
            self.last += 1
            self.items.append((self.last, text))
            del self.items[:-self.MAX_KEPT]

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

    def __init__(self, address, jarvis, guest=False, widget_store=None, hockey=None, weather=None, monitor=None, remote=None, health=None, hub=None,
                 gym_store=None):
        super().__init__(address, JarvisHandler)
        self.hub = hub or device_hub.DeviceHub()      # Warteschlange zum PC-Agent (S6)
        self.jarvis = jarvis
        self.guest = guest
        self.remote = remote          # Pforte fuer Zugriff vom Handy (remote_gate.py), None = Remote gibt es nicht
        self.widget_store = widget_store or widgets.default_store()
        # Gym-Plan: nur beim Besitzer (der Standard-Speicher); in Tests nur, wenn einer uebergeben wird
        self.gym_store = gym_store or (gym.default_store() if widget_store is None and not guest else None)
        if self.gym_store is not None and self.widget_store.gym is None:
            self.widget_store.gym = self.gym_store
        self.hockey = hockey or widgets.HockeyFeed()
        self.weather = weather or weather_tool.default_service()
        self.monitor = monitor or system_status_tool.PerformanceMonitor()
        self.health = health or pc_health.default_health()
        self.feed = BackgroundFeed()
        self.hints_by_loop = False    # Server-Betrieb (server_loop.py): der Takt holt die Hinweise ab, nicht die Seite
        # Jarvis ist nicht fuer mehrere gleichzeitige Nachrichten gebaut.
        self.message_lock = threading.Lock()
        # Gast-Bereiche (Mark 5, C3): pro Bereich ein eigener TesterJarvis, erst beim ersten Zugriff gebaut
        self._testers = {}
        self._tester_lock = threading.Lock()
        self._tester_defaults = None

    def tester_for(self, profile_id):
        """Der Jarvis dieses Gast-Bereichs, oder None, wenn es den Bereich nicht (mehr) gibt."""
        gate = self.remote
        if gate is None or gate.profiles is None or not profile_module.is_profile_id(profile_id) or gate.profiles.get(profile_id) is None:
            return None
        with self._tester_lock:
            found = self._testers.get(profile_id)
            if found is None:
                raw = getattr(self.jarvis, "client", None)
                raw = getattr(raw, "_client", raw)          # der Gast zaehlt nie auf dem Konto des Besitzers
                found = tester_module.TesterJarvis(profile_id, gate.profiles.path_for(profile_id), gate.profiles, raw)
                self._testers[profile_id] = found
            return found

    def tick_testers(self):
        """Faellige Erinnerungen aller Gast-Bereiche melden (jede nur in der App ihres Gastes). Gibt die Zahl zurueck."""
        gate = self.remote
        if gate is None or gate.profiles is None:
            return 0
        count = 0
        for profile in gate.profiles.list():
            found = self.tester_for(profile["id"])
            if found is not None:
                try:
                    count += found.check_reminders()
                except Exception:
                    pass        # ein Gast darf den Takt der anderen nie anhalten
        return count

    def start_tester_ticker(self, interval=reminders.CHECK_SECONDS):
        stop = threading.Event()

        def run():
            while not stop.wait(interval):
                self.tick_testers()

        threading.Thread(target=run, name="tester-reminders", daemon=True).start()
        return stop

    def tester_defaults(self):
        """Standard-Einstellungen fuer Gaeste: eine Wegwerf-Datei, nie die settings.json des Besitzers."""
        if self._tester_defaults is None:
            manager = SettingsManager(Path(tempfile.mkdtemp()) / "tester_settings.json")
            defaults = manager.get_all()
            defaults["voice"] = dict(defaults["voice"], engine="Browser")       # die Stimme von OpenAI kostet den Besitzer Geld: nur die des Browsers
            self._tester_defaults = {"settings": defaults, "about": {"version": VERSION, "system": ""}}
        return self._tester_defaults


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

    def end_headers(self):
        # Antworten ueber den Remote-Namen: Browser soll nichts raten und keine Adresse weitergeben
        if getattr(self, "kind", None) == "remote" or getattr(self, "via_remote", False):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_json(self, status, data, headers=()):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
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

    def request_kind(self):
        """"local" (am PC), "remote" (vom Handy ueber den Remote-Namen) oder None (abgelehnt)."""
        host_header = self.headers.get("Host")
        if (host_header or "").rsplit(":", 1)[0] in ("localhost", "127.0.0.1", "[::1]"):
            return "local"
        gate = self.server.remote
        if gate is None:
            return None
        return gate.request_kind(host_header, self.client_address[0])

    def host_allowed(self):
        """Nur Anfragen an localhost (oder, wenn eingeschaltet, an den Remote-Namen) zulassen (Schutz vor DNS-Rebinding)."""
        return self.request_kind() is not None

    def origin_allowed(self):
        """Eine fremde Webseite darf Jarvis nicht fernsteuern."""
        origin = self.headers.get("Origin")
        kind = getattr(self, "kind", None) or self.request_kind()

        if kind == "remote":
            return self.server.remote.origin_ok("remote", origin)

        if origin is None:
            return True

        return urlparse(origin).hostname in ("localhost", "127.0.0.1", "::1")

    # --- Zugriff vom Handy (Remote, siehe DESIGN_REMOTE.md) --------------------

    def remote_get(self, path):
        """Pforte fuer GET-Anfragen ueber den Remote-Namen. True = Antwort ist schon gesendet."""
        gate = self.server.remote
        self.device = gate.device_from_cookie(self.headers.get("Cookie"))

        if self.device is None:
            if remote_policy.is_public("GET", path):
                self.send_static("/pair.html")
            elif path in remote_policy.PUBLIC_STATIC:
                self.send_static(path)
            elif path.startswith("/api/"):
                self.send_json(401, {"error": "Nicht angemeldet.", "pair": True})
            else:
                self.send_static("/pair.html", status=401)     # nicht gekoppelt: die Seite erklaert, was zu tun ist
            return True

        if self.device["profile"] != OWNER:
            # Gast-Bereich: eigene, kurze Liste. Alles andere unter /api/ ist 403, nie der Weg in den Code des Besitzers.
            if path.startswith("/api/"):
                self.tester_get(path)
                return True
            if remote_policy.is_public("GET", path):
                self.send_static("/pair.html")
                return True
            target = remote_policy.guest_file(path)       # Gast-Seite und nur ihre Dateien, sonst 404
            if target is None:
                self.send_json(404, {"error": "Nicht gefunden"})
            else:
                self.send_static(target)
            return True

        if self.device.get("full") is True:
            return self.become_owner()                    # Vollzugriff (Server-Betrieb): ab hier wie am PC

        if path.startswith("/api/") and not remote_policy.api_allowed("GET", path):
            self.send_json(403, {"error": "Über Remote nicht verfügbar."})
            return True

        if path == "/api/remote/whoami":
            self.send_json(200, {"remote": True, "device": self.device["name"], "levels": gate.levels()})
            return True

        if path == "/api/settings":
            self.send_json(200, gate.settings_for_remote(settings_state(self.server.jarvis)))
            return True

        if remote_policy.is_public("GET", path):
            self.send_static("/pair.html")
            return True

        return False

    def remote_post(self, path, data):
        """Pforte fuer POST-Anfragen ueber den Remote-Namen. True = Antwort ist schon gesendet."""
        gate = self.server.remote

        if remote_policy.is_public("POST", path):
            code = data.get("code")
            previous = gate.device_from_cookie(self.headers.get("Cookie"))      # schon gekoppelt? Dann wechselt das Geraet nur
            status, token, device = gate.store.redeem(code if isinstance(code, str) else None, "remote-pairing")
            if status == "ok":
                if previous is not None and previous["id"] != device["id"]:
                    gate.store.forget(previous["id"])             # der alte Zugang dieses Geraets verschwindet aus der Liste
                self.send_json(200, {"ok": True, "name": device["name"]},
                               headers=[("Set-Cookie", gate.set_cookie_header(token))])
            elif status == "locked":
                self.send_json(429, {"error": "Zu viele Versuche. Bitte später noch einmal."})
            else:
                self.send_json(400, {"error": "Der Link ist ungültig, abgelaufen oder schon benutzt."})
            return True

        self.device = gate.device_from_cookie(self.headers.get("Cookie"))

        if self.device is None:
            self.send_json(401, {"error": "Nicht angemeldet.", "pair": True})
            return True

        if path == "/api/remote/logout":
            gate.store.forget(self.device["id"])                 # Eintrag weg, das Token ist ungueltig
            self.send_json(200, {"ok": True}, headers=[("Set-Cookie", gate.clear_cookie_header())])
            return True

        if self.device["profile"] != OWNER:
            self.tester_post(path, data)
            return True

        if self.device.get("full") is True:
            return self.become_owner()                    # Vollzugriff (Server-Betrieb): ab hier wie am PC

        if not remote_policy.api_allowed("POST", path, gate.levels()):
            self.send_json(403, {"error": "Über Remote nicht verfügbar."})
            return True

        return False

    def become_owner(self):
        """Gekoppeltes Geraet mit Vollzugriff (nur im Server-Terminal vergeben, DESIGN_SERVER.md): der Rest der Anfrage laeuft wie am PC.

        Cookie, Origin und Remote-Name sind vorher schon geprueft. Die Antwort traegt weiter die Schutz-Kopfzeilen des Remote-Namens."""
        self.kind = "local"
        self.via_remote = True
        self.own_device_id = self.device["id"]     # dieses Geraet darf sich nicht selbst sperren (remote_admin_post)
        self.device = None                  # kein "Handy": Nachrichten, Notizen usw. laufen wie am PC
        return False

    # --- Gast-Bereich (Tester) ---------------------------------------------------

    TESTER_DENIED = {"error": "Im Testbereich nicht verfügbar."}

    def tester_widgets_payload(self, tester):
        data = tester.widget_store.get()
        mine = tester.widget_store.device_notes(only={self.device["id"]})
        data["device_note"] = mine[0]["text"] if mine else ""
        return data

    def tester_get(self, path):
        """Alle Adressen, die ein Gast lesen darf. Antworten kommen nur aus seinem Bereich oder sind fest und leer."""
        tester = self.server.tester_for(self.device["profile"])

        if tester is None or not tester.ready():
            return self.send_json(403, self.TESTER_DENIED)

        gate = self.server.remote
        profile = gate.profiles.get(self.device["profile"])

        if path == "/api/remote/whoami":
            return self.send_json(200, {"remote": True, "device": self.device["name"], "levels": dict(gate.TESTER_LEVELS),
                                        "tester": True, "area": profile["name"]})
        if path == "/api/settings":
            return self.send_json(200, gate.settings_for_tester(self.server.tester_defaults(), profile["name"]))
        if path == "/api/background":
            after = parse_qs(urlparse(self.path).query).get("after")
            try:
                after = int(after[0]) if after is not None else None
            except ValueError:
                return self.send_json(400, {"error": "Ungueltige Anfrage"})
            return self.send_json(200, tester.background(after))
        if path == "/api/timers":
            return self.send_json(200, {"timers": []})
        if path == "/api/ringing":
            return self.send_json(200, {"ringing": [], "sound": "Computer", "version": 0, "snooze_minutes": 5, "server_sound": False})
        if path == "/api/alarms":
            return self.send_json(200, {"alarms": []})
        if path == "/api/focus":
            return self.send_json(200, {"active": False})
        if path == "/api/weather":
            return self.send_json(200, {"summary": None})
        if path == "/api/projects":
            return self.send_json(200, {"projects": [], "active": tester_module.NO_ACTIVE})
        if path == "/api/widgets":
            return self.send_json(200, self.tester_widgets_payload(tester))
        if path == "/api/sync":
            known = parse_qs(urlparse(self.path).query).get("known", [""])[0]
            return self.send_json(200, tester.sync_state(known))

        return self.send_json(403, self.TESTER_DENIED)

    def gym_payload(self):
        store = self.server.gym_store
        return {"today": store.today_view(), "plan": store.get_plan()}

    def handle_gym_post(self, path, data):
        store = self.server.gym_store
        if store is None:
            return self.send_json(404, {"error": "Gym ist hier nicht eingerichtet."})
        try:
            day = None
            if data.get("day") is not None:
                if not isinstance(data["day"], str):
                    raise gym.GymError("Ungültiger Tag.")
                try:
                    day = date.fromisoformat(data["day"])
                except ValueError:
                    raise gym.GymError("Ungültiger Tag.")
            result = None
            if path == "/api/gym/plan":
                store.set_plan(data.get("days"))
            elif path == "/api/gym/log":
                result = store.log(data.get("exercise"), data.get("weight"), data.get("reps"), day=day)
            else:
                store.clear_log(data.get("exercise"), day=day)
        except gym.GymError as error:
            return self.send_json(400, {"error": str(error)})
        payload = self.gym_payload()
        payload["result"] = result
        payload["widgets"] = self.server.widget_store.get()
        return self.send_json(200, payload)

    def tester_post(self, path, data):
        """Alle Adressen, die ein Gast schreiben darf, alle auf seinen Bereich. Alles andere: 403."""
        tester = self.server.tester_for(self.device["profile"])

        if tester is None or not tester.ready():
            return self.send_json(403, self.TESTER_DENIED)

        if path == "/api/message":
            text = data.get("message")
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > remote_policy.MAX_REMOTE_MESSAGE_CHARS:
                return self.send_json(400, {"error": "Ungültige Anfrage"})
            response = tester.process_message(text)
            return self.send_json(200, {"status": "response", "content": response["content"]})

        if path == "/api/conversation/new":
            tester.clear_conversation()
            return self.send_json(200, {"projects": [], "active": tester_module.NO_ACTIVE, "messages": []})

        if path in ("/api/widgets/notes", "/api/widgets/goals", "/api/widgets/lists", "/api/widgets/events", "/api/widgets/device_note",
                    "/api/widgets/events/delete", "/api/widgets/events/delete_series"):
            store = tester.widget_store
            try:
                if path.endswith("device_note"):
                    mine = {d["id"] for d in self.server.remote.store.devices()
                            if not d["revoked"] and d["profile"] == self.device["profile"]}
                    store.set_device_note(self.device["id"], self.device["name"], data.get("text"), keep_ids=mine)
                elif path.endswith("notes"):
                    store.set_notes(data.get("text"))
                elif path.endswith("goals"):
                    store.set_goals(data.get("items"))
                elif path.endswith("lists"):
                    store.set_lists(data.get("lists"))
                elif path.endswith("delete"):
                    store.delete_event(data.get("id"))
                elif path.endswith("delete_series"):
                    store.delete_series(data.get("series"))
                else:
                    store.add_event(data.get("title"), data.get("date"), data.get("time", ""))
            except ValueError as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, self.tester_widgets_payload(tester))

        return self.send_json(403, self.TESTER_DENIED)

    def remote_message(self, data):
        """Nachricht vom Handy: eigene Grenzen, eigener Weg in Jarvis (nur erlaubte Stufen), nie Rueckfragen."""
        gate = self.server.remote
        text = data.get("message")

        if not isinstance(text, str) or not text.strip() or len(text.strip()) > remote_policy.MAX_REMOTE_MESSAGE_CHARS:
            return self.send_json(400, {"error": "Ungültige Anfrage"})

        handler = getattr(self.server.jarvis, "process_remote_message", None)

        if handler is None:
            return self.send_json(503, {"error": "Nachrichten über Remote sind noch nicht freigeschaltet."})

        gate.refresh_limits()

        if not gate.limits.allow_message(self.device["id"]) or not gate.limits.allow_ai_call():
            return self.send_json(429, {"error": "Zu viele Anfragen. Bitte etwas warten."})

        with self.server.message_lock:
            response = handler(text.strip(), self.device["name"], gate.levels())

        if response.get("status") != "response":
            # Rueckfragen, Plaene und Befehle gibt es nur am PC
            return self.send_json(200, {"status": "response", "content": "Das geht nur am PC."})

        return self.send_json(200, {"status": "response", "content": response["content"]})

    def widgets_payload(self):
        """Seitenleisten-Daten. Mit Remote dazu: am PC die Notizen der gekoppelten Handys (nur lesen), am Handy nur die eigene."""
        data = self.server.widget_store.get()
        gate = self.server.remote

        if gate is None:
            return data

        store = self.server.widget_store

        if self.device is not None:
            mine = store.device_notes(only={self.device["id"]})
            data["device_note"] = mine[0]["text"] if mine else ""
        else:
            known = {d["id"] for d in gate.store.devices() if not d["revoked"]}
            data["device_notes"] = [note for note in store.device_notes(only=known) if note["text"].strip()]

        return data

    # --- Anfragen -------------------------------------------------------

    def agent_post(self, path, raw, length):
        """Adressen des PC-Agents (S6): /agent/pair (Kopplung), /agent/next (Auftrag holen), /agent/result (Ergebnis abgeben).

        Nie aus einem Browser: Ein Origin-Kopf ist verboten (Browser senden ihn bei fremden Seiten immer), das Token steht im Authorization-Kopf
        und nie in einem Cookie. Ein Agent-Token oeffnet nichts anderes als diese drei Adressen."""
        if self.headers.get("Origin") is not None:
            return self.send_json(403, {"error": "Nicht erlaubt"})

        gate = self.server.remote

        if gate is None or path not in ("/agent/pair", "/agent/next", "/agent/result"):
            return self.send_json(404, {"error": "Unbekannte Adresse"})

        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self.send_json(415, {"error": "Nur application/json"})

        if length <= 0 or length > MAX_BODY_BYTES:
            return self.send_json(400, {"error": "Ungueltige Laenge"})

        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self.send_json(400, {"error": "Ungueltige Anfrage"})

        if not isinstance(data, dict):
            return self.send_json(400, {"error": "Ungueltige Anfrage"})

        if path == "/agent/pair":
            code = data.get("code")
            status, token, device = gate.store.redeem(code if isinstance(code, str) else None, "remote-pairing", kind="agent")
            if status == "ok":
                return self.send_json(200, {"token": token, "name": device["name"]})
            if status == "locked":
                return self.send_json(429, {"error": "Zu viele Versuche. Bitte später noch einmal."})
            return self.send_json(400, {"error": "Der Code ist ungültig, abgelaufen oder schon benutzt."})

        agent = gate.agent_from_header(self.headers.get("Authorization"))

        if agent is None:
            return self.send_json(401, {"error": "Nicht angemeldet."})

        hub = self.server.hub

        if path == "/agent/next":
            wait = data.get("wait", 25)
            if not isinstance(wait, (int, float)) or isinstance(wait, bool):
                return self.send_json(400, {"error": "Ungueltige Anfrage"})
            return self.send_json(200, {"job": hub.next_job(agent["id"], wait)})

        accepted = hub.submit(agent["id"], data.get("id"), data.get("ok"), data.get("data"))
        return self.send_json(200 if accepted else 404, {"ok": accepted})

    def do_GET(self):
        self.kind = self.request_kind()
        self.device = None
        self.via_remote = False
        self.own_device_id = None

        if self.kind is None:
            return self.send_json(403, {"error": "Host nicht erlaubt"})

        path = urlparse(self.path).path

        if path.startswith("/agent/"):
            return self.send_json(405, {"error": "Nur POST"})

        if self.kind == "remote" and self.remote_get(path):
            return

        if self.server.guest and path.startswith("/api/"):
            return self.guest_get(path)

        if path == "/api/timers":
            return self.send_json(200, {"timers": timer.list_timers()})

        if path == "/api/agent/status":
            return self.send_json(200, agent_status(self.server))

        if path == "/api/ringing":
            return self.send_json(200, ringing.default_ringer().state())

        if path == "/api/focus":
            return self.send_json(200, focus.default_manager().state())

        if path == "/api/remote/state":
            return self.send_json(200, remote_panel_state(self.server.remote))

        if path == "/api/gym":
            if self.server.gym_store is None:
                return self.send_json(404, {"error": "Gym ist hier nicht eingerichtet."})
            return self.send_json(200, self.gym_payload())

        if path == "/api/folders":
            try:
                return self.send_json(200, {"folders": folders.default_list().list(), "max": folders.MAX_FOLDERS})
            except device_hub.DeviceError as error:
                return self.send_json(503, {"error": str(error)})

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
            return self.send_json(200, self.widgets_payload())

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
                return self.send_json(200, system_status_tool.current_facts())
            except device_hub.DeviceError as error:
                return self.send_json(503, {"error": str(error)})
            except Exception:
                return self.send_json(502, {"error": "Die Systemdaten konnten nicht gelesen werden."})

        if path == "/api/performance":
            try:
                return self.send_json(200, self.server.monitor.sample())
            except device_hub.DeviceError as error:
                return self.send_json(503, {"error": str(error)})
            except Exception:
                return self.send_json(502, {"error": "Die Leistungsdaten konnten nicht gelesen werden."})

        # PC-Lage fuer die Fenster "PC-Lage" und "Laufwerke": nur am PC (ueber Remote und fuer Gaeste nicht freigegeben)
        if path == "/api/pc_lage":
            if not abilities.task_enabled("GET_SYSTEM_INFO", self.server.jarvis.settings_manager):
                return self.send_json(200, {"disabled": True})
            try:
                return self.send_json(200, {"pc_lage": self.server.health.report()})
            except device_hub.DeviceError as error:
                return self.send_json(503, {"error": str(error)})
            except Exception:
                return self.send_json(502, {"error": "Die PC-Lage konnte nicht gelesen werden."})

        if path == "/api/weather":
            # Kurzer Satz fuer den Startbericht. Nie ein Fehler: ohne Wetter faellt der Satz einfach weg.
            summary = None
            if abilities.task_enabled("GET_WEATHER", self.server.jarvis.settings_manager):
                try:
                    summary = self.server.weather.summary()
                except Exception:
                    summary = None
            return self.send_json(200, {"summary": summary})

        # Willkommensseite: Wochenvorhersage fuer den Heimatort oder (?place=...) fuer einen gesuchten Ort. Ist die Faehigkeit aus, kommt "disabled".
        if path == "/api/forecast":
            if not abilities.task_enabled("GET_WEATHER", self.server.jarvis.settings_manager):
                return self.send_json(200, {"disabled": True})
            asked = parse_qs(urlparse(self.path).query).get("place", [""])[0]
            try:
                result = self.server.weather.week_forecast(asked or "heimat", icons=True)
            except Exception:
                return self.send_json(502, {"error": "Das Wetter ist gerade nicht abrufbar."})
            if not result.success:
                return self.send_json(502, {"error": result.error})
            return self.send_json(200, {"forecast": result.data})

        # Willkommensseite: Erinnerungen, Schlagzeilen und Tagesbriefing nur lesen. Ist die Faehigkeit aus, kommt "disabled".
        if path == "/api/reminders":
            if not abilities.task_enabled("LIST_REMINDERS", self.server.jarvis.settings_manager):
                return self.send_json(200, {"reminders": [], "disabled": True})
            store = reminders.default_store()
            items = sorted(store.list(), key=lambda r: r["due"])[:10]
            return self.send_json(200, {"reminders": [
                {"id": r["id"], "text": r["text"], "due": r["due"], "repeat": store.repeat_info(r).get("repeat")} for r in items]})

        if path == "/api/news":
            if not abilities.task_enabled("GET_NEWS", self.server.jarvis.settings_manager):
                return self.send_json(200, {"items": [], "disabled": True})
            result = news_tool.default_service().get_news("alle", "", 8)
            if not result.success:
                return self.send_json(502, {"error": result.error or "Die News sind gerade nicht abrufbar."})
            return self.send_json(200, {"items": [
                {"title": i["title"], "source": i["source"], "summary": (i.get("summary") or "")[:300], "url": i["url"], "published": i["published"]}
                for i in result.data["items"]]})

        if path == "/api/briefing":
            if not abilities.task_enabled("GET_BRIEFING", self.server.jarvis.settings_manager):
                return self.send_json(200, {"text": None, "disabled": True})
            try:
                return self.send_json(200, {"text": self.server.jarvis.daily_briefing()})
            except ConnectionError:
                raise            # Browser hat aufgelegt: kein Fehler von Jarvis
            except Exception:
                traceback.print_exc()
                return self.send_json(502, {"error": "Das Briefing konnte nicht erstellt werden."})

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

        if path == "/api/sync":
            try:
                known = parse_qs(urlparse(self.path).query).get("known", [""])[0]
                return self.send_json(200, sync_state(self.server.jarvis, known))
            except ConnectionError:
                raise            # Browser hat aufgelegt: kein Fehler von Jarvis
            except Exception:
                traceback.print_exc()
                return self.send_json(500, {"error": "Abgleich nicht moeglich."})

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

        self.kind = self.request_kind()
        self.device = None
        self.via_remote = False
        self.own_device_id = None

        path = urlparse(self.path).path

        if self.kind is not None and path.startswith("/agent/"):
            return self.agent_post(path, raw, length)          # PC-Agent: Token statt Cookie, kein Browser (S6)

        if self.kind is None or not self.origin_allowed():
            return self.send_json(403, {"error": "Nicht erlaubt"})

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

        if self.kind == "remote" and self.remote_post(path, data):
            return

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

            if self.device is not None and path == "/api/message":
                return self.remote_message(data)

            if path == "/api/plan/abort":
                return self.send_json(200, {"aborted": bool(self.server.jarvis.abort_plan())})

            # Sprachausgabe: Text rein, MP3 raus. Ohne message_lock, damit Jarvis
            # beim Vorlesen nicht auf die naechste Nachricht warten muss.
            if path == "/api/speak":
                return self.handle_speak(data)

            # Notizen und Ziele speichern: kleine lokale Datei, braucht den message_lock nicht
            if path in ("/api/widgets/notes", "/api/widgets/goals", "/api/widgets/lists", "/api/widgets/events", "/api/widgets/device_note",
                        "/api/widgets/events/delete", "/api/widgets/events/delete_series"):
                store = self.server.widget_store
                try:
                    if path.endswith("device_note"):
                        # Nur ein gekoppeltes Handy hat eine eigene Notiz, und es schreibt nur seine
                        gate = self.server.remote
                        known = {d["id"] for d in gate.store.devices() if not d["revoked"]} if gate is not None else None
                        store.set_device_note(self.device["id"] if self.device else None, self.device["name"] if self.device else "",
                                              data.get("text"), keep_ids=known)
                    elif path.endswith("notes"):
                        store.set_notes(data.get("text"))
                    elif path.endswith("goals"):
                        store.set_goals(data.get("items"))
                    elif path.endswith("lists"):
                        store.set_lists(data.get("lists"))
                    elif path.endswith("delete"):
                        store.delete_event(data.get("id"))
                    elif path.endswith("delete_series"):
                        store.delete_series(data.get("series"))
                    else:
                        store.add_event(data.get("title"), data.get("date"), data.get("time", ""))
                except ValueError as error:
                    return self.send_json(400, {"error": str(error)})
                return self.send_json(200, self.widgets_payload())

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

            # Remote-Verwaltung (R4): nur am PC (das Handy hat diese Adressen nicht), lokal, ohne message_lock
            if path in ("/api/remote/pair_link", "/api/remote/revoke", "/api/remote/restore", "/api/remote/revoke_all", "/api/remote/forget") \
                    or path in PROFILE_PATHS:
                status, body = remote_admin_post(self.server.remote, path, data, own_id=getattr(self, "own_device_id", None))
                return self.send_json(status, body)

            # Gym: Plan aendern nur am PC (steht in keiner Remote-Stufe); Ergebnis eintragen darf auch das Handy (Stufe Alltag)
            if path in ("/api/gym/plan", "/api/gym/log", "/api/gym/clear"):
                return self.handle_gym_post(path, data)

            # Freigegebene Ordner pflegen (Step 2.14): nur hier, nie per Chat; lokal, ohne message_lock
            if path in ("/api/folders/add", "/api/folders/remove"):
                folder = data.get("path")
                if not isinstance(folder, str):
                    return self.send_json(400, {"error": "Es wurde kein Ordner angegeben."})
                try:
                    if path.endswith("/add"):
                        updated = folders.default_list().add(folder)
                    else:
                        updated = folders.default_list().remove(folder)
                except folders.AccessError as error:
                    return self.send_json(400, {"error": str(error)})
                return self.send_json(200, {"folders": updated, "max": folders.MAX_FOLDERS})

            # Fokus-Sitzung abbrechen (Step 2.13): lokal und harmlos, soll auch gehen, waehrend Jarvis antwortet
            if path == "/api/focus/stop":
                summary = focus.default_manager().stop()
                return self.send_json(200, {"stopped": summary is not None, "summary": summary,
                                            "state": focus.default_manager().state()})

            # Briefing beim ersten Start des Tages (Step 2.12): hoechstens einmal pro Tag, sonst text = null
            if path == "/api/hints":
                if self.server.hints_by_loop:
                    return self.send_json(200, {"hints": []})        # kommen als Meldung im Verlauf und per Push
                return self.send_json(200, {"hints": self.server.jarvis.proactive_hints()})
            if path == "/api/goals/evening":
                return self.send_json(200, {"text": self.server.jarvis.evening_goals()})
            if path == "/api/briefing/auto":
                return self.send_json(200, {"text": self.server.jarvis.auto_briefing()})

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

            # Willkommensseite: Medientaste und Lautstaerke (nur am PC; ueber Remote sind diese Adressen gesperrt)
            if path == "/api/media":
                if not abilities.task_enabled("MEDIA_CONTROL", self.server.jarvis.settings_manager):
                    return self.send_json(403, {"error": "Die Musiksteuerung ist in den Einstellungen aus."})
                result = media_tool.media_control(data.get("action"))
                if not result.success:
                    return self.send_json(400, {"error": result.error})
                return self.send_json(200, result.data)
            if path == "/api/agent/ping":
                return self.send_json(200, agent_ping(self.server))
            if path == "/api/volume":
                if not abilities.task_enabled("SET_VOLUME", self.server.jarvis.settings_manager):
                    return self.send_json(403, {"error": "Die Lautstärke-Steuerung ist in den Einstellungen aus."})
                percent = data.get("percent")
                if isinstance(percent, bool) or not isinstance(percent, int):
                    return self.send_json(400, {"error": "Die Lautstärke muss eine ganze Zahl sein."})
                result = volume_tool.set_volume(percent)
                if not result.success:
                    return self.send_json(400, {"error": result.error})
                return self.send_json(200, {"percent": percent})

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

    def send_static(self, url_path, status=200):
        if url_path == "/":
            # Besitzer sieht zuerst die Willkommensseite, auf dem Handy die Handy-Version (device_page.py). Klick auf den Kern fuehrt am PC zu /index.html. Der Gastmodus startet direkt in der App.
            if self.server.guest:
                url_path = "/index.html"
            else:
                url_path = device_page.start_page(urlparse(self.path).query, self.headers.get("User-Agent", ""))

        # Nur Dateien innerhalb von web/ ausliefern (kein "../")
        target = (WEB_DIR / url_path.lstrip("/")).resolve()

        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            return self.send_json(404, {"error": "Nicht gefunden"})

        body = target.read_bytes()
        self.send_response(status)
        self.send_header(
            "Content-Type",
            CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def main(argv=None, on_ready=None, open_browser=True):
    """on_ready(server) und open_browser=False nutzt die Desktop-App (jarvis_app.py); sonst unveraendert."""
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
        apple = calendar_sync.from_config()  # Apple-Kalender (Step 2.19): nur wenn in der .env eingerichtet
        if apple is not None:
            widgets.attach_remote(apple)
            threading.Thread(target=apple.events, daemon=True).start()     # Termine schon beim Start holen
        ringing.start_ticker()              # beendet zu lange laeutende Wecker/Timer (Step 2.11)

    remote = None
    if not args.guest and REMOTE_HOST:
        # Zugriff vom Handy (siehe DESIGN_REMOTE.md): nur vorbereitet, an ist es erst mit dem Schalter in den Einstellungen
        import remote_auth
        import remote_gate
        import profiles
        remote = remote_gate.RemoteGate(REMOTE_HOST, remote_auth.DeviceStore(), jarvis.settings_manager, profiles.ProfileStore())

    server = JarvisServer((SERVER_HOST, args.port), jarvis, guest=args.guest, remote=remote)
    url = f"http://localhost:{server.server_address[1]}"

    if remote is not None and remote.profiles is not None:
        server.start_tester_ticker()        # Erinnerungen der Gast-Bereiche (Mark 5, C3b): jede nur in der App ihres Gastes

    print(f"J.A.R.V.I.S. {'(GASTMODUS) ' if args.guest else ''}laeuft auf {url}  (beenden mit Strg+C)")
    if remote is not None:
        print(f"Remote ist vorbereitet für https://{REMOTE_HOST} (aktuell {'AN' if remote.active() else 'AUS'}, "
              f"Schalter in den Einstellungen).")

    if open_browser:
        webbrowser.open(url)
    if on_ready is not None:
        on_ready(server)

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
