"""Klingeln (2.11): Ringer, Sirene (mit Fake-winsound), Kurzbefehle, Auto-Ende, Timer-Hook."""

import io
import sys
import tempfile
import time
import wave
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import background_tasks
import ringing
import timer
from ringing import Ringer, Siren, handle_message, stop_intent


class FakeWinsound:
    SND_FILENAME, SND_ASYNC, SND_LOOP, SND_PURGE = 1, 2, 8, 64

    def __init__(self):
        self.calls = []

    def PlaySound(self, what, flags):
        self.calls.append((what, flags))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


tmp = Path(tempfile.mkdtemp())

# 1) WAV: gültiges, kurzes Mono-16-Bit-Muster
data = ringing.make_wav_bytes()
with wave.open(io.BytesIO(data)) as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 8000)
    seconds = w.getnframes() / w.getframerate()
    assert 1.3 < seconds < 2.0, seconds                       # 3 x (0,18 + 0,10) + 0,80 = 1,64 s
    frames = w.readframes(w.getnframes())
assert max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True)) for i in range(0, len(frames), 2)) > 5000   # nicht stumm

# 2) Sirene: Endlosschleife starten, nur einmal, stoppen
fake = FakeWinsound()
siren = Siren(player=fake, folder=tmp)
assert siren.available and siren.start() is True and siren.start() is False       # zweiter Start: nichts doppelt
assert len(fake.calls) == 1
path, flags = fake.calls[0]
assert Path(path).exists() and flags == fake.SND_FILENAME | fake.SND_ASYNC | fake.SND_LOOP
siren.stop()
siren.stop()                                                                      # zweites Stop ist harmlos
assert fake.calls[-1] == (None, fake.SND_PURGE) and len(fake.calls) == 2 and not siren.playing
assert Siren(player=None).__class__ is Siren                                      # ohne winsound (Linux): kein Absturz
silent = Siren(player=None)
silent.player = None
assert silent.start() is False

class Broken(FakeWinsound):
    def PlaySound(self, what, flags):
        raise RuntimeError("kein Audiogerät")

assert Siren(player=Broken(), folder=tmp).start() is False                       # Fehler werden abgefangen, nicht geworfen

# 3) Ringer: läuten, auflisten, ausschalten
clock, fake = Clock(), FakeWinsound()
ringer = Ringer(siren=Siren(player=fake, folder=tmp), clock=clock)
assert not ringer.is_ringing() and ringer.active() == [] and ringer.stop() == []
a = ringer.start("alarm", "Wecker", briefing=True)
t = ringer.start("timer", "Nudeln\n  mit   Soße " + "x" * 100)
assert a["id"] == 1 and t["id"] == 2 and len(t["label"]) <= ringing.MAX_LABEL_LENGTH and "\n" not in t["label"]
assert ringer.start("timer", "") ["label"] == "Timer" and ringer.start("alarm", None)["label"] == "Wecker"
assert len([c for c in fake.calls if c[1] & fake.SND_LOOP]) == 1                  # eine Sirene für alle
clock.t += 65
rows = ringer.active()
assert [r["id"] for r in rows] == [1, 2, 3, 4] and rows[0]["seconds"] == 65 and rows[0]["remaining"] == 600 - 65
v = ringer.version
state = ringer.state()
assert state["sound"] == "Computer" and state["server_sound"] is True and len(state["ringing"]) == 4
try:
    ringer.start("musik", "x")
    raise AssertionError("unbekannte Art muss abgelehnt werden")
except ValueError:
    pass

stopped = ringer.stop(which=2)
assert [r["id"] for r in stopped] == [2] and ringer.version > v and fake.calls[-1][0] != None   # Sirene läuft weiter
assert ringer.stop(which=99) == []
stopped = ringer.stop(kind="timer")
assert [r["id"] for r in stopped] == [3]
stopped = ringer.stop(kind="timer")                      # kein Timer mehr, aber Wecker läutet: "Timer aus" meint "Ruhe"
assert sorted(r["id"] for r in stopped) == [1, 4]
assert not ringer.is_ringing() and fake.calls[-1] == (None, fake.SND_PURGE)         # Ton aus, sobald nichts mehr läutet

# 4) Obergrenze
for _ in range(ringing.MAX_RINGING):
    assert ringer.start("timer", "x") is not None
assert ringer.start("timer", "zu viel") is None
ringer.stop()

