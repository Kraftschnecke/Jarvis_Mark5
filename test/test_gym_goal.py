"""Das feste Gym-Tagesziel in den taeglichen Zielen: Name, Offday von selbst erledigt, Haken, feste Serie, nicht loeschbar."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import widgets
from gym import GymStore

tmp = Path(tempfile.mkdtemp())
TODAY = [date(2026, 11, 23)]                                   # Montag
now = lambda: TODAY[0]
gym = GymStore(tmp / "gym.json", today=now)
store = widgets.WidgetStore(tmp / "widgets.json", today=now)


def gym_item(state):
    items = [g for g in state["goals"] if g.get("managed") == "gym"]
    assert len(items) <= 1
    return items[0] if items else None


def post(state, *extra, drop_gym=False):
    """Wie die Seite: die ganze Liste zurueckschicken (mit dem festen Ziel)."""
    items = [{k: g[k] for k in ("text", "done", "daily", "managed") if k in g} for g in state["goals"] if not (drop_gym and g.get("managed"))]
    store.set_goals(items + list(extra))
    return store.get()


# 1) Kein Gym verbunden / kein Plan: kein Gym-Ziel
assert gym_item(store.get()) is None
store.gym = gym
assert gym_item(store.get()) is None

# 2) Plan: Montag Push, Dienstag Offday (leer), Mittwoch Pull
gym.set_plan([{"weekday": 0, "name": "Push", "exercises": [{"name": "Bank", "weight": 60, "sets": 3, "reps": 8}]},
              {"weekday": 2, "name": "Pull", "exercises": [{"name": "Rudern", "weight": 50, "sets": 3, "reps": 8}]}])
state = store.get()
g = gym_item(state)
assert g["text"] == "Gym: Push" and g["done"] is False and g["daily"] is True and g["streak"] == 0 and state["goals"][0] is g
assert store.get()["goals"].count(g) == 1

# 3) Haken setzen (so wie die Seite es schickt); die Datei speichert es nicht als normales Ziel
state = store.get()
for item in state["goals"]:
    if item.get("managed"):
        item["done"] = True
store.set_goals([{k: x[k] for k in ("text", "done", "daily", "managed") if k in x} for x in state["goals"]])
state = store.get()
assert gym_item(state)["done"] is True and gym_item(state)["streak"] == 1
raw = widgets.json.loads((tmp / "widgets.json").read_text(encoding="utf-8"))
assert raw["goals"]["items"] == [] and raw["gym_done"] == {"date": "2026-11-23", "done": True} and raw["history"]["2026-11-23"][widgets.GYM_KEY] is True

# 4) Andere Ziele daneben bleiben normal; das feste Ziel laesst sich nicht entfernen oder umschreiben
state = post(state, {"text": "Lesen", "done": False, "daily": True})
assert [g["text"] for g in state["goals"]] == ["Gym: Push", "Lesen"] and "managed" not in state["goals"][1]
state = post(state, drop_gym=True)                                  # Seite laesst das Gym-Ziel weg: es ist trotzdem da, Haken bleibt
assert gym_item(state)["done"] is True and [g["text"] for g in state["goals"]] == ["Gym: Push", "Lesen"]
state = post(state, {"text": "Fake", "done": True, "daily": False, "managed": "gym"}, drop_gym=True)   # nur der Haken zaehlt, nie der Text
assert [g["text"] for g in state["goals"]] == ["Gym: Push", "Lesen"] and gym_item(state)["done"] is True
assert [g["text"] for g in widgets.json.loads((tmp / "widgets.json").read_text(encoding="utf-8"))["goals"]["items"]] == ["Lesen"]

# 5) Dienstag = Offday: von selbst erledigt, Serie lebt weiter; Haken von gestern gilt nicht
TODAY[0] = date(2026, 11, 24)
state = store.get()
g = gym_item(state)
assert g["text"] == "Gym: Offday" and g["done"] is True and g["streak"] == 2
state = post(state)
assert gym_item(state)["done"] is True
assert "gym_done" in widgets.json.loads((tmp / "widgets.json").read_text(encoding="utf-8")) and gym_item(store.get())["streak"] == 2
state = store.get()
for item in state["goals"]:
    if item.get("managed"):
        item["done"] = False                                     # am Offday laesst sich nichts abwaehlen
store.set_goals([{k: x[k] for k in ("text", "done", "daily", "managed") if k in x} for x in state["goals"]])
assert gym_item(store.get())["done"] is True

# 6) Mittwoch = Pull: neuer Tag, nicht abgehakt, Serie ab gestern (Mo Haken, Di Offday)
TODAY[0] = date(2026, 11, 25)
g = gym_item(store.get())
assert g["text"] == "Gym: Pull" and g["done"] is False and g["streak"] == 2
state = post(store.get())                                          # speichert den Stand (offen) fuer heute
assert gym_item(state)["done"] is False
# Donnerstag + Freitag Offday ohne Besuch der Seite: die Serie reisst am nicht abgehakten Mittwoch
TODAY[0] = date(2026, 11, 26)
g = gym_item(store.get())
assert g["done"] is True and g["streak"] == 1                      # Mittwoch war offen -> nur heute
# Mittwoch nachtraeglich: gar nicht moeglich ueber die Seite; die Serie ist an der Luecke gerissen
TODAY[0] = date(2026, 11, 27)
assert gym_item(store.get())["streak"] == 2

# 7) Serie bleibt beim Namenswechsel (Push -> Pull -> Push) bestehen: fester Schluessel
TODAY[0] = date(2026, 11, 30)                                       # Montag, Push, neue Woche: Fr/Sa/So sind Offday, Do auch
g = gym_item(store.get())
assert g["text"] == "Gym: Push" and g["done"] is False and g["streak"] == 4          # Do, Fr, Sa, So (Offdays); Mi offen davor

# 8) Plan wieder leer: Gym-Ziel verschwindet, Haken-Datei stoert nicht
gym.set_plan([])
assert gym_item(store.get()) is None and [g["text"] for g in store.get()["goals"]] == ["Lesen"]

# 9) Fremde Daten in gym_done / Fremder Schluessel
data = widgets.json.loads((tmp / "widgets.json").read_text(encoding="utf-8"))
data["gym_done"] = "kaputt"
(tmp / "widgets.json").write_text(widgets.json.dumps(data), encoding="utf-8")
gym.set_plan([{"weekday": 0, "name": "Push", "exercises": []}])
assert gym_item(store.get())["done"] is False

# 10) Gaeste/ohne Gym: ein Ziel mit managed-Feld bleibt ein normales Ziel (kein Gym-Objekt = nie ein festes Ziel)
plain = widgets.WidgetStore(tmp / "plain.json", today=now)
plain.set_goals([{"text": "Gym: Fake", "done": True, "daily": True, "managed": "gym"}])
assert plain.get()["goals"] == []
print("ALL TESTS PASSED")
