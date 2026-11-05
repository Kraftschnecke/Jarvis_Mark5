"""App-Installation (Mark 5, Step 4B.2): Manifest, Icons, Service-Worker, Einbindung; der Server liefert alles richtig aus."""
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

import http.client
import json
import re
import struct
import threading

import server
from settings_manager import SettingsManager

WEB = PROJECT_DIR / "web"
folder = Path(tempfile.mkdtemp())
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, monitor=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=jarvis.settings_manager, guest=True), guest=True)
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()


def get(srv, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Host": host} if host else {})
    response = conn.getresponse()
    body = response.read()
    headers = dict(response.getheaders())
    conn.close()
    return response.status, headers, body


def png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "kein PNG"
    return struct.unpack(">II", data[16:24])


# 1) Manifest
manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
assert manifest["name"] == "J.A.R.V.I.S." and manifest["short_name"] == "Jarvis"
assert manifest["start_url"] == "/" and manifest["scope"] == "/" and manifest["display"] == "standalone" and manifest["lang"] == "de"
assert re.fullmatch(r"#[0-9a-f]{6}", manifest["theme_color"]) and re.fullmatch(r"#[0-9a-f]{6}", manifest["background_color"])
purposes = {}
for icon in manifest["icons"]:
    data = (WEB / icon["src"]).read_bytes()
    w, h = png_size(data)
    assert icon["type"] == "image/png" and icon["sizes"] == f"{w}x{h}" and w == h, icon
    purposes.setdefault(icon["purpose"], []).append(w)
assert 192 in purposes["any"] and 512 in purposes["any"] and purposes["maskable"] == [512], "Chrome verlangt 192 und 512"
assert png_size((WEB / "apple-touch-icon.png").read_bytes()) == (180, 180)

# 2) Service-Worker: reicht nur durch, speichert nichts
sw = (WEB / "sw.js").read_text(encoding="utf-8")
code = "\n".join(line for line in sw.splitlines() if not line.strip().startswith("//"))
assert 'addEventListener("fetch"' in code and "respondWith(fetch(event.request))" in code
for forbidden in ("caches", "cache.", "indexedDB", "localStorage", "postMessage", "importScripts", "Response("):
    assert forbidden not in code, f"der Service-Worker darf nichts speichern oder veraendern: {forbidden}"

# 3) Einbindung in die Seite
html = (WEB / "index.html").read_text(encoding="utf-8")
head = html.split("</head>")[0]
for tag in ('<link rel="manifest" href="manifest.webmanifest">', '<link rel="apple-touch-icon" href="apple-touch-icon.png">',
            '<meta name="apple-mobile-web-app-capable" content="yes">', '<meta name="theme-color" content="#1d1c1b">',
            'navigator.serviceWorker.register("sw.js")'):
    assert tag in head, tag
assert manifest["theme_color"] == "#1d1c1b"

# 4) Der Server liefert alles mit dem richtigen Typ, ohne Zwischenspeicher
expected = {"/manifest.webmanifest": "application/manifest+json", "/sw.js": "text/javascript", "/icon-192.png": "image/png",
            "/icon-512.png": "image/png", "/icon-maskable-512.png": "image/png", "/apple-touch-icon.png": "image/png"}
for srv in (httpd, guest_httpd):
    for path, kind in expected.items():
        status, headers, body = get(srv, path)
        assert status == 200 and headers["Content-Type"].startswith(kind), (path, status, headers.get("Content-Type"))
        assert headers["Cache-Control"] == "no-cache", path
        assert body == (WEB / path.lstrip("/")).read_bytes()
status, headers, body = get(httpd, "/manifest.webmanifest")
assert json.loads(body)["start_url"] == "/"
# Fremder Host wird auch fuer diese Dateien abgewiesen (Schutz vor DNS-Rebinding bleibt)
assert get(httpd, "/manifest.webmanifest", host="evil.example")[0] == 403
assert get(httpd, "/sw.js", host="evil.example:8000")[0] == 403
assert get(httpd, "/../server.py")[0] in (403, 404) and get(httpd, "/nope.webmanifest")[0] == 404

# 5) Die Seite bleibt lokal: Server hoert weiter nur auf 127.0.0.1
assert "SERVER_HOST = \"127.0.0.1\"" in (PROJECT_DIR / "config.py").read_text(encoding="utf-8")

print("ALL TESTS PASSED")
