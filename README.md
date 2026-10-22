# J.A.R.V.I.S. (Mark 5)

Persönlicher KI-Assistent: Python-Kern, OpenAI-Modell, Neon-PostgreSQL für
Erinnerungen, Projekte und Konversationen, Web-Oberfläche im Browser.

Stand, Roadmap und Entscheidungen: `PROJEKT_STATUS_MARK5.md` (Mark 4: `PROJEKT_STATUS_MARK4.md`).

## Voraussetzungen

- Windows, Python 3.13 (Start mit `py`)
- Ein OpenAI-API-Key
- Eine Neon-PostgreSQL-Datenbank (Verbindungs-URL)
- Optional: Brave-Search-API-Key (nur für die Websuche)

## Einrichten

Im Projektordner:

```
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
copy programs.example.json programs.json
```

1. `.env` öffnen und `OPENAI_API_KEY`, `DATABASE_URL` und `BRAVE_API_KEY` eintragen.
   Die `.env` gehört nie in Git.
2. `programs.json` öffnen und nur Programme eintragen, die Jarvis starten darf.
   Alles, was dort nicht steht (außer ein paar eingebauten Windows-Programmen),
   startet Jarvis nicht.
3. `settings.json` entsteht beim ersten Start von selbst. Der Text eines Projekts (`project.md`) liegt in der Datenbank; ansehen mit `py show_project.py` (Liste) bzw. `py show_project.py <ID>`.
   Die Tabellen in der Datenbank (Erinnerungen, Projekte, Konversationen, Nachrichten)
   legt Jarvis ebenfalls selbst an, eine leere Neon-Datenbank reicht.

## Starten

- Web-Oberfläche: `py server.py` oder Doppelklick auf `start_jarvis.bat`.
  Der Browser öffnet `http://127.0.0.1:8000`. Beenden mit Strg+C.
- Kommandozeile: `py main.py`

Der Server hört nur auf dem eigenen Rechner (`127.0.0.1`), er hat noch keinen Login.

- Gastmodus (nur plaudern, keine Aktionen, kein Gedächtnis): `py server.py --guest --port 8001`, siehe `DESIGN_GUEST.md`.
- Sprache und Weckwort brauchen Chrome oder Edge. Das Vorlesen mit der OpenAI-Stimme kostet ein paar Cent
  (Einstellungen → Voice; alles ist standardmäßig aus), siehe `DESIGN_VOICE.md`.
- Die Seitenleiste rechts (Uhr, Kalender, Notizen, Ziele, Eishockey) wählst du unter Einstellungen → Widgets,
  siehe `DESIGN_WIDGETS.md`. Notizen, Ziele und Termine liegen in `widgets.json` (nicht in Git).

## Tests

```
py run_tests.py        # kurze Übersicht
py run_tests.py -v     # mit Ausgabe jedes Tests
```

Die Tests brauchen weder Internet noch Datenbank noch API-Key. Die JavaScript-Tests brauchen Node.js (ohne Node
gibt es nur einen Hinweis). Stabilitätstest (simulierte Dauerlast mit Fehlern, kostet nichts):

```
py stabilitaetstest.py 300
```

Manuelle Abnahme: `ABNAHMETEST_MARK4.md` (Gesamtprüfung), Einzelheiten in `ABNAHMETEST_WEB.md` und `ABNAHMETEST_CLI.md`.
