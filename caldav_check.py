"""Fehlersuche fuer den Apple-Kalender (Mark 5, Step 2.19). Nur lesen, aendert nichts.

Start im Projektordner:   py caldav_check.py

Zeigt Schritt fuer Schritt: Anmeldung -> Kalenderbereich -> Liste deiner Kalender -> die Termine der naechsten 14 Tage.
Das Passwort wird nie angezeigt.
"""

from datetime import date, timedelta

import config
from tools.caldav_tool import CalDav, CalDavError


def main():
    account = config.caldav_account()
    if account is None:
        print("In der .env fehlen CALDAV_USER und CALDAV_PASSWORD (siehe .env.example).")
        return

    print(f"Apple-ID: {account['user']}\n")
    client = CalDav(account["user"], account["password"])

    try:
        home = client.discover()
        print("  OK      Anmeldung und Kalenderbereich gefunden")
        calendars = client.calendars()
    except CalDavError as error:
        print(f"  FEHLER  {error}")
        return

    print(f"  OK      {len(calendars)} Kalender mit Terminen:")
    for calendar in calendars:
        print(f"            - {calendar['name']}")

    read = account["calendars"]
    chosen = [c for c in calendars if not read or c["name"].casefold() in {n.casefold() for n in read}]
    missing = [n for n in read if n.casefold() not in {c["name"].casefold() for c in calendars}]
    for name in missing:
        print(f"  FEHLER  Einen Kalender namens {name!r} gibt es nicht (CALDAV_CALENDARS in der .env).")
    if not chosen:
        return

    write = account["write_calendar"]
    if write and write.casefold() not in {c["name"].casefold() for c in calendars}:
        print(f"  FEHLER  Schreib-Kalender {write!r} gibt es nicht (CALDAV_WRITE_CALENDAR in der .env).")
    print(f"\n  Jarvis liest: {', '.join(c['name'] for c in chosen)}")
    print(f"  Jarvis schreibt in: {write or 'keinen (CALDAV_WRITE_CALENDAR ist leer)'}")

    today = date.today()
    for calendar in chosen:
        try:
            events = client.events(calendar["url"], today, today + timedelta(days=14))
            entries = client.last_entries
        except CalDavError as error:
            print(f"\n  FEHLER  {calendar['name']}: {error}")
            continue
        print(f"\n  {calendar['name']}: {len(events)} Termine in den nächsten 14 Tagen (Apple lieferte {entries} Einträge)")
        for event in events[:8]:
            print(f"            {event['date']} {event['time'] or 'ganztägig':<9} {event['title']}")

        if not events:
            try:
                wide = client.events(calendar["url"], today, today + timedelta(days=365), expand=False)
                print(f"            Zum Vergleich: im nächsten Jahr (ohne Serien-Auflösung) {len(wide)} Einträge ({client.last_entries} von Apple)")
            except CalDavError as error:
                print(f"            Vergleichsabfrage fehlgeschlagen: {error}")

    print("\nFertig.")


if __name__ == "__main__":
    main()
