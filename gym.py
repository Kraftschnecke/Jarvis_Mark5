"""Gym-Plan (Etappe G): ein Wochenplan mit Ziel je Uebung: Gewicht (kg, 0 = Koerpergewicht), Saetze, Wiederholungen je Satz.
Eintrag: eine Liste von Saetzen, jeder mit eigenem Gewicht und eigenen Wiederholungen (100 kg x 6, dann 96 kg x 8).
Besser als das Ziel: fuer jedes vorkommende Gewicht w zaehlt "alle Saetze mit mindestens w kg" als Stufe
(w, Anzahl dieser Saetze, kleinste Wiederholungszahl darunter). Ist eine Stufe in allen drei Werten mindestens so gut wie das Ziel
und in einem besser, wird die beste solche Stufe (hoechstes Gewicht zuerst) das neue Ziel (der Code rechnet das, nicht die KI).
Bei gleichem Gewicht in allen Saetzen ist das genau die einfache Regel (Gewicht, Saetze, kleinste Wiederholung).
Wird ein Eintrag am selben Tag korrigiert oder geloescht, geht das Ziel erst auf den alten Stand zurueck (wenn es noch der damals
gesetzte Stand ist) und wird dann neu verglichen.

Alle Texte aus dem Plan werden nur bereinigt und nie als Anweisung gelesen.
"""

import json
import math
import os
import secrets
import threading
from datetime import date, timedelta
from pathlib import Path

MAX_EXERCISES = 12
MAX_NAME = 60
MAX_DAY_NAME = 30
MAX_NOTE = 80
MAX_WEIGHT = 1000.0
MAX_SETS = 20
MAX_REPS = 100
LOG_KEEP_DAYS = 365
LOG_BACK_DAYS = 7                       # nachtragen darf man hoechstens eine Woche rueckwirkend
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
OFF_WORDS = {"offday", "off day", "off", "ruhetag", "pause", "frei", "rest", "restday", "rest day"}
OFFDAY = "Offday"
GOAL_PREFIX = "Gym: "

_LOCK = threading.RLock()


class GymError(ValueError):
    """Meldung, die man dem Nutzer zeigen darf."""


def _clean_text(value, limit):
    if not isinstance(value, str):
        return ""
    text = " ".join("".join(ch for ch in value if ch.isprintable() or ch == " ").split())
    return text[:limit]


