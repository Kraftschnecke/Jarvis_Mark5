"""Gym-Plan (Etappe G): Plan pruefen, Offday, Eintraege, "besser" = neues Ziel, Korrekturen, Grenzen."""
import json
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import gym
from gym import GymError, GymStore

tmp = Path(tempfile.mkdtemp())
TODAY = [date(2026, 11, 24)]                                   # ein Dienstag
store = GymStore(tmp / "gym.json", today=lambda: TODAY[0])


def refused(call, part=""):
    try:
        call()
    except GymError as error:
        assert part in str(error), (part, str(error))
        return
    raise AssertionError("GymError erwartet: " + part)


def ex(name, weight=60, sets=3, reps=8, **extra):
    return dict({"name": name, "weight": weight, "sets": sets, "reps": reps}, **extra)


# 1) Ohne Plan: alles Offday, kein Gym-Ziel
plan = store.get_plan()
assert plan["has_plan"] is False and [d["label"] for d in plan["days"]][:2] == ["Montag", "Dienstag"] and all(d["offday"] and d["name"] == "Offday" for d in plan["days"])
assert store.goal_text() is None and store.has_plan() is False
view = store.today_view()
assert view["has_plan"] is False and view["offday"] and view["label"] == "Dienstag" and view["total"] == 0

# 2) Plan speichern: Tag mit Uebungen = Training; nur Name = Training; "Offday"/"Ruhetag" als Name = Offday; leer = Offday
plan = store.set_plan([
    {"weekday": 0, "name": "Push", "exercises": [ex("Bankdrücken", 60), ex("Schulterdrücken", 30, 3, 10)]},
    {"weekday": 1, "name": "Pull", "exercises": [ex("Klimmzüge", 0, 4, 6), ex("Rudern", 50.5)]},
    {"weekday": 2, "name": "Ruhetag", "exercises": []},
    {"weekday": 3, "name": "Cardio", "exercises": []},
    {"weekday": 4, "name": "", "exercises": [ex("Kniebeugen", 80, 5, 5)]},
])
days = {d["weekday"]: d for d in plan["days"]}
assert plan["has_plan"] and days[0]["name"] == "Push" and not days[0]["offday"] and len(days[0]["exercises"]) == 2
assert days[2]["offday"] and days[3]["name"] == "Cardio" and not days[3]["offday"] and days[3]["exercises"] == []
assert days[4]["name"] == "Training" and days[5]["offday"] and days[6]["offday"]
ids = [e["id"] for d in plan["days"] for e in d["exercises"]]
assert len(ids) == 5 and len(set(ids)) == 5 and all(i.isalnum() and len(i) <= 16 for i in ids)
assert days[1]["exercises"][1]["weight"] == 50.5 and days[1]["exercises"][0]["weight"] == 0
assert store.goal_text() == "Gym: Pull" and store.goal_text(date(2026, 11, 25)) == "Gym: Offday" and store.goal_text(date(2026, 11, 23)) == "Gym: Push"
assert store.goal_text(date(2026, 11, 27)) == "Gym: Training" and store.has_plan()

# 3) Plan wird streng geprueft (nichts wird still umgebogen); IDs bleiben, wenn man den Plan wieder speichert
for bad, part in (
        ("x", "sieben"), ([{}] * 8, "sieben"), ([{"weekday": 7}], "Wochentag"), ([{"weekday": -1}], "Wochentag"), ([{"weekday": True}], "Wochentag"),
        ([{"weekday": "1"}], "Wochentag"), ([{"weekday": 1}, {"weekday": 1}], "Wochentag"), (["x"], "Wochentag"),
        ([{"weekday": 1, "exercises": "x"}], "Übungen"),
        ([{"weekday": 1, "exercises": [ex("A", sets=0)]}], "Sätze"), ([{"weekday": 1, "exercises": [ex("A", sets=21)]}], "Sätze"),
        ([{"weekday": 1, "exercises": [ex("A", sets=2.5)]}], "ganze Zahl"), ([{"weekday": 1, "exercises": [ex("A", reps=0)]}], "Wiederholungen"),
        ([{"weekday": 1, "exercises": [ex("A", reps=101)]}], "Wiederholungen"), ([{"weekday": 1, "exercises": [ex("A", weight=-1)]}], "Gewicht"),
        ([{"weekday": 1, "exercises": [ex("A", weight=1001)]}], "Gewicht"), ([{"weekday": 1, "exercises": [ex("A", weight=float("nan"))]}], "Zahl"),
        ([{"weekday": 1, "exercises": [ex("A", weight=float("inf"))]}], "Zahl"), ([{"weekday": 1, "exercises": [ex("A", weight="60")]}], "Zahl"),
        ([{"weekday": 1, "exercises": [ex("A", weight=True)]}], "Zahl"), ([{"weekday": 1, "exercises": [ex("   ")]}], "Namen"),
        ([{"weekday": 1, "exercises": [ex(5)]}], "Namen"), ([{"weekday": 1, "exercises": ["x"]}], "Ungültige Übung"),
        ([{"weekday": 1, "exercises": [ex(f"U{i}") for i in range(13)]}], "Höchstens 12")):
    refused(lambda: store.set_plan(bad), part)
