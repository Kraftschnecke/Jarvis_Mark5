"""Remote R5 (Mark 5): Handy-Ansicht. remote_mode.js mit Node, Banner, nur erlaubte Anfragen, kein Verwalten, Schutz vor iOS-Zoom."""
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def stub_if_missing(name, **attrs):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("requests")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

project_stub = types.ModuleType("project")
for name in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
             "save_message", "get_conversation", "rename_conversation", "create_project", "reset_conversation",
             "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub

import re
import shutil
import subprocess

WEB = PROJECT_DIR / "web"
html = (WEB / "index.html").read_text(encoding="utf-8")
app = (WEB / "app.js").read_text(encoding="utf-8")
css = (WEB / "style.css").read_text(encoding="utf-8")
js = (WEB / "remote_mode.js").read_text(encoding="utf-8")

import remote_policy

# 1) Einbindung: Skript vor app.js, Streifen unter der Kopfzeile und vor dem Chat, Notch-sicher
assert html.count('src="remote_mode.js"') == 1 and html.index('src="remote_mode.js"') < html.index('src="app.js"')
assert html.index('class="topbar"') < html.index('id="remote-banner"') < html.index('id="chat"')
assert 'id="remote-banner" hidden role="status"' in html
assert "viewport-fit=cover" in html and "innerHTML" not in js

# 2) Modus kommt vom Server ("remote": true in den Einstellungen), nicht von der Adresse im Browser
block = app.split("function setRemoteMode(value) {")[1].split("document.addEventListener")[0]
assert 'document.body.classList.toggle("remote", value)' in block and "refreshRemoteBanner()" in block
assert "setRemoteMode(data.remote === true)" in app
assert "location" not in block and "hostname" not in block
banner = app.split("async function refreshRemoteBanner() {")[1].split("function setRemoteMode")[0]
assert '"/api/remote/whoami"' in banner and "nicht angemeldet" in banner and "innerHTML" not in banner
assert "/api/remote/whoami" in remote_policy.GET_API

# 3) Am Handy werden keine Adressen gefragt, die es dort nicht gibt: PC-Widgets aus, kein Briefing/Abendfrage/Hinweise, kein Weckwort
assert 'return remoteMode && !window.JarvisRemoteMode.widgetAllowed(choice) ? "Off" : choice;' in app
assert "!guestMode && !remoteMode && !ended" in app                                  # Weckwort
assert "if (guestMode || remoteMode || !(settings.goals && settings.goals.evening)) return;" in app
assert "if (guestMode || remoteMode || !h || !(h.appointments || h.weather)) return;" in app
assert "if (!remoteMode && settings.briefing && settings.briefing.auto) {" in app
assert "if (remoteMode) return;        // Umbenennen" in app
assert "area.readOnly" not in app                                                   # Notizen am Handy bearbeitbar (Stufe Alltag, Server prueft)
assert "Lege sie am PC an." in app

# Jedes Widget, das am Handy erlaubt bleibt, fragt nur erlaubte Adressen; was verboten ist, steht in der Verbotsliste
for name, path in (("PC Facts", "/api/system"), ("Performance", "/api/performance"), ("Edmonton Oilers", "/api/hockey"), ("Adler Mannheim", "/api/hockey")):
    assert path not in remote_policy.GET_API, path
    assert name in js, name
for renderer in ("renderCalendar", "renderNotes", "renderGoals", "renderLists"):
    assert renderer in app
for path in ("/api/widgets", "/api/weather", "/api/timers", "/api/focus", "/api/ringing", "/api/background", "/api/alarms", "/api/projects", "/api/sync"):
    assert path in remote_policy.GET_API, path                                       # was die Seite im Takt fragt, ist erlaubt

# Alles, was die Seite im festen Takt oder beim Start fragt, ist entweder erlaubt oder in Remote abgeschaltet
polled = set(re.findall(r'api\("GET", "(/api/[a-z_/]+)"', app))
needs_switch_off = polled - remote_policy.GET_API
assert needs_switch_off == {"/api/actions", "/api/folders", "/api/hockey", "/api/memories", "/api/performance", "/api/remote/state", "/api/system"}, needs_switch_off

# 3b) Notizen am Handy: allgemein (alle Geraete) oder nur dieses Geraet; der PC zeigt die Handy-Notizen nur an
notes_block = app.split("function renderNotes(section) {")[1].split("function renderGoals(section) {")[0]
assert "innerHTML" not in notes_block
assert '"/api/widgets/device_note" : "/api/widgets/notes"' in notes_block
assert "if (remoteMode) {" in notes_block and '"Allgemein"' in notes_block and '"Nur dieses Gerät"' in notes_block
assert 'mode === "device" ? (data.device_note || "") : data.notes' in notes_block          # das Handy liest nur seine eigene Notiz
assert "data.device_notes" in notes_block and "Notiz von " in notes_block and "w-note-text" in notes_block
assert "if (timer) await save();" in notes_block                                           # beim Umschalten geht nichts verloren
assert "registerRefresher(section" in notes_block and "document.activeElement === area" in notes_block   # nie mitten in der Eingabe ueberschreiben
for path in ("/api/widgets/notes", "/api/widgets/device_note"):
    assert path in remote_policy.DAILY_POST_API and path not in remote_policy.POST_API     # nur mit der Stufe Alltag
assert "/api/widgets/events" not in remote_policy.DAILY_POST_API                           # Termine bleiben am PC

# 4) CSS: am Handy kein Verwalten, Eingabefelder mit 16 px gegen den iOS-Zoom, sichere Raender
for selector in ("body.remote #open-settings", "body.remote #new-project", "body.remote .wake", "body.remote .row .more"):
    assert selector in css, selector
assert "textarea, input[type=\"text\"]" in css and "font-size: 16px" in css
assert "env(safe-area-inset-bottom)" in css and "env(safe-area-inset-top)" in css
assert "height: 100dvh" in css
assert ".remote-banner[hidden] { display: none; }" in css

# 5) remote_mode.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "remote_mode_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "remote_mode.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, remote_mode.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