def _number(value, what, low, high, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GymError(f"{what}: bitte eine Zahl.")
    if isinstance(value, float) and not math.isfinite(value):
        raise GymError(f"{what}: bitte eine Zahl.")
    if whole and (isinstance(value, float) and not value.is_integer()):
        raise GymError(f"{what}: bitte eine ganze Zahl.")
    if not low <= value <= high:
        raise GymError(f"{what}: von {low:g} bis {high:g}.")
    return int(value) if whole else round(float(value), 2)


def is_off_name(name):
    return _clean_text(name, MAX_DAY_NAME).casefold() in OFF_WORDS


def _weekday_name(day):
    return WEEKDAYS[day.weekday()]


class GymStore:
    def __init__(self, path="gym.json", today=date.today):
        self.path = Path(path)
        self.today = today
        self._lock = _LOCK

    # ---- Datei
    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"plan": {}, "logs": {}}
        if not isinstance(data, dict):
            return {"plan": {}, "logs": {}}
        return {"plan": self._clean_plan(data.get("plan")), "logs": self._clean_logs(data.get("logs"))}

    def _save(self, data):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- Bereinigen (gilt fuer Gelesenes und Geschriebenes)
    @staticmethod
    def _clean_exercise(item, strict=False):
        """Eine Uebung oder None. strict=True: Fehler mit Meldung statt stillem Weglassen."""
        try:
            if not isinstance(item, dict):
                raise GymError("Ungültige Übung.")
            name = _clean_text(item.get("name"), MAX_NAME)
            if not name:
                raise GymError("Eine Übung braucht einen Namen.")
            exercise_id = item.get("id")
            if not isinstance(exercise_id, str) or not exercise_id or len(exercise_id) > 16 or not exercise_id.isalnum():
                exercise_id = secrets.token_hex(4)
            return {"id": exercise_id, "name": name,
                    "weight": _number(item.get("weight", 0), f"{name}, Gewicht", 0, MAX_WEIGHT),
                    "sets": _number(item.get("sets", 3), f"{name}, Sätze", 1, MAX_SETS, whole=True),
                    "reps": _number(item.get("reps", 8), f"{name}, Wiederholungen", 1, MAX_REPS, whole=True),
                    "note": _clean_text(item.get("note", ""), MAX_NOTE)}
        except GymError:
            if strict:
                raise
            return None

    @classmethod
    def _clean_plan(cls, plan, strict=False):
        """{"0": {"name": "Push", "exercises": [...]}, ...} - nur Wochentage 0..6, nur gueltige Uebungen."""
        clean = {}
        source = plan if isinstance(plan, dict) else {}
        for key in map(str, range(7)):
            day = source.get(key)
            if not isinstance(day, dict):
                continue
            exercises, seen = [], set()
            for item in day.get("exercises") if isinstance(day.get("exercises"), list) else []:
                exercise = cls._clean_exercise(item, strict)
                if exercise is not None and exercise["id"] not in seen:
                    seen.add(exercise["id"])
                    exercises.append(exercise)
            if strict and isinstance(day.get("exercises"), list) and len(day["exercises"]) > MAX_EXERCISES:
                raise GymError(f"Höchstens {MAX_EXERCISES} Übungen pro Tag.")
            name = _clean_text(day.get("name"), MAX_DAY_NAME)
            if exercises or (name and not is_off_name(name)):
                clean[key] = {"name": name or "Training", "exercises": exercises[:MAX_EXERCISES]}
        return clean

    @staticmethod
    def _clean_sets(value):
        """Liste von {"weight", "reps"} (1 bis MAX_SETS Saetze) oder None."""
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_SETS:
            return None
        sets = []
        for item in value:
            if not isinstance(item, dict) or isinstance(item.get("reps"), bool) or not isinstance(item.get("reps"), int) \
                    or not 0 <= item["reps"] <= MAX_REPS:
                return None
            try:
                sets.append({"weight": _number(item.get("weight", 0), "Gewicht", 0, MAX_WEIGHT), "reps": item["reps"]})
            except GymError:
                return None
        return sets

    @staticmethod
    def _clean_goal(value):
        if not isinstance(value, dict):
            return None
        try:
            return {"weight": _number(value.get("weight"), "x", 0, MAX_WEIGHT),
                    "sets": _number(value.get("sets"), "x", 1, MAX_SETS, whole=True),
                    "reps": _number(value.get("reps"), "x", 1, MAX_REPS, whole=True)}
        except GymError:
            return None

    @classmethod
    def _clean_logs(cls, logs):
        clean = {}
        for day, entry in (logs if isinstance(logs, dict) else {}).items():
            if not _valid_date(day) or not isinstance(entry, dict) or not isinstance(entry.get("entries"), dict):
                continue
            entries = {}
            for exercise_id, result in entry["entries"].items():
                if not isinstance(exercise_id, str) or len(exercise_id) > 16 or not isinstance(result, dict):
                    continue
                sets = cls._clean_sets(result.get("sets"))
                if sets is None and isinstance(result.get("reps"), list):          # aelteres Format: ein Gewicht, Wiederholungen je Satz
                    sets = cls._clean_sets([{"weight": result.get("weight", 0), "reps": r} for r in result["reps"]])
                if sets is None:
                    continue
                item = {"name": _clean_text(result.get("name"), MAX_NAME), "sets": sets}
                before = cls._clean_goal(result.get("goal_before"))
                if result.get("improved") is True and before is not None:
                    after = cls._clean_goal(result.get("goal_after")) or cls.improvement(before, sets)
                    if after is not None:
                        item.update({"improved": True, "goal_before": before, "goal_after": after})
                entries[exercise_id] = item
            if entries:
                clean[day] = {"day": _clean_text(entry.get("day"), MAX_DAY_NAME), "entries": entries}
        return {day: clean[day] for day in sorted(clean)[-LOG_KEEP_DAYS:]}

    # ---- Plan
    def get_plan(self):
        """Alle sieben Tage in Reihenfolge: {"weekday", "label", "name", "offday", "exercises"}."""
        with self._lock:
            plan = self._load()["plan"]
        return {"days": [self._day_view(plan, index) for index in range(7)], "has_plan": bool(plan)}

    @staticmethod
    def _day_view(plan, index):
        day = plan.get(str(index))
        return {"weekday": index, "label": WEEKDAYS[index], "name": day["name"] if day else OFFDAY,
                "offday": day is None, "exercises": [dict(e) for e in day["exercises"]] if day else []}

    def set_plan(self, days):
        """Den ganzen Plan ersetzen. days: Liste von {"weekday": 0..6, "name", "exercises": [...]}. Wirft GymError."""
        if not isinstance(days, list) or len(days) > 7:
            raise GymError("Der Plan hat höchstens sieben Tage.")
        source, seen = {}, set()
        for day in days:
            if not isinstance(day, dict) or isinstance(day.get("weekday"), bool) or not isinstance(day.get("weekday"), int) \
                    or not 0 <= day["weekday"] <= 6 or day["weekday"] in seen:
                raise GymError("Ungültiger Wochentag im Plan.")
            seen.add(day["weekday"])
            if not isinstance(day.get("exercises", []), list):
                raise GymError("Ungültige Übungen.")
            source[str(day["weekday"])] = {"name": day.get("name", ""), "exercises": day.get("exercises", [])}
        plan = self._clean_plan(source, strict=True)
        with self._lock:
            data = self._load()
            data["plan"] = plan
            self._save(data)
        return self.get_plan()

    def has_plan(self):
        with self._lock:
            return bool(self._load()["plan"])

    # ---- Heute
    def today_view(self, day=None):
        """Der Tag mit Zielen, dem letzten Mal und dem heutigen Eintrag je Uebung."""
        day = day or self.today()
        with self._lock:
            data = self._load()
        plan, logs = data["plan"], data["logs"]
        view = self._day_view(plan, day.weekday())
        today_entries = logs.get(day.isoformat(), {}).get("entries", {})
        for exercise in view["exercises"]:
            exercise["today"] = today_entries.get(exercise["id"])
            exercise["last"] = self._last_result(logs, exercise["id"], day)
        done = sum(1 for e in view["exercises"] if e["today"])
        return {"date": day.isoformat(), "has_plan": bool(plan), "weekday": day.weekday(), "label": WEEKDAYS[day.weekday()],
                "name": view["name"], "offday": view["offday"], "exercises": view["exercises"],
                "logged": done, "total": len(view["exercises"])}

    @staticmethod
    def _last_result(logs, exercise_id, before):
        """Der letzte Eintrag dieser Uebung vor diesem Tag: {"date", "weight", "reps"} oder None."""
        for key in sorted(logs, reverse=True):
            if key < before.isoformat() and exercise_id in logs[key]["entries"]:
                entry = logs[key]["entries"][exercise_id]
                return {"date": key, "sets": entry["sets"]}
        return None

    def goal_text(self, day=None):
        """Text des Tagesziels ("Gym: Push", "Gym: Offday") oder None, wenn es noch keinen Plan gibt."""
        day = day or self.today()
        with self._lock:
            plan = self._load()["plan"]
        if not plan:
            return None
        entry = plan.get(str(day.weekday()))
        return GOAL_PREFIX + (entry["name"] if entry else OFFDAY)

    def goal_info(self, day=None):
        """(Text, offday) des Tagesziels oder None, wenn es noch keinen Plan gibt."""
        day = day or self.today()
        with self._lock:
            plan = self._load()["plan"]
        if not plan:
            return None
        entry = plan.get(str(day.weekday()))
        return GOAL_PREFIX + (entry["name"] if entry else OFFDAY), entry is None

    # ---- Eintragen
    @staticmethod
    def improvement(goal, sets):
        """Das neue Ziel {"weight", "sets", "reps"}, wenn dieser Eintrag besser ist als das Ziel, sonst None."""
        target = (goal["weight"], goal["sets"], goal["reps"])
        best = None
        for weight in {s["weight"] for s in sets}:
            group = [s for s in sets if s["weight"] >= weight]
            level = (weight, len(group), min(s["reps"] for s in group))
            if level != target and all(a >= b for a, b in zip(level, target)) and (best is None or level > best):
                best = level
        return None if best is None else {"weight": best[0], "sets": best[1], "reps": best[2]}

    @staticmethod
    def _entry_sets(weight, reps, sets):
        """Aus der Eingabe die Saetze machen: entweder `sets` (je Satz Gewicht und Wiederholungen) oder ein Gewicht mit Wiederholungen je Satz."""
        if sets is None:
            if not isinstance(reps, list):
                raise GymError(f"Trage die Wiederholungen jedes Satzes ein (1 bis {MAX_SETS} Sätze).")
            sets = [{"weight": weight, "reps": r} for r in reps]
        if not isinstance(sets, list) or not 1 <= len(sets) <= MAX_SETS:
            raise GymError(f"Trage jeden Satz ein (1 bis {MAX_SETS} Sätze).")
        clean = []
        for item in sets:
            if not isinstance(item, dict):
                raise GymError("Ungültiger Satz.")
            clean.append({"weight": _number(item.get("weight"), "Gewicht", 0, MAX_WEIGHT),
                          "reps": _number(item.get("reps"), "Wiederholungen", 0, MAX_REPS, whole=True)})
        return clean

    def _check_day(self, day, what):
        today = self.today()
        day = day or today
        if not isinstance(day, date) or day > today or day < today - timedelta(days=LOG_BACK_DAYS):
            raise GymError(f"{what} geht höchstens {LOG_BACK_DAYS} Tage zurück.")
        return day

    @staticmethod
    def _restore_goal(exercise, previous):
        """Ein durch diesen Eintrag gesetztes Ziel zuruecksetzen (nur wenn es noch genau dieser Stand ist)."""
        if previous.get("improved") and all(exercise[k] == previous["goal_after"][k] for k in ("weight", "sets", "reps")):
            exercise.update(previous["goal_before"])

    def log(self, exercise_id, weight=None, reps=None, day=None, sets=None):
        """Eintrag fuer eine Uebung des Tages. Gibt {"entry", "improved", "goal"} zurueck. Wirft GymError."""
        day = self._check_day(day, "Nachtragen")
        if not isinstance(exercise_id, str):
            raise GymError("Diese Übung gibt es nicht.")
        sets = self._entry_sets(weight, reps, sets)
        with self._lock:
            data = self._load()
            plan = data["plan"]
            entry_day = plan.get(str(day.weekday()))
            exercise = next((e for e in entry_day["exercises"] if e["id"] == exercise_id), None) if entry_day else None
            if exercise is None:
                raise GymError("Diese Übung gibt es an diesem Tag nicht im Plan.")
            logs = data["logs"]
            record = logs.setdefault(day.isoformat(), {"day": entry_day["name"], "entries": {}})
            previous = record["entries"].get(exercise_id)
            if previous:                                                    # Korrektur: das Ziel erst zuruecksetzen
                self._restore_goal(exercise, previous)
            goal_before = {k: exercise[k] for k in ("weight", "sets", "reps")}
            result = {"name": exercise["name"], "sets": sets}
            new_goal = self.improvement(goal_before, sets)
            if new_goal is not None:
                result.update({"improved": True, "goal_before": goal_before, "goal_after": new_goal})
                exercise.update(new_goal)
            record["entries"][exercise_id] = result
            self._save({"plan": plan, "logs": self._clean_logs(logs)})
            goal = {k: exercise[k] for k in ("weight", "sets", "reps")}
        return {"entry": result, "improved": new_goal is not None, "goal": goal}

    def clear_log(self, exercise_id, day=None):
        """Einen Eintrag wieder loeschen (ein neues Ziel daraus geht auf den alten Stand zurueck)."""
        day = self._check_day(day, "Das")
        with self._lock:
            data = self._load()
            record = data["logs"].get(day.isoformat())
            previous = record["entries"].pop(exercise_id, None) if record and isinstance(exercise_id, str) else None
            if previous is None:
                return False
            entry_day = data["plan"].get(str(day.weekday()))
            exercise = next((e for e in entry_day["exercises"] if e["id"] == exercise_id), None) if entry_day else None
            if exercise is not None:
                self._restore_goal(exercise, previous)
            self._save({"plan": data["plan"], "logs": self._clean_logs(data["logs"])})
        return True


def _valid_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


_default = None


def default_store():
    global _default
    if _default is None:
        _default = GymStore()
    return _default


def set_default_store(store):
    global _default
    _default = store
