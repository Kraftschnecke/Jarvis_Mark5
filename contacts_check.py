"""Fehlersuche fuer die Apple-Kontakte (Mark 5, Step 2.22). Nur lesen, aendert nichts.

Start im Projektordner:   py contacts_check.py            (Anzahlen)
                          py contacts_check.py Timon      (zeigt zusaetzlich, wie Kontakte mit diesem Namen bei Apple aussehen)

Zeigt Schritt fuer Schritt: Anmeldung -> Kontaktbereich -> Adressbuecher -> Anzahl Kontakte und Geburtstage, und vergleicht die
sparsame Abfrage (nur noetige Felder) mit der vollen. Das Passwort wird nie angezeigt; Namen nur fuer den gesuchten Namen auf deinem Bildschirm.
"""

import re
import sys

import config
from tools.caldav_tool import CalDavError
from tools.contacts_tool import CardDav, parse_vcards


def prop_names(vcard):
    unfolded = re.sub(r"\r?\n[ \t]", "", vcard)
    return sorted({line.split(":", 1)[0].split(";")[0].split(".")[-1].upper() for line in unfolded.splitlines() if ":" in line})


def main():
    account = config.caldav_account()
    if account is None:
        print("In der .env fehlen CALDAV_USER und CALDAV_PASSWORD (siehe .env.example).")
        return

    query = " ".join(sys.argv[1:]).strip().casefold()
    print(f"Apple-ID: {account['user']}\n")
    client = CardDav(account["user"], account["password"])

    try:
        client.discover()
        print("  OK      Anmeldung und Kontaktbereich gefunden")
        books = client.books()
    except CalDavError as error:
        print(f"  FEHLER  {error}")
        return

    print(f"  OK      {len(books)} Adressbuch/Adressbücher")
    for book in books:
        try:
            small = client.raw_cards(book["url"])
            full = client.raw_cards(book["url"], full=True)
        except CalDavError as error:
            print(f"  FEHLER  {book['name']}: {error}")
            continue
        for label, raws in (("sparsame Abfrage", small), ("volle Abfrage   ", full)):
            cards = [c for text in raws for c in parse_vcards(text)]
            bday_lines = sum(len(re.findall(r"(?im)^(?:[\w-]+\.)?BDAY[;:]", re.sub(r"\r?\n[ \t]", "", text))) for text in raws)
            print(f"  {label}: {len(raws)} Antworten, {len(cards)} Kontakte, {bday_lines} BDAY-Zeilen, {sum(1 for c in cards if c['birthday'])} Geburtstage erkannt")
        if query:
            print(f"\n  Treffer für „{query}“ (volle Abfrage), nur Feldnamen:")
            shown = 0
            for text in full:
                for card in parse_vcards(text):
                    if all(w in card["name"].casefold() for w in query.split()):
                        print(f"    - {card['name']}: Felder {', '.join(prop_names(text))}")
                        shown += 1
            if not shown:
                words = [w for w in query.split() if w]
                near = sorted({c["name"] for text in full for c in parse_vcards(text) if any(w in c["name"].casefold() for w in words)})[:10]
                print("    keiner mit allen Wörtern." + (f" Mit einem Wort: {', '.join(near)}" if near else " Auch mit einem Wort allein keiner."))


if __name__ == "__main__":
    main()
