"""Webseite im Browser oeffnen (Mark 5, Step 2.26): nur https, feste Regeln fuer Adressen, immer erst fragen."""
import sys
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

import abilities
import action_executor
import guest
import risk
import task_executor
import tools.browser_tool as bt
from action import Action
from task_registry import TaskRegistry
from tasks import register_all_tasks

opened = []
state = {"result": True}


def fake_open(target):
    opened.append(target)
    if isinstance(state["result"], Exception):
        raise state["result"]
    return state["result"]


bt._open = fake_open

# 1) Gute Adressen (und was daraus wird)
GOOD = {
    "youtube.com": "https://youtube.com",
    "www.youtube.com/watch?v=abc": "https://www.youtube.com/watch?v=abc",
    "https://www.wikipedia.org": "https://www.wikipedia.org",
    "HTTPS://GitHub.com/Foo": "https://github.com/Foo",
    "http://example.org/x": "https://example.org/x",           # http wird zu https
    "//cdn.example.org/a": "https://cdn.example.org/a",
    "a.com:443/x": "https://a.com/x",
    "https://a.com/%41?x=1&y=2#frag": "https://a.com/%41?x=1&y=2#frag",
    "  https://de.wikipedia.org/wiki/K%C3%B6ln  ": "https://de.wikipedia.org/wiki/K%C3%B6ln",
    "https://münchen.de/ä?q=ö#x": "https://xn--mnchen-3ya.de/%C3%A4?q=%C3%B6#x",
    "https://xn--mnchen-3ya.de": "https://xn--mnchen-3ya.de",
    "sub.domain.co.uk": "https://sub.domain.co.uk",
}
for raw, expected in GOOD.items():
    assert bt.normalize_url(raw) == (expected, None), (raw, bt.normalize_url(raw))

# 2) Schlechte Adressen: nichts davon wird je geoeffnet
BAD = ["javascript:alert(1)", "JavaScript:alert(1)", "file:///C:/Windows/system32/calc.exe", "file://C:/x", "data:text/html,<script>1</script>",
       "ms-settings:", "steam://run/1", "ftp://a.com/x", "mailto:a@b.de", "vbscript:x", "file://a.com/x", "FILE://a.com/x", "javascript://a.com/%0Aalert(1)", "data://a.com/x", "ftp://a.com/x", "ws://a.com/x", "wss://a.com/x", "about:blank", "chrome://settings", "tel:123",
       "https:evil.com", "http:evil.com", "https://user:pw@a.com", "https://user@a.com", "https://a.com@evil.com", "https://a.com:8443", "a.com:80",
       "https://localhost/", "localhost", "https://127.0.0.1/", "https://192.168.0.1/", "https://[::1]/", "https://10.0.0.1:443/", "http://2130706433/",
       "https://intranet", "https://server/", "https://a.local", "https://printer.lan/", "https://x.internal", "https://router.home.arpa", "https://a.test", "https://a.example",
       "https://-a.com", "https://a-.com", "https://a..com", "https://a.c", "https://a.b1", "https://.com", "https://a.com.", "https://a_b.com",
       "a.com b", "a.com\tb", "a.com\nb", "a.com\x00", "https://a.com/\x07", "https://" + "a" * 64 + ".com", "https://a.com/" + "x" * 2100,
       "", "   ", None, 5, {"x": 1}, ["a.com"], "a.com:abc", "https://", "https:///a.com", "/etc/passwd", "C:\\Windows\\notepad.exe", "\\\\server\\share"]
for raw in BAD:
    url, error = bt.normalize_url(raw)
    assert url is None and error, repr(raw)[:60]
assert "https" in bt.normalize_url("javascript:alert(1)")[1] and "Benutzername" in bt.normalize_url("https://u:p@a.com")[1]
assert "Port" in bt.normalize_url("https://a.com:8443")[1] and "Adresse nennen" not in bt.normalize_url("")[1] and "Nenne eine Adresse" in bt.normalize_url("")[1]

# 3) Suche
assert bt.build_search("Katzenvideos") == ("https://www.google.com/search?q=Katzenvideos", None)
assert bt.build_search("katzen & hunde  äö?") == ("https://www.google.com/search?q=katzen+%26+hunde+%C3%A4%C3%B6%3F", None)
assert bt.build_search("a=b&c=d#x")[0] == "https://www.google.com/search?q=a%3Db%26c%3Dd%23x", "Sonderzeichen koennen die Adresse nicht veraendern"
assert bt.build_search("x\u200by")[0].endswith("q=xy")
for bad in ("", "   ", None, 5, "x" * 300):
    assert bt.build_search(bad)[0] is None, bad
assert bt.build_search("x" * 200)[0] is not None

# 4) resolve: Adresse vor Suche; nichts -> Frage
assert bt.resolve("youtube.com", "Katzen") == ("https://youtube.com", "website", None)
assert bt.resolve("", "Katzen")[1] == "search" and bt.resolve(None, "Katzen")[1] == "search" and bt.resolve({"description": "x"}, "Katzen")[1] == "search"
assert bt.resolve("", "")[2] and bt.resolve(None, None)[2] and bt.resolve("javascript:1", "Katzen")[0] is None, "eine ungueltige Adresse wird nicht durch die Suche ersetzt"
assert bt.check("youtube.com") is None and bt.check("", "x") is None and bt.check("javascript:1") and bt.check("", "")

