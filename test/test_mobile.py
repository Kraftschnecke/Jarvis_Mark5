"""Handy-Version (mobile.html): Gerueste, Reihenfolge der Skripte, nichts fuer Gaeste, Logik mit Node."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
WEB = PROJECT_DIR / "web"

import remote_policy

files = {name: (WEB / name).read_text(encoding="utf-8") for name in ("mobile.html", "mobile.css", "mobile.js", "mobile_logic.js", "embed.js")}
html, css, js, logic = (files[n] for n in ("mobile.html", "mobile.css", "mobile.js", "mobile_logic.js"))

# 1) Kopf wie bei den anderen Seiten: installierbar, Notch-tauglich, Design vor dem Zeichnen
for tag in ('viewport-fit=cover', '<link rel="manifest" href="manifest.webmanifest">', '<link rel="stylesheet" href="style.css">',
            '<link rel="stylesheet" href="mobile.css">', 'navigator.serviceWorker.register("sw.js")', "jarvis.theme", "jarvis.accent",
            'apple-mobile-web-app-capable'):
    assert tag in html, tag

# 2) Drei Seiten, drei Punkte, gleiche Namen wie in der Logik
ids = re.findall(r'<section class="mpage[^"]*" id="p-(\w+)"', html)
assert ids == ["start", "jarvis", "fenster"], ids
assert 'id="mpages"' in html and 'id="mpeek"' in html and 'id="mdots"' in html
assert len(re.findall(r"<button type=\"button\" aria-label=\"\w+\"><i></i></button>", html)) == 3
node = shutil.which("node")
order = [html.index(f'src="{name}"') for name in ("widgets.js", "welcome_logic.js", "welcome_panels.js", "welcome_dialogs.js", "welcome_app.js", "mobile_logic.js", "mobile.js")]
assert order == sorted(order), "Skripte muessen in dieser Reihenfolge geladen werden"
for forbidden in ("onclick=", "onload=", "javascript:", "app_base.js", "app_owner.js", "welcome.js"):
    assert forbidden not in html, forbidden
# Der Chat ist die App der Seite index.html in einem Rahmen; ?embed=1 sagt ihr, dass sie im Rahmen laeuft
assert re.search(r'<iframe id="mchat"[^>]*data-src="index.html\?embed=1"', html) and not re.search(r'<iframe[^>]* src=', html) and 'title="Jarvis"' in html
for needle in ('id="mstart"', 'id="mwindows"', 'id="layer"', 'id="mcore"', 'id="date"', 'id="status"', 'id="status2"', 'id="clock"'):
    assert needle in html, needle
assert 'href="/?pc=1"' in html                                          # Weg zurueck zur PC-Ansicht

# 3) Nur Text, nie HTML einsetzen
for name, text in files.items():
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert forbidden not in text, (name, forbidden)

# 4) Wischen macht der Browser (scroll-snap), mit Platz fuer Notch und Home-Balken, dvh gegen die wandernde Safari-Leiste
for needle in ("scroll-snap-type: x mandatory", "scroll-snap-align: start", "env(safe-area-inset-top)", "env(safe-area-inset-bottom)", "100dvh",
               "overscroll-behavior", "@media (prefers-reduced-motion: reduce)", "var(--accent)", "var(--base)"):
    assert needle in css, needle
assert not re.findall(r"#[0-9a-fA-F]{6}\b", css), "feste Farben gehoeren nicht hierher"
# Namen duerfen nicht mit style.css kollidieren
style = (WEB / "style.css").read_text(encoding="utf-8")
for name in set(re.findall(r"\.([a-z][a-z-]*)", css)):
    assert not re.search(rf"(?<![\w-])\.{name}(?![\w-])", style), f".{name} gibt es schon in style.css"
for needle in ("scrollTo", "hashFor", "replaceState", "ArrowRight", "ArrowLeft", "hashchange", "resize", "aria-current"):
    assert needle in js, needle
for needle in ("if (index === 1) loadChat();", "WelcomeApp.create", "splitWindows", "dialogs.manage()", "dialogs.calendar()", "dialogs[id]()"):
    assert needle in js, needle
for use in re.finditer(r"history\.replaceState", js):
    assert "try" in js[max(0, use.start() - 120):use.start()], "replaceState ohne try"

# Chat im Rahmen: kein "zurueck zur Startseite", Wisch vom Rand, nur mit ?embed=1; die Datei kommt nach app_start.js
index = (WEB / "index.html").read_text(encoding="utf-8")
assert index.index('src="app_start.js"') < index.index('src="embed.js"')
assert 'classList.contains("embed")' in (WEB / "app_start.js").read_text(encoding="utf-8")
assert "embed=1" in files["embed.js"]
assert "touch-action: pan-y" in style and "#embed-edge" in style and "body.embed .sidebar" in style

# 5) Der Gast bekommt nichts davon
for name in ("mobile.html", "mobile.css", "mobile.js", "mobile_logic.js", "embed.js", "welcome_app.js"):
    assert remote_policy.guest_file("/" + name) is None, name
guest_page = (WEB / "guest.html").read_text(encoding="utf-8")
assert "mobile.html" not in guest_page and "mobile.js" not in guest_page and "mobile.css" not in guest_page

# 6) Logik mit Node
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "mobile_check.js")], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mobile OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, die Handy-Version wurde nur statisch geprueft.")

print("test_mobile: ALL TESTS PASSED")
