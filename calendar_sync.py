"""Der Apple-Kalender als zweite Quelle fuer den Jarvis-Kalender (Mark 5, Step 2.19).

Regeln:
- Jarvis LIEST die Kalender aus CALDAV_CALENDARS (leer = alle) und zeigt ihre Termine im Kalender-Widget, im Briefing
  und im Chat. Was du am Handy eintraegst, erscheint hier (nach hoechstens ``ttl`` Sekunden).
- Jarvis SCHREIBT nur in den einen Kalender CALDAV_WRITE_CALENDAR (leer = nirgends) und nur einfache Termine
  (Serien bleiben lokal). Geloescht werden kann nur dort und nur ein einfacher Termin, nie eine Serie.
- Termine aus anderen Kalendern (z. B. Arbeit) sind schreibgeschuetzt.
- Faellt Apple aus, zeigt Jarvis die zuletzt geholten Termine und sagt es (``status``); ein Fehler blockiert nichts.
- Termintitel von dort sind unvertraut (gesaeubert in ``caldav_tool``); sie gehen wie jede Antwort an das Modell.
- Zugangsdaten: nur .env, nie in Antworten oder Logs.
"""

import hashlib
import threading
import time
from datetime import date, timedelta

import config
from tools.caldav_tool import CalDav, CalDavError

WINDOW_PAST_DAYS = 7
WINDOW_FUTURE_DAYS = 180
CALENDAR_LIST_SECONDS = 3600


class AppleCalendar:
    def __init__(self, account, client_factory=CalDav, clock=time.time, today=date.today, ttl=300, error_ttl=60):
        self.account = account
        self._factory = client_factory
        self._clock = clock
        self._today = today
        self.ttl = ttl
        self.error_ttl = error_ttl
        self._lock = threading.RLock()
        self._client = None
        self._calendars = None
        self._calendars_at = 0.0
        self._events = []
        self._index = {}
        self._fresh_until = 0.0
        self.error = ""
        self.ok = False

    # ---- Einstellungen
    @property
    def write_name(self):
        return self.account.get("write_calendar", "") if self.account else ""

    def can_write(self):
        return bool(self.account and self.write_name)

    def _read_names(self):
        return [n.casefold() for n in self.account.get("calendars", [])]

    # ---- Verbindung
    def _get_client(self):
        if self._client is None:
            self._client = self._factory(self.account["user"], self.account["password"])
        return self._client

    def _calendar_list(self):
        now = self._clock()
        if self._calendars is None or now - self._calendars_at > CALENDAR_LIST_SECONDS:
            self._calendars = self._get_client().calendars()
            self._calendars_at = now
        return self._calendars

    @staticmethod
    def _event_id(calendar, event):
        raw = f"{calendar}|{event['uid']}|{event['date']}|{event['time']}"
        return "apple:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _make(self, calendar_name, event):
        deletable = (calendar_name.casefold() == self.write_name.casefold() and bool(self.write_name)
                     and not event.get("recurring") and event.get("single", True) and bool(event.get("href")))
        shown = {"id": self._event_id(calendar_name, event), "title": event["title"], "date": event["date"], "time": event["time"],
                 "source": "apple", "calendar": calendar_name, "readonly": not deletable}
        return shown, {"href": event.get("href", ""), "deletable": deletable, "calendar": calendar_name}

    def _refresh(self):
        today = self._today()
        start, end = today - timedelta(days=WINDOW_PAST_DAYS), today + timedelta(days=WINDOW_FUTURE_DAYS)
        client = self._get_client()
        wanted = self._read_names()
        events, index = [], {}
        for calendar in self._calendar_list():
            if wanted and calendar["name"].casefold() not in wanted:
                continue
            for event in client.events(calendar["url"], start, end):
                shown, meta = self._make(calendar["name"], event)
                if shown["id"] in index:
                    continue
                events.append(shown)
                index[shown["id"]] = meta
        events.sort(key=lambda e: (e["date"], e["time"] or "00:00", e["title"]))
        return events, index

    # ---- Lesen
    def events(self):
        """Termine aus Apple (zwischengespeichert). Wirft nie: bei einem Fehler die letzten bekannten Termine."""
        if not self.account:
            return []
        with self._lock:
            if self._clock() < self._fresh_until:
                return list(self._events)
            try:
                self._events, self._index = self._refresh()
                self.ok, self.error = True, ""
                self._fresh_until = self._clock() + self.ttl
            except (CalDavError, OSError, ValueError, KeyError) as error:
                self.ok, self.error = False, str(error) or "Unbekannter Fehler"
                self._calendars = None                       # naechstes Mal alles neu entdecken
                self._fresh_until = self._clock() + self.error_ttl
            return list(self._events)

    def status(self):
        return {"enabled": bool(self.account), "ok": self.ok, "error": self.error, "write_calendar": self.write_name,
                "can_write": self.can_write()}

    def invalidate(self):
        with self._lock:
            self._fresh_until = 0.0

    # ---- Schreiben (nur ein Kalender, nur einfache Termine)
    def add(self, title, day, at=""):
        if not self.can_write():
            raise ValueError("Es ist kein Kalender zum Schreiben eingerichtet (CALDAV_WRITE_CALENDAR in der .env).")
        with self._lock:
            try:
                calendars = self._calendar_list()
                target = next((c for c in calendars if c["name"].casefold() == self.write_name.casefold()), None)
                if target is None:
                    raise ValueError(f"Den Kalender „{self.write_name}“ gibt es bei Apple nicht.")
                uid, href = self._get_client().create_event(target["url"], title, day, at)
            except CalDavError as error:
                raise ValueError(str(error)) from error
            event = {"uid": uid, "title": title, "date": day, "time": at, "href": href, "single": True, "recurring": False}
            shown, meta = self._make(target["name"], event)
            self._events = sorted(self._events + [shown], key=lambda e: (e["date"], e["time"] or "00:00", e["title"]))
            self._index[shown["id"]] = meta
            # War der Zwischenspeicher noch frisch, bleibt er es (der neue Termin steht schon darin). Sonst wird beim
            # naechsten Lesen komplett neu geholt: ein halber Speicher darf nie als "frisch" gelten.
        return shown

    def delete(self, event_id):
        with self._lock:
            meta = self._index.get(event_id)
            if meta is None:
                raise ValueError("Diesen Termin gibt es nicht mehr. Der Kalender wird gleich neu geladen.")
            if not meta["deletable"]:
                raise ValueError(f"Dieser Termin gehört zum Kalender „{meta['calendar']}“ (oder ist eine Serie) und lässt sich in Jarvis "
                                 "nicht löschen. Lösche ihn am Handy.")
            try:
                self._get_client().delete_event(meta["href"])
            except CalDavError as error:
                raise ValueError(str(error)) from error
            self._events = [e for e in self._events if e["id"] != event_id]
            self._index.pop(event_id, None)



def from_config():
    """Der Apple-Kalender aus der .env, oder None wenn nicht eingerichtet."""
    account = config.caldav_account()
    return AppleCalendar(account) if account else None
