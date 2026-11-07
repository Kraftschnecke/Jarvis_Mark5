"""Widgets der rechten Seitenleiste (Etappe C): Notizen, Tagesziele, Kalender-Termine, Eishockey.

Notizen, Ziele und Termine liegen in widgets.json neben settings.json (nur auf deinem Rechner).
Spielplaene kommen aus dem Netz, und zwar nur ueber den Server: der Browser ruft nie selbst
ins Internet. Ohne Netz zeigt die Seite den letzten bekannten Stand oder eine Meldung.
"""

import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import net_fetch
import recurrence

MAX_NOTES = 5000
MAX_DEVICE_NOTES = 10            # Notizen einzelner Geraete (Handy), eine je Geraet
MAX_DEVICE_NAME = 40
MAX_GOALS = 20
MAX_GOAL_LENGTH = 200
MAX_EVENTS = 500
MAX_EVENT_TITLE = 100
SERIES_HORIZON_DAYS = 365        # Serien ohne Ende werden immer ein Jahr im Voraus ausgelegt
MAX_SERIES = 20
MAX_LABEL = 80
MAX_LISTS = 10
MAX_LIST_ITEMS = 60
MAX_LIST_NAME = 40
MAX_LIST_ITEM = 100
HISTORY_DAYS = 120               # so lange werden erledigte Tagesziele fuer Serien (Streaks) gemerkt
WEEK_DAYS = 7
EVENT_KEEP_DAYS = 31            # Termine, die laenger her sind, werden beim Speichern aufgeraeumt

