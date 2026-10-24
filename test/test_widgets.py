"""Widgets (Etappe C): Notizen, Tagesziele, NHL-Spielplan (ohne Netz, mit gefaelschter Quelle)."""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import widgets
import net_fetch
from widgets import HockeyError, HockeyFeed, WidgetStore, parse_games, pick_games

folder = Path(tempfile.mkdtemp())

# ---- Notizen und Ziele
day = [date(2026, 10, 21)]
store = WidgetStore(folder / "w.json", today=lambda: day[0])
assert not (folder / "w.json").exists(), "ohne Speichern entsteht keine Datei"
assert store.get() == {"notes": "", "goals": [], "date": "2026-10-21", "events": []}

store.set_notes("Milch kaufen\nÜmlaut ß")
assert store.get()["notes"] == "Milch kaufen\nÜmlaut ß"
assert WidgetStore(folder / "w.json").get()["notes"] == "Milch kaufen\nÜmlaut ß", "bleibt nach Neustart"
for bad in (None, 5, ["a"], "x" * (widgets.MAX_NOTES + 1)):
    try:
        store.set_notes(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
store.set_notes("x" * widgets.MAX_NOTES)

store.set_goals([{"text": "  Sport   machen ", "done": False}, {"text": "Jarvis testen", "done": True}])
assert store.get()["goals"] == [{"text": "Sport machen", "done": False, "daily": False},
                                {"text": "Jarvis testen", "done": True, "daily": False}]
assert len(store.get()["notes"]) == widgets.MAX_NOTES, "Ziele speichern darf Notizen nicht loeschen"
store.set_notes("neu")
assert len(store.get()["goals"]) == 2, "Notizen speichern darf Ziele nicht loeschen"

# Ziele gelten nur heute
day[0] = date(2026, 10, 22)
assert store.get()["goals"] == [] and store.get()["notes"] == "neu"
store.set_goals([])
day[0] = date(2026, 10, 21)
assert store.get()["goals"] == [], "neuer Stand ersetzt den alten Tag"

bad_goal_lists = [
    "x", None, [{"text": "a"}], [{"text": "a", "done": "ja"}], [{"text": "", "done": False}],
    [{"text": "   ", "done": False}], [{"text": 5, "done": False}], ["a"],
    [{"text": "x" * (widgets.MAX_GOAL_LENGTH + 1), "done": False}],
    [{"text": "a", "done": False}] * (widgets.MAX_GOALS + 1),
]
for bad in bad_goal_lists:
    try:
        store.set_goals(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
store.set_goals([{"text": "x" * widgets.MAX_GOAL_LENGTH, "done": False}] * widgets.MAX_GOALS)
assert len(store.get()["goals"]) == widgets.MAX_GOALS

# Kaputte oder fremde Datei: leer statt Absturz
for content in ("{kaputt", "[1,2]", '{"notes": 5, "goals": "x"}', '{"goals": {"date": "2026-10-21", "items": [1, {"text": 3}]}}'):
    (folder / "k.json").write_text(content, encoding="utf-8")
    assert WidgetStore(folder / "k.json", today=lambda: date(2026, 10, 21)).get() == \
        {"notes": "", "goals": [], "date": "2026-10-21", "events": []}, content
# Speichern ueber kaputte Datei klappt
WidgetStore(folder / "k.json").set_notes("ok")
assert json.loads((folder / "k.json").read_text(encoding="utf-8"))["notes"] == "ok"
assert not (folder / "w.tmp").exists()


# ---- Spielplan: Antwort in der Form der NHL-Schnittstelle (club-schedule-season)
def game(start, state, home, away, hs=None, as_=None):
    def side(abbrev, name, score):
        node = {"abbrev": abbrev, "commonName": {"default": name}, "placeName": {"default": "X"}}
        if score is not None:
            node["score"] = score
        return node
    return {"id": 1, "startTimeUTC": start, "gameState": state,
            "homeTeam": side(*home, hs), "awayTeam": side(*away, as_)}


EDM, CGY, VAN, SEA, LAK, SJS, ANA = (("EDM", "Oilers"), ("CGY", "Flames"), ("VAN", "Canucks"),
                                     ("SEA", "Kraken"), ("LAK", "Kings"), ("SJS", "Sharks"), ("ANA", "Ducks"))
season = {"games": [
    game("2026-10-30T02:00:00Z", "FUT", EDM, SEA),
    game("2026-10-10T02:00:00Z", "OFF", CGY, EDM, 2, 4),
    game("2026-10-12T02:00:00Z", "FINAL", EDM, VAN, 3, 1),
    game("2026-10-24T02:00:00Z", "PRE", LAK, EDM),
    game("2026-10-26T02:00:00Z", "FUT", EDM, SJS),
    game("2026-10-28T02:00:00Z", "FUT", ANA, EDM),
    game("2026-11-02T02:00:00Z", "FUT", EDM, CGY),
    {"id": 9, "startTimeUTC": "kein Datum", "gameState": "FUT", "homeTeam": {}, "awayTeam": {}},
    "kaputt", None,
]}
games = parse_games(season, "EDM")
assert len(games) == 7, "kaputte Eintraege werden uebersprungen"
assert [g["start"][:10] for g in games] == sorted(g["start"][:10] for g in games), "nach Zeit sortiert"
picked = pick_games(games)
assert picked["current"]["state"] == "final" and picked["current"]["start"].startswith("2026-10-12"), "letztes beendetes Spiel"
assert picked["current"]["home"] == {"abbrev": "EDM", "name": "Oilers", "score": 3}
assert picked["current"]["away"]["score"] == 1 and picked["current"]["team_is_home"] is True
assert [g["start"][:10] for g in picked["next"]] == ["2026-10-24", "2026-10-26", "2026-10-28", "2026-10-30"]
assert len(picked["next"]) == widgets.NEXT_GAMES and picked["next"][0]["team_is_home"] is False

# Laufendes Spiel hat Vorrang vor dem letzten beendeten und steht nicht in "next"
live_season = {"games": season["games"] + [game("2026-10-23T02:00:00Z", "LIVE", EDM, CGY, 1, 1)]}
picked = pick_games(parse_games(live_season, "EDM"))
assert picked["current"]["state"] == "live" and picked["current"]["home"]["score"] == 1
assert all(g["state"] == "future" for g in picked["next"])
assert pick_games(parse_games({"games": [game("2026-10-23T02:00:00Z", "CRIT", EDM, CGY, 1, 1)]}, "EDM"))["current"]["state"] == "live"
assert pick_games([]) == {"current": None, "next": []}
assert parse_games(None, "EDM") == [] and parse_games({"games": "x"}, "EDM") == [] and parse_games([], "EDM") == []
# Punktestand muss eine ganze Zahl sein, sonst keiner
weird = game("2026-10-10T02:00:00Z", "FINAL", EDM, CGY, True, "3")
parsed = parse_games({"games": [weird]}, "EDM")[0]
assert parsed["home"]["score"] is None and parsed["away"]["score"] is None

# ---- HockeyFeed: Zwischenspeicher, Fehler, alter Stand
now = [1000.0]
calls = []


def fetch(url):
    calls.append(url)
    if fetch.fail:
        raise OSError("kein Netz")
    return season


fetch.fail = False
feed = HockeyFeed(fetch=fetch, clock=lambda: now[0], ttl=300)
result = feed.get("Edmonton Oilers")
assert calls == ["https://api-web.nhle.com/v1/club-schedule-season/EDM/now"]
assert result["team"] == "Edmonton Oilers" and result["stale"] is False and len(result["next"]) == 4
assert json.dumps(result), "muss als JSON auslieferbar sein"
feed.get("Edmonton Oilers")
assert len(calls) == 1, "innerhalb von 5 Minuten kein neuer Abruf"
now[0] += 301
fetch.fail = True
stale = feed.get("Edmonton Oilers")
assert len(calls) == 2 and stale["stale"] is True and stale["current"] == result["current"], "alter Stand statt Fehler"
fetch.fail = False
assert feed.get("Edmonton Oilers")["stale"] is False

fresh = HockeyFeed(fetch=fetch, clock=lambda: now[0])
fetch.fail = True
try:
    fresh.get("Edmonton Oilers")
    raise AssertionError("ohne Netz und ohne alten Stand muss es einen Fehler geben")
except HockeyError as error:
    assert "nicht erreichbar" in str(error)
try:
    fresh.get("Adler Mannheim")
    raise AssertionError
except HockeyError:
    pass
assert set(widgets.TEAMS) == {"Edmonton Oilers", "Adler Mannheim"}
assert widgets.TEAMS["Edmonton Oilers"]["next"] == 4 and widgets.TEAMS["Adler Mannheim"]["next"] == 3
for source in widgets.TEAMS.values():
    net_fetch.check_url(source["url"], widgets.ALLOWED_HOSTS)

# Das Netz-Hilfsprogramm spricht nur mit den erlaubten Hosts
try:
    widgets.fetch_json("https://example.com/v1/x")
    raise AssertionError
except HockeyError:
    pass
try:
    widgets.fetch_json("http://api-web.nhle.com/v1/x")
    raise AssertionError
except HockeyError:
    pass


# ---- Taegliche Ziele: kommen jeden Tag zurueck, als nicht erledigt
day = [date(2026, 10, 21)]
store = WidgetStore(folder / "d.json", today=lambda: day[0])
store.set_goals([{"text": "Gym", "done": True, "daily": True}, {"text": "Steuer", "done": True, "daily": False},
                 {"text": "Lesen", "done": False}])
assert [(g["text"], g["done"], g["daily"]) for g in store.get()["goals"]] == [
    ("Gym", True, True), ("Steuer", True, False), ("Lesen", False, False)], "daily ist optional"
day[0] = date(2026, 10, 22)
assert store.get()["goals"] == [{"text": "Gym", "done": False, "daily": True}], "nur taegliche Ziele, wieder offen"
store.set_goals(store.get()["goals"] + [{"text": "Neu", "done": False, "daily": False}])
day[0] = date(2026, 10, 23)
assert [g["text"] for g in store.get()["goals"]] == ["Gym"]
day[0] = date(2026, 10, 22)                       # derselbe Tag nochmal: nichts geht verloren
assert [g["text"] for g in store.get()["goals"]] == ["Gym", "Neu"]
try:
    store.set_goals([{"text": "a", "done": False, "daily": "ja"}])
    raise AssertionError
except ValueError:
    pass

# ---- Termine
day = [date(2026, 10, 21)]
store = WidgetStore(folder / "e.json", today=lambda: day[0])
a = store.add_event("  Zahnarzt  ", "2026-10-23", "14:30")
b = store.add_event("Geburtstag", "2026-10-23")
c = store.add_event("Frueh", "2026-10-23", "08:00")
d = store.add_event("Spaeter", "2026-12-01", "")
assert a["title"] == "Zahnarzt" and a["time"] == "14:30" and b["time"] == "" and len({a["id"], b["id"], c["id"]}) == 3
assert [e["title"] for e in store.events_on("2026-10-23")] == ["Geburtstag", "Frueh", "Zahnarzt"], "nach Uhrzeit, ganztaegig zuerst"
assert [e["title"] for e in store.upcoming_events(3)] == ["Geburtstag", "Frueh", "Zahnarzt"]
assert store.upcoming_events(10)[-1]["title"] == "Spaeter"
assert WidgetStore(folder / "e.json").get()["events"][0]["id"], "bleibt nach Neustart"
store.delete_event(a["id"])
assert "Zahnarzt" not in [e["title"] for e in store.get()["events"]]
for bad in ("zzz", None, 5):
    try:
        store.delete_event(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
bad_events = [
    (None, "2026-10-23", ""), ("", "2026-10-23", ""), ("   ", "2026-10-23", ""), ("x" * 101, "2026-10-23", ""),
    ("A", "23.10.2026", ""), ("A", "2026-13-01", ""), ("A", "2026-02-30", ""), ("A", None, ""), ("A", "2026-10-23", "25:00"),
    ("A", "2026-10-23", "9:00"), ("A", "2026-10-23", "14:60"), ("A", "2026-10-23", 5),
    ("A", "2020-01-01", ""), ("A", "2040-01-01", ""),
]
for title, day_, at in bad_events:
    try:
        store.add_event(title, day_, at)
        raise AssertionError((title, day_, at))
    except ValueError:
        pass
store.add_event("Gestern", "2026-10-20")                 # kleine Vergangenheit ist erlaubt
# Alte Termine (aelter als 31 Tage) werden beim naechsten Speichern aufgeraeumt
day[0] = date(2026, 12, 15)
store.add_event("Heute neu", "2026-12-16")
assert [e["title"] for e in store.get()["events"]] == ["Spaeter", "Heute neu"]
# Kaputte Eintraege in der Datei werden ignoriert
(folder / "x.json").write_text(json.dumps({"events": [1, {"title": "a"}, {"id": "i", "title": "T", "date": "2026-10-23", "time": ""},
                                                       {"id": "j", "title": "U", "date": "kaputt", "time": ""}]}), encoding="utf-8")
assert [e["title"] for e in WidgetStore(folder / "x.json").get()["events"]] == ["T"]
# Obergrenze
full = WidgetStore(folder / "full.json", today=lambda: date(2026, 10, 21))
(folder / "full.json").write_text(json.dumps({"events": [
    {"id": f"i{n}", "title": "t", "date": "2026-10-22", "time": ""} for n in range(widgets.MAX_EVENTS)]}), encoding="utf-8")
try:
    full.add_event("zu viel", "2026-10-22")
    raise AssertionError
except ValueError:
    pass
# Notizen/Ziele speichern darf Termine nicht loeschen und umgekehrt
store.set_notes("n"); store.set_goals([])
assert len(store.get()["events"]) == 2
store.add_event("Noch einer", "2026-12-17")
assert store.get()["notes"] == "n"

# ---- Berlin-Zeit ohne tzdata (EU-Sommerzeit)
from datetime import datetime, timezone
def utc(y, m, d, h, mi): return datetime(y, m, d, h, mi, tzinfo=timezone.utc)
assert widgets.berlin_to_utc(datetime(2026, 12, 25, 12, 0)) == utc(2026, 12, 25, 11, 0)       # Winter +1
assert widgets.berlin_to_utc(datetime(2026, 7, 1, 12, 0)) == utc(2026, 7, 1, 10, 0)           # Sommer +2
assert widgets.berlin_to_utc(datetime(2026, 3, 29, 1, 59)) == utc(2026, 3, 29, 0, 59)         # kurz vor Umstellung
assert widgets.berlin_to_utc(datetime(2026, 3, 29, 3, 0)) == utc(2026, 3, 29, 1, 0)           # danach Sommer
assert widgets.berlin_to_utc(datetime(2026, 10, 24, 23, 0)) == utc(2026, 10, 24, 21, 0)       # Samstag noch Sommer
assert widgets.berlin_to_utc(datetime(2026, 10, 25, 4, 0)) == utc(2026, 10, 25, 3, 0)         # danach Winter
assert widgets.berlin_to_utc(datetime(2027, 3, 28, 3, 0)) == utc(2027, 3, 28, 1, 0)           # anderes Jahr
assert widgets.berlin_to_utc(datetime(2027, 10, 31, 4, 0)) == utc(2027, 10, 31, 3, 0)

# ---- Kalenderdatei der Adler (Aufbau wie die echte Datei: TZID, DURATION, Zeilenumbruch mit Leerzeichen)
ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "BEGIN:VTIMEZONE", "TZID:Europe/Berlin", "BEGIN:DAYLIGHT", "DTSTART:19700329T020000", "END:DAYLIGHT", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:1", "SUMMARY:Adler Mannheim vs. Iserlohn Roosters",
    "DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20261011T190000", "DURATION:PT3H", "END:VEVENT",
    "BEGIN:VEVENT", "UID:2", "SUMMARY:Graz 99ers vs. Adler Mannheim", "DTSTART;TZID=Europe/Berlin;VALUE=DATE-TIME:20261021T180000",
    "DURATION:PT3H", "END:VEVENT",
    "BEGIN:VEVENT", "UID:3", "SUMMARY:Adler Mannheim vs. Straubing", "  Tigers", "DTSTART;TZID=Europe/Berlin:20261030T193000",
    "END:VEVENT",
    "BEGIN:VEVENT", "UID:4", "SUMMARY:Adler Mannheim vs. Utc\\, Team", "DTSTART:20261101T183000Z", "END:VEVENT",
    "BEGIN:VEVENT", "UID:5", "SUMMARY:Adler Mannheim vs. Fremd", "DTSTART;TZID=America/New_York:20261102T193000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:6", "SUMMARY:Teamabend", "DTSTART;TZID=Europe/Berlin:20261103T193000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:7", "SUMMARY:Adler Mannheim vs. Ganztag", "DTSTART;VALUE=DATE:20261104", "END:VEVENT",
    "BEGIN:VEVENT", "UID:8", "SUMMARY:Adler Mannheim vs. Kaputt", "DTSTART;TZID=Europe/Berlin:morgen", "END:VEVENT",
    "BEGIN:VEVENT", "UID:9", "DTSTART;TZID=Europe/Berlin:20261105T193000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:10", "SUMMARY:Adler Mannheim vs. Sommer", "DTSTART;TZID=Europe/Berlin:20261106T193000", "END:VEVENT",
    "END:VCALENDAR", ""])
now = utc(2026, 10, 21, 16, 30)                    # 18:30 Berlin: Graz-Spiel (18:00 Berlin) laeuft
games = widgets.parse_ics(ICS, "adler mannheim", now)
assert [g["home"]["name"] + "|" + g["away"]["name"] for g in games] == [
    "Adler Mannheim|Iserlohn Roosters", "Graz 99ers|Adler Mannheim", "Adler Mannheim|Straubing Tigers",
    "Adler Mannheim|Utc, Team", "Adler Mannheim|Sommer"], "Fremde Zeitzone, Ganztag, kaputt, ohne Gegner/Titel: uebersprungen"
assert [g["state"] for g in games] == ["final", "live", "future", "future", "future"]
assert [g["team_is_home"] for g in games] == [True, False, True, True, True]
assert games[1]["start"] == "2026-10-21T16:00:00Z", "18:00 Berlin im Oktober = 16:00 UTC"
assert games[2]["start"] == "2026-10-30T18:30:00Z" and games[3]["start"] == "2026-11-01T18:30:00Z"
assert games[4]["start"] == "2026-11-06T18:30:00Z", "ab 25.10. Winterzeit"
assert all(g["home"]["score"] is None and g["away"]["score"] is None for g in games)
# Beendet nach 3 Stunden
assert widgets.parse_ics(ICS, "adler mannheim", utc(2026, 10, 21, 19, 1))[1]["state"] == "final"
assert widgets.parse_ics(ICS, "adler mannheim", utc(2026, 10, 21, 15, 59))[1]["state"] == "future"
for junk in ("", "kein kalender", "BEGIN:VEVENT", "END:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:A vs. B"):
    assert widgets.parse_ics(junk, "adler mannheim", now) == []
picked = widgets.pick_games(games, widgets.TEAMS["Adler Mannheim"]["next"])
assert picked["current"]["state"] == "live" and len(picked["next"]) == 3

# Adler ueber HockeyFeed: drei naechste Spiele, kein Punktestand
feed = HockeyFeed(fetch=lambda url: ICS, clock=lambda: now.timestamp())
result = feed.get("Adler Mannheim")
assert result["scores"] is False and len(result["next"]) == 3 and result["current"]["state"] == "live"
assert HockeyFeed(fetch=lambda url: json.dumps(season), clock=lambda: 0).get("Edmonton Oilers")["scores"] is True

# ---- Weiterleitungen nur auf erlaubte Hosts (Regeln stehen in net_fetch, Test dort: test_net_fetch.py)
import urllib.request
redirects = net_fetch.SafeRedirects(widgets.ALLOWED_HOSTS)
req = urllib.request.Request("https://adler-mannheim.de/x")
for target in ("https://evil.example/x", "http://adler-mannheim.de/x", "file:///etc/passwd", "https://adler-mannheim.de.evil.example/"):
    try:
        redirects.redirect_request(req, None, 302, "Found", {}, target)
        raise AssertionError(target)
    except net_fetch.NetError:
        pass
assert redirects.redirect_request(req, None, 302, "Found", {}, "https://www.adler-mannheim.de/y") is not None

print("ALL TESTS PASSED")
