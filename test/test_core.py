"""Jarvis-Kern (Mark 5, Step 4B.5): core.js mit Node, Einbindung in die Seite, Stile fuer alle Zustaende, Bewegung aus."""
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
css = (WEB / "core.css").read_text(encoding="utf-8")
js = (WEB / "core.js").read_text(encoding="utf-8")

# 1) Einbindung: Stil und Skript, core.js vor app.js, der Platz in der Titelleiste neben dem Schriftzug
assert '<link rel="stylesheet" href="core.css">' in html
assert html.index('src="core.js"') < html.index('src="app.js"')
assert html.index('id="core-slot"') < html.index('class="logo"')
assert html.index('class="topbar"') < html.index('id="core-slot"') < html.index('id="status"')

# 2) Jeder Zustand hat eigene Stile (auch ohne Bewegung erkennbar), nichts davon laedt etwas von aussen
for state in ("idle", "listening", "thinking", "speaking", "error"):
    assert state in js
for state in ("listening", "thinking", "speaking", "error"):
    assert f'.jarvis-core[data-state="{state}"]' in css, state
assert '.jarvis-core[data-state="error"] { color: #d9695f' in css      # Fehler ist rot
assert "scale(1.2)" in css and "scale(0.85)" in css            # statische Unterschiede fuer "Bewegung aus"
assert "url(" not in css and "http" not in css and "@import" not in css
assert "http://www.w3.org/2000/svg" in js and "innerHTML" not in js

# 3) Bewegung aus: per Klick (data-motion) und per Systemeinstellung, beides schaltet alle Animationen ab
assert 'html[data-motion="off"] .jarvis-core *,\nhtml[data-motion="off"] .jarvis-core { animation: none !important; }' in css
assert re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{\s*html:not\(\[data-motion=\"on\"\]\)", css)

# 4) app.js: Zustand aus Status, Sprechen und Zuhoeren abgeleitet, Klick speichert die Wahl nur im Browser
assert "window.JarvisCore.create(document" in app and 'getElementById("core-slot")' in app
block = app.split("function refreshCore()")[1].split("// Hotkey der Desktop-App")[0]
for part in ('statusEl.dataset.state === "error"', "speakingNow", 'micButton.classList.contains("listening")',
             'statusEl.dataset.state === "busy"'):
    assert part in block, part
assert "MutationObserver(refreshCore).observe(statusEl" in app and "MutationObserver(refreshCore).observe(micButton" in app
speaking = app.split("onSpeaking: (value) => {")[1].split("synth:")[0]
assert "refreshCore();" in speaking                             # Sprechen wechselt den Kern sofort
assert 'localStorage.setItem("jarvis.motion"' in block and "try {" in block      # Speicher kann fehlen
assert "innerHTML" not in block

# 5) Der Dienst-Worker und der Server liefern die neuen Dateien aus
import server
assert ".css" in server.CONTENT_TYPES and ".js" in server.CONTENT_TYPES
assert (WEB / "core.css").is_file() and (WEB / "core.js").is_file()

# 6) core.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "core_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "core.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, core.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
