"""Webseite lesen (Mark 5, Step 2.6): Text eines Artikels holen, damit Jarvis ihn zusammenfassen kann.

Wohin Jarvis ueberhaupt gehen darf (das ist der Kern der Sicherheit, siehe risk.py):
- Artikel aus der zuletzt genannten News-Liste ("fass den dritten Artikel zusammen"): direkt.
- jede andere Adresse (du tippst einen Link): erst Rueckfrage mit der Adresse, dann Abruf.
Das Sprachmodell kann sich also keine Adresse ausdenken und im Hintergrund aufrufen; eine
eingeschleuste Adresse (in einer Schlagzeile, auf einer Seite) wird nie ohne dein "Ja" geoeffnet.

Der Abruf laeuft ueber ``net_fetch`` mit ``ANY_PUBLIC_HOST``: nur https, nur oeffentliche Adressen
(nichts im eigenen Rechner oder Heimnetz), die Verbindung nutzt die geprueften Adressen (kein
DNS-Rebinding), Zeit- und Groessenlimit. Der Seitentext ist unvertraute Eingabe (untrusted.py):
Skripte, Menues und Werbung werden entfernt, der Rest wird gesaeubert und gekuerzt.
"""

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from net_fetch import ANY_PUBLIC_HOST, NetError, fetch_text
from tools import news_tool
from tools.tool_result import ToolResult
from untrusted import clean_text

# Viele Zeitungen sperren Programme ohne "Mozilla/..." in der Kennung (Fehler 403)
PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Jarvis/5.0; personal assistant)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de,en;q=0.8",
}
BLOCKED_STATUS = (401, 403, 429)
MIN_ARTICLE_CHARS = 300      # kuerzer: sieht nach Menuetext oder JavaScript-Seite aus, Rueckfall versuchen
MAX_JSON_CHARS = 300_000

PAGE_TIMEOUT = 8
PAGE_MAX_BYTES = 2_000_000
MAX_TEXT = 8000          # Zeichen Artikeltext fuer das Sprachmodell
MAX_TITLE = 200
MAX_URL = 700

# Diese Seiten liefern ohne Browser keinen Artikel (Weiterleitung bzw. Aufbau erst per JavaScript)
UNREADABLE_HOSTS = {
    "news.google.com": "Diesen Link (Google News) kann ich nicht selbst lesen, er leitet nur per Browser weiter. "
                       "Öffne ihn selbst, oder suche mit der Bing-News-Quelle, die direkte Links liefert.",
    "msn.com": "MSN baut seine Artikel erst im Browser auf, deshalb kann ich sie nicht lesen. "
               "Öffne den Link selbst, oder frage nach derselben Meldung bei einer anderen Quelle.",
}

_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "nav", "header", "footer",
         "aside", "form", "button", "select", "dialog", "head"}
_BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
          "blockquote", "figcaption", "ul", "ol", "table", "main"}
_VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed", "param", "track"}


