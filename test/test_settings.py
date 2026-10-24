"""Einstellungen und Anrede (Step 3.4)."""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import personality
from settings_manager import SettingsManager

folder = Path(tempfile.mkdtemp())

# 1) Neue Datei: genau die Einstellungen, die etwas bewirken
sm = SettingsManager(folder / "neu.json")
assert sm.get_all() == {
    "appearance": {"theme": "Dark", "accent_color": "J.A.R.V.I.S. Blue", "font_size": 13},
    "jarvis": {"address": "Sir", "home_place": "Mannheim"},
    "memory": {"enabled": True},
    "voice": {"output": False, "engine": "OpenAI", "voice": "Onyx (male)", "speed": "Normal", "input": False, "input_language": "German", "wake_word": False},
    "widgets": {"top": "Clock", "middle": "Notes", "bottom": "Off", "fourth": "Off", "fifth": "Off"},
    "abilities": {"web_search": True, "weather": True, "news": True, "wikipedia": True, "translate": True, "reminders": True, "worldtime": True, "convert": True, "pages": True, "timers": True, "calendar": True, "volume": True, "programs": True, "files": True},
    "news": {"tagesschau": True, "heise": True, "spiegel": False, "sportschau": False, "espn_nhl": False, "oilersnation": False, "gnews": False, "bingnews": False, "bbc": False},
    "limits": {"ai_calls_per_day": 500, "speech_calls_per_day": 200},
}
assert json.loads((folder / "neu.json").read_text(encoding="utf-8")) == sm.get_all()

# 2) Alte settings.json (Mark 3): Entfernte Einstellungen werden verworfen,
#    gueltige Werte bleiben
old = {
    "general": {"language": "Deutsch", "startup_behavior": "Normal startup", "confirmations": False},
    "appearance": {"theme": "Light", "accent_color": "Custom", "font_size": 17, "ui_scale": "125 %"},
    "jarvis": {"name": "Friday", "address": "Chef", "personality": "Casual"},
    "voice": {"speed": 150},
    "memory": {"enabled": False},
    "unbekannt": {"x": 1},
}
(folder / "alt.json").write_text(json.dumps(old), encoding="utf-8")
sm = SettingsManager(folder / "alt.json")
assert sm.get_all() == {
    "appearance": {"theme": "Light", "accent_color": "Custom", "font_size": 17},
    "jarvis": {"address": "Chef", "home_place": "Mannheim"},
    "memory": {"enabled": False},
    "voice": {"output": False, "engine": "OpenAI", "voice": "Onyx (male)", "speed": "Normal", "input": False, "input_language": "German", "wake_word": False},
    "widgets": {"top": "Clock", "middle": "Notes", "bottom": "Off", "fourth": "Off", "fifth": "Off"},
    "abilities": {"web_search": True, "weather": True, "news": True, "wikipedia": True, "translate": True, "reminders": True, "worldtime": True, "convert": True, "pages": True, "timers": True, "calendar": True, "volume": True, "programs": True, "files": True},
    "news": {"tagesschau": True, "heise": True, "spiegel": False, "sportschau": False, "espn_nhl": False, "oilersnation": False, "gnews": False, "bingnews": False, "bbc": False},
    "limits": {"ai_calls_per_day": 500, "speech_calls_per_day": 200},
}, sm.get_all()
# ... und die Datei selbst ist bereinigt
assert json.loads((folder / "alt.json").read_text(encoding="utf-8")) == sm.get_all()

# 2b) Falsche Typen oder Werte in der Datei werden verworfen
bad = {"voice": {"output": "ja", "speed": "Turbo", "input": 1}, "memory": {"enabled": "nein"}}
(folder / "falsch.json").write_text(json.dumps(bad), encoding="utf-8")
sm = SettingsManager(folder / "falsch.json")
assert sm.get("voice", "output") is False and sm.get("voice", "speed") == "Normal"
assert sm.get("voice", "input") is False and sm.get("memory", "enabled") is True
(folder / "gut.json").write_text(json.dumps({"voice": {"output": True, "speed": "Fast", "input": True}}), encoding="utf-8")
gut = SettingsManager(folder / "gut.json").get_category("voice")
assert gut == {"output": True, "engine": "OpenAI", "voice": "Onyx (male)", "speed": "Fast",
               "input": True, "input_language": "German", "wake_word": False}, gut
(folder / "gut2.json").write_text(json.dumps({"voice": {"engine": "Browser", "voice": "Nova (female)",
                                                        "input_language": "English"}}), encoding="utf-8")
gut = SettingsManager(folder / "gut2.json").get_category("voice")
assert (gut["engine"], gut["voice"], gut["input_language"]) == ("Browser", "Nova (female)", "English")
(folder / "schlecht.json").write_text(json.dumps({"voice": {"engine": "Google", "voice": "Darth (male)",
                                                            "input_language": "Klingon"}}), encoding="utf-8")
schlecht = SettingsManager(folder / "schlecht.json").get_category("voice")
assert (schlecht["engine"], schlecht["voice"], schlecht["input_language"]) == ("OpenAI", "Onyx (male)", "German")

# 3) Kaputte oder fremde Datei -> Standardwerte
(folder / "kaputt.json").write_text("{nicht json", encoding="utf-8")
assert SettingsManager(folder / "kaputt.json").get("jarvis", "address") == "Sir"
(folder / "liste.json").write_text("[1, 2]", encoding="utf-8")
assert SettingsManager(folder / "liste.json").get("memory", "enabled") is True
(folder / "typ.json").write_text(json.dumps({"jarvis": "Sir", "memory": 5}), encoding="utf-8")
assert SettingsManager(folder / "typ.json").get_all()["jarvis"] == {"address": "Sir", "home_place": "Mannheim"}

# 4) set/get/reset
sm = SettingsManager(folder / "set.json")
sm.set("jarvis", "address", "Boss")
assert SettingsManager(folder / "set.json").get("jarvis", "address") == "Boss"
sm.reset()
assert sm.get("jarvis", "address") == "Sir"

# 5) Anrede: Standard, setzen, ungueltig -> "Sir"
assert personality.get_address() == "Sir"
personality.set_address("Chef")
assert personality.get_address() == "Chef"
for bad in ("", "  ", " Chef", "Chef ", "a\nb", "x" * 31, 5, None, ["Sir"]):
    assert not personality.is_valid_address(bad), bad
    personality.set_address(bad)
    assert personality.get_address() == "Sir", bad
assert personality.is_valid_address("x" * 30) and personality.is_valid_address("Herr Doktor")
assert personality.is_valid_address("Mäxchen") and personality.is_valid_address("Chefin")

# 6) Der Prompt benutzt die aktuelle Anrede und bleibt sonst gleich
personality.set_address("Chef")
text = personality.jarvis_personality()
assert "address me as Chef" in text and "Sir" not in text
personality.set_address("Sir")
assert personality.jarvis_personality() == personality.JARVIS_PERSONALITY
assert "address me as Sir and not by my name" in personality.JARVIS_PERSONALITY

# Schalter fuer Faehigkeiten: gueltige Werte bleiben, falsche Typen und unbekannte Namen fliegen raus
(folder / "faehig.json").write_text(json.dumps({"abilities": {"web_search": False, "timers": "nein", "gibtsnicht": True}}), encoding="utf-8")
sm = SettingsManager(folder / "faehig.json")
assert sm.get("abilities", "web_search") is False
assert sm.get("abilities", "timers") is True, "Text statt Wahrheitswert wird verworfen"
assert "gibtsnicht" not in sm.get_category("abilities")

print("ALL TESTS PASSED")
