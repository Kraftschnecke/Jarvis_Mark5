"""Remote R4 (Mark 5): Einstellungsseite "Remote". remote_admin.js mit Node, Einbindung, Zeilen passen zu den Einstellungen des Servers, nur textContent."""
import sys
import webapp
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
app = webapp.app_text()
css = (WEB / "style.css").read_text(encoding="utf-8")
js = (WEB / "remote_admin.js").read_text(encoding="utf-8")

import server
from settings_manager import SettingsManager

# 1) Einbindung
assert html.count('src="remote_admin.js"') == 1 and html.index('src="remote_admin.js"') < html.index('src="app_base.js"')
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
for path in ("/api/remote/state", "/api/remote/pair_link", "/api/remote/revoke", "/api/remote/revoke_all", "/api/remote/forget",
             "/api/remote/profile_add", "/api/remote/profile_limits", "/api/remote/profile_delete", "/api/remote/profile_reset", "/api/remote/profile_reset_usage"):
    assert '"' + path + '"' in panel, path
    assert '"' + path + '"' in (PROJECT_DIR / "server.py").read_text(encoding="utf-8"), path
assert "innerHTML" not in panel and "insertAdjacentHTML" not in panel and "outerHTML" not in panel
assert "admin.canPair(info)" in panel                                   # Koppel-Feld nur, wenn Remote an ist
assert "name.maxLength = 40;\n      name.setAttribute(" in panel and "input.readOnly = true" in panel
assert "if (!armed) {\n          armed = true;\n          all.textContent = \"Wirklich alle sperren?\";" in panel and "window.setTimeout" in panel
assert "if (data) {\n          lastPairLink = null;\n          render(data.state);" in panel      # nach "alle sperren" ist der Link weg
assert "holder.isConnected" in panel                                    # Zeitgeber laeuft nicht weiter, wenn die Seite gewechselt wurde
assert panel.index("view.canRevoke") < panel.index('"/api/remote/revoke"') < panel.index('"/api/remote/forget"')
assert '"Wirklich löschen?", "/api/remote/profile_delete"' in panel and "if (!armed) {\n            armed = true;\n            button.textContent = armedLabel;" in panel   # Bereich loeschen: zwei Klicks
assert "admin.parseLimit(ai.value)" in panel and "showError(\"Limits sind ganze Zahlen" in panel     # Limits werden vor dem Senden geprueft
assert "localStorage" not in panel and "sessionStorage" not in panel    # der Link wird nirgends gespeichert
assert "console.log" not in panel
for cls in ("remote-panel", "remote-status", "remote-device-name", "remote-link", "remote-profiles", "remote-profile", "remote-limit"):
    assert "." + cls in css, cls

# 3b) PC-Agent (S6): Status und Verbindungstest nutzen echte Adressen des Servers, nur textContent, Test-Knopf nur bei verbundenem Agent
assert '"/api/agent/status"' in panel and '"/api/agent/ping"' in panel
server_text = (PROJECT_DIR / "server.py").read_text(encoding="utf-8")
assert '"/api/agent/status"' in server_text and '"/api/agent/ping"' in server_text
assert "if (info.active) box.appendChild(buildAgentLine());" in panel
assert "if (state.online === true) {\n        line.appendChild(smallButton(\"Verbindung testen\"" in panel
assert "admin.agentView(state)" in panel and "(PC-Agent)" in panel

# 4) remote_admin.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "remote_admin_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "remote_admin.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, remote_admin.js wurde nicht geprueft.")


# 5) Testbereich (Gast, C4): Anzeige im Browser, die Sperre steht im Server (test_server_tester.py)
pair_page = (PROJECT_DIR / "web" / "pair.html").read_text(encoding="utf-8")
assert 'id="code-form"' in pair_page and 'id="code"' in pair_page and "extractCode" in pair_page
assert 'autocapitalize="characters"' in pair_page and 'placeholder="Code, z. B. K7M2-QX9P"' in pair_page         # Code wird gross getippt
assert 'id="install"' in pair_page and '(display-mode: standalone)' in pair_page and 'document.getElementById("install").hidden = true;' in pair_page   # in der App keine Installationsanleitung
assert "innerHTML" not in pair_page and "localStorage" not in pair_page and "sessionStorage" not in pair_page
assert 'input.value = "";                      // der Code bleibt nicht im Feld stehen' in pair_page                                    # der Code bleibt nicht im Feld stehen
assert "form[hidden], #session[hidden] { display: none; }" in pair_page                      # hidden wird nicht von display:flex ueberstimmt
assert "Als App installieren" in pair_page and "Zum Home-Bildschirm" in pair_page and "Diese Website als App installieren" in pair_page
assert "history.replaceState" in pair_page and pair_page.index("history.replaceState") < pair_page.index("pair(code);\n    })();")
assert app.count("setTesterMode(") == 2 and "data.remote === true && data.tester === true" in app      # nur ueber Remote
assert "async function newConversation(project) {\n  if (testerMode) {" in app and 'api("POST", "/api/conversation/new", {})' in app
assert "if (testerMode) {\n    // Im Testbereich gibt es keine Projekte" in app
assert "body.tester .row .more" in css