assert [e["name"] for e in store.get_plan()["days"][1]["exercises"]] == ["Klimmzüge", "Rudern"]       # der alte Plan ist unveraendert
again = store.set_plan([{"weekday": d["weekday"], "name": d["name"], "exercises": d["exercises"]} for d in plan["days"]])
assert [e["id"] for d in again["days"] for e in d["exercises"]] == ids
assert len(store.set_plan([{"weekday": 0, "name": "x" * 99, "exercises": [ex("N" * 200, note="n" * 200)]}])["days"][0]["name"]) == gym.MAX_DAY_NAME
only = store.get_plan()["days"][0]["exercises"][0]
assert len(only["name"]) == gym.MAX_NAME and len(only["note"]) == gym.MAX_NOTE
clean = store.set_plan([{"weekday": 0, "name": "Pu\x00sh\n‮", "exercises": [dict(ex("Ban\x07k\x1b"), id="a/b", evil="x", sets=3)]}])
assert clean["days"][0]["name"] == "Push" and clean["days"][0]["exercises"][0]["name"] == "Bank" and "evil" not in clean["days"][0]["exercises"][0]
assert clean["days"][0]["exercises"][0]["id"].isalnum()                                              # unbrauchbare ID: neue
assert store.set_plan([])["has_plan"] is False

# 4) Heute-Ansicht: richtiger Wochentag, Uebungen mit Ziel; (ab hier ein fester Plan)
plan = store.set_plan([
    {"weekday": 1, "name": "Pull", "exercises": [ex("Klimmzüge", 0, 4, 6), ex("Rudern", 50, 3, 8)]},
    {"weekday": 2, "name": "Push", "exercises": [ex("Bankdrücken", 60, 3, 8)]},
])
pull = {e["name"]: e["id"] for e in plan["days"][1]["exercises"]}
push = {e["name"]: e["id"] for e in plan["days"][2]["exercises"]}
view = store.today_view()
assert view["name"] == "Pull" and not view["offday"] and view["total"] == 2 and view["logged"] == 0 and view["label"] == "Dienstag"
assert [e["name"] for e in view["exercises"]] == ["Klimmzüge", "Rudern"] and view["exercises"][0]["today"] is None and view["exercises"][0]["last"] is None
assert store.today_view(date(2026, 11, 26))["offday"] and store.today_view(date(2026, 11, 26))["exercises"] == []

# 5) Eintragen: Pruefungen
rows = pull["Rudern"]
for call, part in (
        (lambda: store.log("gibtsnicht", 50, [8, 8, 8]), "nicht im Plan"), (lambda: store.log(5, 50, [8]), "gibt es nicht"),
        (lambda: store.log(push["Bankdrücken"], 60, [8, 8, 8]), "nicht im Plan"),                              # Uebung eines anderen Tages
        (lambda: store.log(rows, -1, [8]), "Gewicht"), (lambda: store.log(rows, "50", [8]), "Zahl"), (lambda: store.log(rows, True, [8]), "Zahl"),
        (lambda: store.log(rows, float("nan"), [8]), "Zahl"), (lambda: store.log(rows, 50, []), "Satz"), (lambda: store.log(rows, 50, "8"), "Wiederholungen"),
        (lambda: store.log(rows, 50, [8] * 21), "Satz"), (lambda: store.log(rows, 50, [8, -1]), "Wiederholungen"),
        (lambda: store.log(rows, 50, [8, 101]), "Wiederholungen"), (lambda: store.log(rows, 50, [8, 7.5]), "ganze Zahl"), (lambda: store.log(rows, 50, [True]), "Zahl"),
        (lambda: store.log(rows, 50, [8], day=date(2026, 11, 25)), "Nachtragen"),                              # Zukunft
        (lambda: store.log(rows, 50, [8], day=date(2026, 11, 16)), "Nachtragen"),                              # 8 Tage zurueck
        (lambda: store.log(rows, 50, [8], day="2026-11-24"), "Nachtragen")):
    refused(call, part)
