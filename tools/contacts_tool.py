"""Apple-Kontakte (iCloud) per CardDAV lesen (Mark 5, Step 2.22). NUR LESEN.

Was dieses Werkzeug tut: Kontakte holen und daraus
  - find_contact: Geburtstag, Telefonnummer oder E-Mail-Adresse eines Kontakts nennen,
  - upcoming_birthdays: die naechsten Geburtstage auflisten.
Was es NICHT tut: Kontakte anlegen, aendern oder loeschen. Es gibt im Modul keine Schreib-Methode (nur PROPFIND und REPORT).

Zugang: dieselbe Apple-ID und dasselbe **app-spezifische Passwort** wie beim Kalender (CALDAV_USER, CALDAV_PASSWORD
in der .env). Alles Netz laeuft ueber net_fetch (nur https, feste Hosts: contacts.icloud.com und die von Apple genannten
pNN-contacts.icloud.com). Ein Verweis auf einen anderen Host wird abgelehnt, damit die Zugangsdaten nie an fremde Server gehen.
Namen, Nummern und Adressen sind Daten von Dritten: gesaeubert, gekuerzt und nur als Daten an das Sprachmodell gegeben.
Vom Kontakt wird nur geholt, was gebraucht wird (Name, Firma, Geburtstag, Telefon, E-Mail), und nur das Gefragte geht weiter.
"""

import base64
import re
import threading
import time
import urllib.parse
from datetime import date

import config
import net_fetch
from net_fetch import NetError
from tools.caldav_tool import CalDavError, _absolute, _safe_xml
from tools.tool_result import ToolResult
from untrusted import clean_text

DAV = "{DAV:}"
CARD = "{urn:ietf:params:xml:ns:carddav}"
ROOT_URL = "https://contacts.icloud.com/"
HOST_PATTERN = re.compile(r"^(contacts|p\d{1,3}-contacts)\.icloud\.com$")
TIMEOUT = 20
MAX_BYTES = 8_000_000
MAX_CARDS = 5000
MAX_FIELD = 80
MAX_MATCHES = 5
MAX_BIRTHDAYS = 20
DEFAULT_DAYS = 30
MAX_DAYS = 365
CACHE_SECONDS = 600
ERROR_SECONDS = 60

_PROPS = ("FN", "N", "NICKNAME", "ORG", "BDAY", "TEL", "EMAIL")
_TOPICS = {"birthday": "birthday", "geburtstag": "birthday", "phone": "phone", "telefon": "phone", "tel": "phone",
           "email": "email", "mail": "email", "e-mail": "email"}


def _check_host(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or not parts.hostname
            or not HOST_PATTERN.match(parts.hostname.lower()) or parts.port not in (None, 443)):
        raise CalDavError("Apple hat eine unerwartete Serveradresse genannt; aus Sicherheitsgründen höre ich hier auf.")
    return url


