"""Wikipedia nachschlagen (Mark 5, Step 2.5): "Wer war Hermann Hesse?", "Was ist ein Quasar?"

Eine Anfrage an die MediaWiki-Schnittstelle von wikipedia.org (kostenlos, ohne Schluessel) sucht den
Begriff und liefert gleich die Einleitung der besten Treffer. Zuerst die deutsche Wikipedia, gibt es dort
nichts, die englische. Begriffsklaerungsseiten ("Mercury kann bedeuten ...") werden uebersprungen; gibt es
nur solche, nennt Jarvis die Moeglichkeiten.

Der Suchbegriff geht an wikipedia.org, sonst nichts. Wikipedia kann jeder bearbeiten: der Text ist
unvertraute Eingabe (untrusted.py), wird gesaeubert und gekuerzt und ist nie eine Anweisung.
Die Antwort nennt immer die Quelle (Titel + Link).
"""

import threading
import time
from urllib.parse import urlparse

from net_fetch import NetError, fetch_json
from tools.tool_result import ToolResult
from untrusted import clean_text

LANGUAGES = {"de": "de.wikipedia.org", "en": "en.wikipedia.org"}
# Wikimedia verlangt eine erkennbare Kennung (allgemeine Kennungen werden gern gesperrt).
# Wer will, haengt hier eine Kontaktadresse an.
USER_AGENT = "Jarvis/5.0 (personal home-built assistant; Python urllib)"

CACHE_SECONDS = 3600
MAX_CACHED = 100
MAX_QUERY = 100
MAX_TITLE = 150
MAX_DESCRIPTION = 200
MAX_EXTRACT = 1500
MAX_URL = 300
RESULTS = 3


def _language(value):
    word = value.strip().casefold() if isinstance(value, str) else ""
    return {"en": "en", "englisch": "en", "english": "en"}.get(word, "de")


def _page_url(page, host):
    """Link zur Seite, nur https auf einer Wikipedia-Adresse, sonst aus dem Titel gebaut."""
    url = page.get("fullurl")
    if isinstance(url, str) and len(url) <= MAX_URL:
        parts = urlparse(url)
        try:
            port = parts.port
        except ValueError:
            return ""
        if (parts.scheme == "https" and parts.hostname == host and port in (None, 443)
                and not parts.username and not parts.password):
            return url
    return ""


class WikiService:
    def __init__(self, fetch=fetch_json, clock=time.time):
        self.fetch = fetch
        self.clock = clock
        self._cache = {}
        self._lock = threading.Lock()

    def _search(self, language, query):
        """Seiten der Suche in Reihenfolge der Treffer: [{title, description, extract, url, disambiguation}]."""
        host = LANGUAGES[language]
        key = (language, query.casefold())
        with self._lock:
            cached = self._cache.get(key)
            if cached and self.clock() - cached[0] < CACHE_SECONDS:
                return cached[1]
        data = self.fetch(f"https://{host}/w/api.php", (host,), params={
            "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
            "generator": "search", "gsrsearch": query, "gsrlimit": RESULTS, "gsrnamespace": 0,
            "prop": "extracts|pageprops|info|description", "exintro": 1, "explaintext": 1, "exlimit": RESULTS,
            "ppprop": "disambiguation", "inprop": "url",
        }, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        pages = data.get("query", {}).get("pages") if isinstance(data, dict) and isinstance(data.get("query"), dict) else None
        found = []
        for page in pages if isinstance(pages, list) else []:
            if not isinstance(page, dict) or page.get("missing") or not isinstance(page.get("title"), str):
                continue
            index = page.get("index")
            props = page.get("pageprops")
            found.append({
                "rank": index if isinstance(index, int) and not isinstance(index, bool) else 99,
                "title": clean_text(page["title"], MAX_TITLE).strip(),
                "description": clean_text(page.get("description"), MAX_DESCRIPTION).strip(),
                "extract": clean_text(" ".join(page["extract"].split()), MAX_EXTRACT).strip() if isinstance(page.get("extract"), str) else "",
                "url": _page_url(page, host),
                "disambiguation": isinstance(props, dict) and "disambiguation" in props,
            })
        found.sort(key=lambda p: p["rank"])
        with self._lock:
            if len(self._cache) >= MAX_CACHED:
                self._cache.clear()
            self._cache[key] = (self.clock(), found)
        return found

    def lookup(self, topic, language="de"):
        """Nachschlagen als ToolResult (Daten: title, description, extract, url, language, source, also_see)."""
        query = " ".join(clean_text(topic, MAX_QUERY).split()) if isinstance(topic, str) else ""
        if not query:
            return ToolResult(success=False, error="Was soll ich in Wikipedia nachschlagen?")
        first = _language(language)
        order = [first] + [other for other in LANGUAGES if other != first]
        try:
            for code in order:
                pages = self._search(code, query)
                readable = [p for p in pages if not p["disambiguation"] and p["extract"]]
                if readable:
                    best = readable[0]
                    return ToolResult(success=True, data={
                        "title": best["title"], "description": best["description"], "extract": best["extract"],
                        "url": best["url"], "language": code, "source": f"Wikipedia ({code})",
                        "also_see": [p["title"] for p in pages if p is not best and not p["disambiguation"]][:2],
                    })
                options = [p["title"] for p in pages if p["disambiguation"]]
                if options:
                    return ToolResult(success=False, error=(
                        f"„{query}“ ist mehrdeutig in Wikipedia ({code}). Meinst du: " + ", ".join(options) +
                        "? Nenne mir bitte einen genaueren Begriff."))
        except NetError as error:
            return ToolResult(success=False, error=f"Wikipedia ist gerade nicht erreichbar: {error}")
        return ToolResult(success=False, error=f"Zu „{query}“ habe ich in Wikipedia nichts gefunden.")


_default_service = None


def default_service():
    global _default_service
    if _default_service is None:
        _default_service = WikiService()
    return _default_service


def set_default_service(service):
    global _default_service
    _default_service = service


def wiki_lookup(topic, language="de"):
    return default_service().lookup(topic, language)
