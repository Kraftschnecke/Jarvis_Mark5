"""Wecker-Banner (Step 2.11): alarm.js mit Node, Einbindung in die Seite, Einstellungsseite."""

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
alarm = (WEB / "alarm.js").read_text(encoding="utf-8")

# Einbindung: Skript vor app.js, Banner versteckt, Knoepfe vorhanden
assert html.index('src="alarm.js"') < html.index('src="app.js"')
assert re.search(r'<div[^>]*id="ringing"[^>]*\bhidden\b', html), "Banner muss ohne Läuten versteckt sein"
for element in ("ringing-title", "ringing-detail", "ringing-hint", "ringing-off", "ringing-snooze"):
    assert f'id="{element}"' in html, element
assert 'role="alert"' in html.split('id="ringing"')[1].split(">")[0]

# Die Seite fragt den Server ab und schickt Aus/Schlummern dorthin; im Gastmodus nichts
assert "/api/ringing" in alarm and "/api/ringing/stop" in alarm
assert "if (!guestMode) ringer.poll();" in app and "setInterval(pollRinging, 1000);" in app
assert "body.guest .ringing" in css
assert ".ringing[hidden] { display: none; }" in css and "prefers-reduced-motion" in css.split(".ringing-off")[1]

# Texte aus dem Server (Namen) nur als Text einsetzen, nie als HTML
ui_code = app.split("const ringingBar")[1].split("setInterval(pollRinging")[0]
for code in (ui_code, alarm):
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code and "eval(" not in code
assert "textContent = view.title" in ui_code and "textContent = view.detail" in ui_code

# Einstellungsseite: alle fuenf Zeilen mit passenden Grenzen (wie im Server)
page = app.split('key: "Alarm"')[1].split('key: "Limits"')[0]
assert 'key: "sound", type: "select", options: ["Computer", "Browser", "Aus"]' in page
assert 'key: "ring_timers", type: "toggle"' in page and 'key: "briefing", type: "toggle"' in page
assert 'key: "max_minutes", type: "number", min: 1, max: 60' in page
assert 'key: "snooze_minutes", type: "number", min: 1, max: 60' in page

# Wecker im Kalender (Step 2.11b): Namen nur als Text, Endpunkte, Bestaetigung bei Wiederholung
cal = app.split("function alarmItem")[1].split("function update(data)")[0]
assert "innerHTML" not in cal and "insertAdjacentHTML" not in cal
for endpoint in ("/api/alarms/delete", "/api/alarms/update", "/api/alarms"):
    assert endpoint in cal, endpoint
assert "if (alarm.repeat && !armed)" in cal                      # ganze Serie: erst nach zweitem Klick
assert "has-alarm" in app and "W.alarmsByDate" in app and ".w-cal-day.has-alarm" in css

node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "alarm_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALARM UI OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, alarm.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
