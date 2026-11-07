"""Was Remote darf (Mark 5, Remote R1). Siehe DESIGN_REMOTE.md, Abschnitt 5.

Drei Stufen, einzeln schaltbar. Was in keiner Stufe steht, gibt es ueber Remote nicht.
Neue Faehigkeiten (abilities.py) MUESSEN hier entweder einer Stufe oder NEVER_REMOTE zugeordnet werden; der Test prueft das.
"""
import abilities

LEVELS = ("info", "daily", "pc")
LEVEL_LABELS = {
    "info": "Auskunft",
    "daily": "Alltag",
    "pc": "PC-Steuerung (harmlos)",
}
DEFAULT_LEVELS = {"info": True, "daily": True, "pc": False}

LEVEL_ABILITIES = {
    "info": ("web_search", "weather", "news", "translate", "wikipedia", "worldtime", "convert"),
    "daily": ("timers", "reminders", "alarm", "briefing", "focus", "calendar", "lists", "goals"),
    "pc": ("volume", "music", "system"),
}
LEVEL_CORE_TASKS = {
    "info": ("GET_TIME", "GET_DATE", "CALCULATE"),
    "daily": ("STOP_RINGING",),
    "pc": ("GET_SYSTEM_INFO",),
}
# Nie ueber Remote, auch nicht einstellbar: privat, greift auf den Rechner zu oder braucht eine Rueckfrage
NEVER_REMOTE = ("pages", "history", "browser", "screen", "clipboard", "mail", "contacts", "programs",
                "documents", "notes", "files")

MAX_REMOTE_MESSAGE_CHARS = 1000

# Adressen, die ein angemeldetes Geraet aufrufen darf. Alles andere unter /api/ ist 403.
GET_API = frozenset({
    "/api/settings",          # nur gefilterte Ansicht (Darstellung, Anrede, Stimme)
    "/api/background", "/api/timers", "/api/ringing", "/api/alarms", "/api/widgets", "/api/weather",
    "/api/projects",          # Liste der Projekte und Unterhaltungen (nur lesen)
    "/api/focus",             # laufende Fokus-Sitzung anzeigen
    "/api/sync", "/api/remote/whoami",
})
POST_API = frozenset({
    "/api/message", "/api/speak", "/api/ringing/stop", "/api/timer/cancel", "/api/focus/stop",
    "/api/conversation/open", "/api/conversation/new", "/api/project/open",
})
# Nur mit der Stufe "Alltag": Ziele abhaken, Listen pflegen (Einkaufsliste), gemeinsame Notiz und die eigene Notiz des Handys. Termine bleiben am PC.
DAILY_POST_API = frozenset({"/api/widgets/goals", "/api/widgets/lists", "/api/widgets/notes", "/api/widgets/device_note"})
# Ohne Anmeldung (Kopplung)
PUBLIC_GET = frozenset({"/pair"})
PUBLIC_POST = frozenset({"/api/remote/pair"})
# Dateien, die auch ohne Anmeldung kommen duerfen: nichts Geheimes, der Browser holt sie ohne Cookie (Manifest, Icons)
PUBLIC_STATIC = frozenset({"/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png",
                           "/icon-maskable-512.png", "/apple-touch-icon.png"})


def normalize_levels(value):
    """Gueltige Stufen-Einstellung: unbekannte Namen weg, Fehlendes und Unsinn bekommen die Voreinstellung."""
    source = value if isinstance(value, dict) else {}
    return {level: source[level] if isinstance(source.get(level), bool) else DEFAULT_LEVELS[level] for level in LEVELS}


def allowed_tasks(levels):
    """Die Aufgaben (task_type), die Remote mit diesen Stufen kennt."""
    levels = normalize_levels(levels)
    by_id = {ability.id: ability for ability in abilities.ABILITIES}
    tasks = set()
    for level in LEVELS:
        if not levels[level]:
            continue
        tasks.update(LEVEL_CORE_TASKS[level])
        for ability_id in LEVEL_ABILITIES[level]:
            tasks.update(by_id[ability_id].tasks)
    return frozenset(tasks)


def api_allowed(method, path, levels=None):
    """Darf ein angemeldetes Geraet diese /api/-Adresse aufrufen? levels: die eingeschalteten Stufen (ohne Angabe: nur die festen Adressen)."""
    if method == "GET":
        return path in GET_API
    if method == "POST":
        if path in POST_API:
            return True
        if levels is None or path not in DAILY_POST_API:
            return False
        return normalize_levels(levels)["daily"]
    return False


def is_public(method, path):
    """Adressen, die auch ohne Anmeldung antworten (nur die Kopplung)."""
    return (method == "GET" and path in PUBLIC_GET) or (method == "POST" and path in PUBLIC_POST)