assert store.today_view()["logged"] == 0

# 6) "Besser" = in allen drei Werten mindestens gleich, in einem mehr
goal = {"weight": 50, "sets": 3, "reps": 8}
cases = [
    (50, [8, 8, 8], False),            # genau das Ziel
    (52.5, [8, 8, 8], True),           # schwerer
    (50, [8, 8, 9], False),            # ein Satz mehr Wiederholungen, aber der kleinste bleibt 8
    (50, [9, 9, 9], True),             # alle Saetze mehr Wiederholungen
    (50, [8, 8, 8, 8], True),          # ein Satz mehr
    (50, [8, 8], False),               # ein Satz weniger
    (50, [8, 8, 7], False),            # ein Satz schwaecher
    (47.5, [10, 10, 10], False),       # leichter, auch bei mehr Wiederholungen
    (55, [8, 8, 7], False),            # schwerer, aber ein Satz schwaecher
    (55, [6, 6, 6, 6], False),         # schwerer, mehr Saetze, aber weniger Wiederholungen
    (55, [9, 9, 9, 9], True),          # in allem mehr
    (50, [0, 0, 0], False),
]
for weight, reps, expected in cases:
    got = GymStore.improvement(goal, [{"weight": weight, "reps": r} for r in reps])
    assert (got is not None) is expected, (weight, reps, expected, got)
    if expected:
        assert got == {"weight": weight, "sets": len(reps), "reps": min(reps)}, got

# Saetze mit verschiedenen Gewichten: 100 kg x 6, dann 96 kg x 8
imp = lambda g, sets: GymStore.improvement(g, [{"weight": w, "reps": r} for w, r in sets])
assert imp({"weight": 100, "sets": 1, "reps": 5}, [(100, 6), (96, 8)]) == {"weight": 100, "sets": 1, "reps": 6}
assert imp({"weight": 96, "sets": 2, "reps": 6}, [(100, 6), (96, 8)]) is None                                    # genau das Ziel (beide Saetze zaehlen ab 96 kg)
assert imp({"weight": 96, "sets": 2, "reps": 5}, [(100, 6), (96, 8)]) == {"weight": 96, "sets": 2, "reps": 6}      # beide Saetze zaehlen ab 96 kg, kleinste Wdh. 6
assert imp({"weight": 96, "sets": 2, "reps": 6}, [(100, 5), (96, 8)]) is None                                     # 100 x 5 reicht nicht fuer 6 Wdh.
assert imp({"weight": 100, "sets": 2, "reps": 6}, [(100, 6), (96, 8)]) is None                                    # nur ein Satz mit 100 kg
assert imp({"weight": 50, "sets": 2, "reps": 5}, [(60, 5), (55, 8), (50, 8)]) == {"weight": 55, "sets": 2, "reps": 5}      # mehrere Stufen sind besser: die mit dem hoechsten Gewicht
assert imp({"weight": 50, "sets": 3, "reps": 8}, [(52.5, 8), (50, 8), (50, 8)]) is None                          # gleiche Stufe wie das Ziel
assert imp({"weight": 50, "sets": 3, "reps": 8}, [(52.5, 9), (52.5, 9), (50, 8), (50, 8)]) == {"weight": 50, "sets": 4, "reps": 8}
assert imp({"weight": 50, "sets": 3, "reps": 8}, [(55, 8), (55, 8), (55, 8)]) == {"weight": 55, "sets": 3, "reps": 8}

