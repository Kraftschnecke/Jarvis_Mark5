"""Prueft jeden News-Feed einzeln (Mark 5, Step 2.2). Aufruf:  py news_check.py [Stichwort]

Zeigt je Quelle: erreichbar?, wie viele Eintraege, die ersten Titel, und ob das Stichwort vorkommt.
Entwicklerwerkzeug, nicht Teil von Jarvis.
"""

import sys

from net_fetch import NetError, fetch_text
from tools import news_tool

keyword = " ".join(sys.argv[1:]).strip().casefold()

for feed_id, (label, url, hosts) in news_tool.FEEDS.items():
    print(f"\n== {label} ({url})")
    try:
        text = fetch_text(url, hosts, timeout=news_tool.FEED_TIMEOUT, max_bytes=news_tool.MAX_FEED_BYTES)
        items = news_tool.parse_feed(text, label)
    except NetError as error:
        print(f"   FEHLER: {error}" + (f" (Status {error.status})" if error.status else ""))
        continue
    print(f"   OK: {len(items)} Eintraege")
    for item in items[:3]:
        print(f"   - {item['title']}")
    if keyword:
        hits = [i for i in items if any(w in (i['title'] + ' ' + i['summary']).casefold() for w in keyword.split())]
        print(f"   Treffer fuer '{keyword}': {len(hits)}")
        for item in hits[:3]:
            print(f"     * {item['title']}")