class CardDav:
    """Schmaler, lesender Client. ``fetch`` ist austauschbar (Tests)."""

    def __init__(self, user, password, fetch=net_fetch.fetch_text, root=ROOT_URL):
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self._auth = {"Authorization": "Basic " + token}
        self._fetch = fetch
        self._root = root
        self.home = None

    def _request(self, method, url, body, depth="0"):
        if method not in ("PROPFIND", "REPORT"):                   # lesen und sonst nichts
            raise CalDavError("Interner Fehler: unerlaubte Methode.")
        _check_host(url)
        host = urllib.parse.urlsplit(url).hostname.lower()
        headers = {**self._auth, "Depth": depth, "Content-Type": "application/xml; charset=utf-8"}
        try:
            return self._fetch(url, tuple({host}), method=method, data=body, timeout=TIMEOUT, max_bytes=MAX_BYTES, headers=headers)
        except NetError as error:
            if error.status in (401, 403):
                raise CalDavError("Apple hat die Anmeldung abgelehnt. Nimm ein app-spezifisches Passwort (appleid.apple.com → Anmeldung und Sicherheit) und prüfe die Apple-ID.") from error
            raise CalDavError(f"Der Kontakte-Server von Apple ist nicht erreichbar ({error}).") from error

    @staticmethod
    def _first_href(root, path):
        node = root.find(path)
        if node is None:
            return None
        href = node.find(f"{DAV}href")
        return href.text.strip() if href is not None and href.text else None

    def discover(self):
        body = '<?xml version="1.0"?><propfind xmlns="DAV:"><prop><current-user-principal/></prop></propfind>'
        root = _safe_xml(self._request("PROPFIND", self._root, body))
        principal = self._first_href(root, f".//{DAV}current-user-principal")
        if not principal:
            raise CalDavError("Apple hat kein Konto zu diesen Zugangsdaten genannt.")
        principal_url = _check_host(_absolute(self._root, principal))
        body = ('<?xml version="1.0"?><propfind xmlns="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><prop>'
                '<c:addressbook-home-set/></prop></propfind>')
        root = _safe_xml(self._request("PROPFIND", principal_url, body))
        home = self._first_href(root, f".//{CARD}addressbook-home-set")
        if not home:
            raise CalDavError("Apple hat keinen Kontaktebereich für dieses Konto genannt.")
        self.home = _check_host(_absolute(principal_url, home))
        return self.home

    def books(self):
        """Adressbuecher: [{"name", "url"}]."""
        home = self.home or self.discover()
        body = '<?xml version="1.0"?><propfind xmlns="DAV:"><prop><displayname/><resourcetype/></prop></propfind>'
        root = _safe_xml(self._request("PROPFIND", home, body, depth="1"))
        found = []
        for response in root.findall(f"{DAV}response"):
            if response.find(f".//{DAV}resourcetype/{CARD}addressbook") is None:
                continue
            href = response.find(f"{DAV}href")
            if href is None or not href.text:
                continue
            name = response.find(f".//{DAV}displayname")
            found.append({"name": clean_text((name.text or "") if name is not None else "", 60) or "Kontakte",
                          "url": _check_host(_absolute(home, href.text))})
        return found

    def raw_cards(self, book_url, full=False):
        """vCard-Texte eines Adressbuchs. Standard: nur die noetigen Felder; ``full`` fordert alles an (nur zur Fehlersuche)."""
        props = "" if full else "".join(f'<c:prop name="{name}"/>' for name in _PROPS)
        body = ('<?xml version="1.0"?><c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                f'<d:prop><c:address-data>{props}</c:address-data></d:prop>'
                '<c:filter><c:prop-filter name="FN"/></c:filter></c:addressbook-query>')
        root = _safe_xml(self._request("REPORT", _check_host(book_url), body, depth="1"))
        return [node.text for node in root.iter(f"{CARD}address-data") if node.text]

    def cards(self, book_url, full=False):
        """Alle Kontakte eines Adressbuchs als Liste von Dicts (siehe parse_vcards)."""
        cards = []
        for text in self.raw_cards(book_url, full):
            cards += parse_vcards(text)
            if len(cards) >= MAX_CARDS:
                break
        return cards[:MAX_CARDS]


# ---- vCard lesen

def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def _unescape(value):
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _components(raw):
    """Teile an unmaskierten Semikola trennen (erst danach entmaskieren): Firma\\;GmbH;Abteilung -> ['Firma;GmbH', 'Abteilung']."""
    return [_unescape(part).strip() for part in re.split(r"(?<!\\);", raw)]


def parse_birthday(params, value):
    """(Jahr oder None, Monat, Tag) oder None. Versteht 1990-03-15, 19900315, --03-15, --0315; Apples Platzhalterjahr 1604 = ohne Jahr."""
    value = value.strip().split("T")[0]
    match = re.fullmatch(r"(?:(\d{4})-?(\d{2})-?(\d{2})|--(\d{2})-?(\d{2}))", value)
    if not match:
        return None
    if match.group(1):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if "X-APPLE-OMIT-YEAR" in params.upper() or year < 1800:
            year = None
    else:
        year, month, day = None, int(match.group(4)), int(match.group(5))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        date(2000, month, day)                                   # 2000 ist ein Schaltjahr: 29.2. ist erlaubt
    except ValueError:
        return None
    return (year, month, day)


