"""Links im Chat (Mark 5, Step 2.2): links.js mit Node, Einbindung, sichere Darstellung."""

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
links = (WEB / "links.js").read_text(encoding="utf-8")
css = (WEB / "style.css").read_text(encoding="utf-8")

# Einbindung: links.js vor app.js, app.js nutzt es
assert html.index('src="links.js"') < html.index('src="app.js"')
assert "JarvisLinks.splitLinks(text)" in app

# Sichere Darstellung: Anker nur ueber das DOM, mit noopener, Rechnername sichtbar, nie innerHTML
render = app.split("function renderText")[1].split("function addMessage")[0]
assert "innerHTML" not in render and "insertAdjacentHTML" not in render
assert 'anchor.rel = "noopener noreferrer"' in render and 'anchor.target = "_blank"' in render
assert "anchor.textContent = piece.label" in render and "piece.host" in render
assert "https:" in links and "javascript" not in links.replace("// ", "")   # nur https wird zugelassen
assert re.search(r"\.message a\s*\{", css) and ".link-host" in css

# Der News-Prompt verlangt Links aus dem Ergebnis, ohne erfundene Adressen
import brain
import inspect
source = inspect.getsource(brain.respond_to_task)
assert "Markdown link [headline](url)" in source and "Never invent or change a url" in source

node = shutil.which("node")
if node:
    result = subprocess.run([node, str(PROJECT_DIR / "test" / "links_check.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "links.js OK" in result.stdout
else:
    print("Hinweis: Node.js nicht gefunden, links.js wurde nicht geprueft.")

print("ALL TESTS PASSED")