# 6) Rollen-Seiten: guest.html zeigt nur, was ein Gast braucht; jede Datei, die sie laedt, darf ein Gast auch holen
import re
import remote_policy
guest_page = (PROJECT_DIR / "web" / "guest.html").read_text(encoding="utf-8")
owner_page = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
for owner_only in ('id="new-project"', 'id="memory-danger"', 'id="settings"', 'id="open-settings"', "remote_admin.js", "app_owner.js"):
    assert owner_only in owner_page and owner_only not in guest_page, owner_only
for needed in ('id="new-conversation"', 'id="composer"', 'id="widgets"', 'id="logout-button"', 'id="phone-prefs"', 'class="tester remote"'):
    assert needed in guest_page, needed
assert 'id="logout-button"' in owner_page and "J.A.R.V.I.S. Gast" in guest_page
loaded = re.findall(r'<script src="([^"]+)"', guest_page) + re.findall(r'<link rel="stylesheet" href="([^"]+)"', guest_page) \
    + re.findall(r'<link rel="manifest" href="([^"]+)"', guest_page) + re.findall(r'<link rel="(?:icon|apple-touch-icon)"[^>]* href="([^"]+)"', guest_page)
assert len(loaded) >= 14, loaded
for name in loaded:
    assert ("/" + name) in remote_policy.GUEST_STATIC, name          # sonst bekommt der Gast hier ein 404
    assert (PROJECT_DIR / "web" / name).is_file(), name
assert "/remote_admin.js" not in remote_policy.GUEST_STATIC and "/index.html" not in remote_policy.GUEST_STATIC
assert remote_policy.guest_file("/") == remote_policy.guest_file("/index.html") == remote_policy.guest_file("/guest.html") == "/guest.html"
for name in webapp.GUEST_APP_FILES:
    assert remote_policy.guest_file("/" + name) == "/" + name and 'src="' + name + '"' in guest_page, name
assert remote_policy.guest_file("/app_owner.js") is None and remote_policy.guest_file("/app.js") is None and remote_policy.guest_file("/remote_admin.js") is None
assert 'src="app_owner.js"' in owner_page and all('src="' + name + '"' in owner_page for name in webapp.APP_FILES)
assert owner_page.index('src="app_base.js"') < owner_page.index('src="app_state.js"') < owner_page.index('src="app_owner.js"') < owner_page.index('src="app_start.js"')
assert guest_page.index('src="app_base.js"') < guest_page.index('src="app_state.js"') < guest_page.index('src="app_start.js"')
# Was nur dem Besitzer gehoert, steht in keiner Datei, die ein Gast laedt
guest_code = webapp.app_text(webapp.GUEST_APP_FILES)
for owner_marker in ("buildRemotePanel", "buildMemoryList", "buildFolderList", "buildActionList", "dangerDialog", "JarvisRemoteAdmin",
                     "/api/remote/state", "/api/remote/pair_link", "/api/memories", "/api/folders", "/api/actions", "const PAGES = ["):
    assert owner_marker not in guest_code, owner_marker
    assert owner_marker in webapp.app_text(("app_owner.js",)), owner_marker
for bad in ("/server.py", "/../server.py", "/.env", "/profiles.json", "/web/app_base.js", "/App_base.js", "/app_base.js/", "", "/api/x"):
    assert remote_policy.guest_file(bad) is None, bad

# app.js: ein fehlendes Element ist kein Fehler mehr, aber auch kein Weg am Besitzer-Teil vorbei (der Server liefert Gaesten nur ihre Seite)
assert app.count("document.getElementById(") == 1 and "function byId(id) {\n  return document.getElementById(id) ||" in app
assert 'byId("logout-button").addEventListener("click"' in app and '"/api/remote/logout"' in app and 'byId("logout-button").hidden = !value;' in app

print("ALL TESTS PASSED")