def parse_vcards(text):
    """Liest vCards. Gibt [{"name", "org", "nickname", "birthday", "phones", "emails"}] zurueck (Fremddaten: gesaeubert)."""
    cards, current = [], None
    for line in _unfold(text).split("\n"):
        upper = line.strip().upper()
        if upper == "BEGIN:VCARD":
            current = {"fn": "", "n": [], "org": "", "nickname": "", "birthday": None, "phones": [], "emails": []}
            continue
        if upper == "END:VCARD":
            if current is not None:
                cards.append(_finish(current))
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, _, params = head.partition(";")
        name = name.split(".")[-1].upper()                        # "item1.TEL" -> "TEL"
        raw, value = value, _unescape(value)
        if name == "FN":
            current["fn"] = value
        elif name == "N":
            current["n"] = _components(raw)                      # Nachname, Vorname, ...
        elif name == "NICKNAME":
            current["nickname"] = value
        elif name == "ORG":
            current["org"] = " ".join(p for p in _components(raw) if p)
        elif name == "BDAY":
            current["birthday"] = parse_birthday(params, value)
        elif name == "TEL" and value.strip() and len(current["phones"]) < 5:
            current["phones"].append(clean_text(value.strip(), 40))
        elif name == "EMAIL" and value.strip() and len(current["emails"]) < 5:
            current["emails"].append(clean_text(value.strip(), 100))
    return cards


def _finish(card):
    name = card["fn"].strip()
    if not name and card["n"]:
        parts = card["n"] + ["", ""]
        name = f"{parts[1]} {parts[0]}".strip()
    name = name or card["org"].strip()
    return {"name": clean_text(" ".join(name.split()), MAX_FIELD), "org": clean_text(card["org"], MAX_FIELD),
            "nickname": clean_text(card["nickname"], MAX_FIELD), "birthday": card["birthday"],
            "phones": card["phones"], "emails": card["emails"]}


# ---- Abfragen

def _clamp_days(value):
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(MAX_DAYS, days))


def _next_birthday(month, day, today):
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:                                         # 29.2. in einem Nicht-Schaltjahr: 28.2.
            candidate = date(year, 2, 28)
        if candidate >= today:
            return candidate
    return None


def _format_birthday(birthday):
    year, month, day = birthday
    return f"{day:02d}.{month:02d}.{year}" if year else f"{day:02d}.{month:02d}."


class ContactBook:
    """Kontakte aus Apple, kurz zwischengespeichert. ``client`` und ``clock`` sind austauschbar (Tests)."""

    def __init__(self, account, client=None, clock=time.monotonic):
        self.account = account
        self._client = client
        self._clock = clock
        self._cards = []
        self._fresh_until = 0.0
        self._error = None                                       # letzter Fehler, gilt waehrend der Fehlerpause
        self._lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            self._client = CardDav(self.account["user"], self.account["password"])
        return self._client

    def cards(self):
        with self._lock:
            if self._clock() < self._fresh_until:
                if self._error is not None:
                    raise self._error                            # Pause nach einem Fehler: dieselbe Meldung, nicht still "nichts gefunden"
                return list(self._cards)
            client = self._get_client()
            try:
                cards = []
                for book in client.books():
                    cards += client.cards(book["url"])
            except CalDavError as error:
                self._error, self._fresh_until = error, self._clock() + ERROR_SECONDS      # nicht bei jeder Frage neu haemmern
                raise
            self._error = None
            self._cards, self._fresh_until = cards[:MAX_CARDS], self._clock() + CACHE_SECONDS
            return list(self._cards)

    def find(self, name):
        words = [w for w in re.split(r"\s+", str(name or "").casefold().strip()) if w]
        if not words:
            return []
        hits = []
        for card in self.cards():
            haystack = f"{card['name']} {card['nickname']}".casefold()
            if all(w in haystack for w in words):
                hits.append(card)
        hits.sort(key=lambda c: (c["name"].casefold() != " ".join(words), c["name"].casefold()))
        return hits

    def birthdays(self, days, today=None):
        today = today or date.today()
        found = []
        for card in self.cards():
            if not card["birthday"]:
                continue
            year, month, day = card["birthday"]
            when = _next_birthday(month, day, today)
            if when is None or (when - today).days > days:
                continue
            item = {"name": card["name"], "date": when.isoformat(), "in_days": (when - today).days}
            if year:
                item["turns"] = when.year - year
            found.append(item)
        found.sort(key=lambda i: (i["in_days"], i["name"].casefold()))
        return found


