"""E-Mails lesen (Mark 5, Step 2.20). NUR LESEN.

Was dieses Werkzeug tut: sich per IMAP (verschluesselt, Port 993) anmelden, den Posteingang
schreibgeschuetzt oeffnen und
  - check_mail: von den neuesten Mails (ungelesen oder alle) Absender, Betreff und Datum holen,
    nummeriert (die Liste merkt sich Jarvis, damit man "die dritte" sagen kann),
  - read_mail: den TEXT einer Mail aus dieser Liste holen (zum Zusammenfassen oder fuer eine Frage dazu).
Was es NICHT tut: Mails senden, loeschen, verschieben, als gelesen markieren, Anhaenge herunterladen.
Es gibt in diesem Modul keinen Weg dafuer (kein SMTP, kein STORE/COPY/DELETE/APPEND, nur BODY.PEEK).

Absender und Betreff stammen von Fremden und sind unvertraut: gesaeubert, gekuerzt, und sie gehen
nur als Daten an das Sprachmodell. Das Passwort steht nur in der .env und kommt in keiner Antwort,
keinem Log und keiner Fehlermeldung vor.
"""

import imaplib
import email
import html
import re
import socket
import ssl
import time
from email import policy
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

import config
from tools.tool_result import ToolResult
from untrusted import clean_text

TIMEOUT_SECONDS = 15
MAX_COUNT = 20
DEFAULT_COUNT = 10
MAX_SUBJECT = 150
MAX_SENDER = 80

MAX_BODY = 9000                 # Zeichen Mailtext, die zum Sprachmodell gehen
MAX_RAW = 200000                # Bytes, die hoechstens von einer Mail geholt werden
ACTIVE_SECONDS = 30 * 60        # so lange gilt "die dritte" fuer die zuletzt gezeigte Liste

_FIELDS = "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)]"     # PEEK: markiert nichts als gelesen
_FULL = f"BODY.PEEK[]<0.{MAX_RAW}>"                          # ganze Mail (gekuerzt), ebenfalls ohne "gelesen"-Markierung


class MailState:
    """Die zuletzt gezeigte Mail-Liste (damit "fass die dritte zusammen" weiss, welche gemeint ist)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.account = ""
        self.items = []
        self.at = 0.0

    def set(self, account, items):
        self.account, self.items, self.at = account, list(items), self.clock()

    def active(self):
        return bool(self.items) and self.clock() - self.at <= ACTIVE_SECONDS


_default_state = MailState()


def default_state():
    return _default_state


def set_default_state(state):
    global _default_state
    _default_state = state


_ORDINALS = {"erste": 1, "erster": 1, "ersten": 1, "first": 1, "zweite": 2, "zweiter": 2, "zweiten": 2, "second": 2,
             "dritte": 3, "dritter": 3, "dritten": 3, "third": 3, "vierte": 4, "vierten": 4, "fourth": 4,
             "fünfte": 5, "fuenfte": 5, "fünften": 5, "fifth": 5,
             "neueste": 1, "neuste": 1, "letzte": 1, "latest": 1, "newest": 1, "last": 1, "oberste": 1}


def _decode(value):
    """E-Mail-Kopfzeile (auch =?utf-8?...?=) als Text; kaputte Kodierung wird zu ?."""
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return re.sub(r"[^\x20-\x7e]", "?", str(value or ""))


def _one_line(text, limit):
    return clean_text(re.sub(r"\s+", " ", text).strip(), limit)


def _parse_headers(raw):
    """Aus den rohen Kopfzeilen (bytes) Absender, Betreff, Datum. Alles gesaeubert."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    headers = {}
    current = None

    for line in text.splitlines():
        if line[:1] in (" ", "\t") and current:
            headers[current] += " " + line.strip()
        elif ":" in line:
            current, _, value = line.partition(":")
            current = current.strip().lower()
            headers[current] = value.strip()

    name, address = parseaddr(_decode(headers.get("from", "")))
    sender = _one_line(name or address, MAX_SENDER)
    subject = _one_line(_decode(headers.get("subject", "")), MAX_SUBJECT) or "(kein Betreff)"

    date = ""
    try:
        parsed = parsedate_to_datetime(headers.get("date", ""))
        date = parsed.astimezone().strftime("%Y-%m-%d %H:%M") if parsed.tzinfo else parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass

    return {"from": sender or "(unbekannt)", "subject": subject, "date": date}


