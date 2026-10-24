"""Tageslimit fuer kostenpflichtige Aufrufe (Mark 5, Step 1.4)."""

import contextlib
import io
import sys
import tempfile
import types
from datetime import date
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

import cost_guard
import guest
import jarvis as jarvis_module
import server
import speech
from cost_guard import LimitReached, UsageCounter
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())
day = [date(2026, 10, 22)]
limits = {"ai": 3, "speech": 2}
counter = UsageCounter(folder / "usage.json", lambda: dict(limits), today=lambda: day[0])

# 1) Zaehlen und Limit: der 4. Aufruf wird NICHT mehr durchgelassen
for _ in range(3):
    counter.check("ai")
    counter.count("ai")
try:
    counter.check("ai")
    raise AssertionError("Limit erreicht, check muss werfen")
except LimitReached as error:
    assert error.kind == "ai" and error.limit == 3
    assert "KI-Aufrufe" in str(error) and "3" in str(error) and "Limits" in str(error)
counter.check("speech")                      # anderes Limit, noch frei
assert counter.snapshot() == {"date": "2026-10-22", "ai": 3, "speech": 0, "limits": {"ai": 3, "speech": 2}}

# 2) Der Stand ueberlebt einen Neustart (neues Zaehler-Objekt, gleiche Datei)
again = UsageCounter(folder / "usage.json", lambda: dict(limits), today=lambda: day[0])
assert again.snapshot()["ai"] == 3

# 3) Neuer Tag: wieder bei 0
day[0] = date(2026, 10, 23)
assert counter.snapshot()["ai"] == 0
counter.check("ai")
day[0] = date(2026, 10, 22)

# 4) Limit 0 = kein Limit; Limit hochsetzen wirkt sofort
limits["ai"] = 0
counter.check("ai")
for _ in range(50):
    counter.count("ai")
counter.check("ai")
limits["ai"] = 10
try:
    counter.check("ai")
    raise AssertionError
except LimitReached:
    pass
limits["ai"] = 100
counter.check("ai")

# 5) Kaputte Datei: kein Absturz, Zaehler faengt bei 0 an
(folder / "kaputt.json").write_text("{nicht json", encoding="utf-8")
broken = UsageCounter(folder / "kaputt.json", lambda: {"ai": 1, "speech": 1}, today=lambda: day[0])
assert broken.snapshot()["ai"] == 0
broken.count("ai")
assert broken.snapshot()["ai"] == 1
(folder / "unsinn.json").write_text('{"date": "2026-10-22", "counts": {"ai": -5, "speech": "viel"}}', encoding="utf-8")
weird = UsageCounter(folder / "unsinn.json", lambda: {"ai": 1, "speech": 1}, today=lambda: day[0])
assert weird.snapshot()["ai"] == 0 and weird.snapshot()["speech"] == 0

# 6) Huelle um den Client: prueft vorher, zaehlt nachher, Fehler zaehlen nicht, Rest geht durch
calls = []


class FakeResponses:
    fail = False

    def create(self, **kw):
        calls.append(("ai", kw))
        if FakeResponses.fail:
            raise RuntimeError("Netz")
        return types.SimpleNamespace(output_text="ok")


class FakeSpeech:
    def create(self, **kw):
        calls.append(("speech", kw))
        return types.SimpleNamespace(content=b"MP3")


class FakeClient:
    responses = FakeResponses()
    audio = types.SimpleNamespace(speech=FakeSpeech(), transcriptions="x")
    models = "durchgereicht"


limits.update(ai=2, speech=1)
guarded = cost_guard.guard(FakeClient(), UsageCounter(folder / "huelle.json", lambda: dict(limits), today=lambda: day[0]))
assert guarded.responses.create(model="m", input="a").output_text == "ok"
FakeResponses.fail = True
try:
    guarded.responses.create(model="m", input="b")
except RuntimeError:
    pass
FakeResponses.fail = False
assert guarded.counter.snapshot()["ai"] == 1, "fehlgeschlagener Aufruf zaehlt nicht"
guarded.responses.create(model="m", input="c")
n = len(calls)
try:
    guarded.responses.create(model="m", input="d")
    raise AssertionError
except LimitReached:
    pass
assert len(calls) == n, "Bei erreichtem Limit geht NICHTS an OpenAI raus"
assert guarded.audio.speech.create(input="hallo").content == b"MP3"
try:
    guarded.audio.speech.create(input="nochmal")
    raise AssertionError
except LimitReached as error:
    assert "Sprachausgabe" in str(error)
assert guarded.models == "durchgereicht" and guarded.audio.transcriptions == "x"

# 7) Sprachausgabe: Limit wird eine verstaendliche Meldung (kein Klassenname)
try:
    speech.synthesize(guarded, "Guten Tag, Sir.", "Onyx (male)")
    raise AssertionError
except speech.SpeechError as error:
    assert "Tageslimit" in str(error) and "LimitReached" not in str(error)

# 8) Jarvis: feste Meldung, KEIN Traceback, keine offene Rueckfrage
j = object.__new__(jarvis_module.Jarvis)
j.pending_action = {"id": "x"}
j.pending_plan = None


def over_limit(message):
    raise LimitReached("ai", 500)


j._process_message = over_limit
err = io.StringIO()
with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
    result = j.process_message("Hallo")
assert err.getvalue() == "", err.getvalue()
assert result["status"] == "response" and "Tageslimit" in result["content"] and "500" in result["content"]
assert ", das Tageslimit" in result["content"], result["content"]
assert j.pending_action is None

# 9) Gast: eigene Meldung ohne Zahlen, eigener Zaehler
g = guest.GuestJarvis(FakeClient())
g._answer = over_limit
result = g.process_message("Hallo")
assert "ausgelastet" in result["content"] and "500" not in result["content"]
assert guest.GUEST_AI_CALLS_PER_DAY > 0

# 10) Einstellungen und Server: nur Zahlen von 0 bis 100000, Stand wird mitgeliefert
for key in ("ai_calls_per_day", "speech_calls_per_day"):
    check = server.EDITABLE_SETTINGS[("limits", key)]
    assert check(0) and check(500) and check(100000)
    assert not check(-1) and not check(100001) and not check("500") and not check(True) and not check(2.5)
settings = SettingsManager(folder / "s.json")
assert settings.get("limits", "ai_calls_per_day") == 500 and settings.get("limits", "speech_calls_per_day") == 200
fake = types.SimpleNamespace(guest=False, settings_manager=settings, cost_counter=counter)
state = server.settings_state(fake)
assert state["usage"]["date"] == "2026-10-22" and set(state["usage"]["limits"]) == {"ai", "speech"}
assert server.settings_state(types.SimpleNamespace(guest=True, settings_manager=settings))["usage"] is None

# 11) Zaehler-Dateien gehoeren nicht in Git
ignored = (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")
assert "usage.json" in ignored and "usage_guest.json" in ignored

print("ALL TESTS PASSED")
