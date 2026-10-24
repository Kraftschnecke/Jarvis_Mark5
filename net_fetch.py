"""Gemeinsamer Helfer fuer Dienste im Internet (Mark 5, Step 1.2).

JEDE Anfrage von Jarvis ins Netz (Wetter, News, Eishockey, Websuche, spaeter mehr) laeuft hier durch.
Dadurch gelten ueberall dieselben Regeln, und sie stehen an genau einer Stelle:

- nur https, nur Port 443, keine Adressen mit Benutzername/Passwort
- nur Hosts aus einer Liste, die der Aufrufer angibt (``hosts=("api.open-meteo.com",)``).
  Nur wer wirklich beliebige Webseiten lesen muss, nimmt ``ANY_PUBLIC_HOST``; dann werden
  Adressen im eigenen Rechner oder Heimnetz abgelehnt (localhost, 192.168.x.x, ...).
- Weiterleitungen werden mit denselben Regeln geprueft
- Zeitlimit und Groessenlimit (die Antwort wird nie ganz geladen, wenn sie zu gross ist)
- alle Fehler kommen als ``NetError`` mit einem verstaendlichen deutschen Satz

WICHTIG: Was dieser Helfer liefert, ist Text von fremden Servern, also **unvertraute Daten**.
Geht er an das Sprachmodell, muss er vorher durch ``untrusted.clean_text`` / ``wrap_untrusted``.
Es ist nie eine Anweisung (siehe ``untrusted.py``).

DNS rebinding (Schritt 2.6): Bei ``ANY_PUBLIC_HOST`` wird der Name nicht nur vorab geprueft
(``check_url``), sondern die Verbindung selbst benutzt genau die Adresse, die beim Verbinden
aufgeloest und als oeffentlich geprueft wurde (``_PinnedHTTPSConnection``). Es gibt also keine
Luecke zwischen Pruefung und Abruf; das gilt auch fuer jede Weiterleitung. Dabei wird kein
System-Proxy benutzt (direkte Verbindung). Fuer Dienste mit fester Host-Liste ist das nicht noetig.
"""

import http.client
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 8              # Sekunden
DEFAULT_MAX_BYTES = 2_000_000    # 2 MB
USER_AGENT = "Jarvis"

ANY_PUBLIC_HOST = object()       # Marker: jeder oeffentliche Host (siehe Moduldoku)

_resolve = socket.getaddrinfo    # austauschbar fuer Tests


class NetError(Exception):
    """Der Abruf ist fehlgeschlagen. Der Text ist fuer den Nutzer gedacht."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _require_public(host):
    """Der Name darf nur auf oeffentliche Internet-Adressen zeigen."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise NetError("Adressen aus Zahlen sind nicht erlaubt.")
    _public_addresses(host, 443)


def check_url(url, hosts):
    """Gibt die Adresse zurueck, wenn sie erlaubt ist, sonst NetError."""
    if hosts is not ANY_PUBLIC_HOST:
        if not isinstance(hosts, (tuple, list, set, frozenset)) or not hosts:
            raise NetError("Interner Fehler: keine erlaubten Hosts angegeben.")
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise NetError("Ungueltige Adresse.") from error
    if parts.scheme != "https":
        raise NetError("Nur https-Adressen sind erlaubt.")
    host = parts.hostname
    if not host or parts.username or parts.password:
        raise NetError("Ungueltige Adresse.")
    if port not in (None, 443):
        raise NetError("Unerlaubte Adresse.")
    if hosts is ANY_PUBLIC_HOST:
        _require_public(host)
    elif host not in {entry.lower() for entry in hosts}:
        raise NetError("Unerlaubte Adresse.")
    return url


class SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur dorthin, wo auch der erste Abruf hin duerfte."""

    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            check_url(newurl, self.hosts)
        except NetError as error:
            raise NetError("Weiterleitung auf eine unerlaubte Adresse.") from error
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _public_addresses(host, port):
    """Aufgeloeste Adressen des Namens; NetError, wenn auch nur eine nicht oeffentlich ist."""
    try:
        infos = _resolve(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise NetError("Die Adresse wurde nicht gefunden.") from error
    addresses = [str(info[4][0]).split("%")[0] for info in infos]
    if not addresses:
        raise NetError("Die Adresse wurde nicht gefunden.")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise NetError("Unerlaubte Adresse.")
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Verbindet sich mit der gerade geprueften Adresse (kein zweites Aufloesen des Namens)."""

    def connect(self):
        address = _public_addresses(self.host, self.port or 443)[0]
        sock = socket.create_connection((address, self.port or 443), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)   # Zertifikat gilt dem Namen


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PinnedHTTPSConnection, req, context=self._context)


def _download(request, hosts, timeout, max_bytes):
    """Der eigentliche Abruf. Wirft rohe Fehler; ``fetch_text`` uebersetzt sie."""
    if hosts is ANY_PUBLIC_HOST:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _PinnedHTTPSHandler(), SafeRedirects(hosts))
    else:
        opener = urllib.request.build_opener(SafeRedirects(hosts))
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise NetError("Die Antwort ist zu gross.")
    return raw


def fetch_text(url, hosts, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT,
               max_bytes=DEFAULT_MAX_BYTES, fallback_encoding=None):
    """Holt Text per GET. ``hosts``: Tupel erlaubter Hostnamen oder ``ANY_PUBLIC_HOST``.

    Text wird als UTF-8 gelesen; mit ``fallback_encoding`` (z.B. "cp1252") wird bei Fehlern
    diese Kodierung versucht (aeltere Webseiten)."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    check_url(url, hosts)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        raw = _download(request, hosts, timeout, max_bytes)
    except NetError:
        raise
    except urllib.error.HTTPError as error:
        raise NetError(f"Der Dienst antwortet mit Fehler {error.code}.", status=error.code) from error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, TimeoutError):
            raise NetError("Der Dienst hat nicht rechtzeitig geantwortet.") from error
        if isinstance(reason, ssl.SSLError):
            raise NetError("Die sichere Verbindung zum Dienst ist fehlgeschlagen.") from error
        raise NetError("Keine Verbindung zum Dienst.") from error
    except TimeoutError as error:
        raise NetError("Der Dienst hat nicht rechtzeitig geantwortet.") from error
    except OSError as error:
        raise NetError("Keine Verbindung zum Dienst.") from error
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        if fallback_encoding:
            try:
                return raw.decode(fallback_encoding)
            except (UnicodeDecodeError, LookupError):
                pass
        raise NetError("Die Antwort ist nicht lesbar.") from error


def fetch_json(url, hosts, **kwargs):
    """Wie ``fetch_text``, aber die Antwort wird als JSON gelesen."""
    text = fetch_text(url, hosts, **kwargs)
    try:
        return json.loads(text)
    except ValueError as error:
        raise NetError("Die Antwort ist kein gueltiges JSON.") from error
