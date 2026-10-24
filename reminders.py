"""Erinnerungen zu einer Uhrzeit (Mark 5, Step 2.9): "Erinnere mich um 19:00 an die Wäsche".

Anders als ein Timer (nur im Speicher, nach einem Neustart weg) steht eine Erinnerung in der Datei
``reminders.json`` (lokal, nicht in Git) und ueberlebt einen Neustart.

Ablauf:
- ``ReminderStore.add``: prueft Text, Datum und Uhrzeit, speichert die Erinnerung und traegt sie als
  "⏰ Text" in den Kalender ein (widgets.json). Nur Erinnerungen: normale Termine fasst dieses Modul nie an.
- ``ReminderScheduler``: ein Hintergrund-Thread schaut alle paar Sekunden nach, ob etwas faellig ist. Faellige
  Erinnerungen werden ZUERST aus der Datei und dem Kalender entfernt und dann als Meldung abgeschickt
  (so kommt jede genau einmal, auch bei einem Absturz mitten drin).
- Lief Jarvis zur Faelligkeit nicht, kommt die Erinnerung beim naechsten Start mit dem Hinweis "verpasst".

Wiederholungen (Step 2.10): Eine wiederkehrende Erinnerung ist EIN Eintrag mit einer Regel (recurrence.py), der
nur den naechsten Termin zeigt. Beim Ausloesen wird der naechste angelegt, bis Anzahl oder Enddatum erreicht sind.
Verpasste Termine einer Serie kommen nur einmal ("verpasst"), danach geht es mit dem naechsten kuenftigen weiter.

Zeiten sind die Ortszeit dieses Rechners.
"""

import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path

import recurrence
import widgets
from background_tasks import submit_result
from untrusted import clean_text

MAX_OPEN = 50
MAX_TEXT = 90                       # plus "⏰ " passt in den Kalendertitel (100 Zeichen)
MAX_DAYS_AHEAD = 365
MISSED_AFTER = timedelta(minutes=2)  # so viel spaeter gilt eine Erinnerung als "verpasst"
CHECK_SECONDS = 3
CALENDAR_PREFIX = "⏰ "
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

_FILE_LOCK = threading.RLock()
_DUE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_ALL_WORDS = {"alle", "alles", "all", "everything", "alle erinnerungen", "all reminders"}


