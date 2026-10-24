"""Zeigt, was bei einer Webseite zurueckkommt (Mark 5, Step 2.6). Aufruf:  py page_check.py https://...

Entwicklerwerkzeug, nicht Teil von Jarvis. Ruft die Seite so ab wie Jarvis (gleiche Regeln, gleiche Kennung)
und zeigt Status, Groesse, Titel, erkannte Art und den Anfang des Textes. Bei einer Seite ohne Text
erkennt man hier, ob sie blockiert, leer oder per JavaScript aufgebaut ist.
"""

import re
import sys

from net_fetch import ANY_PUBLIC_HOST, NetError, fetch_text
from tools import page_tool

if len(sys.argv) != 2:
    sys.exit("Aufruf: py page_check.py https://adresse")

url = sys.argv[1]
print(f"== {url}")
try:
    page = fetch_text(url, ANY_PUBLIC_HOST, timeout=page_tool.PAGE_TIMEOUT, max_bytes=page_tool.PAGE_MAX_BYTES,
                      headers=page_tool.PAGE_HEADERS, fallback_encoding="cp1252")
except NetError as error:
    print(f"ABRUF FEHLGESCHLAGEN: {error}" + (f" (Status {error.status})" if error.status else ""))
    sys.exit(1)

lower = page.lower()
print(f"Abruf OK: {len(page)} Zeichen")
print(f"  <article>: {lower.count('<article')}  <p>: {lower.count('<p')}  <script>: {lower.count('<script')}")
print(f"  JSON-LD: {lower.count('ld+json')}  articleBody: {page.count('articleBody')}  og:description: {lower.count('og:description')}")
print(f"  Hinweise auf Cookie-/Bot-Seiten: {len(re.findall(r'consent|captcha|cloudflare|enable javascript|access denied', lower))}")
try:
    title, text, truncated, kind = page_tool.extract_text(page)
except NetError as error:
    print(f"KEIN TEXT: {error}")
    print("Anfang der Seite:", " ".join(page[:400].split()))
    sys.exit(1)
print(f"Titel: {title}\nArt: {kind}  Laenge: {len(text)}  gekuerzt: {truncated}")
print("Anfang:", text[:400].replace("\n", " | "))