# 7) Eintrag speichern, Ergebnis, Ziel waechst mit
r = store.log(rows, 50, [8, 8, 7])
assert r["improved"] is False and r["goal"] == {"weight": 50, "sets": 3, "reps": 8} and r["entry"]["sets"] == [{"weight": 50, "reps": 8}, {"weight": 50, "reps": 8}, {"weight": 50, "reps": 7}] and "improved" not in r["entry"]
view = store.today_view()
assert view["logged"] == 1 and view["exercises"][1]["today"]["sets"][2]["reps"] == 7
r = store.log(rows, 52.5, [8, 8, 8])                                                      # Korrektur am selben Tag, jetzt besser
assert r["improved"] and r["goal"] == {"weight": 52.5, "sets": 3, "reps": 8} and r["entry"]["goal_before"] == {"weight": 50, "sets": 3, "reps": 8} and r["entry"]["goal_after"] == {"weight": 52.5, "sets": 3, "reps": 8}
assert store.today_view()["exercises"][1]["weight"] == 52.5 and store.today_view()["logged"] == 1
r = store.log(rows, 50, [8, 8, 8])                                                         # nochmal korrigiert: schlechter -> Ziel zurueck auf 50
assert r["improved"] is False and store.today_view()["exercises"][1]["weight"] == 50
store.log(rows, 52.5, [9, 9, 9])
assert store.today_view()["exercises"][1]["weight"] == 52.5 and store.today_view()["exercises"][1]["reps"] == 9
assert store.clear_log(rows) is True and store.today_view()["exercises"][1]["weight"] == 50 and store.today_view()["exercises"][1]["reps"] == 8
assert store.today_view()["logged"] == 0 and store.clear_log(rows) is False and store.clear_log("nix") is False and store.clear_log(5) is False

# 8) Mehrere Tage: das letzte Mal; ein spaeterer Fortschritt wird beim Loeschen eines frueheren Eintrags nicht zurueckgedreht
TODAY[0] = date(2026, 11, 24)
store.log(rows, 52.5, [8, 8, 8])                              # Dienstag: Ziel 52.5
TODAY[0] = date(2026, 12, 1)                                  # eine Woche spaeter, wieder Dienstag
view = store.today_view()
assert view["exercises"][1]["weight"] == 52.5 and view["exercises"][1]["last"] == {"date": "2026-11-24", "sets": [{"weight": 52.5, "reps": 8}] * 3}
store.log(rows, 55, [8, 8, 8])                                # Ziel 55
assert store.today_view()["exercises"][1]["weight"] == 55
# der Eintrag vom 24.11. ist genau 7 Tage her: loeschen geht, aber das Ziel (jetzt 55) bleibt, weil es nicht mehr der damalige Stand ist
assert store.clear_log(rows, day=date(2026, 11, 24)) is True and store.today_view()["exercises"][1]["weight"] == 55
refused(lambda: store.clear_log(rows, day=date(2026, 11, 23)), "Tage zurück")                    # 8 Tage zurueck geht nicht
assert store.today_view()["exercises"][1]["last"] is None

# 9) Gestern nachtragen zaehlt zum Wochentag von gestern (nur dessen Uebungen)
TODAY[0] = date(2026, 12, 3)                                                              # Donnerstag
yesterday = date(2026, 12, 2)                                                             # Mittwoch = Push
r = store.log(push["Bankdrücken"], 62.5, [8, 8, 8], day=yesterday)
assert r["improved"] and store.today_view(yesterday)["exercises"][0]["today"]["sets"][0]["weight"] == 62.5
refused(lambda: store.log(pull["Rudern"], 50, [8], day=yesterday), "nicht im Plan")        # Rudern ist ein Pull-Tag (Dienstag)
assert store.today_view()["offday"]                                                       # heute (Donnerstag) ist Offday

# 10) Dauerhaft und robust: neu laden, kaputte Datei, fremde Eintraege werden beim Lesen bereinigt
fresh = GymStore(tmp / "gym.json", today=lambda: TODAY[0])
assert fresh.get_plan() == store.get_plan() and fresh.today_view(yesterday)["exercises"][0]["today"]["sets"][0]["weight"] == 62.5
(tmp / "kaputt.json").write_text("{nicht json", encoding="utf-8")
assert GymStore(tmp / "kaputt.json").get_plan()["has_plan"] is False
(tmp / "fremd.json").write_text(json.dumps({"plan": {"0": {"name": "X", "exercises": [{"name": "A", "weight": "viel", "sets": 3, "reps": 8}, {"name": "B", "weight": 5, "sets": 3, "reps": 8}]},
                                                "9": {"name": "Z", "exercises": []}, "1": "x"},
                                            "logs": {"kein-datum": {"entries": {"a": {"weight": 1, "reps": [1]}}},
                                                     "2026-11-30": {"day": "X", "entries": {"b": {"name": "B", "weight": 5, "reps": [8, "x"]},
                                                                                              "c": {"name": "C", "weight": 5, "reps": [8, 8]}}}}}), encoding="utf-8")