# 5) Auto-Ende nach max_minutes + Meldung im Hintergrund
background_tasks.get_results()
ringer.configure(max_minutes=2)
ringer.start("alarm", "Aufstehen")
clock.t += 119
assert ringer.expire() == [] and ringer.is_ringing()
clock.t += 1
gone = ringer.expire()
assert [r["label"] for r in gone] == ["Aufstehen"] and not ringer.is_ringing()
msgs = background_tasks.get_results()
assert msgs == [{"type": "RINGING_EXPIRED", "data": {"label": "Aufstehen", "kind": "alarm", "minutes": 2}}], msgs

# 6) Einstellungen: ungültige Werte werden ignoriert, "Browser"/"Aus" schalten die Computer-Sirene ab
ringer.configure(max_minutes=0, snooze_minutes=999, sound="Laut", ring_timers="ja")
assert (ringer.max_minutes, ringer.snooze_minutes, ringer.sound, ringer.ring_timers) == (2, 5, "Computer", True)
ringer.configure(max_minutes=True, snooze_minutes=False)
assert (ringer.max_minutes, ringer.snooze_minutes) == (2, 5)                      # bool ist keine Zahl
ringer.start("alarm", "x")
assert ringer.siren.playing
ringer.configure(sound="Browser")
assert not ringer.siren.playing and ringer.is_ringing() and ringer.state()["server_sound"] is False
ringer.start("alarm", "y")
assert not ringer.siren.playing                                                   # im Browser-Modus nie Server-Ton
ringer.configure(sound="Computer")
assert ringer.siren.playing                                                       # zurückgeschaltet: läutet wieder
ringer.configure(sound="Aus")
assert not ringer.siren.playing and ringer.is_ringing()                           # Aus: leise, aber sichtbar (Banner)
ringer.stop()
ringer.configure(sound="Computer", max_minutes=10)

# 7) Kurzbefehle: erkannt
yes_stop = ["Wecker aus", "Jarvis, Wecker aus!", "wecker aus.", "Stopp", "stop", "aus", "Alles aus", "Timer aus",
            "mach den Timer aus", "stell den Wecker aus", "hey Jarvis stell bitte den Wecker aus", "Wecker stoppen",
            "Alarm ausschalten", "Jarvis bitte Wecker ausschalten", "Ruhe", "Wecker abstellen", "den Wecker bitte aus"]
for m in yes_stop:
    assert stop_intent(m) is not None and stop_intent(m)[0] == "stop", m
assert stop_intent("Wecker aus")[1] == "alarm" and stop_intent("Alarm aus")[1] == "alarm"
assert stop_intent("Timer aus")[1] == "timer" and stop_intent("Stopp")[1] is None and stop_intent("Alles aus")[1] is None
assert stop_intent("Schlummern") == ("snooze", None, None) and stop_intent("snooze 10 min") == ("snooze", None, 10)
assert stop_intent("noch 5 Minuten") == ("snooze", None, 5) and stop_intent("Jarvis, noch 10 min") == ("snooze", None, 10)

# 8) Kurzbefehle: NICHT erkannt (gehen zum Router, damit nichts Falsches ausgeht)
for m in ["stopp die Musik", "stell die Lautstärke auf 30", "Wecker um 7 Uhr", "mach das Licht aus", "wie spät ist es",
          "der Wecker soll morgen früh aus bleiben weil ich frei habe", "Wecker", "", "   ", "Timer 5 Minuten", "lösche den Wecker",
          "danke Jarvis", "noch 5 Euro", "aus Berlin", None, 42, ["aus"], "aus " * 40]:
    assert stop_intent(m) is None, m

# 9) handle_message: nur wenn etwas läutet
fake = FakeWinsound()
ringer = Ringer(siren=Siren(player=fake, folder=tmp), clock=Clock())
assert handle_message("Wecker aus", "Sir", ringer) is None                        # nichts läutet: normaler Weg
assert handle_message("Stopp", "Sir", ringer) is None
ringer.briefing_provider = lambda: "Heute: 3 Termine."
ringer.start("alarm", "Wecker", briefing=True)
assert handle_message("Wie spät ist es", "Sir", ringer) is None and ringer.is_ringing()   # andere Nachricht: läutet weiter
reply = handle_message("Jarvis, Wecker aus", "Sir", ringer)
assert reply == "Sir, Wecker aus. Heute: 3 Termine." and not ringer.is_ringing(), reply
assert fake.calls[-1] == (None, fake.SND_PURGE)

ringer.start("alarm", "Wecker", briefing=False)
assert handle_message("Wecker aus", "Sir", ringer) == "Sir, Wecker aus."          # ohne Briefing-Wunsch kein Briefing
ringer.start("alarm", "Zähneputzen", briefing=True)
assert handle_message("Wecker aus", "Sir", ringer) == "Sir, Wecker aus (Zähneputzen). Heute: 3 Termine."
ringer.start("timer", "Nudeln")
assert handle_message("Timer aus", "Sir", ringer) == "Sir, Timer aus (Nudeln)."
ringer.start("timer", "Nudeln")
ringer.start("alarm", "Wecker")
reply = handle_message("alles aus", "Sir", ringer)
assert reply.startswith("Sir, Alles aus (Nudeln, Wecker).") and not ringer.is_ringing(), reply

