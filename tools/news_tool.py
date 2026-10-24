"""News (Mark 5, Step 2.2): Schlagzeilen aus ausgewaehlten RSS-/Atom-Feeds.

Die Feeds stehen fest in einer Liste (FEEDS). In den Einstellungen (Seite "News") schaltest du
jeden einzeln an oder aus. Beliebige Adressen kann man bewusst NICHT eintragen: So darf Jarvis nur
Server ansprechen, die hier mit Namen stehen (kein Risiko, dass er Adressen im Heimnetz abruft).
Eine neue Quelle kommt als eine Zeile in FEEDS dazu.

Alles aus den Feeds ist unvertraute Eingabe (untrusted.py): HTML-Tags raus, versteckte Zeichen
raus, Laenge und Anzahl begrenzt, Links nur https. Ein Feed ist nie eine Anweisung.
XML mit DOCTYPE/ENTITY wird abgelehnt (Schutz vor "Entity-Bomben"); es wird nur die Standardbibliothek benutzt.
"""

import html
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

from net_fetch import NetError, fetch_text
from tools.tool_result import ToolResult
from untrusted import clean_text

# id -> (Anzeigename, Adresse, erlaubte Hosts)
FEEDS = {
    "tagesschau": ("Tagesschau", "https://www.tagesschau.de/index~rss2.xml",
                   ("www.tagesschau.de", "tagesschau.de")),
    "heise": ("heise online", "https://www.heise.de/rss/heise-atom.xml",
              ("www.heise.de", "heise.de")),
    "spiegel": ("Spiegel", "https://www.spiegel.de/schlagzeilen/index.rss",
                ("www.spiegel.de", "spiegel.de")),
    "sportschau": ("Sportschau", "https://www.sportschau.de/index~rss2.xml",
                   ("www.sportschau.de", "sportschau.de")),
    "espn_nhl": ("ESPN NHL", "https://www.espn.com/espn/rss/nhl/news",
                 ("www.espn.com", "espn.com")),
    "oilersnation": ("Oilers Nation", "https://oilersnation.com/feed",
                     ("oilersnation.com", "www.oilersnation.com")),
    "gnews": ("Google News (Suche)", "https://news.google.com/rss/search",
              ("news.google.com",)),
    "bingnews": ("Bing News (Suche)", "https://www.bing.com/news/search",
                 ("www.bing.com", "bing.com")),
    "bbc": ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml",
            ("feeds.bbci.co.uk",)),
}
DEFAULT_ON = ("tagesschau", "heise")
# Suchfeeds liefern nichts ohne Thema: das Stichwort geht als Suchbegriff an den Dienst
SEARCH_PARAMS = {
    "gnews": lambda q: {"q": q, "hl": "de", "gl": "DE", "ceid": "DE:de"},
    "bingnews": lambda q: {"q": q, "format": "rss", "setmkt": "de-DE"},
}
SEARCH_ONLY = tuple(SEARCH_PARAMS)

# Diese Seiten bauen den Artikel erst im Browser auf: Jarvis kann sie nicht zusammenfassen.
# Sie stehen nicht in den Suchergebnissen (nur dort; feste Feeds liefern nie solche Links).
HIDDEN_HOSTS = ("msn.com",)

CACHE_SECONDS = 600
MAX_FEED_BYTES = 1_000_000
FEED_TIMEOUT = 6
MAX_ITEMS_PER_FEED = 20
MAX_COUNT = 10
DEFAULT_COUNT = 5
MAX_TITLE = 200
MAX_SUMMARY = 300
MAX_URL = 700      # Google-News-Weiterleitungen sind lang (ca. 250-450 Zeichen)
MAX_TOPIC = 60

_HTML_TAG = re.compile(r"<[^>]{0,300}>")
_FORBIDDEN_XML = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_ALL_WORDS = ("", "alle", "alles", "all", "egal", "any")


def default_settings():
    """Voreinstellung fuer settings.json: {"tagesschau": True, ...}."""
    return {feed_id: feed_id in DEFAULT_ON for feed_id in FEEDS}


def _plain(value, max_length):
    """Text ohne HTML-Tags und -Entities, gesaeubert, auf eine Zeile verdichtet und gekuerzt."""
    if not isinstance(value, str):
        return ""
    text = html.unescape(_HTML_TAG.sub(" ", value))
    return clean_text(" ".join(text.split()), max_length).strip()