def _pick_account(accounts, wanted):
    """Gibt (name, konto) oder (None, fehlertext)."""
    if not accounts:
        return None, ("Es ist noch kein Postfach eingerichtet. Du trägst es selbst in der Datei .env ein "
                      "(MAIL_ACCOUNTS, MAIL_<NAME>_HOST, _USER, _PASSWORD), siehe .env.example.")

    wanted = wanted.strip().lower() if isinstance(wanted, str) else ""
    wanted = "" if wanted in ("alle", "all", "leer", "egal") else wanted

    if not wanted:
        if len(accounts) == 1:
            name = next(iter(accounts))
            return name, accounts[name]
        return None, "Es gibt mehrere Postfächer: " + ", ".join(sorted(accounts)) + ". Welches soll ich abrufen?"

    exact = [n for n in accounts if n == wanted]
    partial = [n for n in accounts if wanted in n or n in wanted]
    hits = exact or partial

    if len(hits) != 1:
        return None, "Dieses Postfach kenne ich nicht. Eingerichtet sind: " + ", ".join(sorted(accounts)) + "."

    return hits[0], accounts[hits[0]]


def _clamp_count(value):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_COUNT
    return max(1, min(MAX_COUNT, number))


def _is_true(value, default=True):
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return default
    word = value.strip().lower()
    if word in ("false", "nein", "no", "alle", "all", "0"):
        return False
    if word in ("true", "ja", "yes", "ungelesen", "unread", "1"):
        return True
    return default


def _technical(error, account):
    """Art und (gekuerzter) Text eines Verbindungsfehlers fuer die Fehlersuche. Zugangsdaten werden unkenntlich gemacht."""
    text = str(error)
    for secret in (account.get("password"), account.get("user")):
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return f"{type(error).__name__}: {_one_line(text, 120)}"


def ssl_context(account):
    """Pruefende TLS-Einstellung: Zertifikate von Windows PLUS die Liste von certifi (die mit dem OpenAI-Paket kommt).
    Optional eine eigene Zertifikatsdatei (MAIL_<NAME>_CAFILE in der .env, vom Besitzer gewaehlt). Die Pruefung bleibt IMMER an."""
    context = ssl.create_default_context()

    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass                      # ohne certifi bleibt es bei den Windows-Zertifikaten

    cafile = account.get("cafile")
    if cafile:
        context.load_verify_locations(cafile=cafile)       # Fehler (Datei fehlt) landet als Verbindungsfehler beim Nutzer

    return context


def _connect(account):
    context = ssl_context(account)
    return imaplib.IMAP4_SSL(account["host"], account["port"], ssl_context=context, timeout=TIMEOUT_SECONDS)


