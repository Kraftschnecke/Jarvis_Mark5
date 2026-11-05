"""Apple-Kalender (iCloud) per CalDAV lesen und einzelne Termine anlegen/loeschen (Mark 5, Step 2.19).

Zugang: Apple-ID und ein **app-spezifisches Passwort** (nicht das normale Apple-Passwort), beides nur in der
.env (CALDAV_USER, CALDAV_PASSWORD). Alles Netz laeuft ueber net_fetch (nur https, feste Hosts).
Erlaubte Server: caldav.icloud.com und die von Apple genannten pNN-caldav.icloud.com. Eine Weiterleitung oder ein
Verweis auf einen anderen Host wird abgelehnt, damit die Zugangsdaten nie an fremde Server gehen.
Termine von dort sind unvertraut (Titel kann jeder in eine Einladung schreiben): gesaeubert und gekuerzt.
"""

import base64
import re
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import net_fetch
from net_fetch import NetError
from untrusted import clean_text

DAV = "{DAV:}"
CAL = "{urn:ietf:params:xml:ns:caldav}"
ROOT_URL = "https://caldav.icloud.com/"
HOST_PATTERN = re.compile(r"^(caldav|p\d{1,3}-caldav)\.icloud\.com$")
MAX_TITLE = 120
MAX_EVENTS = 500
TIMEOUT = 15


class CalDavError(Exception):
    """Fehler mit einem Satz fuer den Nutzer."""


