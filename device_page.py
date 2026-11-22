"""Welche Startseite bekommt der Besitzer: die PC-Willkommensseite oder die Handy-Version (mobile.html).

Eine Adresse ("/"), zwei Oberflaechen. Entschieden wird am Geraet, das fragt (User-Agent), mit zwei Schaltern in der Adresse:
  /?pc=1      erzwingt die PC-Ansicht (auch auf dem Handy)
  /?handy=1   erzwingt die Handy-Ansicht (auch am PC, zum Ausprobieren)
Tablets (iPad, Android ohne "Mobile") bekommen die PC-Ansicht. Gaeste sind nicht betroffen, sie haben ihre eigene Seite.
"""

from urllib.parse import parse_qs

DESKTOP_PAGE = "/welcome.html"
PHONE_PAGE = "/mobile.html"


def is_phone(user_agent):
    """True bei iPhone, iPod und Android-Handys (Android-Tablets nennen sich nicht "Mobile")."""
    text = (user_agent or "").lower()
    if "iphone" in text or "ipod" in text:
        return True
    return "android" in text and "mobile" in text


def start_page(query, user_agent):
    """Pfad der Startseite fuer den Besitzer. query = Teil der Adresse nach dem "?"."""
    flags = parse_qs(query or "", keep_blank_values=True)
    if "pc" in flags:
        return DESKTOP_PAGE
    if "handy" in flags:
        return PHONE_PAGE
    return PHONE_PAGE if is_phone(user_agent) else DESKTOP_PAGE
