"""Wecker im Kalender (Step 2.11b): Uebersicht, Bearbeiten, Loeschen im Speicher und ueber HTTP."""

import http.client
import json
import sys
import threading
import tempfile
import types
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def stub_if_missing(name, **attrs):
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


stub_if_missing("openai", OpenAI=object)
stub_if_missing("psycopg")
stub_if_missing("psutil")
stub_if_missing("requests")
stub_if_missing("dotenv", load_dotenv=lambda *a, **k: None)
try:
    import pycaw.pycaw  # noqa: F401
except ImportError:
    sys.modules["pycaw"] = types.ModuleType("pycaw")
    inner = types.ModuleType("pycaw.pycaw")
    inner.AudioUtilities = None
    inner.IAudioEndpointVolume = None
    sys.modules["pycaw.pycaw"] = inner

project_stub = types.ModuleType("project")
for name in ("search_projects", "get_conversations", "create_conversation", "load_conversation_messages",
             "save_message", "get_conversation", "rename_conversation", "create_project", "reset_conversation",
             "delete_conversation", "get_projects", "rename_project", "delete_project"):
    setattr(project_stub, name, lambda *a, **k: None)
sys.modules["project"] = project_stub

import reminders
import server
import widgets
from reminders import ReminderError, ReminderScheduler, ReminderStore
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
clock = [datetime(2026, 10, 22, 6, 0, 0)]                      # Donnerstag
now = lambda: clock[0]
calendar = widgets.WidgetStore(folder / "w.json", today=lambda: clock[0].date())
store = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
reminders.set_default_store(store)
widgets.set_default_store(calendar)

A = store.add("Wecker", "", "06:30", kind="alarm")
B = store.add("Arbeit", "", "06:45", freq="werktags", kind="alarm", briefing=True)
C = store.add("Kurs", "2026-10-27", "07:00", freq="weekly", count=3, kind="alarm")
R = store.add("Wäsche", "", "19:00")                                   # normale Erinnerung, mit Kalendereintrag

# 1) Uebersicht: alle Wecker, nach Uhrzeit, mit den Tagen, an denen sie klingeln
rows = store.alarms_overview()
assert [r["label"] for r in rows] == ["Wecker", "Arbeit", "Kurs"] and R["id"] not in [r["id"] for r in rows]
assert [r["time"] for r in rows] == ["06:30", "06:45", "07:00"] and [r["briefing"] for r in rows] == [False, True, False]
assert rows[0]["dates"] == ["2026-10-22"] and rows[0]["repeat"] is None
assert rows[2]["dates"] == ["2026-10-27", "2026-11-03", "2026-11-10"] and rows[2]["repeat"] == "jeden Dienstag, 3 Mal"
work = rows[1]["dates"]
assert work[:4] == ["2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"] and work[-1] == "2026-12-23" and len(work) == 45
assert all(datetime.fromisoformat(d).weekday() < 5 for d in work), "werktags: nie am Wochenende"
assert rows[1]["repeat"] == "werktags (Mo–Fr)"
assert len(store.alarms_overview(horizon_days=7)[1]["dates"]) == 6                                   # 22., 23., 26.-29.
assert ReminderStore(folder / "leer.json", now=now, calendar=lambda: calendar).alarms_overview() == []