def _unwrap_bing(url):
    """Bing-Treffer verlinken ueber bing.com/news/apiclick.aspx?...&url=<echte Adresse>: die echte Adresse nehmen."""
    parts = urlparse(url)
    if (parts.hostname or "").lower() in ("www.bing.com", "bing.com") and parts.path.lower() == "/news/apiclick.aspx":
        target = parse_qs(parts.query).get("url", [""])[0]
        if target:
            return target
    return url


def _safe_url(value):
    if not isinstance(value, str):
        return ""
    url = _unwrap_bing(clean_text(value, MAX_URL + 1).strip())
    return url if len(url) <= MAX_URL and urlparse(url).scheme == "https" else ""


def _hidden(url):
    host = (urlparse(url).hostname or "").lower() if url else ""
    return any(host == h or host.endswith("." + h) for h in HIDDEN_HOSTS)


def _local(tag):
    """Tag-Name ohne Namensraum: '{http://www.w3.org/2005/Atom}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(element, *names):
    for child in element:
        if _local(child.tag) in names and child.text and child.text.strip():
            return child.text
    return None


def _link(element):
    """RSS: <link>text</link>. Atom: <link href="..." rel="alternate"/>."""
    for child in element:
        if _local(child.tag) != "link":
            continue
        if child.text and child.text.strip():
            return child.text
        if child.get("href") and child.get("rel", "alternate") == "alternate":
            return child.get("href")
    return None


def _parse_date(text):
    """RSS-Datum (RFC 822) oder Atom/RDF-Datum (ISO 8601) als Datum mit Zeitzone (UTC), sonst None."""
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_feed(text, label):
    """Eintraege eines Feeds: Liste von Woerterbuechern. Wirft NetError bei unlesbarem XML."""
    if not isinstance(text, str) or _FORBIDDEN_XML.search(text):
        raise NetError("Der Feed ist nicht lesbar.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise NetError("Der Feed ist nicht lesbar.") from error
    if _local(root.tag) not in ("rss", "feed", "RDF"):
        raise NetError("Das ist kein News-Feed.")   # z.B. eine Fehlerseite mit Status 200

    items = []
    for element in root.iter():
        if _local(element.tag) not in ("item", "entry"):
            continue
        title = _plain(_child_text(element, "title"), MAX_TITLE)
        if not title:
            continue
        items.append({
            "source": label,
            "title": title,
            "summary": _plain(_child_text(element, "description", "summary", "content"), MAX_SUMMARY),
            "url": _safe_url(_link(element)),
            "published": _parse_date(_child_text(element, "pubDate", "published", "updated", "date")),
        })
        if len(items) >= MAX_ITEMS_PER_FEED:
            break
    return items


def _parse_count(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_COUNT
    return max(1, min(MAX_COUNT, number))


class NewsService:
    def __init__(self, fetch=fetch_text, clock=time.time, enabled=None):
        self.fetch = fetch
        self.clock = clock
        self.enabled = enabled or (lambda: [feed_id for feed_id in FEEDS if feed_id in DEFAULT_ON])
        self._cache = {}
        self._lock = threading.Lock()
        self._last = []        # zuletzt genannte Schlagzeilen: [{"number", "url", "title"}] (fuer READ_PAGE)

    def _load_feed(self, feed_id, topic=""):
        label, url, hosts = FEEDS[feed_id]
        search = feed_id in SEARCH_ONLY
        key = (feed_id, topic) if search else feed_id
        with self._lock:
            cached = self._cache.get(key)
            if cached and self.clock() - cached[0] < CACHE_SECONDS:
                return cached[1]
        if search:
            text = self.fetch(url, hosts, params=SEARCH_PARAMS[feed_id](topic),
                              timeout=FEED_TIMEOUT, max_bytes=MAX_FEED_BYTES)
        else:
            text = self.fetch(url, hosts, timeout=FEED_TIMEOUT, max_bytes=MAX_FEED_BYTES)
        items = parse_feed(text, label)
        with self._lock:
            if len(self._cache) >= 100:
                self._cache.clear()
            self._cache[key] = (self.clock(), items)
        return items

    def _choose_feeds(self, source):
        """(Liste der Feed-IDs, Fehlertext)."""
        active = [feed_id for feed_id in self.enabled() if feed_id in FEEDS]
        if not active:
            return None, "Es ist keine News-Quelle eingeschaltet. Das geht in den Einstellungen auf der Seite News."
        word = source.strip().casefold() if isinstance(source, str) else ""
        if word in _ALL_WORDS:
            return active, None
        for feed_id, (label, _, _) in FEEDS.items():
            if word in (feed_id, label.casefold()):
                matches = [feed_id]
                break
        else:
            # Teilname ("nhl", "sport"): nur gueltig, wenn genau eine Quelle passt
            matches = [i for i, (label, _, _) in FEEDS.items() if word in i or word in label.casefold()]
        if len(matches) == 1:
            feed_id = matches[0]
            if feed_id in active:
                return [feed_id], None
            return None, f"Die Quelle {FEEDS[feed_id][0]} ist in den Einstellungen ausgeschaltet."
        return None, "Diese Quelle kenne ich nicht. Verfügbar: " + ", ".join(FEEDS[i][0] for i in FEEDS) + "."

    def get_news(self, source="alle", topic="", count=DEFAULT_COUNT):
        """Schlagzeilen als ToolResult (Daten: items + failed). Neueste zuerst."""
        feed_ids, problem = self._choose_feeds(source)
        if problem:
            return ToolResult(success=False, error=problem)

        limit = _parse_count(count)
        needle = clean_text(topic, MAX_TOPIC).strip().casefold() if isinstance(topic, str) else ""
        if needle in _ALL_WORDS:
            needle = ""

        if not needle:
            feed_ids = [f for f in feed_ids if f not in SEARCH_ONLY]
            if not feed_ids:
                return ToolResult(success=False, error="Für die Google-News-Suche brauche ich ein Thema.")

        items, failed = [], []

        def load(feed_id):
            try:
                return feed_id, self._load_feed(feed_id, needle), None
            except NetError as error:
                return feed_id, None, error

        with ThreadPoolExecutor(max_workers=len(feed_ids)) as pool:
            results = list(pool.map(load, feed_ids))
        for feed_id, loaded, error in results:
            if error is not None:
                failed.append(FEEDS[feed_id][0])
            else:
                items.extend(loaded)

        if not items and failed:
            return ToolResult(success=False, error="Die News sind gerade nicht abrufbar (" + ", ".join(failed) + ").")

        if needle:
            # Einzelne Woerter zaehlen ("Edmonton Oilers" findet auch "Oilers siegen"); mehr Treffer zuerst
            words = [w for w in needle.split() if len(w) >= 3] or [needle]
            for item in items:
                text = (item["title"] + " " + item["summary"]).casefold()
                item["score"] = sum(1 for w in words if w in text)
            searched = len(items)
            items = [i for i in items if i["score"] > 0]
            if not items:
                note = f" (durchsucht: {searched} Schlagzeilen aus {len(feed_ids) - len(failed)} Quellen"
                note += f"; nicht erreichbar: {', '.join(failed)})" if failed else ")"
                return ToolResult(success=False, error=f"Zu „{needle}“ habe ich keine Schlagzeilen gefunden{note}.")

        items = [i for i in items if not _hidden(i["url"])]
        if not items:
            return ToolResult(success=False, error="Es gibt keine lesbaren Schlagzeilen dazu (Treffer von msn.com blende ich aus, weil ich sie nicht lesen kann).")

        floor = datetime.min.replace(tzinfo=timezone.utc)
        items.sort(key=lambda i: (i.get("score", 0), i["published"] or floor), reverse=True)

        shown = []
        for number, item in enumerate(items[:limit], start=1):
            when = item["published"]
            shown.append({
                "number": number,
                "source": item["source"],
                "title": item["title"],
                "summary": item["summary"],
                "url": item["url"],
                "published": when.strftime("%d.%m.%Y %H:%M UTC") if when else None,
            })
        with self._lock:
            self._last = [{"number": s["number"], "url": s["url"], "title": s["title"], "summary": s["summary"]} for s in shown]
        return ToolResult(success=True, data={"items": shown, "unavailable_sources": failed})

    # ---- Bezug auf die zuletzt genannte Liste ("fass den dritten Artikel zusammen")

    def listed_item(self, number):
        """Eintrag Nr. number der zuletzt genannten Schlagzeilen oder None."""
        try:
            wanted = int(str(number).strip())
        except (TypeError, ValueError):
            return None
        with self._lock:
            return next((dict(i) for i in self._last if i["number"] == wanted and i["url"]), None)

    def is_listed(self, url):
        with self._lock:
            return isinstance(url, str) and bool(url) and any(i["url"] == url for i in self._last)


_default_service = None


def default_service():
    global _default_service
    if _default_service is None:
        _default_service = NewsService()
    return _default_service


def set_default_service(service):
    """Jarvis und Tests setzen hier den Dienst (mit den eingeschalteten Quellen aus den Einstellungen)."""
    global _default_service
    _default_service = service


def listed_item(number):
    return default_service().listed_item(number)


def is_listed(url):
    return default_service().is_listed(url)


def get_news(source="alle", topic="", count=DEFAULT_COUNT):
    return default_service().get_news(source, topic, count)