class ReminderError(ValueError):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen darf."""


def parse_time(value):
    """Uhrzeit aus Sprache oder Text -> "HH:MM", sonst None.

    Versteht 19:00, 19.00, 1900, 730, 19, "19 Uhr", "19:30 Uhr", "7pm", "7:30 am".
    """
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value.strip().casefold())
    meridiem = None
    found = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))? ?(am|pm)", text)
    if found:
        hour, minute, meridiem = int(found.group(1)), int(found.group(2) or 0), found.group(3)
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    else:
        text = re.sub(r" ?uhr ?", " ", text).strip()
        for pattern in (r"(\d{1,2})[:.](\d{2})", r"(\d{1,2}) (\d{2})", r"(\d{1,2})(\d{2})", r"(\d{1,2})()"):
            found = re.fullmatch(pattern, text)
            if found:
                break
        else:
            return None
        hour, minute = int(found.group(1)), int(found.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def clean_reminder_text(value):
    text = clean_text(value, 1000) if isinstance(value, str) else ""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", text)).strip()


def is_all(which):
    """Meint die Angabe "alle Erinnerungen"? (Fuer die Rueckfrage vor dem Loeschen aller.)"""
    return isinstance(which, str) and " ".join(which.casefold().split()).rstrip(".!") in _ALL_WORDS


def describe_due(due, today=None):
    """'2026-10-22T19:00' -> 'heute um 19:00' / 'morgen um 19:00' / 'am Freitag, 23.10. um 19:00'."""
    moment = datetime.fromisoformat(due)
    today = (today or datetime.now()).date()
    clock = moment.strftime("%H:%M")
    if moment.date() == today:
        return f"heute um {clock}"
    if moment.date() == today + timedelta(days=1):
        return f"morgen um {clock}"
    return f"am {WEEKDAYS[moment.weekday()]}, {moment.day:02d}.{moment.month:02d}. um {clock}"


class ReminderStore:
    def __init__(self, path="reminders.json", now=datetime.now, calendar=None):
        self.path = Path(path)
        self.now = now
        self._calendar = calendar or widgets.default_store      # Funktion, die den Kalender (WidgetStore) liefert
        self._lock = _FILE_LOCK

    # ---- Datei
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("reminders") if isinstance(data, dict) else None
        clean = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("text"), str) \
                    and isinstance(item.get("due"), str) and _DUE.match(item["due"]):
                try:
                    datetime.fromisoformat(item["due"])
                except ValueError:
                    continue
                event = item.get("event_id")
                entry = {"id": item["id"], "text": item["text"][:MAX_TEXT], "due": item["due"],
                         "event_id": event if isinstance(event, str) else None}
                repeat = self._clean_repeat(item.get("repeat"))
                if repeat:
                    entry["repeat"] = repeat
                clean.append(entry)
        clean.sort(key=lambda r: (r["due"], r["text"]))
        return clean[:MAX_OPEN]

    @staticmethod
    def _clean_repeat(value):
        """Gespeicherte Wiederholung {rule, start, index} oder None, wenn sie fehlt oder kaputt ist."""
        if not isinstance(value, dict) or not isinstance(value.get("rule"), dict):
            return None
        rule = recurrence.Rule.from_dict(value["rule"])
        index = value.get("index")
        if rule is None or not widgets._valid_date(value.get("start")) or isinstance(index, bool) \
                or not isinstance(index, int) or index < 0:
            return None
        return {"rule": rule.to_dict(), "start": value["start"], "index": index}

    def _save(self, items):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"reminders": items}, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- Kalender (nur die eigenen Eintraege, ueber ihre Nummer)
    def _calendar_add(self, text, due):
        try:
            event = self._calendar().add_event(CALENDAR_PREFIX + text, due[:10], due[11:16])
            return event["id"]
        except (ValueError, OSError):
            return None                 # der Kalender ist voll oder nicht beschreibbar: die Erinnerung gilt trotzdem

    def _calendar_remove(self, event_id):
        if not event_id:
            return
        try:
            self._calendar().delete_event(event_id)
        except (ValueError, OSError):
            pass                        # schon vom Nutzer geloescht

    # ---- Anlegen, zeigen, loeschen
    def add(self, text, day, at, freq=None, interval=None, count=None, until=None):
        """Neue Erinnerung. Gibt {id, text, due, event_id, rolled, repeat?} zurueck, sonst ReminderError.

        freq/interval/count/until machen sie wiederkehrend (siehe recurrence.parse_rule)."""
        text = clean_reminder_text(text)
        if not text:
            raise ReminderError("Woran soll ich dich erinnern?")
        if len(text) > MAX_TEXT:
            raise ReminderError(f"Der Text darf höchstens {MAX_TEXT} Zeichen lang sein.")
        clock = parse_time(at)
        if clock is None:
            raise ReminderError("Um wie viel Uhr soll ich dich erinnern?")
        now = self.now().replace(second=0, microsecond=0)

        rolled = False
        wanted = day.strip().casefold() if isinstance(day, str) else ""
        if wanted in ("", "heute", "today", "none", "null", "-"):
            chosen = now.date()
            if datetime.fromisoformat(f"{chosen.isoformat()}T{clock}") <= self.now():
                chosen += timedelta(days=1)      # "um 8 Uhr" um 9 Uhr gesagt: gemeint ist morgen
                rolled = True
        elif widgets._valid_date(wanted):
            chosen = datetime.fromisoformat(wanted).date()
        else:
            raise ReminderError("Das Datum habe ich nicht verstanden.")
        due_moment = datetime.fromisoformat(f"{chosen.isoformat()}T{clock}")
        if due_moment <= self.now():
            raise ReminderError("Dieser Zeitpunkt ist schon vorbei. Nenne mir bitte einen Zeitpunkt in der Zukunft.")
        if due_moment > now + timedelta(days=MAX_DAYS_AHEAD):
            raise ReminderError(f"Erinnerungen sind höchstens {MAX_DAYS_AHEAD} Tage im Voraus möglich.")
        due = due_moment.strftime("%Y-%m-%dT%H:%M")

        repeat = None
        try:
            rule = recurrence.parse_rule(freq, interval, count, until, chosen)
            if rule is not None and not (rule.count == 1):
                if not rule.open_ended:
                    days = recurrence.occurrences(chosen, rule)
                    if len(days) > recurrence.MAX_OCCURRENCES:
                        raise ValueError(f"Das wären mehr als {recurrence.MAX_OCCURRENCES} Erinnerungen. Wähle ein früheres Ende.")
                    if days and days[-1] > recurrence.limit_date(now.date()):
                        raise ValueError(f"Die Serie reicht zu weit in die Zukunft (höchstens {recurrence.MAX_YEARS_AHEAD} Jahre).")
                    if len(days) <= 1:
                        rule = None
                if rule is not None:
                    repeat = {"rule": rule.to_dict(), "start": chosen.isoformat(), "index": 0}
        except ValueError as error:
            raise ReminderError(str(error)) from error

        with self._lock:
            items = self._load()
            if len(items) >= MAX_OPEN:
                raise ReminderError(f"Es sind höchstens {MAX_OPEN} offene Erinnerungen möglich.")
            entry = {"id": secrets.token_hex(4), "text": text, "due": due, "event_id": self._calendar_add(text, due)}
            if repeat:
                entry["repeat"] = repeat
            items.append(entry)
            try:
                self._save(items)
            except OSError as error:
                self._calendar_remove(entry["event_id"])
                raise ReminderError(f"Die Erinnerung konnte nicht gespeichert werden: {error}") from error
        return dict(entry, rolled=rolled)

    def list(self):
        with self._lock:
            return self._load()

    def cancel(self, which, scope="next"):
        """Loescht nach Nummer (1 = die naechste), Textteil oder "alle". Gibt die betroffenen zurueck, je mit
        ``next_due``: bei einer wiederkehrenden Erinnerung loescht scope "next" nur den kommenden Termin (die Serie
        laeuft weiter), scope "series" und "alle" beenden sie."""
        with self._lock:
            items = self._load()
            if not items:
                raise ReminderError("Es gibt keine offenen Erinnerungen.")
            text = " ".join(which.split()) if isinstance(which, str) else ""
            if not text:
                raise ReminderError("Welche Erinnerung soll ich löschen?")
            if is_all(text):
                chosen = list(items)
            else:
                number = re.fullmatch(r"(?:nummer|nr\.?|no\.?|number|#)?\s*(\d{1,2})\.?", text.casefold())
                if number:
                    index = int(number.group(1))
                    if not 1 <= index <= len(items):
                        raise ReminderError(f"Eine Erinnerung Nummer {index} gibt es nicht. {self.describe(items)}")
                    chosen = [items[index - 1]]
                else:
                    chosen = [r for r in items if text.casefold() in r["text"].casefold()]
                    if not chosen:
                        raise ReminderError(f"Keine Erinnerung passt zu „{text[:40]}“. {self.describe(items)}")
                    if len(chosen) > 1:
                        raise ReminderError(f"Das passt auf mehrere Erinnerungen. Nenne mir die Nummer. {self.describe(items)}")
            ids = {r["id"] for r in chosen}
            whole_series = is_all(text) or (isinstance(scope, str) and scope.strip().casefold() in ("series", "serie", "all", "alle", "ganze serie"))
            now = self.now()
            kept = [r for r in items if r["id"] not in ids]
            result = []
            for reminder in chosen:
                following = None if whole_series else self._advance(reminder, now)
                if following:
                    kept.append(following)
                result.append(dict(reminder, next_due=following["due"] if following else None))
            self._save(kept)
        for reminder in chosen:
            self._calendar_remove(reminder["event_id"])
        return result

    def _advance(self, entry, now):
        """Naechster kuenftiger Termin einer wiederkehrenden Erinnerung (mit neuem Kalendereintrag) oder None, wenn
        die Serie zu Ende ist oder es keine Wiederholung gibt. Termine, die schon vorbei sind, werden uebersprungen."""
        repeat = entry.get("repeat")
        if not repeat:
            return None
        rule = recurrence.Rule.from_dict(repeat["rule"])
        start = datetime.fromisoformat(repeat["start"]).date()
        clock = entry["due"][11:16]
        n = repeat["index"] + 1
        while n <= repeat["index"] + 5000:
            day = recurrence.occurrence(start, rule, n)
            if recurrence.finished(rule, n, day):
                return None
            due = f"{day.isoformat()}T{clock}"
            if datetime.fromisoformat(due) > now:
                return dict(entry, due=due, repeat=dict(repeat, index=n), event_id=self._calendar_add(entry["text"], due))
            n += 1
        return None

    @staticmethod
    def repeat_info(entry):
        """Fuer die Anzeige: {"repeat": "jeden Dienstag, 8 Mal", "left": 5 oder None} oder {} ohne Wiederholung."""
        repeat = entry.get("repeat")
        if not repeat:
            return {}
        rule = recurrence.Rule.from_dict(repeat["rule"])
        start = datetime.fromisoformat(repeat["start"]).date()
        left = rule.count - repeat["index"] if rule.count is not None else None
        return {"repeat": recurrence.describe(rule, start), "left": left}

    @staticmethod
    def describe(items):
        return "Offen: " + "; ".join(f"{n}: {r['text']} ({describe_due(r['due'])})" for n, r in enumerate(items, start=1))

    def pop_due(self):
        """Faellige Erinnerungen entfernen (Datei und Kalender) und zurueckgeben, mit "missed" = zu spaet."""
        with self._lock:
            items = self._load()
            now = self.now()
            due = [r for r in items if datetime.fromisoformat(r["due"]) <= now]
            if not due:
                return []
            ids = {r["id"] for r in due}
            kept = [r for r in items if r["id"] not in ids]
            fired = []
            for reminder in due:
                following = self._advance(reminder, now)
                if following:
                    kept.append(following)
                fired.append(dict(reminder, missed=now - datetime.fromisoformat(reminder["due"]) > MISSED_AFTER,
                                  next_due=following["due"] if following else None,
                                  last_of_series=bool(reminder.get("repeat")) and following is None))
            self._save(kept)
        for reminder in due:
            self._calendar_remove(reminder["event_id"])
        return fired


class ReminderScheduler:
    """Hintergrund-Thread: meldet faellige Erinnerungen. ``check()`` ist einzeln aufrufbar (Tests)."""

    def __init__(self, store, submit=submit_result, interval=CHECK_SECONDS):
        self.store = store
        self.submit = submit
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def check(self):
        count = 0
        for reminder in self.store.pop_due():
            data = {"text": reminder["text"], "due": reminder["due"], "missed": reminder["missed"]}
            if reminder.get("next_due"):
                data["next_due"] = reminder["next_due"]
            if reminder.get("last_of_series"):
                data["last_of_series"] = True
            self.submit({"type": "REMINDER_DUE", "data": data})
            count += 1
        return count

    def _run(self):
        while True:
            try:
                self.check()
            except Exception:
                pass                    # ein Fehler darf den Thread nie beenden
            if self._stop.wait(self.interval):
                return

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="reminders", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()


_default_store = None
_default_scheduler = None


def default_store():
    global _default_store
    if _default_store is None:
        _default_store = ReminderStore()
    return _default_store


def set_default_store(store):
    """Nur fuer Tests."""
    global _default_store
    _default_store = store


def start_scheduler():
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = ReminderScheduler(default_store())
    _default_scheduler.start()
    return _default_scheduler


def stop_scheduler():
    if _default_scheduler is not None:
        _default_scheduler.stop()