def check_mail(account="", unread_only=True, count=DEFAULT_COUNT, accounts=None, connect=None, state=None):
    """Betreffzeilen der neuesten (ungelesenen) Mails. Aendert nichts im Postfach."""
    accounts = config.mail_accounts() if accounts is None else accounts
    state = state or default_state()
    name, chosen = _pick_account(accounts, account)

    if name is None:
        return ToolResult(success=False, error=chosen)

    only_unread = _is_true(unread_only, True)
    limit = _clamp_count(count)
    connection = None

    try:
        connection = (connect or _connect)(chosen)

        try:
            connection.login(chosen["user"], chosen["password"])
        except imaplib.IMAP4.error:
            # Die Antwort des Servers wird absichtlich nicht weitergegeben (sie kann den Benutzernamen enthalten)
            return ToolResult(success=False, error=f"Die Anmeldung beim Postfach „{name}“ wurde abgelehnt. "
                                                   "Prüfe Benutzername und Passwort in der .env.")

        status, _ = connection.select("INBOX", readonly=True)          # readonly: nichts kann sich aendern
        if status != "OK":
            return ToolResult(success=False, error=f"Der Posteingang von „{name}“ ließ sich nicht öffnen.")

        status, data = connection.uid("SEARCH", None, "UNSEEN")
        unread_ids = data[0].split() if status == "OK" and data and data[0] else []

        if only_unread:
            ids = unread_ids
        else:
            status, data = connection.uid("SEARCH", None, "ALL")
            ids = data[0].split() if status == "OK" and data and data[0] else []

        newest = ids[-limit:][::-1]                                   # neueste zuerst
        mails = []

        for mail_id in newest:
            status, parts = connection.uid("FETCH", mail_id, f"({_FIELDS})")
            if status != "OK" or not parts:
                continue
            raw = next((p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), b"")
            mails.append(dict(_parse_headers(raw), uid=mail_id.decode("ascii", "ignore") if isinstance(mail_id, bytes) else str(mail_id)))

        state.set(name, mails)
        numbered = [{"number": number, "from": m["from"], "subject": m["subject"], "date": m["date"]}
                    for number, m in enumerate(mails, start=1)]
        data = {"account": name, "unread_total": len(unread_ids), "shown": len(mails),
                "only_unread": only_unread, "mails": numbered}

        if not mails:
            data["info"] = "Keine ungelesenen Mails." if only_unread else "Der Posteingang ist leer."
        elif len(ids) > len(mails):
            data["more"] = len(ids) - len(mails)

        return ToolResult(success=True, data=data)

    except (socket.timeout, TimeoutError):
        return ToolResult(success=False, error=f"Das Postfach „{name}“ antwortet nicht (Zeitlimit).")
    except (OSError, imaplib.IMAP4.error, ssl.SSLError) as error:
        return ToolResult(success=False, error=f"Mit dem Postfach „{name}“ konnte ich keine Verbindung herstellen. "
                                               f"Prüfe Server, Port und Internet in der .env. (Technisch: {_technical(error, chosen)}; "
                                               "genauer zeigt es `py mail_check.py`.)")
    except Exception as error:
        return ToolResult(success=False, error=f"Das Postfach „{name}“ ließ sich nicht lesen. (Technisch: {_technical(error, chosen)})")
    finally:
        if connection is not None:
            for step in ("close", "logout"):
                try:
                    getattr(connection, step)()
                except Exception:
                    pass