# Briefing-Fehler legt das Ausschalten nicht lahm
ringer.briefing_provider = lambda: 1 / 0
ringer.start("alarm", "Wecker", briefing=True)
assert handle_message("Wecker aus", "Sir", ringer) == "Sir, Wecker aus." and not ringer.is_ringing()

# 10) Schlummern: Handler bekommt Eintrag + Minuten; ohne Handler wird nur ausgeschaltet
plans = []
ringer.snooze_handler = lambda ring, minutes: plans.append((ring["kind"], ring["label"], minutes))
ringer.start("alarm", "Wecker")
assert handle_message("schlummern", "Sir", ringer) == "Sir, ich wecke dich in 5 Minuten wieder."
assert plans == [("alarm", "Wecker", 5)] and not ringer.is_ringing()
ringer.start("timer", "Ei")
assert handle_message("noch 1 Minute", "Sir", ringer) == "Sir, ich wecke dich in 1 Minute wieder." and plans[-1] == ("timer", "Ei", 1)
ringer.start("alarm", "Wecker")
stopped, minutes = ringer.snooze(500)
assert minutes == ringing.MAX_SNOOZE_MINUTES and plans[-1][2] == 60                 # Obergrenze
ringer.start("alarm", "Wecker")
stopped, minutes = ringer.snooze("abc")
assert minutes == 5                                                                  # Unsinn -> Standard
ringer.snooze_handler = lambda ring, minutes: 1 / 0
ringer.start("alarm", "Wecker")
stopped, _ = ringer.snooze()
assert len(stopped) == 1 and not ringer.is_ringing()                                 # kaputter Handler: trotzdem aus
ringer.snooze_handler = None
ringer.start("alarm", "Wecker")
ringer.snooze()
assert not ringer.is_ringing()

# 11) Timer-Hook: ein abgelaufener Timer läutet (wenn eingeschaltet)
ringing.set_default_ringer(Ringer(siren=Siren(player=FakeWinsound(), folder=tmp)))
background_tasks.get_results()
entry = timer.start_timer(0.05, "Pizza")
deadline = time.time() + 3
while not ringing.default_ringer().is_ringing() and time.time() < deadline:
    time.sleep(0.02)
rows = ringing.default_ringer().active()
assert len(rows) == 1 and rows[0]["kind"] == "timer" and rows[0]["label"] == "Pizza", rows
msgs = background_tasks.get_results()
assert [m["type"] for m in msgs] == ["TIMER_FINISHED"] and msgs[0]["data"]["name"] == "Pizza"      # Meldung kommt weiterhin
ringing.default_ringer().stop()

ringing.default_ringer().configure(ring_timers=False)
timer.start_timer(0.05, "Still")
time.sleep(0.5)
assert not ringing.default_ringer().is_ringing()                                      # aus = wie bisher: nur die Meldung
assert [m["data"]["name"] for m in background_tasks.get_results()] == ["Still"]

# abgebrochener Timer läutet nie
ringing.default_ringer().configure(ring_timers=True)
timer.cancel_timer_by_id(timer.start_timer(0.2, "Abbruch").id)
time.sleep(0.5)
assert not ringing.default_ringer().is_ringing() and background_tasks.get_results() == []

# 12) Takt-Thread: beendet Zu-Lange-Läutende von selbst; doppelter Start ergibt einen Thread
clock = Clock()
ringing.set_default_ringer(Ringer(siren=Siren(player=FakeWinsound(), folder=tmp), clock=clock))
ringing.default_ringer().configure(max_minutes=1)
ringing.default_ringer().start("alarm", "Lang")
first = ringing.start_ticker(interval=0.02)
assert ringing.start_ticker(interval=0.02) is first
clock.t += 61
deadline = time.time() + 3
while ringing.default_ringer().is_ringing() and time.time() < deadline:
    time.sleep(0.02)
assert not ringing.default_ringer().is_ringing()
assert [m["type"] for m in background_tasks.get_results()] == ["RINGING_EXPIRED"]
ringing.default_ringer().start("timer", "Beim Beenden")
ringing.stop_ticker()
assert not ringing.default_ringer().is_ringing()                                      # Server beendet -> Ton aus
first.join(timeout=2)
assert not first.is_alive()

print("ALL TESTS PASSED")
