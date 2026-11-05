"""Statusbericht und Timer-Leiste (Step 6b): status.js mit Node, Einbindung in die Seite."""

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

# Einbindung
assert html.index('src="status.js"') < html.index('src="app.js"')
assert re.search(r'<div[^>]*id="timers"[^>]*\bhidden\b', html), "Timer-Leiste muss ohne Timer versteckt sein"
assert "loadSettings().finally(() => { showStartupReport(); refreshTree(); refreshTimers(); refreshFocus(); });" in app
assert "/api/timers" in app and "/api/timer/cancel" in app

# Namen kommen aus Nachrichten: nur als Text einsetzen, nie als HTML
timer_code = app.split("function renderTimers")[1].split("setInterval(refreshTimers")[0]
assert "innerHTML" not in timer_code and "insertAdjacentHTML" not in timer_code
assert 'el("span", "timer-name", t.name)' in timer_code

node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "status_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "status.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, status.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