# 2) Aendern: nur genannte Angaben, nichts anderes
u = store.update_alarm(A["id"], label="Zug erwischen")
assert u["text"] == "Zug erwischen" and u["due"] == "2026-10-22T06:30" and u["briefing"] is False and u["kind"] == "alarm"
assert store.update_alarm(A["id"], label="  ")["text"] == "Wecker"                                  # leer: Standardname
assert store.update_alarm(A["id"], briefing=True)["briefing"] is True
assert store.update_alarm(A["id"], time="07:15")["due"] == "2026-10-22T07:15"
assert store.update_alarm(A["id"], time="0730")["due"] == "2026-10-22T07:30"                         # alle Schreibweisen
u = store.update_alarm(A["id"], time="05:00")                                                        # heute schon vorbei -> morgen
assert u["due"] == "2026-10-23T05:00"
u = store.update_alarm(A["id"], day="2026-10-25")
assert u["due"] == "2026-10-25T05:00" and u["event_id"] is None
u = store.update_alarm(A["id"], time="08:00", day="2026-10-24", label="Alles neu", briefing=False)
assert (u["text"], u["due"], u["briefing"]) == ("Alles neu", "2026-10-24T08:00", False)
for kwargs, part in (({"label": "x" * 91}, "höchstens"), ({"briefing": "ja"}, "ja oder nein"), ({"time": "abc"}, "Uhrzeit"),
                     ({"time": "25:00"}, "Uhrzeit"), ({"day": "morgen"}, "Datum"), ({"day": "2026-13-45"}, "Datum"),
                     ({"day": "2026-10-20"}, "schon vorbei"), ({"day": "2027-12-01"}, "höchstens 365")):
    try:
        store.update_alarm(A["id"], **kwargs)
        raise AssertionError(kwargs)
    except ReminderError as error:
        assert part in str(error), (kwargs, str(error))
assert store.list("alarm")[0]["text"] != "x" * 91 and store.update_alarm(A["id"], label="Wecker")["due"] == "2026-10-24T08:00"   # Fehler aendern nichts
for bad_id in ("gibtsnicht", R["id"], "", None):
    try:
        store.update_alarm(bad_id, label="x")
        raise AssertionError(bad_id)
    except ReminderError as error:
        assert "gibt es nicht" in str(error)
assert [r["text"] for r in store.list()] == ["Wäsche"] and len(calendar.events_on("2026-10-22")) == 1      # Erinnerung + Kalender unberuehrt

# Serie: Uhrzeit gilt fuer alle kuenftigen Termine, das Datum laesst sich nicht aendern
try:
    store.update_alarm(B["id"], day="2026-10-30")
    raise AssertionError
except ReminderError as error:
    assert "wiederkehrenden" in str(error)
u = store.update_alarm(B["id"], time="06:50")
assert u["due"] == "2026-10-22T06:50" and u["repeat"]["index"] == 0 and u["briefing"] is True
rings = []
sch = ReminderScheduler(store, submit=lambda m: None, ring=lambda label, brief: rings.append(label))
clock[0] = datetime(2026, 10, 22, 6, 50, 10)
assert sch.check() == 1 and rings == ["Arbeit"]                                                       # 06:45 gilt nicht mehr, 06:50 schon
assert [r["due"] for r in store.list("alarm") if r["text"] == "Arbeit"] == ["2026-10-23T06:50"]        # naechster Termin mit neuer Uhrzeit
clock[0] = datetime(2026, 10, 22, 6, 0, 0)
u = store.update_alarm(B["id"], time="05:00")                                                         # morgen frueher: Freitag 05:00
assert u["due"] == "2026-10-23T05:00"
clock[0] = datetime(2026, 10, 23, 6, 0, 0)
u = store.update_alarm(B["id"], time="05:30")                                                         # Freitag 05:30 schon vorbei
assert u["due"] == "2026-10-26T05:30" and u["repeat"]["index"] == 2, u                                  # naechster Werktag: Montag (Index 2)
clock[0] = datetime(2026, 10, 22, 6, 0, 0)
assert store.update_alarm(C["id"], time="08:00")["due"] == "2026-10-27T08:00"
assert [r["time"] for r in store.alarms_overview() if r["label"] == "Kurs"] == ["08:00"]

# Neustart: alles bleibt
again = ReminderStore(folder / "r.json", now=now, calendar=lambda: calendar)
assert sorted((r["text"], r["due"]) for r in again.list("alarm")) == sorted((r["text"], r["due"]) for r in store.list("alarm"))