# Alle Zugriffe auf widgets.json (Seite UND Jarvis-Aufgaben) laufen durch dieses eine Schloss,
# damit sich zwei gleichzeitige Speichervorgaenge nichts ueberschreiben.
_FILE_LOCK = threading.RLock()

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class WidgetStore:
    def __init__(self, path="widgets.json", today=date.today, remote=None):
        self.path = Path(path)
        self.today = today
        self._lock = _FILE_LOCK
        self.remote = remote            # Apple-Kalender (calendar_sync.AppleCalendar) oder None

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data):
        # Erst in eine Nebendatei, dann umbenennen: ein Absturz hinterlaesst keine halbe Datei
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def goal_key(text):
        """Gleiches Ziel trotz anderer Gross-/Kleinschreibung oder Leerzeichen."""
        return " ".join(str(text).casefold().split())

    @staticmethod
    def _clean_history(history):
        """{"2026-11-05": {"fitnessstudio": True}}: nur gueltige Tage, nur Wahrheitswerte, nur die letzten HISTORY_DAYS."""
        clean = {}
        for day, goals in (history if isinstance(history, dict) else {}).items():
            if _valid_date(day) and isinstance(goals, dict):
                clean[day] = {k[:MAX_GOAL_LENGTH]: v for k, v in goals.items() if isinstance(k, str) and isinstance(v, bool)}
        return {day: clean[day] for day in sorted(clean)[-HISTORY_DAYS:]}

    @staticmethod
    def streak(history, key, today):
        """Wie viele Tage in Folge das Ziel erledigt wurde. Heute noch offen: zaehlt ab gestern (die Serie lebt noch)."""
        day = today
        if not history.get(day.isoformat(), {}).get(key):
            day -= timedelta(days=1)
        count = 0
        while count < HISTORY_DAYS and history.get(day.isoformat(), {}).get(key):
            count += 1
            day -= timedelta(days=1)
        return count

    def _week(self, history, items, today):
        """Die letzten 7 Tage (aeltester zuerst): wie viele der taeglichen Ziele erledigt waren. Heute aus der aktuellen Liste."""
        week = []
        for back in range(WEEK_DAYS - 1, -1, -1):
            day = today - timedelta(days=back)
            if back == 0:
                goals = {}
                for g in items:
                    if g["daily"]:
                        key = self.goal_key(g["text"])
                        goals[key] = goals.get(key, False) or g["done"]
            else:
                goals = history.get(day.isoformat(), {})
            week.append({"date": day.isoformat(), "done": sum(1 for v in goals.values() if v), "total": len(goals)})
        return week

    # ---- Listen (Einkauf, Packen, ...; Step 2.30)
    @staticmethod
    def list_key(name):
        """Vergleichsform eines Listennamens: klein, ohne Leerzeichen, ohne Endung "liste" ("Einkaufsliste" -> "einkaufs")."""
        key = "".join(str(name).casefold().split())
        for ending in ("liste", "list"):
            if key.endswith(ending) and len(key) > len(ending):
                return key[:-len(ending)]
        return key

    @classmethod
    def _find_list(cls, lists, name):
        """Die Liste zum Namen: erst genau, sonst der eine Name, der mit dem anderen beginnt (Einkaufsliste ~ Einkauf, Packliste ~ Packen).

        Gibt None zurueck, wenn keiner passt; ValueError, wenn mehrere passen.
        """
        key = cls.list_key(name)
        if not key:
            return None
        exact = [l for l in lists if cls.list_key(l["name"]) == key]
        if exact:
            return exact[0]
        near = [l for l in lists if min(len(key), len(cls.list_key(l["name"]))) >= 4
                and (cls.list_key(l["name"]).startswith(key) or key.startswith(cls.list_key(l["name"])))]
        if len(near) > 1:
            raise ValueError("Welche Liste meinst du: " + ", ".join(l["name"] for l in near) + "?")
        return near[0] if near else None

    @staticmethod
    def _clean_lists(lists):
        clean = []
        for entry in lists if isinstance(lists, list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
                continue
            items = []
            for item in entry.get("items") if isinstance(entry.get("items"), list) else []:
                if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                    items.append({"text": " ".join(item["text"].split())[:MAX_LIST_ITEM], "done": item.get("done") is True})
            clean.append({"name": " ".join(entry["name"].split())[:MAX_LIST_NAME], "items": items[:MAX_LIST_ITEMS]})
        return clean[:MAX_LISTS]

    def set_lists(self, lists):
        """Alle Listen von der Seite ersetzen (strenge Pruefung, wie bei den Zielen)."""
        if not isinstance(lists, list) or len(lists) > MAX_LISTS:
            raise ValueError(f"Höchstens {MAX_LISTS} Listen.")
        clean, keys = [], set()
        for entry in lists:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not isinstance(entry.get("items"), list):
                raise ValueError("Ungültige Liste.")
            name = " ".join(entry["name"].split())
            if not name:
                raise ValueError("Eine Liste braucht einen Namen.")
            if len(name) > MAX_LIST_NAME:
                raise ValueError(f"Ein Listenname darf höchstens {MAX_LIST_NAME} Zeichen lang sein.")
            if self.list_key(name) in keys:
                raise ValueError(f"Die Liste „{name}“ gibt es schon.")
            keys.add(self.list_key(name))
            if len(entry["items"]) > MAX_LIST_ITEMS:
                raise ValueError(f"Höchstens {MAX_LIST_ITEMS} Einträge pro Liste.")
            items = []
            for item in entry["items"]:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not isinstance(item.get("done"), bool):
                    raise ValueError("Ungültiger Eintrag.")
                text = " ".join(item["text"].split())
                if not text:
                    raise ValueError("Ein Eintrag darf nicht leer sein.")
                if len(text) > MAX_LIST_ITEM:
                    raise ValueError(f"Ein Eintrag darf höchstens {MAX_LIST_ITEM} Zeichen lang sein.")
                items.append({"text": text, "done": item["done"]})
            clean.append({"name": name, "items": items})
        with self._lock:
            data = self._load()
            data["lists"] = clean
            self._save(data)

    def add_list_items(self, list_name, items):
        """Einträge auf eine Liste setzen (Jarvis). Die Liste wird angelegt, wenn es sie noch nicht gibt.

        Ein Eintrag, der schon offen auf der Liste steht, kommt nicht doppelt; ein schon abgehakter wird wieder offen.
        Gibt {"list", "created", "added", "already"} zurueck.
        """
        name = " ".join(str(list_name or "").split())
        if not name:
            raise ValueError("Auf welche Liste soll ich das setzen?")
        if len(name) > MAX_LIST_NAME:
            raise ValueError(f"Ein Listenname darf höchstens {MAX_LIST_NAME} Zeichen lang sein.")
        wanted = []
        for text in items if isinstance(items, list) else []:
            text = " ".join(str(text).split())
            if text and text.casefold() not in [w.casefold() for w in wanted]:
                if len(text) > MAX_LIST_ITEM:
                    raise ValueError(f"Ein Eintrag darf höchstens {MAX_LIST_ITEM} Zeichen lang sein.")
                wanted.append(text)
        if not wanted:
            raise ValueError("Was soll ich auf die Liste setzen?")
        with self._lock:
            data = self._load()
            lists = self._clean_lists(data.get("lists"))
            target = self._find_list(lists, name)
            created = target is None
            if created:
                if len(lists) >= MAX_LISTS:
                    raise ValueError(f"Es gibt schon {MAX_LISTS} Listen. Lösche zuerst eine in der Seitenleiste.")
                target = {"name": name, "items": []}
                lists.append(target)
            added, already = [], []
            for text in wanted:
                same = [i for i in target["items"] if i["text"].casefold() == text.casefold()]
                if same and not same[0]["done"]:
                    already.append(same[0]["text"])
                elif same:
                    same[0]["done"] = False
                    added.append(same[0]["text"])
                else:
                    if len(target["items"]) >= MAX_LIST_ITEMS:
                        raise ValueError(f"Auf „{target['name']}“ passen höchstens {MAX_LIST_ITEMS} Einträge.")
                    target["items"].append({"text": text, "done": False})
                    added.append(text)
            data["lists"] = lists
            self._save(data)
        return {"list": target["name"], "created": created, "added": added, "already": already}

    def change_list_item(self, list_name, item, mode):
        """Einen Eintrag abhaken ("done") oder streichen ("remove"). Der Eintrag wird genau, sonst per eindeutigem Teilwort gefunden."""
        if mode not in ("done", "remove"):
            raise ValueError("Abhaken oder streichen?")
        wanted = " ".join(str(item or "").split()).casefold()
        if not wanted:
            raise ValueError("Welchen Eintrag meinst du?")
        with self._lock:
            data = self._load()
            lists = self._clean_lists(data.get("lists"))
            target = self._find_list(lists, list_name) if " ".join(str(list_name or "").split()) else None
            if target is None and len(lists) == 1 and not " ".join(str(list_name or "").split()):
                target = lists[0]
            if target is None:
                raise ValueError("Diese Liste gibt es nicht." if lists else "Es gibt noch keine Liste.")
            exact = [i for i in target["items"] if i["text"].casefold() == wanted]
            near = exact or [i for i in target["items"] if wanted in i["text"].casefold()]
            if not near:
                raise ValueError(f"„{item}“ steht nicht auf der Liste „{target['name']}“.")
            if len(near) > 1:
                raise ValueError("Welchen Eintrag meinst du: " + ", ".join(i["text"] for i in near[:5]) + "?")
            entry = near[0]
            if mode == "done":
                entry["done"] = True
            else:
                target["items"].remove(entry)
            data["lists"] = lists
            self._save(data)
        return {"list": target["name"], "item": entry["text"], "mode": mode}

    def get_lists(self, list_name=""):
        """Alle Listen, oder die eine zum Namen (ValueError, wenn es sie nicht gibt)."""
        lists = self._clean_lists(self._load().get("lists"))
        if not " ".join(str(list_name or "").split()):
            return lists
        target = self._find_list(lists, list_name)
        if target is None:
            raise ValueError("Diese Liste gibt es nicht.")
        return [target]

    @staticmethod
    def _clean_goals(items):
        clean = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                clean.append({"text": item["text"][:MAX_GOAL_LENGTH], "done": item.get("done") is True,
                              "daily": item.get("daily") is True})
        return clean[:MAX_GOALS]

    @staticmethod
    def _clean_events(items):
        clean = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            title, day, at, event_id = item.get("title"), item.get("date"), item.get("time", ""), item.get("id")
            if isinstance(title, str) and isinstance(event_id, str) and isinstance(at, str) \
                    and (at == "" or _TIME.match(at)) and _valid_date(day):
                event = {"id": event_id, "title": title[:MAX_EVENT_TITLE], "date": day, "time": at}
                if isinstance(item.get("series"), str) and isinstance(item.get("repeat"), str):
                    event["series"] = item["series"][:32]
                    event["repeat"] = item["repeat"][:MAX_LABEL]
                clean.append(event)
        clean.sort(key=lambda e: (e["date"], e["time"] or "00:00", e["title"]))
        return clean[:MAX_EVENTS]

    @staticmethod
    def _clean_series(items):
        """Serien ohne Ende (Geburtstage, woechentliche Termine): nur sie brauchen einen Merker zum Nachlegen."""
        clean = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("rule"), dict):
                continue
            rule = recurrence.Rule.from_dict(item["rule"])
            at = item.get("time", "")
            if rule is not None and rule.open_ended and rule.freq in recurrence.OPEN_ENDED and isinstance(item.get("id"), str) and isinstance(item.get("title"), str) \
                    and isinstance(at, str) and (at == "" or _TIME.match(at)) and _valid_date(item.get("start")) \
                    and _valid_date(item.get("generated_until")) and isinstance(item.get("label"), str):
                clean.append({"id": item["id"], "title": item["title"][:MAX_EVENT_TITLE], "time": at, "start": item["start"],
                              "rule": rule.to_dict(), "label": item["label"][:MAX_LABEL],
                              "generated_until": item["generated_until"]})
        return clean[:MAX_SERIES]

    def _extend_series(self, data):
        """Legt fuer Serien ohne Ende neue Termine bis zu einem Jahr voraus nach. True, wenn sich etwas geaendert hat."""
        series = self._clean_series(data.get("series"))
        if not series:
            return False
        horizon = self.today() + timedelta(days=SERIES_HORIZON_DAYS)
        events = self._clean_events(data.get("events"))
        changed = False
        for item in series:
            generated = date.fromisoformat(item["generated_until"])
            if generated >= horizon:
                continue
            start = date.fromisoformat(item["start"])
            rule = recurrence.Rule.from_dict(item["rule"])
            for day in recurrence.occurrences(start, rule, horizon):
                if day > generated and len(events) < MAX_EVENTS:
                    events.append({"id": secrets.token_hex(4), "title": item["title"], "date": day.isoformat(),
                                   "time": item["time"], "series": item["id"], "repeat": item["label"]})
            item["generated_until"] = horizon.isoformat()
            changed = True
        if changed:
            data["series"], data["events"] = series, events
        return changed

    def get(self):
        with self._lock:
            data = self._load()
            if self._extend_series(data):
                self._save(data)
        today = self.today().isoformat()
        notes = data.get("notes") if isinstance(data.get("notes"), str) else ""
        goals = data.get("goals") if isinstance(data.get("goals"), dict) else {}
        items = self._clean_goals(goals.get("items"))
        if goals.get("date") != today:
            # Neuer Tag: einmalige Ziele sind weg, taegliche kommen wieder, als noch nicht erledigt
            items = [dict(g, done=False) for g in items if g["daily"]]
        events = self._clean_events(data.get("events"))
        history = self._clean_history(data.get("history"))
        day = self.today()
        items = [dict(g, streak=self.streak(history, self.goal_key(g["text"]), day)) if g["daily"] else g for g in items]
        result = {"notes": notes, "goals": items, "date": today, "events": events,
                  "week": self._week(history, items, day), "lists": self._clean_lists(data.get("lists"))}
        if self.remote is not None:
            # Termine aus Apple dazu (schreibgeschuetzt ausser im Schreib-Kalender); der Zustand der Verbindung steht dabei
            merged = events + self.remote.events()
            merged.sort(key=lambda e: (e["date"], e["time"] or "00:00", e["title"]))
            result["events"] = merged
            result["sync"] = self.remote.status()
        return result

    def remote_write_enabled(self):
        """True, wenn neue einfache Termine in den Apple-Kalender gehen."""
        return self.remote is not None and self.remote.can_write()

    def set_notes(self, text):
        if not isinstance(text, str) or len(text) > MAX_NOTES:
            raise ValueError(f"Die Notiz darf höchstens {MAX_NOTES} Zeichen lang sein.")
        with self._lock:
            data = self._load()
            data["notes"] = text
            self._save(data)

    def set_device_note(self, device_id, name, text, keep_ids=None):
        """Die Notiz eines einzelnen Geraets (Handy). Nur dieses Geraet aendert sie, der PC zeigt sie nur an.

        keep_ids: die Geraete, die es noch gibt. Notizen gesperrter oder entfernter Geraete werden dabei aufgeraeumt.
        """
        if not isinstance(device_id, str) or not device_id or len(device_id) > 64:
            raise ValueError("Diese Notiz gibt es nur an einem gekoppelten Handy.")
        if not isinstance(text, str) or len(text) > MAX_NOTES:
            raise ValueError(f"Die Notiz darf höchstens {MAX_NOTES} Zeichen lang sein.")
        label = " ".join(str(name).split())[:MAX_DEVICE_NAME] or "Handy"
        with self._lock:
            data = self._load()
            notes = data.get("device_notes") if isinstance(data.get("device_notes"), dict) else {}
            if keep_ids is not None:
                notes = {key: value for key, value in notes.items() if key in keep_ids or key == device_id}
            if device_id not in notes and len(notes) >= MAX_DEVICE_NOTES:
                raise ValueError(f"Höchstens {MAX_DEVICE_NOTES} Geräte können eine eigene Notiz haben.")
            notes[device_id] = {"name": label, "text": text}
            data["device_notes"] = notes
            self._save(data)

    def device_notes(self, only=None):
        """Alle Geraete-Notizen als Liste (nur die mit Text). only: nur diese Geraete-Nummern."""
        with self._lock:
            data = self._load()
        notes = data.get("device_notes") if isinstance(data.get("device_notes"), dict) else {}
        result = []
        for device_id, entry in notes.items():
            if only is not None and device_id not in only:
                continue
            if not isinstance(entry, dict) or not isinstance(entry.get("text"), str) or not isinstance(entry.get("name"), str):
                continue
            result.append({"id": device_id, "name": entry["name"][:MAX_DEVICE_NAME], "text": entry["text"][:MAX_NOTES]})
        return result

    def set_goals(self, items):
        if not isinstance(items, list) or len(items) > MAX_GOALS:
            raise ValueError(f"Höchstens {MAX_GOALS} Ziele pro Tag.")
        clean = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) \
                    or not isinstance(item.get("done"), bool) \
                    or not isinstance(item.get("daily", False), bool):
                raise ValueError("Ungültiges Ziel.")
            text = " ".join(item["text"].split())
            if not text:
                raise ValueError("Ein Ziel darf nicht leer sein.")
            if len(text) > MAX_GOAL_LENGTH:
                raise ValueError(f"Ein Ziel darf höchstens {MAX_GOAL_LENGTH} Zeichen lang sein.")
            clean.append({"text": text, "done": item["done"], "daily": item.get("daily", False)})
        with self._lock:
            data = self._load()
            today = self.today().isoformat()
            data["goals"] = {"date": today, "items": clean}
            # Fuer die Serien: der heutige Stand der taeglichen Ziele (spaeter erledigt/abgehakt ueberschreibt)
            history = self._clean_history(data.get("history"))
            day = {}
            for g in clean:
                if g["daily"]:
                    key = self.goal_key(g["text"])
                    day[key] = day.get(key, False) or g["done"]
            if day:
                history[today] = day
            else:
                history.pop(today, None)
            data["history"] = self._clean_history(history)
            self._save(data)

    # ---- Kalender-Termine (von der Seite oder von Jarvis)
    def _check_event(self, title, day, at):
        """Titel, Datum und Uhrzeit pruefen. Gibt (titel, uhrzeit, datum) zurueck."""
        if not isinstance(title, str) or not isinstance(day, str) or not isinstance(at, str):
            raise ValueError("Ungültiger Termin.")
        title = " ".join(title.split())
        at = at.strip()
        if not title:
            raise ValueError("Ein Termin braucht einen Titel.")
        if len(title) > MAX_EVENT_TITLE:
            raise ValueError(f"Der Titel darf höchstens {MAX_EVENT_TITLE} Zeichen lang sein.")
        if not _valid_date(day):
            raise ValueError("Ungültiges Datum.")
        today = self.today()
        chosen = date.fromisoformat(day)
        if chosen < today - timedelta(days=EVENT_KEEP_DAYS) or chosen > today + timedelta(days=365 * 5):
            raise ValueError("Das Datum liegt zu weit weg (höchstens 5 Jahre voraus).")
        if at and not _TIME.match(at):
            raise ValueError("Ungültige Uhrzeit (Format HH:MM).")
        return title, at, chosen

    def add_event(self, title, day, at=""):
        title, at, chosen = self._check_event(title, day, at)
        # Einfache Termine gehen in den Apple-Kalender (dann sind sie auch am Handy). Erinnerungs-Eintraege ("⏰ ...") bleiben lokal.
        if self.remote_write_enabled() and not title.startswith("⏰"):
            return self.remote.add(title, day, at)
        today = self.today()
        with self._lock:
            data = self._load()
            events = self._clean_events(data.get("events"))
            cutoff = (today - timedelta(days=EVENT_KEEP_DAYS)).isoformat()
            events = [e for e in events if e["date"] >= cutoff]
            if len(events) >= MAX_EVENTS:
                raise ValueError(f"Es sind höchstens {MAX_EVENTS} Termine möglich.")
            event = {"id": secrets.token_hex(4), "title": title, "date": day, "time": at}
            events.append(event)
            data["events"] = events
            self._save(data)
        return event

    def add_series(self, title, day, at="", freq=None, interval=None, count=None, until=None):
        """Wiederkehrender Termin. Ohne Wiederholung (freq leer) wie add_event. Gibt die angelegten Termine zurueck."""
        title, at, chosen = self._check_event(title, day, at)
        today = self.today()
        rule = recurrence.parse_rule(freq, interval, count, until, chosen)
        if rule is None:
            return [self.add_event(title, day, at)]
        if rule.open_ended:
            days = recurrence.occurrences(chosen, rule, today + timedelta(days=SERIES_HORIZON_DAYS))
        else:
            days = recurrence.occurrences(chosen, rule)
            if len(days) > recurrence.MAX_OCCURRENCES:
                raise ValueError(f"Das wären mehr als {recurrence.MAX_OCCURRENCES} Termine. Wähle ein früheres Ende.")
            if days and days[-1] > recurrence.limit_date(today):
                raise ValueError(f"Die Serie reicht zu weit in die Zukunft (höchstens {recurrence.MAX_YEARS_AHEAD} Jahre).")
            if len(days) == 1:
                return [self.add_event(title, day, at)]
        label = recurrence.describe(rule, chosen)
        series_id = secrets.token_hex(4)
        with self._lock:
            data = self._load()
            events = self._clean_events(data.get("events"))
            cutoff = (today - timedelta(days=EVENT_KEEP_DAYS)).isoformat()
            events = [e for e in events if e["date"] >= cutoff]
            if len(events) + len(days) > MAX_EVENTS:
                raise ValueError(f"Es sind höchstens {MAX_EVENTS} Termine möglich.")
            series = self._clean_series(data.get("series"))
            if rule.open_ended and len(series) >= MAX_SERIES:
                raise ValueError(f"Es sind höchstens {MAX_SERIES} Serien ohne Ende möglich.")
            created = [{"id": secrets.token_hex(4), "title": title, "date": d.isoformat(), "time": at,
                        "series": series_id, "repeat": label} for d in days]
            events.extend(created)
            data["events"] = events
            if rule.open_ended:
                series.append({"id": series_id, "title": title, "time": at, "start": chosen.isoformat(), "rule": rule.to_dict(),
                               "label": label, "generated_until": (today + timedelta(days=SERIES_HORIZON_DAYS)).isoformat()})
            data["series"] = series
            self._save(data)
        created[0] = dict(created[0], open_ended=rule.open_ended)     # nur fuer die Antwort, wird nicht gespeichert
        return created

    def delete_series(self, series_id):
        """Alle Termine einer Serie (und den Merker zum Nachlegen) loeschen."""
        if not isinstance(series_id, str):
            raise ValueError("Ungültige Serie.")
        with self._lock:
            data = self._load()
            events = self._clean_events(data.get("events"))
            kept = [e for e in events if e.get("series") != series_id]
            series = [s for s in self._clean_series(data.get("series")) if s["id"] != series_id]
            if len(kept) == len(events):
                raise ValueError("Diese Serie gibt es nicht.")
            data["events"], data["series"] = kept, series
            self._save(data)
        return len(events) - len(kept)

    def delete_event(self, event_id):
        if isinstance(event_id, str) and event_id.startswith("apple:"):
            if self.remote is None:
                raise ValueError("Dieser Termin gehört zum Apple-Kalender, der gerade nicht eingerichtet ist.")
            self.remote.delete(event_id)
            return
        if not isinstance(event_id, str):
            raise ValueError("Ungültiger Termin.")
        with self._lock:
            data = self._load()
            events = self._clean_events(data.get("events"))
            kept = [e for e in events if e["id"] != event_id]
            if len(kept) == len(events):
                raise ValueError("Diesen Termin gibt es nicht.")
            data["events"] = kept
            self._save(data)

    def events_on(self, day):
        return [e for e in self.get()["events"] if e["date"] == day]

    def upcoming_events(self, limit=10):
        today = self.today().isoformat()
        return [e for e in self.get()["events"] if e["date"] >= today][:limit]


