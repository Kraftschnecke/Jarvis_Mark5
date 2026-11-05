"""Zentrale Konfiguration von J.A.R.V.I.S.

Alles, was aus der Umgebung (.env) kommt oder an mehreren Stellen gebraucht
wird, steht hier. Andere Module importieren von hier und rufen kein eigenes
load_dotenv() oder os.getenv() auf.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Sprachmodell fuer alle Anfragen. Ueberschreibbar mit JARVIS_MODEL in der .env
MODEL = os.getenv("JARVIS_MODEL", "gpt-5.6-luna")

# Sprachmodell fuer die Sprachausgabe (speech.py). Ueberschreibbar mit JARVIS_TTS_MODEL
TTS_MODEL = os.getenv("JARVIS_TTS_MODEL", "gpt-4o-mini-tts")

# Anzeige in "About" der Einstellungen
VERSION = "Mark 5"

# Wie lange (Sekunden) auf eine Antwort des Sprachmodells gewartet wird
OPENAI_TIMEOUT = float(os.getenv("JARVIS_OPENAI_TIMEOUT", "60"))

# Wie viele der letzten Nachrichten der Konversation das Sprachmodell bekommt
# (Step 2.6). Der volle Verlauf bleibt in der Datenbank und in der Oberflaeche.
# 0 = kein Limit. Ueberschreibbar mit JARVIS_HISTORY_LIMIT in der .env
HISTORY_LIMIT = int(os.getenv("JARVIS_HISTORY_LIMIT", "20"))

# Zeit-Log der KI-Aufrufe (ai_log.py): JARVIS_TIMING=1 in der .env schaltet es ein
TIMING_ENABLED = os.getenv("JARVIS_TIMING", "").strip().lower() in ("1", "true", "yes", "on")

# Cloud-Datenbank (Neon / PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

# Websuche (Brave Search API)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

# Programme, die Jarvis starten darf (Name -> Pfad). Siehe programs.example.json
PROGRAMS_FILE = Path(__file__).resolve().parent / "programs.json"

# Ordner, aus denen Jarvis Dateien lesen darf (Mark 5, Step 2.14). Wird in den Einstellungen gepflegt
FOLDERS_FILE = Path(__file__).resolve().parent / "folders.json"

# Web-Oberflaeche (server.py). Der Server lauscht nur auf dem eigenen Rechner.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.getenv("JARVIS_PORT", "8000"))


def mail_accounts():
    """E-Mail-Postfaecher aus der .env (Mark 5, Step 2.20). Nur der Besitzer traegt sie dort ein.

    MAIL_ACCOUNTS=strato,uni            (Namen, kleingeschrieben, Buchstaben/Ziffern)
    MAIL_STRATO_HOST=imap.strato.de     MAIL_STRATO_USER=...     MAIL_STRATO_PASSWORD=...
    MAIL_STRATO_PORT=993                (optional)
    MAIL_STRATO_CAFILE=C:\\pfad\\zertifikat.pem   (optional: eigene Zertifikatsdatei, wenn die Pruefung sonst scheitert)
    Gibt {name: {"host", "port", "user", "password", "cafile"}} zurueck; unvollstaendige Eintraege fehlen.
    Das Passwort steht nur hier und wird nie angezeigt, geloggt oder an das Sprachmodell gegeben.
    """
    accounts = {}

    for name in os.getenv("MAIL_ACCOUNTS", "").replace(";", ",").split(","):
        name = name.strip().lower()

        if not name or not name.isalnum():
            continue

        prefix = f"MAIL_{name.upper()}_"
        host = os.getenv(prefix + "HOST", "").strip()
        user = os.getenv(prefix + "USER", "").strip()
        password = os.getenv(prefix + "PASSWORD", "")
        port_text = os.getenv(prefix + "PORT", "993").strip()
        cafile = os.getenv(prefix + "CAFILE", "").strip()

        if not (host and user and password and port_text.isdigit()):
            continue

        accounts[name] = {"host": host, "port": int(port_text), "user": user, "password": password, "cafile": cafile}

    return accounts


def caldav_account():
    """Apple-Kalender (iCloud) aus der .env (Mark 5, Step 2.19). None, wenn nicht eingerichtet.

    CALDAV_USER (Apple-ID), CALDAV_PASSWORD (app-spezifisches Passwort),
    CALDAV_CALENDARS=Privat,Arbeit   Kalender, die Jarvis LIEST (leer = alle mit Terminen),
    CALDAV_WRITE_CALENDAR=Privat     der EINE Kalender, in den Jarvis schreibt (leer = Jarvis schreibt nirgends hin).
    """
    user = os.getenv("CALDAV_USER", "").strip()
    password = os.getenv("CALDAV_PASSWORD", "")

    if not user or not password:
        return None

    read = [n.strip() for n in os.getenv("CALDAV_CALENDARS", "").replace(";", ",").split(",") if n.strip()]
    return {"user": user, "password": password, "calendars": read,
            "write_calendar": os.getenv("CALDAV_WRITE_CALENDAR", "").strip()}