# 3) Loeschen: ganze Serie, Name zurueck, Erinnerung bleibt
assert store.delete_alarm(B["id"]) == "Arbeit"
assert [r["label"] for r in store.alarms_overview()] == ["Wecker", "Kurs"]
for bad_id in (B["id"], R["id"], "x"):
    try:
        store.delete_alarm(bad_id)
        raise AssertionError(bad_id)
    except ReminderError as error:
        assert "gibt es nicht" in str(error)
assert [r["text"] for r in store.list()] == ["Wäsche"] and len(calendar.events_on("2026-10-22")) == 1

# 4) HTTP
jarvis = types.SimpleNamespace(settings_manager=SettingsManager(folder / "s.json"), guest=False)
httpd = server.JarvisServer(("127.0.0.1", 0), jarvis, widget_store=calendar, monitor=object())
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def request(method, path, payload=None, content_type="application/json", host=None, target=None):
    conn = http.client.HTTPConnection("127.0.0.1", target or port, timeout=5)
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": content_type} if body is not None else {}
    if host:
        headers["Host"] = host
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, json.loads(data)


status, data = request("GET", "/api/alarms")
assert status == 200 and [a["label"] for a in data["alarms"]] == ["Wecker", "Kurs"] and data["alarms"][0]["dates"] == ["2026-10-24"]
wid = data["alarms"][0]["id"]
with httpd.message_lock:                                                   # auch waehrend Jarvis eine Nachricht bearbeitet
    status, data = request("POST", "/api/alarms/update", {"id": wid, "time": "09:15", "label": "Joggen", "briefing": True})
assert status == 200 and [(a["label"], a["time"], a["briefing"]) for a in data["alarms"]] == [("Joggen", "09:15", True), ("Kurs", "08:00", False)]
status, data = request("POST", "/api/alarms/update", {"id": wid, "time": "kaputt"})
assert status == 400 and "Uhrzeit" in data["error"]
status, data = request("POST", "/api/alarms/update", {"id": wid, "date": "2026-10-20"})
assert status == 400 and "schon vorbei" in data["error"]
assert request("GET", "/api/alarms")[1]["alarms"][0]["label"] == "Joggen"                                # Fehler aendern nichts
for bad in ({"id": 5}, {"id": ""}, {"id": None}, {"id": "x" * 41}, {}, {"id": ["a"]}):
    for path in ("/api/alarms/update", "/api/alarms/delete"):
        assert request("POST", path, bad)[0] == 400, (path, bad)
assert request("POST", "/api/alarms/delete", {"id": "nope"})[0] == 400
status, data = request("POST", "/api/alarms/delete", {"id": wid})
assert status == 200 and [a["label"] for a in data["alarms"]] == ["Kurs"]
assert request("POST", "/api/alarms/update", {"id": wid, "label": "x"})[0] == 400                          # schon weg
assert request("POST", "/api/alarms/update", {"id": "x"}, content_type="text/plain")[0] == 415
assert request("GET", "/api/alarms", host="evil.example")[0] == 403 and request("POST", "/api/alarms/delete", {"id": "x"}, host="evil.example")[0] == 403

# Gastmodus kennt diese Adressen nicht und aendert nichts
guest_httpd = server.JarvisServer(("127.0.0.1", 0), types.SimpleNamespace(settings_manager=jarvis.settings_manager, guest=True), guest=True)
guest_port = guest_httpd.server_address[1]
threading.Thread(target=guest_httpd.serve_forever, daemon=True).start()
assert request("GET", "/api/alarms", target=guest_port)[0] == 403
remaining = store.list("alarm")[0]["id"]
assert request("POST", "/api/alarms/delete", {"id": remaining}, target=guest_port)[0] == 403
assert request("POST", "/api/alarms/update", {"id": remaining, "label": "x"}, target=guest_port)[0] == 403
assert len(store.list("alarm")) == 1
guest_httpd.shutdown()
httpd.shutdown()

print("ALL TESTS PASSED")