def _valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


_default_store = None


def default_store():
    """Die eine Datei widgets.json (Seite und Jarvis-Aufgaben teilen sich diese)."""
    global _default_store
    if _default_store is None:
        _default_store = WidgetStore()
    return _default_store


def attach_remote(remote):
    """Haengt den Apple-Kalender an den gemeinsamen Speicher (nur beim echten Start des Servers, nie in Tests)."""
    default_store().remote = remote


def set_default_store(store):
    """Nur fuer Tests."""
    global _default_store
    _default_store = store


# ----------------------------------------------------------------------
# Eishockey (NHL-Schnittstelle, Adler Mannheim per Kalenderdatei)
# ----------------------------------------------------------------------

# Anzeigename in den Einstellungen -> woher der Spielplan kommt und wie viele Spiele folgen.
# Weitere Teams: hier eintragen und in settings_manager.CHOICES ergaenzen.
TEAMS = {
    "Edmonton Oilers": {
        "kind": "nhl", "abbrev": "EDM", "next": 4,
        "url": "https://api-web.nhle.com/v1/club-schedule-season/EDM/now",
    },
    # Offizielle Kalenderdatei der Adler ("Download Spielplan"): Paarungen und Termine, ohne Ergebnisse
    "Adler Mannheim": {
        "kind": "ics", "match": "adler mannheim", "next": 3,
        "url": "https://adler-mannheim.de/saison/spielplan/iCal.ics",
    },
}
NEXT_GAMES = 4
CACHE_SECONDS = 300
MAX_RESPONSE_BYTES = 8_000_000
ALLOWED_HOSTS = ("api-web.nhle.com", "adler-mannheim.de", "www.adler-mannheim.de")
GAME_DURATION = timedelta(hours=3)      # so lange gilt ein Spiel ohne Ergebnis-Quelle als "laeuft"