# 5) Oeffnen
opened.clear()
r = bt.open_website("youtube.com")
assert r.success and opened == ["https://youtube.com"] and r.data == {"kind": "website", "host": "youtube.com", "url": "https://youtube.com", "done": "Seite im Browser geöffnet"}
opened.clear()
r = bt.open_website("", "Katzen & Hunde")
assert r.success and opened == ["https://www.google.com/search?q=Katzen+%26+Hunde"] and r.data["kind"] == "search" and r.data["host"] == "www.google.com" and "url" not in r.data
opened.clear()
for bad in ("javascript:alert(1)", "file:///C:/x", "https://127.0.0.1", "https://a.com:8443", "", None):
    r = bt.open_website(bad) if bad else bt.open_website(bad, "")
    assert not r.success and r.error, bad
assert opened == [], "ungueltige Adressen erreichen den Browser nie"
state["result"] = False
r = bt.open_website("a.com")
assert not r.success and "Browser" in r.error
state["result"] = RuntimeError("kaputt C:\\geheim")
r = bt.open_website("a.com")
assert not r.success and "geheim" not in r.error and "kaputt" not in r.error
state["result"] = True

# 6) Rueckfrage zeigt Host und volle Adresse; Fehler -> neutrale Zeile
lines = bt.describe("https://www.youtube.com/watch?v=abc")
assert lines[0] == "Seite: www.youtube.com" and lines[1] == "Adresse: https://www.youtube.com/watch?v=abc" and "neuen Tab" in lines[2]
assert bt.describe("münchen.de")[0] == "Seite: xn--mnchen-3ya.de", "Umlaut-Adressen zeigt die Rueckfrage in der xn--Schreibweise"
long_lines = bt.describe("https://a.com/" + "x" * 500)
assert len(long_lines[1]) <= len("Adresse: ") + 200 and long_lines[1].endswith("...")
s_lines = bt.describe("", "Katzen\u200bvideos")
assert s_lines == ["Im Browser suchen nach: Katzenvideos", "Suchmaschine: www.google.com"]
assert bt.describe("javascript:1") == ["Im Browser öffnen"]
assert bt.describe("a.com", "ignoriert")[0] == "Seite: a.com"

# 7) Einbindung: Risiko (immer fragen), Aufgabe, Executor, Faehigkeit, Gast, Aktionsprotokoll-Rueckfrage
registry = TaskRegistry()
register_all_tasks(registry)
task = next(t for t in registry.get_all() if t.task_type == "OPEN_WEBSITE")
assert [a.name for a in task.actions] == ["open_website"]
assert risk.task_risk(task) == risk.CONFIRM and risk.ACTION_RISK["open_website"] == risk.CONFIRM
task.actions[0].parameters = {"url": "youtube.com", "query": ""}
goal, details = risk.describe_task(task)
assert goal == "Im Browser öffnen" and details[0] == "Seite: youtube.com" and "Beispiel" not in " ".join(details) and "Öffne youtube" not in " ".join(details)
opened.clear()
task_executor.execute_task(task, confirmed=False)
assert task.status == "BLOCKED" and opened == [], "ohne Ja wird nichts geoeffnet"
task_executor.execute_task(task, confirmed=True)
assert task.status == "COMPLETED" and opened == ["https://youtube.com"]
res = action_executor.execute_action(Action("open_website", {"url": "", "query": "Wetter"}))
assert res.success and res.data["kind"] == "search"
browser = next(a for a in abilities.ABILITIES if a.id == "browser")
assert browser.default is True and browser.tasks == ("OPEN_WEBSITE",)
assert "OPEN_WEBSITE" not in guest.GUEST_TASKS

# Auch wenn das Modell etwas Boeses vorschlaegt, bleibt es bei der Pruefung vor der Rueckfrage (Jarvis.prepare_note)
import jarvis as jarvis_module
fake_self = types.SimpleNamespace()
reg2 = TaskRegistry()
register_all_tasks(reg2)
bad_task = next(t for t in reg2.get_all() if t.task_type == "OPEN_WEBSITE")
bad_task.actions[0].parameters = {"url": "javascript:alert(1)", "query": ""}
assert "https" in jarvis_module.Jarvis.prepare_note(fake_self, bad_task)
bad_task.actions[0].parameters = {"url": "youtube.com", "query": ""}
assert jarvis_module.Jarvis.prepare_note(fake_self, bad_task) is None
bad_task.actions[0].parameters = {"url": {"description": "x", "type": "string"}, "query": {"description": "y", "type": "string"}}
assert jarvis_module.Jarvis.prepare_note(fake_self, bad_task), "Schema-Platzhalter zaehlen als leer: Rueckfrage nach der Seite"

# Das Modul hat keinen Weg, Programme zu starten oder etwas zu laden
source = open(PROJECT_DIR / "tools" / "browser_tool.py", encoding="utf-8").read()
code = source.split('"""', 2)[2]
for forbidden in ("os.startfile", "subprocess", "os.system", "shell=True", "urlopen", "requests", "net_fetch", "eval(", "exec("):
    assert forbidden not in code, forbidden

print("ALL TESTS PASSED")
