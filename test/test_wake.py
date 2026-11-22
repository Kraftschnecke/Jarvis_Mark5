"""Weckwort (Step 6c): wake.js mit Node, Einbindung in die Seite, Standard aus, nie im Gastmodus."""

import re
import shutil
import subprocess
import sys
import webapp
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from settings_manager import SettingsManager

WEB = PROJECT_DIR / "web"
html = (WEB / "index.html").read_text(encoding="utf-8")
app = webapp.app_text()
css = (WEB / "style.css").read_text(encoding="utf-8")

# 1) Standard aus, Einstellung wird geprueft (nur Wahr/Falsch)
assert SettingsManager.DEFAULT_SETTINGS["voice"]["wake_word"] is False
assert '("voice", "wake_word"): lambda v: isinstance(v, bool)' in (PROJECT_DIR / "server.py").read_text(encoding="utf-8")

# 2) Einbindung: wake.js vor app.js, Anzeige anfangs versteckt
assert html.index('src="wake.js"') < html.index('src="app_base.js"')
badge = re.search(r'<[^>]*id="wake"[^>]*>', html).group(0)
assert " hidden" in badge
assert "body.guest .wake" in css, "im Gastmodus darf keine Weckwort-Anzeige erscheinen"

# 3) Wann hoert der Browser zu? Nur eingeschaltet, nie als Gast, nie waehrend
#    Jarvis antwortet oder spricht (er soll sich nicht selbst hoeren)
refresh = app.split("function refreshWake()")[1].split("\n}\n")[0]
for condition in ('voiceSetting("wake_word") === true', "!guestMode", "!busy", "!speakingNow",
                  "!awaitingAck", "!voice.isListening()", "!ended"):
    assert condition in refresh, condition
for caller in ("function setBusy", "function applyVoice"):
    assert "refreshWake();" in app.split(caller)[1].split("\n}\n")[0], caller

# 4) Der erkannte Befehl geht denselben Weg wie getippter Text
handle = app.split("function handleWake(rest)")[1].split("\n}\n")[0]
assert "sendMessage(rest)" in handle
assert "fetch(" not in handle and "api(" not in handle, "Weckwort darf nichts am Gate vorbei ausloesen"
# Ohne Vorlesen: Ton statt Sprache; mit Vorlesen: "Ja, Sir?"
assert "chime()" in handle and "Ja, Sir?" in handle and "Yes, Sir?" in handle
# Neue Nachricht oder Stopp-Knopf bricht das Warten auf den Befehl ab
assert "awaitingAck = false;" in app.split("async function sendMessage")[1].split("voice.stopSpeaking()")[0]
assert "awaitingAck = false;" in app.split("stopButton.addEventListener")[1].split("voice.stopSpeaking()")[0]

# 5) Einstellungszeile vorhanden
assert 'key: "wake_word"' in app

# 6) wake.js selbst (braucht Node; ohne Node wird nur das gemeldet)
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "wake_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "wake.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, wake.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
