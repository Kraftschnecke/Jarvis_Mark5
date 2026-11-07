"""Live-Abgleich (Mark 5, Step R2b): sync.js mit Node, Einbindung in die Seite, eigene Aktionen, Abgleich nur wenn erlaubt."""
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
js = (WEB / "sync.js").read_text(encoding="utf-8")

# 1) Einbindung: sync.js vor app.js, genau einmal
assert html.count('src="sync.js"') == 1 and html.index('src="sync.js"') < html.index('src="app.js"')
assert "window.JarvisSync.createSync(" in app

# 2) Abgleich laeuft nur, wenn die Seite ihn vertragen kann
block = app.split("syncControl = window.JarvisSync.createSync({")[1].split("syncControl.start(")[0]
assert "isHidden: () => document.hidden" in block
assert "canApply: () => !guestMode && !busy && !ended && !document.querySelector(\".confirm-row\")" in block
assert "showHistory(data.messages)" in block and "applyState({ projects: data.projects, active: data.active })" in block
assert "innerHTML" not in block and "innerHTML" not in js
assert "visibilitychange" in app and "syncControl.poll()" in app

# 3) Eigene Aktionen werden nur gemerkt, nicht doppelt gezeichnet
api_block = app.split("async function api(method, path, body) {")[1].split("\n}\n")[0]
assert 'method === "POST" && syncControl && OWN_CHANGE_PATHS.some' in api_block
assert "syncControl.markOwnChange()" in api_block
assert api_block.index("if (!response.ok)") < api_block.index("markOwnChange")      # nur nach Erfolg
paths = re.search(r"const OWN_CHANGE_PATHS = \[(.*?)\];", app).group(1)
for path in ("/api/message", "/api/confirm", "/api/plan/", "/api/conversation/", "/api/project/"):
    assert '"' + path + '"' in paths, path

# 4) Schrittweite und Abfrage gegen die Adresse, die der Server wirklich hat
assert "const INTERVAL_MS = 2000" in js and '"/api/sync"' in js and 'encodeURIComponent(version)' in js
import server
assert 'path == "/api/sync"' in (PROJECT_DIR / "server.py").read_text(encoding="utf-8")

# 5) sync.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "sync_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sync.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, sync.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
