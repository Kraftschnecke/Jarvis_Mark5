"""Wiederholungen (Mark 5, Step 2.10): wiederkehrende Kalendereintraege und Erinnerungen.

Eine Regel besteht aus der Haeufigkeit (taeglich, woechentlich, monatlich, jaehrlich), einem Abstand
("alle 2 Wochen") und einem Ende: eine Anzahl ("8 Mal", "fuer die naechsten 8 Wochen") und/oder ein Datum
("bis 20.12.2026"). Ohne Ende sind bei Kalendereintraegen nur woechentlich, monatlich und jaehrlich erlaubt (Geburtstage, Muell),
taeglich und werktags brauchen dort ein Ende. Erinnerungen und Wecker duerfen auch ohne Ende taeglich oder werktags
laufen ("jeden Morgen um 7"), weil sie nur den naechsten Termin speichern (``dense_open``).
"Werktags" ist Montag bis Freitag; faellt der Start auf ein Wochenende, ist der erste Termin der Montag danach.

Alle Termine einer Serie sind Vielfache vom ERSTEN Termin aus gerechnet. Darum bleibt der 31. im Monat der 31.:
Januar 31 -> Februar 28 -> Maerz 31. Ein 29. Februar wird in Nicht-Schaltjahren zum 28.
Das Modul rechnet nur mit Daten. Speichern und Anzeigen steht in widgets.py und reminders.py.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

MAX_OCCURRENCES = 100               # so viele Termine hoechstens in einer Serie
MAX_YEARS_AHEAD = 5                 # der letzte Termin darf hoechstens so weit voraus liegen
OPEN_ENDED = ("weekly", "monthly", "yearly")
MAX_INTERVAL = {"daily": 60, "weekdays": 1, "weekly": 52, "monthly": 24, "yearly": 5}
DENSE = ("daily", "weekdays")      # taegliche Muster: ohne Ende nur fuer Erinnerungen und Wecker
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

_NONE_WORDS = {"", "none", "null", "no", "never", "-", "keine", "kein", "nein", "einmalig", "einmal", "once", "nie"}
_FREQ_WORDS = {
    "daily": "daily", "taeglich": "daily", "täglich": "daily", "jeden tag": "daily", "tag": "daily", "tage": "daily", "day": "daily",
    "weekdays": "weekdays", "werktags": "weekdays", "werktaeglich": "weekdays", "werktäglich": "weekdays", "wochentags": "weekdays",
    "jeden werktag": "weekdays", "an werktagen": "weekdays", "montag bis freitag": "weekdays", "mo-fr": "weekdays", "mo bis fr": "weekdays",
    "weekly": "weekly", "woechentlich": "weekly", "wöchentlich": "weekly", "jede woche": "weekly", "woche": "weekly",
    "wochen": "weekly", "week": "weekly",
    "monthly": "monthly", "monatlich": "monthly", "jeden monat": "monthly", "monat": "monthly", "monate": "monthly", "month": "monthly",
    "yearly": "yearly", "jaehrlich": "yearly", "jährlich": "yearly", "jedes jahr": "yearly", "jahr": "yearly", "jahre": "yearly",
    "year": "yearly", "annual": "yearly", "annually": "yearly",
}


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int = 1
    count: int = None               # Gesamtzahl der Termine (der erste mitgezaehlt) oder None
    until: date = None              # letzter erlaubter Tag oder None

    @property
    def open_ended(self):
        return self.count is None and self.until is None

    def to_dict(self):
        return {"freq": self.freq, "interval": self.interval, "count": self.count,
                "until": self.until.isoformat() if self.until else None}

    @staticmethod
    def from_dict(data):
        """Gespeicherte Regel zurueck, oder None, wenn sie kaputt ist (die Datei kann von Hand veraendert sein)."""
        try:
            until = data.get("until")
            return parse_rule(data.get("freq"), data.get("interval"), data.get("count"), until, date.min,
                              check_start=False, dense_open=True)
        except (ValueError, AttributeError, TypeError):
            return None


def _number(value, name, low, high):
    if isinstance(value, bool):
        raise ValueError(f"{name}: ungültiger Wert.")
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        raise ValueError(f"{name}: ungültiger Wert.")
    if not low <= value <= high:
        raise ValueError(f"{name}: erlaubt sind {low} bis {high}.")
    return value


def parse_rule(freq, interval, count, until, start, check_start=True, dense_open=False):
    """Regel aus den Angaben von Sprache/Text. None = keine Wiederholung. ValueError mit lesbarem Satz sonst."""
    if freq is None or (isinstance(freq, str) and freq.strip().casefold() in _NONE_WORDS):
        return None
    if not isinstance(freq, str):
        raise ValueError("Die Wiederholung habe ich nicht verstanden (täglich, wöchentlich, monatlich oder jährlich).")
    kind = _FREQ_WORDS.get(" ".join(freq.casefold().split()))
    if kind is None:
        raise ValueError("Die Wiederholung habe ich nicht verstanden (täglich, wöchentlich, monatlich oder jährlich).")

    if kind == "weekdays" and not (interval is None or interval == 1 or (isinstance(interval, str) and interval.strip() in ("", "1"))):
        raise ValueError("„Werktags“ kennt keinen Abstand.")
    if interval is None or (isinstance(interval, str) and not interval.strip()):
        step = 1
    else:
        step = _number(interval, "Abstand", 1, MAX_INTERVAL[kind])

    if count is None or (isinstance(count, str) and count.strip().casefold() in _NONE_WORDS) or count == 0:
        total = None
    else:
        total = _number(count, "Anzahl", 1, MAX_OCCURRENCES)

    end = None
    if until is not None and not (isinstance(until, str) and until.strip().casefold() in _NONE_WORDS):
        if isinstance(until, date):
            end = until
        else:
            try:
                end = date.fromisoformat(until.strip()) if isinstance(until, str) else None
            except ValueError:
                end = None
            if end is None:
                raise ValueError("Das Enddatum habe ich nicht verstanden.")
        if check_start and end < start:
            raise ValueError("Das Enddatum liegt vor dem ersten Termin.")

    rule = Rule(kind, step, total, end)
    if rule.open_ended and kind not in OPEN_ENDED and not (dense_open and kind in DENSE):
        raise ValueError("Eine tägliche oder werktägliche Wiederholung braucht ein Ende, zum Beispiel „für 14 Tage“ oder „bis zum 20.12.“.")
    return rule


def _add_months(day, months):
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def first_date(start, rule):
    """Der erste Termin: der Start selbst, bei "werktags" auf einem Wochenende der Montag danach."""
    if rule.freq == "weekdays" and start.weekday() >= 5:
        return start + timedelta(days=7 - start.weekday())
    return start


def occurrence(start, rule, n):
    """Der n-te Termin (0 = der erste), ohne Ende zu beachten."""
    if rule.freq == "daily":
        return start + timedelta(days=n * rule.interval)
    if rule.freq == "weekdays":
        anchor = first_date(start, rule)
        weekday = anchor.weekday()
        weeks, rest = divmod(weekday + n, 5)
        return anchor - timedelta(days=weekday) + timedelta(days=7 * weeks + rest)
    if rule.freq == "weekly":
        return start + timedelta(days=7 * rule.interval * n)
    if rule.freq == "monthly":
        return _add_months(start, n * rule.interval)
    return _add_months(start, 12 * n * rule.interval)


def finished(rule, n, day=None):
    """Ist der n-te Termin (am Tag ``day``) schon ausserhalb des Endes?"""
    if rule.count is not None and n >= rule.count:
        return True
    return rule.until is not None and day is not None and day > rule.until


def occurrences(start, rule, upto=None):
    """Alle Termine der Serie (Daten), hoechstens bis ``upto``. Haelt bei Anzahl und Enddatum an."""
    days = []
    n = 0
    while n <= MAX_OCCURRENCES * 10:
        day = occurrence(start, rule, n)
        if finished(rule, n, day) or (upto is not None and day > upto):
            break
        days.append(day)
        n += 1
    return days


def limit_date(today):
    """Spaetester erlaubter Termin einer Serie."""
    return _add_months(today, 12 * MAX_YEARS_AHEAD)


def describe(rule, start):
    """'jeden Dienstag, 8 Mal' / 'täglich, bis 20.12.2026' / 'jährlich am 03.05.'"""
    n = rule.interval
    if rule.freq == "daily":
        text = "täglich" if n == 1 else f"alle {n} Tage"
    elif rule.freq == "weekdays":
        text = "werktags (Mo–Fr)"
    elif rule.freq == "weekly":
        day = WEEKDAYS[start.weekday()]
        text = f"jeden {day}" if n == 1 else f"alle {n} Wochen ({day})"
    elif rule.freq == "monthly":
        text = f"jeden Monat am {start.day}." if n == 1 else f"alle {n} Monate am {start.day}."
    else:
        text = f"jährlich am {start.day:02d}.{start.month:02d}." if n == 1 else f"alle {n} Jahre am {start.day:02d}.{start.month:02d}."
    if rule.count is not None:
        text += f", {rule.count} Mal"
    if rule.until is not None:
        text += f", bis {rule.until.day:02d}.{rule.until.month:02d}.{rule.until.year}"
    return text
