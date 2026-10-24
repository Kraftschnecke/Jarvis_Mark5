"""Seitenleiste (Etappe C): Einbindung in die Seite, Einstellungen passen zum Server, widgets.js mit Node."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from settings_manager import SettingsManager

WEB = PROJECT_DIR / "web"
html = (WEB / "index.html").read_text(encoding="utf-8")
app = (WEB / "app.js").read_text(encoding="utf-8")
css = (WEB / "style.css").read_text(encoding="utf-8")

# 1) Seite: widgets.js vor app.js, Leiste und alle fünf Felder anfangs versteckt
assert html.index('src="widgets.js"') < html.index('src="app.js"')
assert " hidden" in re.search(r'<aside[^>]*id="widgets"[^>]*>', html).group(0)
for slot in ("top", "middle", "bottom", "fourth", "fifth"):
    assert " hidden" in re.search(r'<section[^>]*id="widget-%s"[^>]*>' % slot, html).group(0), slot

# 2) Standard: oben Uhr, mitte Notizen, unten aus (kein Netz-Abruf ohne dein Zutun)
assert SettingsManager.DEFAULT_SETTINGS["widgets"] == {"top": "Clock", "middle": "Notes", "bottom": "Off", "fourth": "Off", "fifth": "Off"}

# 3) Die Auswahl in den Einstellungen ist genau die Liste, die der Server akzeptiert
page = app.split('key: "Widgets"')[1].split('key: "Activity"')[0]
for slot in ("top", "middle", "bottom", "fourth", "fifth"):
    row = re.search(r'key: "%s", type: "select", options: \[([^\]]*)\]' % slot, page).group(1)
    options = tuple(re.findall(r'"([^"]+)"', row))
    assert options == SettingsManager.CHOICES[("widgets", slot)], (slot, options)
# Jede Auswahl hat eine Zeichenfunktion
renderers = app.split("const WIDGET_RENDERERS = {")[1].split("};")[0]
for choices in (SettingsManager.CHOICES[("widgets", s)] for s in ("top", "middle", "bottom", "fourth", "fifth")):
    for name in choices:
        if name != "Off":
            assert re.search(r'(^|[\s{,])"?%s"?:' % re.escape(name), renderers), name

# 4) Sicherheit: Inhalte (Notizen, Ziele, Teamnamen) nie als HTML einsetzen
section = app.split("// Seitenleiste rechts (Etappe C)")[1].split("// Enter sendet")[0]
assert "innerHTML" not in section and "insertAdjacentHTML" not in section and "outerHTML" not in section
assert "api(" in section and "fetch(" not in section, "alles ueber die gemeinsame api()-Funktion"
assert "https://" not in section, "der Browser ruft nie selbst ins Internet"
# Die Leiste kommt in die Seite, wenn Einstellungen geladen werden, und nie im Gastmodus
assert "applyWidgets();" in app.split("function applySettingsState")[1].split("\n}\n")[0]
assert "if (guestMode) return \"Off\"" in section
assert "body.guest .widgets" in css
# Schmale Fenster: Leiste klappt ueber einen Knopf von rechts auf (statt dauerhaft Platz zu brauchen)
assert 'id="widgets-button"' in html and " hidden" in re.search(r'<button[^>]*id="widgets-button"[^>]*>', html).group(0)
narrow = css.split("@media (max-width: 1180px) {")[1].split("\n}\n")[0]
assert "position: fixed" in narrow and "translateX(110%)" in narrow and ".layout.widgets-open .widgets" in narrow
assert "layout.classList.toggle(\"widgets-open\"" in section and "Escape" in section
assert "(max-width: 1180px)" in section
assert "body.guest .widgets-button" in css
assert "!guestMode" in section.split("function updateWidgetsButton")[1].split("\n}\n")[0]
# Jarvis kann Termine eintragen: nach jeder Nachricht werden Kalender und Ziele neu geladen
assert "refreshWidgets();" in app.split("async function sendMessage")[1].split("\nfunction setBusy")[0]

# 4b) Linke Leiste einklappbar (breites Fenster), Zustand gemerkt, Knopf immer sichtbar (ausser Gastmodus)
assert re.search(r"\.menu-button \{ display: inline-block;", css)
assert re.search(r"@media \(min-width: 721px\) \{\s*\.layout\.sidebar-collapsed \.sidebar \{ display: none; \}", css)
click = app.split('menuButton.addEventListener("click"')[1].split("\n});")[0]
assert "sidebar-open" in click and "sidebar-collapsed" in click and "localStorage.setItem" in click
assert "try {" in app.split("narrowForSidebar =")[1].split("menuButton.addEventListener")[0]

# 5) widgets.js (braucht Node; ohne Node wird nur das gemeldet)
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "widgets_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "widgets.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, widgets.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