other = GymStore(tmp / "fremd.json", today=lambda: date(2026, 12, 1))
plan = other.get_plan()
assert [e["name"] for e in plan["days"][0]["exercises"]] == ["B"] and plan["days"][1]["offday"] and plan["has_plan"]
assert json.loads((tmp / "gym.json").read_text(encoding="utf-8"))["plan"]
assert not (tmp / "gym.tmp").exists()

# 11) Gleichzeitiges Eintragen geht nicht verloren
TODAY[0] = date(2026, 12, 1)
many = store.set_plan([{"weekday": 1, "name": "Pull", "exercises": [ex(f"Übung {i}") for i in range(10)]}])
exercise_ids = [e["id"] for e in many["days"][1]["exercises"]]
threads = [threading.Thread(target=lambda eid=eid: store.log(eid, 20, [10, 10, 10])) for eid in exercise_ids]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert store.today_view()["logged"] == 10

# 12) Saetze mit eigenem Gewicht eintragen (100 kg x 6, dann 96 kg x 8) und Korrektur
TODAY[0] = date(2026, 12, 1)
mixed = store.set_plan([{"weekday": 1, "name": "Pull", "exercises": [ex("Bank", 100, 1, 5)]}])
bank = mixed["days"][1]["exercises"][0]["id"]
r = store.log(bank, sets=[{"weight": 100, "reps": 6}, {"weight": 96, "reps": 8}])
assert r["improved"] and r["goal"] == {"weight": 100, "sets": 1, "reps": 6}
assert r["entry"]["sets"] == [{"weight": 100, "reps": 6}, {"weight": 96, "reps": 8}] and r["entry"]["goal_after"] == r["goal"]
assert store.today_view()["exercises"][0]["today"]["sets"][1] == {"weight": 96, "reps": 8}
r = store.log(bank, sets=[{"weight": 100, "reps": 4}, {"weight": 96, "reps": 8}])          # korrigiert: schlechter, Ziel zurueck
assert r["improved"] is False and store.today_view()["exercises"][0]["weight"] == 100 and store.today_view()["exercises"][0]["reps"] == 5
for bad, part in (([], "Satz"), ("x", "Satz"), ([{"weight": 100}], "Zahl"), ([{"weight": 100, "reps": 5.5}], "ganze Zahl"), ([{"weight": -1, "reps": 5}], "Gewicht"),
                  ([{"weight": 100, "reps": 101}], "Wiederholungen"), (["x"], "Ungültiger Satz"), ([{"weight": 100, "reps": 5}] * 21, "Satz"),
                  ([{"weight": True, "reps": 5}], "Zahl"), ([{"weight": 100, "reps": True}], "Zahl")):
    refused(lambda: store.log(bank, sets=bad), part)
assert store.today_view()["exercises"][0]["today"]["sets"][0]["reps"] == 4                  # Fehlversuche aendern nichts
store.log(bank, sets=[{"weight": 102.5, "reps": 5}])
assert store.today_view()["exercises"][0]["weight"] == 102.5 and store.clear_log(bank) and store.today_view()["exercises"][0]["weight"] == 100

# 13) Aelteres Dateiformat (ein Gewicht + Wiederholungen je Satz) wird gelesen; kaputte Saetze fallen weg
legacy = tmp / "legacy.json"
legacy.write_text(json.dumps({"plan": {"1": {"name": "Pull", "exercises": [{"id": "x1", "name": "Rudern", "weight": 55, "sets": 3, "reps": 8}]}},
                              "logs": {"2026-11-24": {"day": "Pull", "entries": {"x1": {"name": "Rudern", "weight": 55, "reps": [8, 8, 8], "improved": True,
                                                                                         "goal_before": {"weight": 52.5, "sets": 3, "reps": 8}}},
                                                                 "bad": {"name": "B", "sets": [{"weight": "x", "reps": 5}]}}}}), encoding="utf-8")
old = GymStore(legacy, today=lambda: date(2026, 12, 1)).today_view(date(2026, 12, 1))
assert old["exercises"][0]["last"] == {"date": "2026-11-24", "sets": [{"weight": 55, "reps": 8}] * 3}
fresh = GymStore(legacy, today=lambda: date(2026, 11, 24))
assert fresh.today_view()["exercises"][0]["today"]["improved"] is True and fresh.today_view()["exercises"][0]["today"]["goal_after"] == {"weight": 55, "sets": 3, "reps": 8}
assert "bad" not in fresh.today_view()["exercises"][0]["today"]["name"]

print("ALL TESTS PASSED")