_LIVE = {"LIVE", "CRIT"}
_FINAL = {"FINAL", "OFF"}


class HockeyError(Exception):
    pass


def fetch_text(url):
    """Holt Text aus dem Netz ueber den gemeinsamen Helfer (net_fetch): nur diese Hosts, nur https."""
    try:
        return net_fetch.fetch_text(url, ALLOWED_HOSTS, max_bytes=MAX_RESPONSE_BYTES)
    except net_fetch.NetError as error:
        raise HockeyError(str(error)) from error


def fetch_json(url):
    try:
        return json.loads(fetch_text(url))
    except ValueError as error:
        raise HockeyError("Die Antwort ist kein gueltiges JSON.") from error


def _name(node):
    """Name eines Teams: NHL liefert {"default": "Oilers"} oder einen Text."""
    if isinstance(node, dict):
        node = node.get("default")
    return node if isinstance(node, str) else None


def _side(node):
    if not isinstance(node, dict):
        return None
    abbrev = node.get("abbrev")
    if not isinstance(abbrev, str):
        return None
    score = node.get("score")
    return {
        "abbrev": abbrev,
        "name": _name(node.get("commonName")) or _name(node.get("placeName")) or abbrev,
        "score": score if isinstance(score, int) and not isinstance(score, bool) else None,
    }