def _check_host(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or not parts.hostname or not HOST_PATTERN.match(parts.hostname.lower()) or parts.port not in (None, 443):
        raise CalDavError("Apple hat eine unerwartete Serveradresse genannt; aus Sicherheitsgründen höre ich hier auf.")
    return url


def _safe_xml(text):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise CalDavError("Die Antwort von Apple ist ungewöhnlich aufgebaut und wurde abgelehnt.")
    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        raise CalDavError("Die Antwort von Apple ließ sich nicht lesen.") from error


def _absolute(base, href):
    return urllib.parse.urljoin(base, href.strip())


class CalDav:
    """Schmaler Client. ``fetch`` ist austauschbar (Tests)."""

    def __init__(self, user, password, fetch=net_fetch.fetch_text, root=ROOT_URL):
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        self._auth = {"Authorization": "Basic " + token}
        self._fetch = fetch
        self._root = root
        self._hosts = {urllib.parse.urlsplit(root).hostname}
        self.home = None
        self.last_entries = 0

    def _request(self, method, url, body, depth="0", content_type="application/xml; charset=utf-8", extra=None, write=False):
        _check_host(url)
        host = urllib.parse.urlsplit(url).hostname.lower()
        headers = {**self._auth, "Depth": depth, "Content-Type": content_type, **(extra or {})}
        try:
            return self._fetch(url, tuple({host}), method=method, data=body, timeout=TIMEOUT, headers=headers)
        except NetError as error:
            if error.status in (401, 403) and not write:
                raise CalDavError("Apple hat die Anmeldung abgelehnt. Nimm ein app-spezifisches Passwort (appleid.apple.com → Anmeldung und Sicherheit) und prüfe die Apple-ID.") from error
            if write:
                raise CalDavError(f"Apple hat das Speichern im Kalender abgelehnt oder ist nicht erreichbar ({error}).") from error
            raise CalDavError(f"Der Kalender-Server von Apple ist nicht erreichbar ({error}).") from error

    @staticmethod
    def _first_href(root, tag_path):
        node = root.find(tag_path)
        if node is None:
            return None
        href = node.find(f"{DAV}href")
        return href.text.strip() if href is not None and href.text else None

    def discover(self):
        """Findet das Kalender-Verzeichnis. Gibt dessen Adresse zurueck."""
        body = '<?xml version="1.0"?><propfind xmlns="DAV:"><prop><current-user-principal/></prop></propfind>'
        root = _safe_xml(self._request("PROPFIND", self._root, body))
        principal = self._first_href(root, f".//{DAV}current-user-principal")
        if not principal:
            raise CalDavError("Apple hat kein Konto zu diesen Zugangsdaten genannt.")
        principal_url = _check_host(_absolute(self._root, principal))

        body = ('<?xml version="1.0"?><propfind xmlns="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><prop><c:calendar-home-set/></prop></propfind>')
        root = _safe_xml(self._request("PROPFIND", principal_url, body))
        home = self._first_href(root, f".//{CAL}calendar-home-set")
        if not home:
            raise CalDavError("Apple hat keinen Kalenderbereich für dieses Konto genannt.")
        self.home = _check_host(_absolute(principal_url, home))
        return self.home

    def calendars(self):
        """Liste der Kalender: [{"name", "url"}] (nur solche mit Terminen, nicht Erinnerungen)."""
        home = self.home or self.discover()
        body = ('<?xml version="1.0"?><propfind xmlns="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><prop><displayname/><resourcetype/>'
                '<c:supported-calendar-component-set/></prop></propfind>')
        root = _safe_xml(self._request("PROPFIND", home, body, depth="1"))
        found = []
        for response in root.findall(f"{DAV}response"):
            if response.find(f".//{DAV}resourcetype/{CAL}calendar") is None:
                continue
            components = {c.get("name") for c in response.findall(f".//{CAL}supported-calendar-component-set/{CAL}comp")}
            if components and "VEVENT" not in components:
                continue
            href = response.find(f"{DAV}href")
            if href is None or not href.text:
                continue
            name = response.find(f".//{DAV}displayname")
            found.append({"name": clean_text((name.text or "") if name is not None else "", 60) or "Kalender",
                          "url": _check_host(_absolute(home, href.text))})
        return found

    def events(self, calendar_url, start, end, expand=True):
        """Termine von ``start`` bis ``end`` (date). Mit ``expand`` loest Apple Serien in Einzeltermine auf."""
        s, e = start.strftime("%Y%m%dT000000Z"), end.strftime("%Y%m%dT000000Z")
        data = f'<c:expand start="{s}" end="{e}"/>' if expand else ""
        body = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/>'
                f'<c:calendar-data>{data}</c:calendar-data></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
                f'<c:comp-filter name="VEVENT"><c:time-range start="{s}" end="{e}"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        root = _safe_xml(self._request("REPORT", _check_host(calendar_url), body, depth="1"))
        events = []
        self.last_entries = 0                       # wie viele Eintraege Apple geliefert hat (fuer die Fehlersuche)
        for response in root.iter(f"{DAV}response"):
            node = response.find(f".//{CAL}calendar-data")
            if node is None:
                continue
            self.last_entries += 1
            href = response.find(f"{DAV}href")
            try:
                resource = _check_host(_absolute(calendar_url, href.text)) if href is not None and href.text else ""
            except CalDavError:
                resource = ""
            found = parse_events(node.text or "")
            for event in found:
                event["href"] = resource
                event["single"] = len(found) == 1       # eine Datei = ein Termin (sonst Serie mit Ausnahmen)
            events += found
            if len(events) >= MAX_EVENTS:
                break
        events.sort(key=lambda ev: (ev["date"], ev["time"]))
        return events[:MAX_EVENTS]

    def create_event(self, calendar_url, title, day, at=""):
        """Legt EINEN einfachen Termin an (kein Serie). Gibt (uid, adresse) zurueck."""
        uid = str(uuid.uuid4()).upper()
        ics = build_ics(uid, title, day, at)
        url = _check_host(calendar_url).rstrip("/") + "/" + urllib.parse.quote(uid) + ".ics"
        self._request("PUT", url, ics, content_type="text/calendar; charset=utf-8", extra={"If-None-Match": "*"}, write=True)
        return uid, url

    def delete_event(self, resource_url):
        """Loescht die Termin-Datei (nur Adressen bei Apple)."""
        self._request("DELETE", _check_host(resource_url), None, write=True)


# ---- iCalendar schreiben ----

def _escape(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def _fold(line):
    """Zeilen hoechstens 75 Bytes lang, Fortsetzung mit Leerzeichen (UTF-8-Zeichen werden nicht zerschnitten)."""
    out, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 74:
            out.append(current)
            current, size = " " + char, 1 + width
        else:
            current += char
            size += width
    out.append(current)
    return "\r\n".join(out)


def build_ics(uid, title, day, at="", now=None):
    """iCalendar-Text fuer einen Termin. ``day`` YYYY-MM-DD, ``at`` HH:MM oder leer (ganztaegig, sonst eine Stunde)."""
    chosen = date.fromisoformat(day)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    if at:
        hour, minute = (int(part) for part in at.split(":"))
        start = datetime.combine(chosen, dtime(hour, minute)).astimezone(timezone.utc)
        end = start + timedelta(hours=1)
        when = [f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}"]
    else:
        when = [f"DTSTART;VALUE=DATE:{chosen.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(chosen + timedelta(days=1)).strftime('%Y%m%d')}"]
    clean_title = " ".join(str(title).split())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//Kalender//DE", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
             f"UID:{uid}", f"DTSTAMP:{stamp}", *when, f"SUMMARY:{_escape(clean_title)}", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# ---- iCalendar lesen ----

def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def _unescape(value):
    for escaped, plain in (("\\n", " "), ("\\N", " "), ("\\,", ","), ("\\;", ";"), ("\\\\", "\\")):
        value = value.replace(escaped, plain)
    return value


def _parse_when(name_and_params, value):
    """DTSTART/DTEND -> (date, "HH:MM" oder "", ganztaegig). Zeiten werden in die Ortszeit des Rechners umgerechnet."""
    params = dict(p.split("=", 1) for p in name_and_params.split(";")[1:] if "=" in p)
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        day = datetime.strptime(value[:8], "%Y%m%d").date()
        return day, "", True
    stamp = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        stamp = stamp.replace(tzinfo=timezone.utc).astimezone()
    elif params.get("TZID"):
        try:
            stamp = stamp.replace(tzinfo=ZoneInfo(params["TZID"])).astimezone()
        except Exception:
            pass                       # unbekannte Zeitzone: Zeit so lassen
    return stamp.date(), stamp.strftime("%H:%M"), False


def parse_events(text):
    """Termine aus iCalendar-Text: [{"uid","title","date","time","end_time","all_day"}]. Kaputte Eintraege werden uebersprungen."""
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", _unfold(text), flags=re.S):
        fields = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            head, _, value = line.partition(":")
            fields.setdefault(head.split(";")[0].upper(), (head, value))
        if "DTSTART" not in fields or fields.get("STATUS", ("", ""))[1].strip().upper() == "CANCELLED":
            continue
        try:
            day, at, all_day = _parse_when(*fields["DTSTART"])
            end_time = ""
            if "DTEND" in fields and not all_day:
                end_day, end_time, _ = _parse_when(*fields["DTEND"])
                if end_day != day:
                    end_time = ""
        except (ValueError, KeyError):
            continue
        title = clean_text(_unescape(fields.get("SUMMARY", ("", ""))[1]), MAX_TITLE).strip() or "(ohne Titel)"
        uid = clean_text(fields.get("UID", ("", ""))[1].strip(), 200)
        recurring = "RRULE" in fields or "RECURRENCE-ID" in fields
        events.append({"uid": uid, "title": title, "date": day.isoformat(), "time": at, "end_time": end_time, "all_day": all_day,
                       "recurring": recurring})
    return events
