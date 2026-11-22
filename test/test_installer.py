"""Mark 5 C5: Setup-Skript fuer die Gast-App. Kein Compiler hier (Inno Setup gibt es nur fuer Windows): geprueft wird, was drinsteht und was nie drinstehen darf."""
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
iss_path = PROJECT_DIR / "installer" / "jarvis_client.iss"
script = iss_path.read_text(encoding="utf-8")
sections = dict(re.findall(r"^\[(\w+)\]\n(.*?)(?=^\[\w+\]|\Z)", script, re.S | re.M))

# 1) Keine Rechte, keine Zugangsdaten, kein Server im Paket
assert "PrivilegesRequired=lowest" in sections["Setup"] and "admin" not in sections["Setup"].lower().replace("lowest", "")
files = [line for line in sections["Files"].splitlines() if line.strip() and not line.strip().startswith(";")]
assert len(files) == 1 and files[0].startswith('Source: "jarvis.ico"'), files          # nur das Symbol
body = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith((";", "//")))       # Kommentare duerfen "kein Python" sagen
for forbidden in (".env", "remote_devices", "profiles", "settings.json", "server.py", "python", "OPENAI", "sk-", "password", "token", "api_key", "usage.json"):
    assert forbidden.lower() not in body.lower(), forbidden
assert "[Registry]" not in script and "[INI]" not in script                              # nichts an Windows-Einstellungen
assert "[Run]" in script and "postinstall" in sections["Run"] and "skipifsilent" in sections["Run"]

# 2) Nur HTTPS zum Server, App-Fenster mit eigenem Profil
assert "--app=https://" in script and "--user-data-dir=" in script
assert len(re.findall(r"http://", script)) == 1 and "Pos('http://', Result)" in script   # nur zum Abschneiden einer eingefuegten Adresse
assert "--remote-debugging" not in script and "--no-sandbox" not in script and "--disable-web-security" not in script and "--ignore-certificate-errors" not in script
assert 'Name: "{app}\\Profil"' in sections["UninstallDelete"]

# 3) Adresse, Version, Symbol
host = re.search(r'#define DefaultHost "([^"]+)"', script).group(1)
assert "." in host and host not in ("localhost", "127.0.0.1") and host == host.lower() and " " not in host and host.endswith(".ts.net")
version = re.search(r'#define AppVersion "([^"]+)"', script).group(1)
assert version == re.search(r'^VERSION = "([^"]+)"', (PROJECT_DIR / "config.py").read_text(encoding="utf-8"), re.M).group(1)
icon = (PROJECT_DIR / "installer" / "jarvis.ico").read_bytes()
assert icon[:4] == b"\x00\x00\x01\x00" and int.from_bytes(icon[4:6], "little") >= 4 and len(icon) > 1000
assert "SetupIconFile=jarvis.ico" in script
assert "OutputBaseFilename=JarvisGast-Setup" in script

assert "--no-first-run" in script
assert "function EndsWithTailnet" in script and "'.ts.net'" in script and "if not EndsWithTailnet(Host) then" in script   # nur Tailscale-Adressen
# Pascal kennt nur, was weiter oben steht: jede Hilfsfunktion muss vor ihrer ersten Benutzung definiert sein
import re as _re
_defs = {m.group(2): m.start() for m in _re.finditer(r"^(function|procedure)\s+(\w+)", script, _re.M)}
for _name, _pos in _defs.items():
    for _m in _re.finditer(r"\b" + _name + r"\b", script[script.index("[Code]"):]):
        _at = script.index("[Code]") + _m.start()
        if _at < _defs[_name]:
            line = script[:_at].count("\n") + 1
            assert script[script.rfind("\n", 0, _at) + 1:_at].lstrip().startswith(("//", "{")), f"{_name} vor Definition (Zeile {line})"
assert "GetPreviousData('Host'" in script and "SetPreviousData(PreviousDataKey, 'Host'" in script and "procedure RegisterPreviousData" in script

# 4) Das Skript ist in sich schluessig (Pascal-Teil: begin/end, Anführungszeichen, Funktionen, die die Abschnitte benutzen)
code = sections["Code"]
assert len(re.findall(r"\bbegin\b", code, re.I)) == len(re.findall(r"\bend\b", code, re.I))
for line_no, line in enumerate(script.splitlines(), 1):
    if not line.lstrip().startswith(";") and not line.lstrip().startswith("//"):
        assert line.count('"') % 2 == 0, (line_no, line)
        assert line.count("'") % 2 == 0, (line_no, line)
for name in re.findall(r"\{code:(\w+)\}", script):
    assert re.search(rf"function {name}\(Param: String\): String;", code), name           # jede {code:...}-Funktion gibt es mit der richtigen Form
for name in ("InitializeSetup", "InitializeWizard", "NextButtonClick", "HostLooksValid", "CleanHost", "TailscaleInstalled"):
    assert re.search(rf"(function|procedure) {name}\b", code), name
assert "CreateInputQueryPage(wpWelcome" in code and "HostPage.Values[0]" in code
for browser in ("msedge.exe", "chrome.exe"):
    assert browser in code
assert "tailscale.com/download" in code and "MB_YESNO" in code                          # fehlt Tailscale, wird gefragt (nicht verboten)
# Adresse pruefen: nur Kleinbuchstaben, Ziffern, Punkt, Bindestrich
assert "(C = '.') or (C = '-')" in code and "(C >= 'a') and (C <= 'z')" in code

# 5) Anleitung und .gitignore-Hinweis
guide = (PROJECT_DIR / "ANLEITUNG_GASTAPP.md").read_text(encoding="utf-8")
for needle in ("JarvisGast-Setup.exe", "Inno Setup", "SmartScreen", "Tailscale", "Gast-Bereich", "installer/output/"):
    assert needle in guide, needle

print("ALL TESTS PASSED")
