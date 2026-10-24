"""Gemeinsamer Netz-Helfer (Mark 5, Step 1.2): Regeln fuer JEDEN Abruf ins Internet.
Kein echtes Internet: Adressregeln direkt, der Abruf selbst gegen einen lokalen Testserver."""
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import net_fetch
from net_fetch import ANY_PUBLIC_HOST, NetError, check_url

HOSTS = ("api.example.org",)


def refused(url, hosts=HOSTS):
    try:
        check_url(url, hosts)
    except NetError:
        return True
    return False


# ---- Adressregeln mit fester Host-Liste
assert check_url("https://api.example.org/v1/x?a=1", HOSTS)
assert check_url("https://API.example.org/", HOSTS)
assert check_url("https://api.example.org:443/", HOSTS)
for bad in (
    "http://api.example.org/",                  # kein https
    "ftp://api.example.org/",
    "file:///etc/passwd",
    "https://evil.example/",                    # falscher Host
    "https://api.example.org.evil.example/",    # Host nur als Anfang
    "https://evil.example/api.example.org",
    "https://api.example.org:8443/",            # fremder Port
    "https://user:pw@api.example.org/",         # Zugangsdaten in der Adresse
    "https://api.example.org@evil.example/",    # Trick mit @
    "https://127.0.0.1/",
    "https://[::1]/",
    "",
    "nur text",
):
    assert refused(bad), bad
assert refused("https://api.example.org/", ())          # leere Liste erlaubt nichts
assert refused("https://api.example.org/", "api.example.org")   # ein Text statt Liste ist ein Programmierfehler

# ---- ANY_PUBLIC_HOST: nur oeffentliche Adressen
answers = {}


def fake_resolve(host, port, type=0):
    if host not in answers:
        raise OSError("unbekannt")
    return [(2, 1, 6, "", (ip, port)) for ip in answers[host]]


net_fetch._resolve = fake_resolve
answers.update({
    "gut.example": ["93.184.216.34"],
    "lokal.example": ["127.0.0.1"],
    "heimnetz.example": ["192.168.1.20"],
    "gemischt.example": ["93.184.216.34", "10.0.0.5"],
    "link.example": ["169.254.169.254"],
    "v6lokal.example": ["::1"],
    "v6ula.example": ["fd00::1"],
})
assert check_url("https://gut.example/seite", ANY_PUBLIC_HOST)
for name in ("lokal", "heimnetz", "gemischt", "link", "v6lokal", "v6ula", "gibtsnicht"):
    assert refused(f"https://{name}.example/", ANY_PUBLIC_HOST), name
assert refused("https://93.184.216.34/", ANY_PUBLIC_HOST), "Zahlenadressen nie"
assert refused("https://localhost/", ANY_PUBLIC_HOST)
assert refused("http://gut.example/", ANY_PUBLIC_HOST)

# ---- Weiterleitungen: gleiche Regeln
redirects = net_fetch.SafeRedirects(HOSTS)
req = urllib.request.Request("https://api.example.org/a")
for target in ("https://evil.example/", "http://api.example.org/", "file:///etc/passwd"):
    try:
        redirects.redirect_request(req, None, 302, "Found", {}, target)
        raise AssertionError(target)
    except NetError as error:
        assert "Weiterleitung" in str(error)
assert redirects.redirect_request(req, None, 302, "Found", {}, "https://api.example.org/b") is not None

# ---- Der Abruf selbst (gegen lokalen Testserver, ohne die https-Regel von fetch_text)
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/ok":
            body = "grüße".encode("utf-8")
        elif self.path == "/gross":
            body = b"x" * 5000
        elif self.path == "/langsam":
            time.sleep(1.5)
            body = b"spaet"
        elif self.path == "/kaputt":
            body = b"\xff\xfe\xfa"
        elif self.path == "/weiter":
            self.send_response(302)
            self.send_header("Location", "https://evil.example/x")
            self.end_headers()
            return
        elif self.path == "/500":
            self.send_response(500)
            self.end_headers()
            return
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass    # der Abrufer hat schon aufgelegt (Zeitlimit-Test)


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"


def get(path, timeout=5, max_bytes=1000):
    """fetch_text mit der gleichen Fehlerzuordnung, aber ohne Adresspruefung (Testserver ist http)."""
    original = net_fetch.check_url
    net_fetch.check_url = lambda url, hosts: url if url.startswith("http://127.0.0.1") else original(url, hosts)
    try:
        return net_fetch.fetch_text(base + path, HOSTS, timeout=timeout, max_bytes=max_bytes)
    finally:
        net_fetch.check_url = original


def error_of(path, **kw):
    try:
        get(path, **kw)
    except NetError as error:
        return error
    raise AssertionError(path)


assert get("/ok") == "grüße"
assert "zu gross" in str(error_of("/gross")), "Antwort ueber dem Limit"
assert "nicht rechtzeitig" in str(error_of("/langsam", timeout=0.3))
assert "nicht lesbar" in str(error_of("/kaputt"))
assert error_of("/500").status == 500 and "500" in str(error_of("/500"))
assert error_of("/nix").status == 404
assert "Weiterleitung" in str(error_of("/weiter"))
dead = HTTPServer(("127.0.0.1", 0), Handler)
dead_port = dead.server_address[1]
dead.server_close()
base_alive = base
base = f"http://127.0.0.1:{dead_port}"
assert "Keine Verbindung" in str(error_of("/ok"))
base = base_alive

# ---- fetch_json und Parameter
sent = []
net_fetch._download = lambda request, hosts, timeout, max_bytes: (sent.append(request), b'{"a": [1, 2]}')[1]
assert net_fetch.fetch_json("https://api.example.org/x", HOSTS, params={"q": "München & Co"}) == {"a": [1, 2]}
assert sent[0].full_url == "https://api.example.org/x?q=M%C3%BCnchen+%26+Co", sent[0].full_url
assert sent[0].get_header("User-agent") == "Jarvis"
net_fetch.fetch_json("https://api.example.org/x?a=1", HOSTS, params={"b": "2"}, headers={"X-Key": "k"})
assert sent[1].full_url.endswith("?a=1&b=2") and sent[1].get_header("X-key") == "k"
net_fetch._download = lambda *a: b"kein json"
try:
    net_fetch.fetch_json("https://api.example.org/x", HOSTS)
    raise AssertionError
except NetError as error:
    assert "JSON" in str(error)

# Abruf einer nicht erlaubten Adresse kommt gar nicht erst bis zum Download
net_fetch._download = lambda *a: (_ for _ in ()).throw(AssertionError("darf nicht abgerufen werden"))
try:
    net_fetch.fetch_text("https://evil.example/", HOSTS)
    raise AssertionError
except NetError:
    pass

print("ALL TESTS PASSED")
