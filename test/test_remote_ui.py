"""Remote R4 (Mark 5): Einstellungsseite "Remote". remote_admin.js mit Node, Einbindung, Zeilen passen zu den Einstellungen des Servers, nur textContent."""
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
js = (WEB / "remote_admin.js").read_text(encoding="utf-8")

import server
from settings_manager import SettingsManager

# 1) Einbindung
assert html.count('src="remote_admin.js"') == 1 and html.index('src="remote_admin.js"') < html.index('src="app.js"')
assert "window.JarvisRemoteAdmin" in app and "innerHTML" not in js

# 2) Die Seite: Schalter und Zahlen gehoeren zu Einstellungen, die der Server kennt und pruefen kann
page = app.split('key: "Remote", icon:')[1].split('key: "Focus", icon:')[0]
rows = re.findall(r'\{ label: "([^"]+)", category: "remote", key: "(\w+)", type: "(\w+)"', page)
assert [(key, kind) for _, key, kind in rows] == [
    ("enabled", "toggle"), ("info", "toggle"), ("daily", "toggle"), ("pc", "toggle"),
    ("max_messages", "number"), ("max_ai_per_day", "number")], rows
defaults = SettingsManager(Path(tempfile.mkdtemp()) / "s.json").get_category("remote")
for _, key, _ in rows:
    assert key in defaults, key
    assert ("remote", key) in server.EDITABLE_SETTINGS, key
assert 'type: "remote-panel"' in page and page.index('type: "remote-panel"') > page.index('key: "max_ai_per_day"')
assert 'min: 0, max: 1000' in page and 'min: 0, max: 100000' in page
assert "Programme starten und Dateien öffnen gibt es nie über Remote" in page          # ehrlich, was nie geht
assert 'if (row.type === "remote-panel")' in app and "buildRemotePanel()" in app

# 3) Das Panel: richtige Adressen, nur textContent, Link nur kurz, Sicherheitsabfrage bei "Alle sperren"
panel = app.split("function buildRemotePanel() {")[1].split("function buildMemoryList()")[0]
for path in ("/api/remote/state", "/api/remote/pair_link", "/api/remote/revoke", "/api/remote/revoke_all", "/api/remote/forget"):
    assert '"' + path + '"' in panel, path
    assert '"' + path + '"' in (PROJECT_DIR / "server.py").read_text(encoding="utf-8"), path
assert "innerHTML" not in panel and "insertAdjacentHTML" not in panel and "outerHTML" not in panel
assert "admin.canPair(info)" in panel                                   # Koppel-Feld nur, wenn Remote an ist
assert "name.maxLength = 40;\n      name.setAttribute(" in panel and "input.readOnly = true" in panel
assert "if (!armed) {\n          armed = true;\n          all.textContent = \"Wirklich alle sperren?\";" in panel and "window.setTimeout" in panel
assert "if (data) {\n          lastPairLink = null;\n          render(data.state);" in panel      # nach "alle sperren" ist der Link weg
assert "holder.isConnected" in panel                                    # Zeitgeber laeuft nicht weiter, wenn die Seite gewechselt wurde
assert panel.index("view.canRevoke") < panel.index('"/api/remote/revoke"') < panel.index('"/api/remote/forget"')
assert "localStorage" not in panel and "sessionStorage" not in panel    # der Link wird nirgends gespeichert
assert "console.log" not in panel
for cls in ("remote-panel", "remote-status", "remote-device-name", "remote-link"):
    assert "." + cls in css, cls

# 4) remote_admin.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "remote_admin_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "remote_admin.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, remote_admin.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
