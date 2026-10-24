"""Wiederholungen (Mark 5, Step 2.10): Rechnen mit Serien, ohne alles andere getestet."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recurrence
from recurrence import Rule, describe, finished, limit_date, occurrence, occurrences, parse_rule

TUE = date(2026, 10, 27)          # ein Dienstag
iso = lambda days: [d.isoformat() for d in days]


def fails(*args, part):
    try:
        parse_rule(*args)
    except ValueError as error:
        assert part in str(error), (args, str(error))
        return
    raise AssertionError(args)


# 1) Nichts oder "keine" -> keine Wiederholung
for none in (None, "", "  ", "none", "null", "keine", "einmalig", "-", "Nie"):
    assert parse_rule(none, None, None, None, TUE) is None, none

# 2) Das Beispiel: "für die nächsten 8 Wochen" = jeden Dienstag, 8 Mal (der erste mitgezählt)
rule = parse_rule("weekly", None, 8, None, TUE)
days = occurrences(TUE, rule)
assert len(days) == 8 and iso(days)[0] == "2026-10-27" and iso(days)[-1] == "2026-12-15"
assert all(d.weekday() == 1 for d in days)
assert describe(rule, TUE) == "jeden Dienstag, 8 Mal"

# 3) Wörter und Schreibweisen für die Häufigkeit; Zahlen als Text
for word, kind in (("Täglich", "daily"), ("taeglich", "daily"), ("jeden Tag", "daily"), ("wöchentlich", "weekly"), ("Weekly", "weekly"),
                   ("jede Woche", "weekly"), ("monatlich", "monthly"), ("jedes Jahr", "yearly"), ("jährlich", "yearly")):
    assert parse_rule(word, "1", "5", None, TUE).freq == kind, word
r = parse_rule("weekly", "2", "3", "", TUE)
assert (r.interval, r.count, r.until) == (2, 3, None) and iso(occurrences(TUE, r)) == ["2026-10-27", "2026-11-10", "2026-11-24"]
assert describe(r, TUE) == "alle 2 Wochen (Dienstag), 3 Mal"
assert parse_rule("weekly", 2.0, 3.0, None, TUE).interval == 2

# 4) Enddatum: der letzte Termin darf genau auf das Enddatum fallen
r = parse_rule("weekly", None, None, "2026-11-17", TUE)
assert iso(occurrences(TUE, r)) == ["2026-10-27", "2026-11-03", "2026-11-10", "2026-11-17"]
assert describe(r, TUE) == "jeden Dienstag, bis 17.11.2026"
r = parse_rule("weekly", None, 10, "2026-11-10", TUE)       # beides: es gilt, was zuerst endet
assert len(occurrences(TUE, r)) == 3
assert len(occurrences(TUE, parse_rule("weekly", None, 2, "2026-12-31", TUE))) == 2

# 5) Monatsende: Januar 31 -> Februar 28 -> März 31 (vom ersten Termin aus gerechnet), Schaltjahr
jan = date(2026, 1, 31)
r = parse_rule("monthly", None, None, None, jan)
assert iso(occurrences(jan, r, date(2026, 5, 31))) == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]
assert iso(occurrences(date(2024, 1, 31), r, date(2024, 3, 1))) == ["2024-01-31", "2024-02-29"]
r = parse_rule("yearly", None, None, None, date(2024, 2, 29))
assert iso(occurrences(date(2024, 2, 29), r, date(2028, 12, 31))) == ["2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]
assert describe(r, date(2024, 2, 29)) == "jährlich am 29.02."
assert iso(occurrences(date(2026, 12, 15), parse_rule("monthly", 2, 3, None, TUE), None)) == ["2026-12-15", "2027-02-15", "2027-04-15"]
assert describe(parse_rule("monthly", None, 3, None, TUE), TUE) == "jeden Monat am 27., 3 Mal"
assert describe(parse_rule("daily", 3, 4, None, TUE), TUE) == "alle 3 Tage, 4 Mal" and describe(parse_rule("daily", None, 5, None, TUE), TUE) == "täglich, 5 Mal"

# 6) Ohne Ende: wöchentlich/monatlich/jährlich ja, täglich nein
for kind in ("weekly", "monthly", "yearly"):
    assert parse_rule(kind, None, None, None, TUE).open_ended
fails("daily", None, None, None, TUE, part="braucht ein Ende")
assert not parse_rule("daily", None, 14, None, TUE).open_ended
# offene Serie wird nur bis zur Grenze ausgelegt (hier ein Jahr)
assert len(occurrences(TUE, parse_rule("weekly", None, None, None, TUE), date(2027, 10, 26))) == 53   # 0 bis 52 Wochen, beide Enden

# 7) Ungültige Eingaben mit lesbarem Satz
fails("manchmal", None, None, None, TUE, part="nicht verstanden")
fails(5, None, None, None, TUE, part="nicht verstanden")
fails("weekly", 0, 3, None, TUE, part="Abstand")
fails("weekly", 53, 3, None, TUE, part="Abstand")
fails("weekly", True, 3, None, TUE, part="Abstand")
fails("weekly", "x", 3, None, TUE, part="Abstand")
fails("daily", 61, 3, None, TUE, part="Abstand")
fails("weekly", None, 101, None, TUE, part="Anzahl")
fails("weekly", None, -2, None, TUE, part="Anzahl")
fails("weekly", None, "viele", None, TUE, part="Anzahl")
fails("weekly", None, True, None, TUE, part="Anzahl")
fails("weekly", None, None, "morgen", TUE, part="Enddatum")
fails("weekly", None, None, "2026-02-30", TUE, part="Enddatum")
fails("weekly", None, None, "2026-10-26", TUE, part="vor dem ersten")
fails("weekly", None, None, 20261231, TUE, part="Enddatum")
assert parse_rule("weekly", None, 0, None, TUE).count is None and parse_rule("weekly", None, "none", "null", TUE).open_ended

# 8) Gespeicherte Regeln: Rundreise und kaputte Dateien
r = parse_rule("weekly", 2, 8, "2026-12-31", TUE)
assert Rule.from_dict(r.to_dict()) == r
for broken in (None, [], {}, {"freq": "x"}, {"freq": "weekly", "interval": 0}, {"freq": "daily"}, {"freq": "weekly", "count": "abc"},
               {"freq": "weekly", "until": "kaputt"}, "text", 5):
    assert Rule.from_dict(broken) is None, broken

# 9) Hilfsfunktionen: finished, occurrence, Grenze nach vorne
r = parse_rule("weekly", None, 3, None, TUE)
assert not finished(r, 2) and finished(r, 3) and not finished(Rule("weekly", 1, None, date(2026, 11, 3)), 5, date(2026, 11, 3))
assert finished(Rule("weekly", 1, None, date(2026, 11, 3)), 5, date(2026, 11, 4))
assert occurrence(TUE, r, 0) == TUE and occurrence(TUE, r, 2) == date(2026, 11, 10)
assert limit_date(date(2026, 10, 22)) == date(2031, 10, 22) and limit_date(date(2024, 2, 29)) == date(2029, 2, 28)
# Sicherheitsgrenze: eine falsch gebaute offene tägliche Regel läuft nicht endlos
assert len(occurrences(TUE, Rule("daily", 1, None, None))) <= recurrence.MAX_OCCURRENCES * 10 + 1

print("ALL TESTS PASSED")