_default_book = None
_book_lock = threading.Lock()


def default_book():
    """Das Kontaktbuch aus der .env, oder None wenn Apple nicht eingerichtet ist."""
    global _default_book
    with _book_lock:
        if _default_book is None:
            account = config.caldav_account()
            if account:
                _default_book = ContactBook(account)
        return _default_book


def set_default_book(book):
    """Nur fuer Tests."""
    global _default_book
    _default_book = book


NOT_SET_UP = ("Die Kontakte sind nicht eingerichtet. Trag CALDAV_USER und CALDAV_PASSWORD (app-spezifisches Passwort) "
              "in die .env ein; siehe .env.example.")


def _topic(value):
    return _TOPICS.get(str(value or "").strip().casefold(), "")


def find_contact(name="", topic="", book=None):
    """Geburtstag, Telefon oder E-Mail eines Kontakts. Ohne Thema: alles Vorhandene. Nur lesen."""
    book = book or default_book()
    if book is None:
        return ToolResult(success=False, error=NOT_SET_UP)
    if not isinstance(name, str) or not name.strip():
        return ToolResult(success=False, error="Zu welchem Kontakt? Nenne einen Namen.")
    wanted = _topic(topic)
    try:
        hits = book.find(name)
    except CalDavError as error:
        return ToolResult(success=False, error=str(error))
    except Exception as error:
        return ToolResult(success=False, error=f"Die Kontakte ließen sich nicht lesen ({type(error).__name__}).")
    if not hits:
        return ToolResult(success=True, data={"query": clean_text(name.strip(), 60), "contacts": [],
                                              "info": "Keinen passenden Kontakt gefunden."})
    contacts = []
    for card in hits[:MAX_MATCHES]:
        item = {"name": card["name"]}
        if card["org"] and card["org"] != card["name"]:
            item["org"] = card["org"]
        if wanted in ("", "birthday"):
            item["birthday"] = _format_birthday(card["birthday"]) if card["birthday"] else None
        if wanted in ("", "phone"):
            item["phones"] = card["phones"]
        if wanted in ("", "email"):
            item["emails"] = card["emails"]
        contacts.append(item)
    data = {"query": clean_text(name.strip(), 60), "contacts": contacts}
    if len(hits) > MAX_MATCHES:
        data["more"] = len(hits) - MAX_MATCHES
    return ToolResult(success=True, data=data)


def upcoming_birthdays(days=DEFAULT_DAYS, book=None, today=None):
    """Die naechsten Geburtstage (heute eingeschlossen), hoechstens 20. Nur lesen."""
    book = book or default_book()
    if book is None:
        return ToolResult(success=False, error=NOT_SET_UP)
    limit = _clamp_days(days)
    try:
        found = book.birthdays(limit, today)
    except CalDavError as error:
        return ToolResult(success=False, error=str(error))
    except Exception as error:
        return ToolResult(success=False, error=f"Die Kontakte ließen sich nicht lesen ({type(error).__name__}).")
    data = {"days": limit, "birthdays": found[:MAX_BIRTHDAYS]}
    if len(found) > MAX_BIRTHDAYS:
        data["more"] = len(found) - MAX_BIRTHDAYS
    if not found:
        data["info"] = f"In den nächsten {limit} Tagen hat niemand Geburtstag (oder es ist kein Geburtstag eingetragen)."
    return ToolResult(success=True, data=data)


def describe_find(name="", topic=""):
    what = {"birthday": "den Geburtstag", "phone": "die Telefonnummer", "email": "die E-Mail-Adresse"}.get(_topic(topic), "die Angaben")
    who = clean_text(str(name or "").strip(), 60) or "einen Kontakt"
    return [f"Kontakt: {who}", f"Gesucht wird {what}. Nur dieser Eintrag geht zum Antworten an OpenAI; nichts wird verändert."]


def describe_birthdays(days=DEFAULT_DAYS):
    return [f"Geburtstage der nächsten {_clamp_days(days)} Tage",
            "Namen und Datum gehen zum Antworten an OpenAI; nichts wird verändert."]
