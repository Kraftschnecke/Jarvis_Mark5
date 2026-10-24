import re
from urllib.parse import urlparse

from config import BRAVE_API_KEY
from net_fetch import NetError, fetch_json
from tools.tool_result import ToolResult
from untrusted import clean_text

SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SEARCH_HOSTS = ("api.search.brave.com",)

# Ohne Timeout wuerde ein haengender Server Jarvis (und die GUI) blockieren.
REQUEST_TIMEOUT_SECONDS = 10

# Suchergebnisse sind Text aus dem Internet (siehe untrusted.py): Anzahl und
# Laenge werden begrenzt, damit eine Seite nicht beliebig viel Text einschleust.
MAX_RESULTS = 10
MAX_TITLE = 200
MAX_DESCRIPTION = 600
MAX_URL = 500

_HTML_TAG = re.compile(r"<[^>]{0,200}>")


def _plain(value, max_length):
    """Text ohne HTML-Tags (Brave liefert z.B. <strong>), gesaeubert und gekuerzt."""
    if not isinstance(value, str):
        return ""

    return clean_text(_HTML_TAG.sub("", value), max_length).strip()


def _safe_url(value):
    """Nur normale Web-Adressen (http/https). Alles andere wird zu ''."""
    if not isinstance(value, str):
        return ""

    url = clean_text(value, MAX_URL).strip()

    return url if urlparse(url).scheme in ("http", "https") else ""


def search_web(query):
    if not BRAVE_API_KEY:
        return ToolResult(
            success=False,
            error="BRAVE_API_KEY fehlt in der .env, die Websuche ist nicht eingerichtet."
        )

    try:
        data = fetch_json(
            SEARCH_URL,
            SEARCH_HOSTS,
            params={"q": query},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": BRAVE_API_KEY
            },
            timeout=REQUEST_TIMEOUT_SECONDS
        )

        results = data.get("web", {}).get("results", []) if isinstance(data, dict) else []

        structured_results = []

        for result in results[:MAX_RESULTS]:
            if not isinstance(result, dict):
                continue

            structured_results.append({
                "title": _plain(result.get("title", ""), MAX_TITLE),
                "url": _safe_url(result.get("url", "")),
                "description": _plain(
                    result.get("description", ""), MAX_DESCRIPTION
                )
            })

        return ToolResult(
            success=True,
            data=structured_results
        )

    except NetError as error:
        return ToolResult(
            success=False,
            error=f"Die Websuche ist fehlgeschlagen: {error}"
        )

    except Exception as error:
        return ToolResult(
            success=False,
            error=str(error)
        )