class _TextExtractor(HTMLParser):
    """Sammelt sichtbaren Text; was in _SKIP steht (samt allem darin) wird uebergangen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.chunks = []
        self._skipped = []          # gerade geoeffnete, uebersprungene Tags
        self._in_title = False
        self._in_article = 0
        self.article_chunks = []
        self.meta = {}              # description, og:description
        self._json_buffer = None    # Inhalt eines <script type="application/ld+json">
        self.json_blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            values = dict(attrs)
            name = (values.get("property") or values.get("name") or "").lower()
            if name in ("description", "og:description") and values.get("content"):
                self.meta.setdefault(name, values["content"])
        if tag == "script" and "ld+json" in (dict(attrs).get("type") or "").lower():
            self._json_buffer = []
        if tag in _VOID:
            if tag == "br":
                self._add("\n")
            return
        if tag in _SKIP:
            # Kopf-/Fusszeile INNERHALB eines Artikels enthaelt oft die Ueberschrift: behalten
            if not (tag in ("header", "footer") and self._in_article):
                self._skipped.append(tag)
            return
        if tag == "article":
            self._in_article += 1
        if tag in _BLOCK:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._json_buffer is not None:
            self.json_blocks.append("".join(self._json_buffer)[:MAX_JSON_CHARS])
            self._json_buffer = None
        if tag in _SKIP:
            if self._skipped and self._skipped[-1] == tag:
                self._skipped.pop()
            return
        if tag == "article":
            self._in_article = max(0, self._in_article - 1)
        if tag in _BLOCK:
            self._add("\n")

    def handle_data(self, data):
        if self._json_buffer is not None:
            self._json_buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skipped:
            self._add(data)

    def _add(self, text):
        self.chunks.append(text)
        if self._in_article:
            self.article_chunks.append(text)


def _tidy(chunks):
    """Zeilen aufraeumen: Leerraum verdichten, leere Zeilen und sehr kurze Menue-Zeilen weglassen."""
    lines = []
    for line in "".join(chunks).split("\n"):
        line = " ".join(line.split())
        if len(line) >= 25:                      # Menuepunkte, Datumszeilen, "Teilen" usw. fallen weg
            lines.append(line)
    return lines


def _find_article_body(node, depth=0):
    """Sucht in eingebetteten Strukturdaten (JSON-LD) nach einem articleBody."""
    if depth > 8:
        return ""
    if isinstance(node, dict):
        body = node.get("articleBody")
        if isinstance(body, str) and body.strip():
            return body
        for value in node.values():
            found = _find_article_body(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for value in node[:50]:
            found = _find_article_body(value, depth + 1)
            if found:
                return found
    return ""


def _structured_text(blocks):
    for block in blocks:
        try:
            body = _find_article_body(json.loads(block))
        except (ValueError, RecursionError):
            continue
        if body:
            return html.unescape(_HTML_TAGS.sub(" ", body))
    return ""


_HTML_TAGS = re.compile(r"<[^>]{0,300}>")


def extract_text(page):
    """(Titel, Text, gekuerzt?, Art) aus HTML. Wirft NetError, wenn nichts Lesbares da ist.

    Art: "article" (Artikeltext der Seite), "structured" (articleBody aus eingebetteten Daten,
    fuer Seiten, die den Text erst per JavaScript aufbauen) oder "description" (nur die
    Kurzbeschreibung der Seite)."""
    parser = _TextExtractor()
    try:
        parser.feed(page)
        parser.close()
    except Exception as error:                   # HTMLParser kann bei kaputtem HTML selten stolpern
        raise NetError("Die Seite ist nicht lesbar.") from error

    # Gibt es ein <article>, ist das der Artikel; sonst der ganze sichtbare Text
    main = "\n".join(_tidy(parser.article_chunks) or _tidy(parser.chunks))
    structured = "\n".join(_tidy([_structured_text(parser.json_blocks)]))
    description = " ".join((parser.meta.get("og:description") or parser.meta.get("description") or "").split())

    if len(main) >= MIN_ARTICLE_CHARS:
        text, kind = main, "article"
    elif len(structured) >= 100:
        text, kind = structured, "structured"
    elif main:
        text, kind = main, "article"
    elif len(description) >= 40:
        text, kind = html.unescape(description), "description"
    else:
        raise NetError("Auf der Seite habe ich keinen lesbaren Text gefunden.")

    truncated = len(text) > MAX_TEXT
    text = clean_text(text, MAX_TEXT) if truncated else clean_text(text, MAX_TEXT + 1)
    title = clean_text(" ".join(html.unescape(parser.title).split()), MAX_TITLE).strip()
    return title, text, truncated, kind


class PageService:
    def __init__(self, fetch=fetch_text, news=None):
        self.fetch = fetch
        self.news = news                         # liefert listed_item/is_listed; Standard: News-Dienst

    def _news(self):
        return self.news or news_tool.default_service()

    def resolve(self, url="", item=""):
        """Welche Adresse ist gemeint? (url, Fehlertext, Eintrag der News-Liste oder None).
        Eine Nummer gilt nur fuer die letzte News-Liste."""
        number = str(item).strip() if isinstance(item, (str, int)) and not isinstance(item, bool) else ""
        if number:
            entry = self._news().listed_item(number)
            if entry is None:
                return None, "Diese Nummer gibt es in der letzten Nachrichten-Liste nicht (oder sie hat keinen Link).", None
            return entry["url"], None, entry
        if isinstance(url, str) and url.strip():
            return url.strip(), None, None
        return None, "Welche Seite soll ich lesen? Nenne mir die Nummer eines Artikels aus der Liste oder einen Link.", None

    @staticmethod
    def _fallback(entry):
        """Wenn die Seite nicht lesbar ist: wenigstens die Kurzmeldung aus der Liste (schon gesaeubert)."""
        if not entry:
            return ""
        short = f" Aus der Liste weiss ich nur: {entry['title']}"
        if entry.get("summary"):
            short += f" – {entry['summary']}"
        return short

    def read_page(self, url="", item=""):
        """Seitentext als ToolResult (Daten: url, host, title, text, truncated, kind)."""
        target, problem, entry = self.resolve(url, item)
        if problem:
            return ToolResult(success=False, error=problem)
        if len(target) > MAX_URL:
            return ToolResult(success=False, error="Die Adresse ist zu lang.")
        host = (urlparse(target).hostname or "").lower()
        unreadable = next((m for h, m in UNREADABLE_HOSTS.items() if host == h or host.endswith("." + h)), None)
        if unreadable:
            return ToolResult(success=False, error=unreadable + self._fallback(entry))
        try:
            page = self.fetch(target, ANY_PUBLIC_HOST, timeout=PAGE_TIMEOUT, max_bytes=PAGE_MAX_BYTES,
                              headers=PAGE_HEADERS, fallback_encoding="cp1252")
            title, text, truncated, kind = extract_text(page)
        except NetError as error:
            hint = " Viele Seiten sperren automatische Abrufe; öffne den Link selbst im Browser." \
                if error.status in BLOCKED_STATUS else ""
            return ToolResult(success=False, error=f"Die Seite ist nicht abrufbar: {error}{hint}{self._fallback(entry)}")
        return ToolResult(success=True, data={
            "url": target, "host": host, "title": title, "text": text, "truncated": truncated, "kind": kind,
        })


_default_service = None


def default_service():
    global _default_service
    if _default_service is None:
        _default_service = PageService()
    return _default_service


def set_default_service(service):
    global _default_service
    _default_service = service


def read_page(url="", item=""):
    return default_service().read_page(url, item)


def is_known_address(action_parameters):
    """Fuer risk.py: Ist die Adresse ein Eintrag der zuletzt genannten News-Liste (Nummer oder genau diese Adresse)?"""
    service = news_tool.default_service()
    number = action_parameters.get("item")
    url = action_parameters.get("url")
    if isinstance(number, (str, int)) and not isinstance(number, bool) and str(number).strip():
        return service.listed_item(number) is not None
    if isinstance(url, str) and url.strip():
        return service.is_listed(url.strip())
    return False