def _choose(which, state):
    """Waehlt eine Mail aus der zuletzt gezeigten Liste. Gibt (nummer, eintrag) oder (None, fehlertext)."""
    if not state.active():
        return None, ("Ich habe gerade keine Mail-Liste vor mir. Lass dir zuerst deine Mails zeigen "
                      "(zum Beispiel „Zeig mir meine letzten Mails“), dann sag mir, welche ich lesen soll.")

    items = state.items
    text = which.strip().casefold().rstrip(".") if isinstance(which, str) else ""

    if not text or text in ("leer", "es", "sie", "diese", "die"):
        if len(items) == 1:
            return 1, items[0]
        return None, "Welche Mail meinst du? Sag die Nummer aus der Liste (1 bis %d) oder den Absender." % len(items)

    number = None
    if text.isdigit():
        number = int(text)
    else:
        for word in re.findall(r"[\wäöüß]+", text):
            if word.isdigit():
                number = int(word)
                break
            if word in _ORDINALS:
                number = _ORDINALS[word]
                break

    if number is not None:
        if 1 <= number <= len(items):
            return number, items[number - 1]
        return None, f"Es gibt nur {len(items)} Mails in der Liste, die Nummer {number} gibt es nicht."

    hits = [(i, m) for i, m in enumerate(items, start=1) if text in (m["from"] + " " + m["subject"]).casefold()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None, f"Ich finde in der Liste keine Mail zu „{_one_line(text, 40)}“. Sag die Nummer."
    return None, "Dazu passen mehrere Mails (" + ", ".join(str(i) for i, _ in hits) + "). Welche Nummer meinst du?"


def check_selection(which, state=None):
    """Fehlertext, wenn die Auswahl nicht aufgeht (vor der Rueckfrage), sonst None."""
    number, result = _choose(which, state or default_state())
    return result if number is None else None


def _html_to_text(text):
    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def _body_text(raw):
    """Lesbarer Text einer Mail (text/plain, sonst HTML ohne Tags). Anhaenge werden nur gezaehlt, nie gelesen."""
    message = email.message_from_bytes(raw, policy=policy.default)
    body = message.get_body(preferencelist=("plain", "html"))
    text = ""

    if body is not None:
        try:
            text = body.get_content()
        except Exception:
            payload = body.get_payload(decode=True) or b""
            text = payload.decode("utf-8", errors="replace")
        if body.get_content_type() == "text/html":
            text = _html_to_text(text)

    text = re.sub(r"[ \t\r\f\v]+", " ", text or "")
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()

    try:
        attachments = sum(1 for _ in message.iter_attachments())
    except Exception:
        attachments = 0

    return text, attachments


def read_mail(which="", question="", accounts=None, connect=None, state=None):
    """Der Text EINER Mail aus der zuletzt gezeigten Liste. Aendert nichts im Postfach."""
    state = state or default_state()
    number, item = _choose(which, state)

    if number is None:
        return ToolResult(success=False, error=item)

    accounts = config.mail_accounts() if accounts is None else accounts
    name = state.account
    chosen = accounts.get(name)

    if chosen is None:
        return ToolResult(success=False, error=f"Das Postfach „{name}“ ist nicht mehr eingerichtet.")

    connection = None

    try:
        connection = (connect or _connect)(chosen)

        try:
            connection.login(chosen["user"], chosen["password"])
        except imaplib.IMAP4.error:
            return ToolResult(success=False, error=f"Die Anmeldung beim Postfach „{name}“ wurde abgelehnt. "
                                                   "Prüfe Benutzername und Passwort in der .env.")

        status, _ = connection.select("INBOX", readonly=True)
        if status != "OK":
            return ToolResult(success=False, error=f"Der Posteingang von „{name}“ ließ sich nicht öffnen.")

        status, parts = connection.uid("FETCH", item["uid"], f"({_FULL})")
        raw = next((p[1] for p in parts or [] if isinstance(p, tuple) and len(p) > 1), b"") if status == "OK" else b""

        if not raw:
            return ToolResult(success=False, error="Diese Mail ist nicht mehr im Posteingang (verschoben oder gelöscht). Lass dir die Liste neu zeigen.")

        text, attachments = _body_text(raw)
        cut = len(raw) >= MAX_RAW or len(text) > MAX_BODY
        data = {"account": name, "number": number, "from": item["from"], "subject": item["subject"], "date": item["date"],
                "text": clean_text(text, MAX_BODY), "attachments": attachments}

        if cut:
            data["cut"] = True
        if not text:
            data["info"] = "Diese Mail hat keinen lesbaren Text (zum Beispiel nur ein Bild oder ein Anhang)."
        asked = _one_line(question, 200) if isinstance(question, str) else ""
        if asked:
            data["question"] = asked

        return ToolResult(success=True, data=data)

    except (socket.timeout, TimeoutError):
        return ToolResult(success=False, error=f"Das Postfach „{name}“ antwortet nicht (Zeitlimit).")
    except (OSError, imaplib.IMAP4.error, ssl.SSLError) as error:
        return ToolResult(success=False, error=f"Mit dem Postfach „{name}“ konnte ich keine Verbindung herstellen. "
                                               f"(Technisch: {_technical(error, chosen)})")
    except Exception as error:
        return ToolResult(success=False, error=f"Die Mail ließ sich nicht lesen. (Technisch: {_technical(error, chosen)})")
    finally:
        if connection is not None:
            for step in ("close", "logout"):
                try:
                    getattr(connection, step)()
                except Exception:
                    pass


def describe_read(which="", state=None):
    """Zeilen fuer die Rueckfrage beim Lesen einer Mail (ohne Zugangsdaten)."""
    state = state or default_state()
    number, item = _choose(which, state)
    if number is None:
        return ["Mail aus der zuletzt gezeigten Liste"]
    return [f"Mail {number}: „{_one_line(item['subject'], 80)}“ von {_one_line(item['from'], 40)}",
            "Der Text dieser Mail geht zum Zusammenfassen an OpenAI. Nichts wird verändert, gesendet oder als gelesen markiert."]


def describe(account=""):
    """Zeilen fuer die Rueckfrage (ohne Zugangsdaten)."""
    accounts = config.mail_accounts()
    name, _ = _pick_account(accounts, account)
    shown = name or (account.strip() if isinstance(account, str) and account.strip() else "Postfach")
    return [f"Postfach: {shown}", "Nur Absender, Betreff und Datum; nichts wird geöffnet, verändert oder gesendet."]