def parse_games(data, abbrev):
    """Macht aus der NHL-Antwort eine einfache Liste. Kaputte Eintraege werden uebersprungen."""
    games = data.get("games") if isinstance(data, dict) else None
    result = []
    for game in games if isinstance(games, list) else []:
        if not isinstance(game, dict):
            continue
        home, away = _side(game.get("homeTeam")), _side(game.get("awayTeam"))
        start = game.get("startTimeUTC")
        if not home or not away or not isinstance(start, str) or len(start) > 40:
            continue
        try:
            datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        state = game.get("gameState")
        result.append({
            "start": start,
            "state": "live" if state in _LIVE else "final" if state in _FINAL else "future",
            "home": home,
            "away": away,
            "team_is_home": home["abbrev"] == abbrev,
        })
    result.sort(key=lambda g: g["start"])
    return result


# ---- Kalenderdatei (iCal) der Adler

def _last_sunday(year, month):
    day = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def berlin_to_utc(local):
    """Ortszeit Berlin (ohne Zeitzone) -> UTC. Sommerzeit: letzter Sonntag im Maerz 2 Uhr
    bis letzter Sonntag im Oktober 3 Uhr (EU-Regel). Ohne tzdata, das gibt es unter Windows nicht immer."""
    begin = datetime.combine(_last_sunday(local.year, 3), datetime.min.time()) + timedelta(hours=2)
    finish = datetime.combine(_last_sunday(local.year, 10), datetime.min.time()) + timedelta(hours=3)
    offset = 2 if begin <= local < finish else 1
    return (local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def _unescape(value):
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def parse_ics(text, match, now=None):
    """Liest die Kalenderdatei. 'Heim vs. Gast' im Titel, Beginn mit Zeitzone Berlin oder UTC.
    Gibt dieselbe Liste wie parse_games zurueck (ohne Punktestand). Unpassendes wird uebersprungen."""
    now = now or datetime.now(timezone.utc)
    games = []
    event = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            event = {}
        elif line == "END:VEVENT":
            game = _ics_game(event, match, now) if event is not None else None
            if game:
                games.append(game)
            event = None
        elif event is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *params = head.split(";")
            if name.upper() in ("SUMMARY", "DTSTART"):
                event[name.upper()] = (value, [p.upper() for p in params])
    games.sort(key=lambda g: g["start"])
    return games


def _ics_game(event, match, now):
    if "SUMMARY" not in event or "DTSTART" not in event:
        return None
    summary = _unescape(event["SUMMARY"][0])
    value, params = event["DTSTART"]
    parts = re.split(r"\s+vs\.?\s+", summary, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    home, away = parts[0].strip()[:60], parts[1].strip()[:60]
    found = re.fullmatch(r"(\d{8}T\d{6})(Z?)", value.strip())
    if not found or any(p.startswith("VALUE=DATE") and "DATE-TIME" not in p for p in params):
        return None                              # ganztaegige Termine u.a. gibt es hier nicht
    try:
        naive = datetime.strptime(found.group(1), "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    tzid = next((p[5:] for p in params if p.startswith("TZID=")), None)
    if found.group(2) == "Z":
        start = naive.replace(tzinfo=timezone.utc)
    elif tzid in (None, "EUROPE/BERLIN"):
        start = berlin_to_utc(naive)
    else:
        return None                              # fremde Zeitzone: lieber nichts als eine falsche Uhrzeit
    if now >= start + GAME_DURATION:
        state = "final"
    elif now >= start:
        state = "live"
    else:
        state = "future"
    return {
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": state,
        "home": {"abbrev": home, "name": home, "score": None},
        "away": {"abbrev": away, "name": away, "score": None},
        "team_is_home": match in home.lower(),
    }


def pick_games(games, count=NEXT_GAMES):
    """Aktuelles Spiel = laufendes, sonst das letzte beendete. Dazu die naechsten `count`."""
    live = [g for g in games if g["state"] == "live"]
    final = [g for g in games if g["state"] == "final"]
    future = [g for g in games if g["state"] == "future"]
    current = live[0] if live else (final[-1] if final else None)
    return {"current": current, "next": future[:count]}


class HockeyFeed:
    def __init__(self, fetch=fetch_text, clock=time.time, ttl=CACHE_SECONDS):
        self.fetch = fetch
        self.clock = clock
        self.ttl = ttl
        self._cache = {}
        self._lock = threading.Lock()

    def _load(self, source):
        text = self.fetch(source["url"])
        if source["kind"] == "ics":
            return parse_ics(text, source["match"], datetime.fromtimestamp(self.clock(), timezone.utc))
        return parse_games(json.loads(text) if isinstance(text, str) else text, source["abbrev"])

    def get(self, team_name):
        source = TEAMS.get(team_name)
        if source is None:
            raise HockeyError("Unbekanntes Team.")
        with self._lock:
            cached = self._cache.get(team_name)
            if cached and self.clock() - cached["at"] < self.ttl:
                return dict(cached["data"], stale=False)
            try:
                games = self._load(source)
            except Exception as error:
                # Ohne Netz: lieber der alte Stand (als veraltet markiert) als nichts
                if cached:
                    return dict(cached["data"], stale=True)
                raise HockeyError("Der Spielplan ist gerade nicht erreichbar.") from error
            data = dict(pick_games(games, source["next"]), team=team_name,
                        scores=source["kind"] == "nhl",
                        updated=datetime.now(timezone.utc).isoformat())
            self._cache[team_name] = {"at": self.clock(), "data": data}
            return dict(data, stale=False)
