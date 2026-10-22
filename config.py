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

# Web-Oberflaeche (server.py). Der Server lauscht nur auf dem eigenen Rechner.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.getenv("JARVIS_PORT", "8000"))
