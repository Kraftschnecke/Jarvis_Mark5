"""DNS-rebinding-Schutz (Mark 5, Step 2.6): die Verbindung nutzt die geprueften Adressen, ohne Netz getestet."""

import socket
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import net_fetch
from net_fetch import ANY_PUBLIC_HOST, NetError

PUBLIC = "93.184.216.34"


def answer(address):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


connects = []


def fake_connect(address, timeout=None, source_address=None):
    connects.append(address)
    raise OSError("kein Netz im Test")


socket.create_connection = fake_connect

# 1) Rebinding: beim Pruefen oeffentlich, beim Verbinden privat -> kein Verbindungsversuch
calls = []


def rebinding(host, port, **kwargs):
    calls.append(host)
    return answer(PUBLIC if len(calls) == 1 else "127.0.0.1")


net_fetch._resolve = rebinding
try:
    net_fetch.fetch_text("https://rebind.example/", ANY_PUBLIC_HOST)
    raise AssertionError("haette abgelehnt werden muessen")
except NetError as error:
    assert str(error) == "Unerlaubte Adresse.", error
assert len(calls) == 2 and connects == [], (calls, connects)

# 2) Gleiches fuer private Adressen im Heimnetz und IPv6-localhost
for bad in ("192.168.1.10", "10.0.0.5", "169.254.169.254", "::1", "fd00::1"):
    calls.clear()
    net_fetch._resolve = lambda host, port, bad=bad, **kw: [(socket.AF_INET6 if ":" in bad else socket.AF_INET, socket.SOCK_STREAM, 6, "", (bad, 443))]
    try:
        net_fetch.fetch_text("https://intern.example/", ANY_PUBLIC_HOST)
        raise AssertionError(bad)
    except NetError as error:
        assert str(error) == "Unerlaubte Adresse.", (bad, error)
assert connects == []

# 3) Stabil oeffentlich: verbunden wird mit der IP-Adresse, nicht noch einmal mit dem Namen
net_fetch._resolve = lambda host, port, **kw: answer(PUBLIC)
try:
    net_fetch.fetch_text("https://gut.example/seite", ANY_PUBLIC_HOST)
    raise AssertionError
except NetError as error:
    assert str(error) == "Keine Verbindung zum Dienst.", error
assert connects == [(PUBLIC, 443)], connects

# 4) Mischantwort (eine oeffentliche, eine private Adresse) wird abgelehnt
connects.clear()
net_fetch._resolve = lambda host, port, **kw: answer(PUBLIC) + answer("10.0.0.1")
try:
    net_fetch.fetch_text("https://mix.example/", ANY_PUBLIC_HOST)
    raise AssertionError
except NetError as error:
    assert str(error) == "Unerlaubte Adresse.", error
assert connects == []

# 5) Feste Host-Liste: bleibt beim bisherigen Weg (kein Pinning, kein eigener Aufloeser)
net_fetch._resolve = lambda *a, **k: (_ for _ in ()).throw(AssertionError("darf nicht aufloesen"))
assert net_fetch.check_url("https://api.open-meteo.com/x", ("api.open-meteo.com",))

# 6) Kodierung: UTF-8 zuerst, cp1252 nur wenn angefordert
net_fetch._download = lambda *a: "Grüße".encode("cp1252")
try:
    net_fetch.fetch_text("https://api.open-meteo.com/x", ("api.open-meteo.com",))
    raise AssertionError
except NetError as error:
    assert "nicht lesbar" in str(error)
assert net_fetch.fetch_text("https://api.open-meteo.com/x", ("api.open-meteo.com",), fallback_encoding="cp1252") == "Grüße"
net_fetch._download = lambda *a: b"\xff\xfe\x00"
try:
    net_fetch.fetch_text("https://api.open-meteo.com/x", ("api.open-meteo.com",), fallback_encoding="utf-16-gibtsnicht")
    raise AssertionError
except NetError:
    pass

print("ALL TESTS PASSED")
