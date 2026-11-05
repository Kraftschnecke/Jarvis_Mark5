"""Fehlersuche fuer das Postfach (Mark 5, Step 2.20). Nur lesen, aendert nichts.

Start im Projektordner:   py mail_check.py            (oder: py mail_check.py strato)

Prueft Schritt fuer Schritt: .env gelesen -> Server gefunden -> Verbindung -> verschluesselte
Verbindung (Zertifikat) -> Anmeldung -> Posteingang -> eine Kopfzeile. Beim ersten Fehler siehst du,
welcher Schritt es ist. Das Passwort wird nie angezeigt.
"""

import imaplib
import socket
import ssl
import sys

import config
from tools.mail_tool import ssl_context


def mask(text, account):
    text = str(text)
    for secret in (account["password"], account["user"]):
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def step(title, action, account):
    try:
        result = action()
    except Exception as error:
        print(f"  FEHLER  {title}\n          {type(error).__name__}: {mask(error, account)}")
        return None, False
    print(f"  OK      {title}" + (f"  ({result})" if isinstance(result, str) and result else ""))
    return result, True


def main():
    accounts = config.mail_accounts()
    print("Postfächer in der .env:", ", ".join(accounts) or "keine (MAIL_ACCOUNTS, HOST, USER und PASSWORD müssen alle gesetzt sein)")

    if not accounts:
        return

    wanted = sys.argv[1].lower() if len(sys.argv) > 1 else next(iter(accounts))
    if wanted not in accounts:
        print(f"Unbekanntes Postfach {wanted!r}.")
        return

    account = accounts[wanted]
    host, port = account["host"], account["port"]
    print(f"\nPostfach {wanted}: {account['user']} auf {host}:{port}\n")

    _, ok = step("Servername wird gefunden", lambda: ", ".join(sorted({i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})), account)
    if not ok:
        return

    def tls():
        context = ssl_context(account)
        with socket.create_connection((host, port), timeout=10) as raw, context.wrap_socket(raw, server_hostname=host) as secure:
            return secure.version()

    _, ok = step("Verschlüsselung (Zertifikat wird geprüft)", tls, account)
    if not ok:
        print("\n  -> Port gesperrt (Firewall, Virenscanner mit E-Mail-Schutz, Netzwerk) oder Zertifikat nicht akzeptiert (z. B. ein Virenscanner, der Verbindungen mitliest). Die Fehlerart oben sagt, welches von beiden.")
        return

    holder = {}

    def connect():
        holder["c"] = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_context(account), timeout=15)
        return "bereit"

    _, ok = step("IMAP-Verbindung", connect, account)
    if not ok:
        return

    connection = holder["c"]
    _, ok = step("Anmeldung", lambda: connection.login(account["user"], account["password"])[0], account)
    if not ok:
        print("\n  -> Benutzername oder Passwort stimmt nicht (bei Strato: das Passwort des E-Mail-Postfachs, nicht das Kundenkonto).")
        return

    _, ok = step("Posteingang schreibgeschützt öffnen", lambda: connection.select("INBOX", readonly=True)[0], account)
    if ok:
        step("Ungelesene Mails zählen", lambda: f"{len(connection.search(None, 'UNSEEN')[1][0].split())} ungelesen", account)
        status, data = connection.search(None, "ALL")
        ids = data[0].split() if status == "OK" and data and data[0] else []
        if ids:
            step("Eine Kopfzeile holen", lambda: connection.fetch(ids[-1], "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")[0], account)

    try:
        connection.logout()
    except Exception:
        pass

    print("\nFertig.")


if __name__ == "__main__":
    main()
