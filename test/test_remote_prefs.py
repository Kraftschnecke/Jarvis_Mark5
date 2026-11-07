"""Handy-Einstellungen (Mark 5, nach R6): Design, Akzentfarbe, Sprachausgabe nur auf dem Handy. remote_prefs.js mit Node, Einbindung, nichts geht an den Server."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

WEB = PROJECT_DIR / "web"
html = (WEB / "index.html").read_text(encoding="utf-8")
app = (WEB / "app.js").read_text(encoding="utf-8")
css = (WEB / "style.css").read_text(encoding="utf-8")
js = (WEB / "remote_prefs.js").read_text(encoding="utf-8")

# 1) Einbindung: Skript vor app.js, Knopf nur am Handy sichtbar (anfangs versteckt), eigener Dialog
assert html.count('src="remote_prefs.js"') == 1 and html.index('src="remote_prefs.js"') < html.index('src="app.js"')
assert 'id="open-phone-prefs" type="button" hidden' in html and "Handy-Einstellungen" in html
assert '<dialog id="phone-prefs">' in html and 'id="phone-prefs-rows"' in html and 'id="phone-prefs-close"' in html
assert "innerHTML" not in js
assert "body.remote #open-phone-prefs { display: flex !important; }" in css

# 1b) Am PC bleibt der Knopf wirklich weg: "hidden" darf nicht von display: flex der Seitenleisten-Knoepfe ueberstimmt werden,
#     und nur der Settings-Knopf schiebt sich mit margin-top: auto nach unten (sonst sitzen zwei Knoepfe mit Luft dazwischen)
assert ".side-button[hidden] { display: none; }" in css
assert css.index(".side-button[hidden] { display: none; }") > css.index(".side-button, .row {")
assert "#open-phone-prefs { margin-top: 0; }" in css and "body.remote #open-settings + #open-phone-prefs { margin-top: auto; }" in css

# 2) Der Knopf folgt dem Modus, den der Server meldet
block = app.split("function setRemoteMode(value) {")[1].split("document.addEventListener")[0]
assert 'document.getElementById("open-phone-prefs").hidden = !value;' in block

# 3) Handy-Werte ueberdecken die Werte des PC nur am Handy, das Original (Server) bleibt erhalten
assert "serverSettings = data.settings;" in app
merge = app.split("function mergePhonePrefs() {")[1].split("}\n")[0]
assert "window.JarvisRemotePrefs.load(localStorage)" in merge and "remoteMode ? window.JarvisRemotePrefs.apply(serverSettings, phonePrefs) : serverSettings" in merge
state = app.split("function applySettingsState(data) {")[1].split("\n}\n")[0]
assert state.index("setRemoteMode(data.remote === true)") < state.index("mergePhonePrefs()") < state.index("applyAppearance()") < state.index("applyVoice()")

# 4) Beim Aendern: speichern, neu mischen, anwenden; keine Anfrage an den Server
change = app.split("function changePhonePref(change) {")[1].split("\n}\n")[0]
for part in ("prefs.normalize(", "prefs.save(localStorage", "mergePhonePrefs()", "applyAppearance()", "applyVoice()"):
    assert part in change, part
assert "api(" not in change and "fetch(" not in change and "/api/settings" not in change
dialog = app.split("// Handy-Einstellungen: nur Anzeige und Browser-Speicher")[1].split('document.getElementById("open-settings")')[0]
assert "api(" not in dialog and "fetch(" not in dialog and "innerHTML" not in dialog
assert "prefs.THEMES" in dialog and "prefs.ACCENTS" in dialog and 'changePhonePref({ speech: box.checked })' in dialog

# 4b) Schriftgroesse und Seitenleiste pro Geraet, Zuruecksetzen, Speicher im Arbeitsspeicher gefuehrt
assert "let phonePrefs = null;" in app and "if (phonePrefs === null) phonePrefs = window.JarvisRemotePrefs.load(localStorage);" in app
assert "applyWidgets()" in change
assert "prefs.FONT_SIZES" in dialog and "prefs.SLOTS" in dialog and 'changePhonePref({ font_size: Number(value) })' in dialog
assert 'smallButton("Alles wie am PC"' in dialog and "phonePrefs = {};" in dialog and "prefs.save(localStorage, phonePrefs)" in dialog
assert dialog.count("applyWidgets()") >= 1
assert "PHONE_SLOT_LABELS" in app and "Seitenleiste: Feld 1" in app

# 5) Der Dialog der PC-Einstellungen ist am Handy weiter nicht erreichbar, und es gibt keine neue erlaubte Adresse
import remote_policy
assert "body.remote #open-settings" in css
assert not any("prefs" in path for path in remote_policy.GET_API | remote_policy.POST_API)
assert "/api/settings" in remote_policy.GET_API and "/api/settings" not in remote_policy.POST_API
assert "/api/speak" in remote_policy.POST_API            # die Sprachausgabe selbst ist am Handy erlaubt

# 6) remote_prefs.js im Test mit Node
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "remote_prefs_check.js")], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "remote_prefs.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, remote_prefs.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
