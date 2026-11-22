"""Geraeteerkennung: PC bekommt die Willkommensseite, Handy die Handy-Version; die Schalter ?pc=1 und ?handy=1 gehen vor."""

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import device_page

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
IPOD = "Mozilla/5.0 (iPod touch; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 14; SM-X700) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
IPAD = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/120.0"

for agent in (IPHONE, IPOD, ANDROID_PHONE):
    assert device_page.is_phone(agent), agent
for agent in (ANDROID_TABLET, IPAD, WINDOWS, MAC, "", None, "curl/8.0", "python-requests"):
    assert not device_page.is_phone(agent), agent
assert device_page.is_phone("IPHONE") and device_page.is_phone("android MOBILE")            # Gross/Klein egal
assert not device_page.is_phone("Android")                                                    # nur "Android": Tablet

D, P = device_page.DESKTOP_PAGE, device_page.PHONE_PAGE
assert (D, P) == ("/welcome.html", "/mobile.html")
assert device_page.start_page("", IPHONE) == P and device_page.start_page("", WINDOWS) == D
assert device_page.start_page(None, IPHONE) == P and device_page.start_page("", None) == D
assert device_page.start_page("pc=1", IPHONE) == D                      # PC-Ansicht auf dem Handy
assert device_page.start_page("handy=1", WINDOWS) == P                  # Handy-Ansicht am PC
assert device_page.start_page("handy=1&pc=1", WINDOWS) == D            # bei Streit gewinnt die PC-Ansicht (sicherer Weg zurueck)
assert device_page.start_page("x=1", IPHONE) == P
assert device_page.start_page("pc", IPHONE) == D and device_page.start_page("handy", WINDOWS) == P     # auch ohne "=1"
assert device_page.start_page("foo=bar&handy=1", ANDROID_TABLET) == P

print("test_device_page: ALL TESTS PASSED")
