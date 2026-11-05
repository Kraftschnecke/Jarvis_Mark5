"""Eine Webseite im Browser oeffnen oder im Browser suchen (Mark 5, Step 2.26).

Was dieses Werkzeug tut: eine Adresse in einem neuen Tab deines Standardbrowsers oeffnen, oder eine Suche bei Google dort
oeffnen. Es holt selbst nichts aus dem Netz und liest keine Seite (dafuer gibt es READ_PAGE).

Sicherheit: erlaubt ist NUR https (eine http-Adresse wird zu https hochgestuft). Alles andere (file:, javascript:, data:,
ms-settings:, steam:, ftp: ... jedes andere Schema) wird abgelehnt, ebenso Adressen mit Benutzername/Passwort, fremden Ports,
Zahlen-Adressen (IP), Rechnernamen ohne Punkt, "localhost" und Heimnetz-Endungen (.local, .lan ...), Hostnamen mit
Sonderzeichen und alles mit Leerzeichen oder Steuerzeichen. Die Rueckfrage zeigt Host und volle Adresse. Geoeffnet wird
erst nach deinem "Ja" (risk.py: confirm), und die Ausfuehrung steht im Aktionsprotokoll.
"""

import re
import urllib.parse
import webbrowser

from tools.tool_result import ToolResult
from untrusted import clean_text

SEARCH_URL = "https://www.google.com/search?q="
MAX_URL = 2000
MAX_QUERY = 200
BLOCKED_ENDINGS = frozenset({"local", "localhost", "internal", "lan", "intranet", "corp", "home", "localdomain", "invalid", "test", "example"})
_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")
_TLD = re.compile(r"[a-z]{2,24}|xn--[a-z0-9-]{2,59}")
_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _ascii_quote(text):
    """Nicht-ASCII-Zeichen prozentcodieren (ein ASCII-Text bleibt unveraendert)."""
    return "".join(c if ord(c) < 128 else urllib.parse.quote(c) for c in text)


def normalize_url(raw):
    """Gibt (Adresse, None) oder (None, Fehlersatz) zurueck. Nur https; http wird zu https."""
    text = _text(raw)
    if not text:
        return None, "Welche Seite soll ich öffnen? Nenne eine Adresse."
    if len(text) > MAX_URL or re.search(r"[\x00-\x20\x7f]", text):
        return None, "Diese Adresse ist ungültig (zu lang oder mit Leerzeichen oder Steuerzeichen)."

    match = _SCHEME.match(text)
    if match and not re.match(r"^[a-zA-Z0-9.-]+:\d+(/|$)", text):
        scheme = match.group(1).lower()
        if scheme not in ("http", "https") or not text[len(match.group(0)):].startswith("//"):
            return None, "Ich öffne nur https-Adressen im Browser, keine anderen Arten von Adressen."
        text = "https://" + text[len(match.group(0)) + 2:]
    elif text.startswith("//"):
        text = "https:" + text
    else:
        text = "https://" + text

    try:
        parts = urllib.parse.urlsplit(text)
        port = parts.port
    except ValueError:
        return None, "Diese Adresse ist ungültig."

    host = (parts.hostname or "").lower()
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return None, "Adressen mit Benutzername oder Passwort öffne ich nicht."
    if port not in (None, 443):
        return None, "Ich öffne nur Adressen auf dem normalen https-Port."
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")          # Umlaut-Adressen: die Rueckfrage zeigt dann die xn--Schreibweise
        except UnicodeError:
            return None, "Diese Adresse ist ungültig."
    labels = host.split(".")
    if (len(labels) < 2 or len(host) > 253 or not all(_LABEL.fullmatch(label) for label in labels)
            or not _TLD.fullmatch(labels[-1]) or labels[-1] in BLOCKED_ENDINGS or host.endswith(".home.arpa")):
        return None, "Das sieht nicht nach einer normalen Internetadresse aus (Rechnername, Zahlenadresse oder Heimnetz öffne ich nicht)."

    return urllib.parse.urlunsplit(("https", host, _ascii_quote(parts.path), _ascii_quote(parts.query), _ascii_quote(parts.fragment))), None


def build_search(query):
    """Gibt (Suchadresse, None) oder (None, Fehlersatz) zurueck."""
    text = " ".join(clean_text(_text(query), MAX_QUERY + 1).split())
    if not text:
        return None, "Wonach soll ich im Browser suchen?"
    if len(text) > MAX_QUERY:
        return None, "Die Suche ist zu lang."
    return SEARCH_URL + urllib.parse.quote_plus(text), None


def resolve(url="", query=""):
    """(Adresse, Art, None) oder (None, None, Fehlersatz). Eine Adresse hat Vorrang vor einer Suche."""
    if _text(url):
        target, error = normalize_url(url)
        return (target, "website", None) if target else (None, None, error)
    if _text(query):
        target, error = build_search(query)
        return (target, "search", None) if target else (None, None, error)
    return None, None, "Welche Seite soll ich öffnen, oder wonach soll ich im Browser suchen?"


def check(url="", query=""):
    """Fehlersatz oder None. Wird VOR der Rueckfrage geprueft, damit nichts Ungueltiges zur Bestaetigung kommt."""
    return resolve(url, query)[2]


def _open(target):
    """Oeffnet die Adresse in einem neuen Tab des Standardbrowsers. Wird in Tests ersetzt."""
    return webbrowser.open(target, new=2)


def open_website(url="", query=""):
    target, kind, error = resolve(url, query)
    if error:
        return ToolResult(success=False, error=error)

    try:
        opened = _open(target)
    except Exception:
        opened = False
    if not opened:
        return ToolResult(success=False, error="Der Browser ließ sich nicht öffnen.")

    host = urllib.parse.urlsplit(target).hostname
    if kind == "search":
        return ToolResult(success=True, data={"kind": "search", "host": host, "done": "Suche im Browser geöffnet"})
    return ToolResult(success=True, data={"kind": "website", "host": host, "url": target, "done": "Seite im Browser geöffnet"})


def describe(url="", query=""):
    """Zeilen fuer die Rueckfrage: genau das, was geoeffnet wird."""
    target, kind, error = resolve(url, query)
    if error:
        return ["Im Browser öffnen"]
    host = urllib.parse.urlsplit(target).hostname
    if kind == "search":
        return [f"Im Browser suchen nach: {clean_text(_text(query), MAX_QUERY)}", f"Suchmaschine: {host}"]
    shown = target if len(target) <= 200 else target[:197] + "..."
    return [f"Seite: {host}", f"Adresse: {shown}", "Sie öffnet sich in einem neuen Tab deines Browsers."]
