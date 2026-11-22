"""Willkommensseite (web/welcome*): Aufbau, Verlinkung auf die App, Fenster, Sicherheit der Anzeige, Gast sieht nichts davon."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WEB = PROJECT_DIR / "web"
sys.path.insert(0, str(PROJECT_DIR))
import remote_policy

html = (WEB / "welcome.html").read_text(encoding="utf-8")
css = (WEB / "welcome.css").read_text(encoding="utf-8")
JS_FILES = ("welcome_logic.js", "welcome_panels.js", "welcome_dialogs.js", "welcome_app.js", "welcome.js")
js = {name: (WEB / name).read_text(encoding="utf-8") for name in JS_FILES}
all_js = "\n".join(js.values())

# 1) Das Logo ist ein echter Link auf die App (geht auch ohne Skript) und hat einen Namen fuer Vorlese-Programme
assert re.search(r'<a [^>]*id="start"[^>]*href="index.html"|<a [^>]*href="index.html"[^>]*id="start"', html)
assert 'aria-label="J.A.R.V.I.S. starten"' in html
assert "<svg" in html and 'aria-hidden="true"' in html

# 2) PWA-Einbindung wie in der App, Design-Voreinstellung vor dem Rendern
for tag in ('<link rel="manifest" href="manifest.webmanifest">', '<link rel="stylesheet" href="style.css">',
            '<link rel="stylesheet" href="welcome.css">', 'navigator.serviceWorker.register("sw.js")', "jarvis.theme", "jarvis.accent"):
    assert tag in html, tag

# 3) Gerueste fuer die Fenster, Datum und Status sind Knoepfe (sehen aus wie Text), Reihenfolge der Skripte
for needle in ('id="col-l"', 'id="col-r"', 'id="layer"', 'id="stage"', 'id="clock"', 'id="greeting"'):
    assert needle in html, needle
assert re.search(r'<button[^>]*id="date"', html) and re.search(r'<button[^>]*id="status"', html)
order = [html.index(f'src="{name}"') for name in ("widgets.js", "welcome_logic.js", "welcome_panels.js", "welcome_dialogs.js", "welcome_app.js", "welcome.js")]
assert order == sorted(order), "Skripte muessen in dieser Reihenfolge geladen werden"
for forbidden in ("app_base.js", "app_owner.js", "app_state.js", "app_start.js", "remote_admin.js", "core.js"):
    assert forbidden not in html, forbidden

# 4) Anzeige nur als Text: nie als HTML einsetzen (Termine, Ziele, Listen kommen aus Eingaben und aus dem Kalender)
for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
    assert forbidden not in all_js, forbidden
assert "textContent" in js["welcome.js"] and "textContent" in js["welcome_app.js"]

# 5) Nur diese Adressen ruft die Seite auf, und der Server kennt sie
used = set(re.findall(r'"(/api/[a-z_/]+)"', all_js))
assert used == {"/api/widgets", "/api/settings", "/api/timers", "/api/focus", "/api/weather", "/api/widgets/events", "/api/widgets/goals",
                "/api/widgets/lists", "/api/focus/stop", "/api/timer/cancel", "/api/widgets/notes", "/api/news", "/api/briefing",
                "/api/reminders", "/api/performance", "/api/system", "/api/media", "/api/volume"}, used
server_text = (PROJECT_DIR / "server.py").read_text(encoding="utf-8")
for path in used:
    assert f'"{path}"' in server_text, path
# Termine eintragen geht ueber Remote nicht: die Seite zeigt dort das Formular gar nicht erst
assert "/api/widgets/events" not in remote_policy.DAILY_POST_API and "app.local" in js["welcome_dialogs.js"]
for path in ("/api/widgets/goals", "/api/widgets/lists"):
    assert path in remote_policy.DAILY_POST_API, path

# 6) Jedes gebaute Fenster hat Anzeige, grosses Fenster und Eintrag in der Seite
logic = js["welcome_logic.js"]
built = re.findall(r'\{ id: "(\w+)", title: "[^"]+", desc: "[^"]+", state: "built" \}', logic)
assert built == ["goals", "focus", "lists", "calendar", "weather", "notes", "news", "briefing", "worldtime", "music", "system", "reminders"], built
assert "DEFAULT_ENABLED = [\"goals\", \"focus\", \"lists\", \"calendar\", \"weather\"]" in js["welcome_logic.js"]   # neue Fenster sind erst mal aus
for window in built:
    assert re.search(rf"\b{window}\b", js["welcome_panels.js"].split("return {")[-1]), f"Anzeige fehlt: {window}"
    assert re.search(rf"\b{window}\b", js["welcome_dialogs.js"].split("return {")[-1]), f"Fenster fehlt: {window}"
    assert "opener[id] = dialogs[id]" in js["welcome.js"], f"nicht verbunden: {window}"
assert "dialogs.manage()" in js["welcome.js"] and 'dialogs.calendar()' in js["welcome.js"]
assert '$("date").addEventListener("click"' in js["welcome.js"] and '$("status").addEventListener("click"' in js["welcome.js"]

# Musik und Lautstaerke nur am PC; News-Links nur http(s); Daten nur als Text
assert "!app.local" in js["welcome_dialogs.js"] and "isWebLink" in js["welcome_dialogs.js"] and "noopener" in js["welcome_dialogs.js"]
assert "isWebLink = (url) => typeof url === \"string\" && /^https?:" in js["welcome_dialogs.js"]
for path in ("/api/media", "/api/volume"):
    assert path not in remote_policy.GET_API and path not in remote_policy.POST_API and path not in remote_policy.DAILY_POST_API, path
for path in ("/api/news", "/api/briefing", "/api/reminders"):
    assert path in remote_policy.GET_API, path

# 7) Gespeicherte Auswahl: ein Schluessel, immer in try/catch (ohne Speicher laeuft die Seite trotzdem)
assert 'STORAGE_KEY = "jarvis.welcome.windows"' in logic
for name in ("welcome.js", "welcome_app.js"):
    for use in re.finditer(r"localStorage\.(get|set)Item", js[name]):
        before = js[name][max(0, use.start() - 200):use.start()]
        assert "try" in before, "localStorage ohne try"

# 8) Verhalten: ehrliche Verbindungsanzeige, Link bleibt Notausgang, Bewegung abschaltbar, Fenster schliessen mit Esc
main = js["welcome.js"]
assert "Jarvis-Server nicht erreichbar" in main and "Systeme bereit" in main
assert "preventDefault" in main and "prefers-reduced-motion" in main and "event.ctrlKey" in main
core = js["welcome_app.js"]                                                  # der gemeinsame Kern (auch fuer die Handy-Version)
assert '"Escape"' in core and 'aria-modal' in core and 'role", "dialog"' in core
assert 'setAttribute("role", "button")' in main and '"Enter"' in main

# 9) Stil: Farben aus den Variablen, feste Farben nur fuer Status (gruen/rot/gelb) und den Schalterknopf
assert "var(--accent)" in css and "var(--base)" in css and "@media (prefers-reduced-motion: reduce)" in css
assert "@media (max-width: 980px)" in css                                   # Handy: alles untereinander
fixed = set(re.findall(r"#[0-9a-fA-F]{6}\b", css))
assert fixed <= {"#3fb950", "#e5534b", "#e7b94a", "#d9d4ca"}, fixed
# Namen, die es in style.css schon gibt, duerfen hier nicht wiederverwendet werden (sonst mischen sich die Stile)
style = (WEB / "style.css").read_text(encoding="utf-8")
for name in set(re.findall(r"\.([a-z][a-z-]*)", css)):
    if name in ("row", "status", "empty", "full", "panel", "box", "bar", "date", "note", "field", "btn", "small", "tile", "form",
                "clamp", "pre", "newsitem", "wlink", "wkey", "wmeter", "wtransport"):
        assert not re.search(rf"(?<![\w-])\.{name}(?![\w-])", style), f".{name} gibt es schon in style.css"

# 10) Der Gast bekommt nichts davon (404), und seine Seite kennt die Willkommensseite nicht
for name in ("welcome.html", "welcome.css", "welcome.js", "welcome_logic.js", "welcome_panels.js", "welcome_dialogs.js", "welcome_app.js"):
    assert remote_policy.guest_file("/" + name) is None, name
    assert ("/" + name) not in remote_policy.GUEST_STATIC, name
assert "welcome" not in (WEB / "guest.html").read_text(encoding="utf-8")

# 11) Logik und Anzeige mit Node (wie die anderen Seiten-Pruefungen)
node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "welcome_check.js")], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "welcome OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, die Willkommensseite wurde nur statisch geprueft.")

print("test_welcome: ALL TESTS PASSED")
