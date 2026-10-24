"""Sprache (Step 6): voice.js mit Node, Einbindung in die Seite, Standard aus."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from settings_manager import SettingsManager

WEB = PROJECT_DIR / "web"

# 1) Sprache ist standardmaessig aus (nichts hoert oder spricht ohne dein Zutun)
voice = SettingsManager.DEFAULT_SETTINGS["voice"]
assert voice == {"output": False, "engine": "OpenAI", "voice": "Onyx (male)", "speed": "Normal", "input": False, "input_language": "German", "wake_word": False}

# 2) Einbindung in die Seite
html = (WEB / "index.html").read_text(encoding="utf-8")
app = (WEB / "app.js").read_text(encoding="utf-8")
assert html.index('src="voice.js"') < html.index('src="app.js"')
mic = re.search(r'<button[^>]*id="mic"[^>]*>', html, re.S).group(0)
assert " hidden" in mic, "Mikrofon-Knopf muss ohne Einstellung versteckt sein"
assert 'type="button"' in mic, "darf das Formular nicht absenden"

# Nur eigene Antworten und Hintergrundmeldungen werden vorgelesen, keine Fehler
speak_calls = re.findall(r"speakReply\(([^)]*)\)", app)
# "text": die Funktionsdefinition selbst und die Antwort auf "Wecker aus" (Banner, Step 2.11, inkl. Briefing)
assert sorted(speak_calls) == ["data.content", "item.text", "text", "text"], speak_calls
assert 'say: (text) => { addMessage("jarvis", text); speakReply(text); }' in app
# Vorlesen nur bei eingeschalteter Einstellung
assert re.search(r'function speakReply\(text\) \{\s*if \(voiceSetting\("output"\) === true\)', app)
# Neue Nachricht beendet das Vorlesen
assert re.search(r"async function sendMessage\(text\) \{[^}]*?voice\.stopSpeaking\(\)", app, re.S)
# Gesprochener Text geht denselben Weg wie getippter
assert "sendMessage(text);" in app.split("function listenOnce")[1].split("function micDown")[0]
assert "listenOnce(false)" in app.split("function micDown")[1].split("\n}\n")[0]
# Seite "Voice" in den Einstellungen mit den drei Schaltern
for key in ('key: "output"', 'key: "speed"', 'key: "input"'):
    assert key in app, key

# Server-Stimme (Step 6b): Browser schickt nur den Text, Stimme/Modell bestimmt der Server
fetch_code = app.split("fetchAudio: async")[1].split("onFallback")[0]
assert '"/api/speak"' in fetch_code and "body: JSON.stringify({ text })" in fetch_code
assert "voice" not in fetch_code.lower().replace("fetchaudio", "")
assert 'voice.speak(text, voiceSetting("speed"), voiceSetting("engine"))' in app
assert "voiceSetting(\"input_language\")" in app.split("function listenOnce")[1].split("function micDown")[0]
for key in ('key: "engine"', 'key: "voice"', 'key: "input_language"'):
    assert key in app, key
assert 'type: "voice-test"' in app and "buildVoiceTest()" in app
assert "innerHTML" not in app.split("function buildVoiceTest")[1].split("function buildActionList")[0]

# Stopp-Knopf (Step 6b): versteckt, nur bei Sprechen oder laufendem Plan sichtbar
stop = re.search(r'<button[^>]*id="stop"[^>]*>', html, re.S).group(0)
assert " hidden" in stop and 'type="button"' in stop
assert "stopButton.hidden = !(speakingNow || planRunning)" in app
assert 'onSpeaking: (value) =>' in app
assert "voice.stopSpeaking();" in app.split("stopButton.addEventListener")[1].split("});")[0]
assert "/api/plan/abort" in app.split("stopButton.addEventListener")[1].split("});")[0]

# 3) voice.js selbst (braucht Node; ohne Node wird nur das gemeldet)
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "voice_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "voice.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, voice.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
