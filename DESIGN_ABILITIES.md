# Wie baue ich eine neue Fähigkeit? (Mark 5, Step 1.1)

Eine **Fähigkeit** ist etwas, das Jarvis auf Zuruf tun kann: Wetter sagen, einen Termin eintragen, einen
Timer stellen. Dieses Dokument ist die Checkliste dafür. Wer sie abarbeitet, baut keine halbe Fähigkeit.
Der Test `test/test_abilities_contract.py` prüft die wichtigsten Punkte automatisch.

## So läuft eine Fähigkeit durch Jarvis

```
Nachricht ──> Router (KI) ──> Aufgabe (Task) mit Parametern
                                  │
                      Risikostufe prüfen (risk.py)  ── forbidden: nie
                                  │                  └─ confirm: erst "Ja?"
                                  ▼
                   Executor: führt die Action aus (action_executor.py)
                                  │  ruft ein Werkzeug (tools/… oder ein eigenes Modul)
                                  ▼
                      Ergebnis ──> KI formuliert die Antwort
                                   (Ergebnis wird als UNVERTRAUTE Daten übergeben)
```

Wichtig daran:

- Das **Sprachmodell entscheidet nur, welche Aufgabe** gemeint ist und füllt die Parameter. Ob etwas
  ausgeführt wird, entscheidet allein `risk.py`, und zwar nach Action-Name, nie nach dem, was das Modell sagt.
- Alles, was von draußen kommt (Web, Dateien, E-Mails), ist **Information, nie eine Anweisung**.
  Die Antwort der KI auf ein Ergebnis fließt nie in den Router, das Memory oder eine weitere Ausführung.

## Begriffe

| Begriff | Bedeutung | Wo |
|---|---|---|
| **Task** (Aufgabe) | Was der Nutzer will, z. B. `ADD_CALENDAR_EVENT`. Hat ein *Ziel*-Satz und Actions. | `tasks.py` |
| **Action** | Ein einzelner Schritt mit Parametern, z. B. `add_calendar_event(title, date, time)`. | `tasks.py`, `action_executor.py` |
| **Werkzeug** | Der Code, der wirklich etwas tut (ein Modul in `tools/` oder ein eigenes wie `widgets.py`). | `tools/…` |
| **Risikostufe** | `safe` (sofort), `confirm` (erst fragen), `forbidden` (nie). | `risk.py` |

Eine Task kann mehrere Actions haben (`START_PROGRAM` = erst `find_program`, dann `open_program`). Sie ist so
riskant wie ihre riskanteste Action.

## Die Checkliste (in dieser Reihenfolge)

### 1. Entscheiden, was die Fähigkeit darf

- [ ] **Ein Satz:** Was tut sie? Was tut sie ausdrücklich *nicht*?
- [ ] **Risikostufe wählen** (Tabelle unten). Im Zweifel die höhere.
- [ ] **Woher kommen Daten?** Aus dem Internet oder von Dateien = unvertraut (Abschnitt „Daten von draußen“).
- [ ] **Kostet es Geld oder berührt es Privates** (Konto, Mails, Kamera)? Dann bekommt sie einen Schalter in
      den Einstellungen, standardmäßig **aus** (`default=False` in `abilities.py`).

### 2. Das Werkzeug schreiben

- [ ] Eine Funktion, die ein `ToolResult` zurückgibt (`success`, `data` oder `error`). **Keine Ausnahme nach außen:**
      Fehler werden zu `ToolResult(success=False, error="…")` mit einem verständlichen Satz.
- [ ] **Alles Netz über `net_fetch.py`** (`fetch_json`/`fetch_text`), nie `requests`/`urllib` direkt:
      dort stehen https-Pflicht, Host-Liste, Zeit- und Größenlimit. Der Host steht als feste Liste im Werkzeug
      (`hosts=("api.open-meteo.com",)`). `ANY_PUBLIC_HOST` nur, wenn beliebige Webseiten gelesen werden müssen.
- [ ] **Eingaben prüfen**, nicht dem Modell trauen (Zahlen im Bereich, Datum gültig, Texte gekürzt).
- [ ] **Geheimnisse** (API-Keys, Tokens) nur aus `.env` über `config.py`, nie in den Code, nie in eine Antwort, nie in ein Log.
- [ ] **Immer mit Zeitlimit.** Nichts, was Jarvis hängen lässt.
- [ ] Braucht es einen Speicher (wie `widgets.json`)? Atomar schreiben (erst temporäre Datei, dann umbenennen) und in `.gitignore` eintragen.

### 3. Task und Action eintragen (`tasks.py`)

- [ ] `create_<name>_task()` mit **einem klaren Ziel-Satz** (er erscheint wörtlich unter „Was kannst du?“ und
      wird dem Router gezeigt).
- [ ] Jeder Parameter als `{"description": …, "type": "string"|"number"|"boolean"}`. Die **Beschreibung ist die Anweisung
      an das Sprachmodell**: Format nennen (`YYYY-MM-DD`), Sonderfälle sagen („nennt der Nutzer keinen, schreibe …“).
- [ ] In `register_all_tasks` eintragen.
- [ ] Der Router bekommt das heutige Datum mit, relative Angaben („morgen“) rechnet er selbst aus.

### 4. Risikostufe eintragen (`risk.py`)

- [ ] Jede Action in `ACTION_RISK`. **Was dort nicht steht, ist verboten.**
- [ ] Gibt es Parameter, die eine sonst harmlose Action gefährlich machen (Pfad zu einer `.exe`)? Dann eine Sonderregel
      wie `_open_file_is_forbidden`.

### 5. Ausführen (`action_executor.py`)

- [ ] Ein Zweig `if action.name == "…":` ruft das Werkzeug. Nur aufrufen und Ergebnis weitergeben, keine eigene Logik.

### 6. Gastmodus

- [ ] Standard: **nicht** für Gäste. Nur wenn die Aufgabe harmlos *und* ohne Bezug zu deinem Rechner ist, kommt sie in
      `GUEST_TASKS` (`guest.py`). Beim Start wird geprüft, dass sie `safe` ist.

### 7. Tests (Pflicht, ohne Internet, ohne echte KI, ohne echte Programme)

- [ ] Ein Test mit **gefälschtem Dienst** (z. B. `net_fetch.fetch_json` austauschen): normaler Fall, Fehlerfall (kein Netz,
      unsinnige Antwort), ungültige Parameter.
- [ ] **Risikostufe** ist die erwartete (steht in `test_risk.py` bzw. wird vom Vertragstest gesehen).
- [ ] Liefert die Fähigkeit Text von draußen: ein Test, dass eine eingeschleuste Anweisung („Ignoriere alle Regeln …“)
      nichts auslöst (Muster: `test_injection.py`).
- [ ] `py run_tests.py` ist grün, auch der Vertragstest.

### 8. Sichtbar machen

- [ ] Erscheint unter „Was kannst du?“ (kommt **automatisch** aus der Registry, nichts von Hand ergänzen). Einmal prüfen.
- [ ] Hat die Fähigkeit Daten, die der Nutzer sehen oder ändern können muss (Liste, Einstellungen)? Dann Anzeige in der
      Weboberfläche (Regel aus Mark 4: alles sichtbar und änderbar).
- [ ] Die Aktion steht im **Aktionsprotokoll** (Settings → Activity). Das passiert automatisch über den Executor; prüfen.

### 9. Abnahme

- [ ] Eine Zeile pro Fähigkeit in der Abnahmeliste: Befehl auf **Deutsch und Englisch**, erwartete Antwort,
      ein Fehlerfall, ein Satz „Steht unter Was kannst du?“.
- [ ] Doku: ein Absatz in der passenden `DESIGN_*.md` oder in diesem Dokument (Abschnitt „Bisherige Fähigkeiten“).

## Risikostufen: wie entscheide ich?

| Frage | Antwort | Stufe |
|---|---|---|
| Liest sie nur öffentliche Daten oder rechnet sie nur? | ja | `safe` |
| Schreibt sie nur in eine Jarvis-eigene Datei, die du sofort wieder ändern kannst (Termin, Notiz)? | ja | `safe` |
| Ändert sie etwas am Rechner, das du sofort rückgängig machen kannst (Lautstärke)? | ja | `safe` |
| Startet sie Programme, öffnet sie Dateien, liest sie private Dateien, greift sie auf Konten zu? | ja | `confirm` |
| Schreibt sie in Dateien außerhalb von Jarvis, sendet sie etwas an andere Menschen, kostet sie spürbar Geld? | ja | `confirm` (oder erst gar nicht bauen) |
| Löscht sie unwiederbringlich, sendet sie E-Mails/Nachrichten ohne Prüfung, ändert sie Systemeinstellungen tief? | ja | `forbidden` |

Faustregel: **Was nur etwas zeigt, ist `safe`. Was etwas verändert, das nicht von selbst zurückkommt, braucht dein Ja.**

## Daten von draußen (Web, Dateien, Mails)

1. **Holen** nur über `net_fetch.py` (oder, für Dateien, nur innerhalb der erlaubten Ordner).
2. **Auf das Nötige reduzieren:** Aus der Antwort werden nur die Felder genommen, die gebraucht werden (wie in
   `web_search_tool`: Titel, Adresse, Beschreibung, jeweils gekürzt). Nie die ganze Antwort durchreichen.
3. **Säubern:** `untrusted.clean_text(text, max_länge)` entfernt versteckte Zeichen und kürzt.
4. **Verpacken:** Alles, was zur KI geht, kommt in `wrap_untrusted(quelle, text)`. Das geschieht für Task-Ergebnisse
   schon in `brain.respond_to_task`; wer Text von draußen anderswo in einen Prompt legt, muss es selbst tun.
5. **Nie ausführen:** Aus fremdem Text darf keine Action entstehen. Das ist durch die Bauweise ausgeschlossen
   (Antwort der KI geht nur an den Nutzer); neue Wege, die das umgehen (z. B. „Jarvis führt aus, was in der Datei steht“),
   sind **verboten**.

## Schalter in den Einstellungen (Step 1.3, fertig)

Jede Aufgabe gehört zu den **Grundfähigkeiten** (`CORE_TASKS` in `abilities.py`: Uhrzeit, Datum, Rechnen, Systeminfo; immer an)
oder zu **genau einer schaltbaren Fähigkeit** (`ABILITIES` in `abilities.py`). Den Schalter gibt es unter
Einstellungen → **Abilities**; er steht in `settings.json` (Kategorie `abilities`). Ist eine Fähigkeit aus:

- bekommt der Router ihre Aufgaben nicht zur Auswahl; wird sie trotzdem verlangt, antwortet Jarvis mit einem festen Satz
  („Die Fähigkeit … ist ausgeschaltet. Du kannst sie in den Einstellungen unter Abilities einschalten.“), ohne KI-Aufruf;
- steht sie nicht unter „Was kannst du?“, dort steht stattdessen eine Zeile **Ausgeschaltet**;
- kann kein Plan sie enthalten, und eine bereits wartende Rückfrage („Soll ich …?“) wird nach dem Ausschalten nicht mehr ausgeführt;
- gilt das sofort, ohne Neustart.

**Für eine neue Fähigkeit** heißt das: Eintrag in `ABILITIES` (id, Name, Beschreibung, Aufgaben, `default`). Die Einstellung, die
Prüfung im Server und die Anzeige in der Oberfläche entstehen daraus von selbst. Der Vertragstest schlägt an, wenn eine Aufgabe
weder Grundfähigkeit noch einer Fähigkeit zugeordnet ist.

- **`default=False`** für alles, was Geld kostet oder Privates berührt (Konten, Mails, Kamera, Dateien außerhalb von Jarvis).
- Der **Gastmodus** hat seine eigene feste Aufgabenliste (`GUEST_TASKS`) und ignoriert deine Schalter. Er läuft in einem eigenen Prozess
  mit eigenen Standard-Einstellungen. Soll eine Fähigkeit für Gäste nie gehen, dann steht sie dort einfach nicht in der Liste.

## Kosten: Tageslimit (Step 1.4, fertig)

`cost_guard.py` sitzt direkt um den OpenAI-Client. Es zählt **KI-Aufrufe** (`responses.create`) und **Sprachausgabe** (`audio.speech.create`)
pro Kalendertag in `usage.json` (nicht in Git, überlebt Neustarts). Limits unter Einstellungen → **Limits**
(Standard 500 KI-Aufrufe und 200 Sprachausgaben pro Tag, 0 = kein Limit).

- Das Limit wird **vor** dem Aufruf geprüft: ist es erreicht, geht nichts an OpenAI. Gezählt wird **nach** einem erfolgreichen Aufruf.
- Jarvis meldet es mit einem festen Satz, ohne Traceback. Die Browser-Stimme kostet nichts und zählt nicht.
- Der **Gastmodus** hat einen eigenen Zähler (`usage_guest.json`, 200 KI-Aufrufe pro Tag) und zehrt nie an deinem Limit.
- **Neue Arten von OpenAI-Aufrufen** (Bilder, Embeddings, Audio-Eingabe) müssen in `cost_guard.py` eingetragen werden, sonst werden sie
  weder gezählt noch begrenzt. Kostet eine Fähigkeit selbst Geld (fremde API), gehört sie mit `default=False` in `abilities.py`.
- Gezählt werden Aufrufe, nicht Euro: Das Limit ist eine Notbremse gegen Schleifen und Missbrauch, keine Abrechnung.
- Die Entwickler-Skripte `router_check.py`, `run_plan.py` und `show_plan.py` nutzen einen eigenen Client und werden nicht gezählt.

## Bisherige Fähigkeiten (Übersicht)

| Aufgabe | Action | Stufe | Werkzeug |
|---|---|---|---|
| `GET_TIME`, `GET_DATE` | `get_current_time`, `get_current_date` | safe | `tools/time_tool.py` |
| `CALCULATE` | `calculate` | safe | `action_executor.calculate_expression` (nur `+ - * /`) |
| `GET_SYSTEM_INFO`, `GET_RUNNING_PROGRAMS` | gleichnamig | safe | `tools/system_status_tool.py` (Fakten, Auslastung, größte Programme nur mit Name/RAM; `system_info_tool.py` leitet nur weiter), `tools/process_tool.py`. Dieselben Daten speisen die Widgets „PC Facts“ und „Performance“ über `/api/system` und `/api/performance` (lokal, nur Eigentümer) |
| `SET_VOLUME` | `set_volume` | safe | `tools/volume_tool.py` |
| `SEARCH_WEB` | `search_web` | safe | `tools/web_search_tool.py` (über `net_fetch`) |
| `GET_WEATHER` | `get_weather` | safe | `tools/weather_tool.py` (über `net_fetch`, Open-Meteo, ohne Schlüssel) |
| `CONVERT` | `convert` | safe | `tools/convert_tool.py` (Einheiten offline; Währungen über `net_fetch` von der EZB, `decimal`-Rechnung) |
| `GET_WORLD_TIME` | `get_world_time` | safe | `tools/world_time_tool.py` (Ortssuche über Open-Meteo-Geocoding, Zeitzonen über `zoneinfo`/`tzdata`) |
| `WIKI_LOOKUP` | `wiki_lookup` | safe | `tools/wiki_tool.py` (MediaWiki-Schnittstelle von de/en.wikipedia.org über `net_fetch`; Text unvertraut, Antwort nennt immer die Quelle) |
| `TRANSLATE` | `translate` | safe | `tools/translate_tool.py` (prüft/säubert Text und Sprache; übersetzt wird von der KI in der Antwort, Text als unvertraute Daten) |
| `SET_REMINDER`, `LIST_REMINDERS`, `CANCEL_REMINDER` | `set_reminder`, `list_reminders`, `cancel_reminder` | safe (`cancel_reminder` mit „alle“: confirm) | `reminders.py` (Datei `reminders.json`, Hintergrund-Prüfer, Kalender-Kopplung „⏰ Text“; Meldung `REMINDER_DUE`). Wiederholungen: ein Eintrag mit Regel, der nach dem Auslösen den nächsten Termin anlegt; `cancel_reminder` mit `scope: series` ist confirm |
| (Wiederholungen) | `add_calendar_event`, `set_reminder` mit `repeat`/`interval`/`count`/`until` | safe | `recurrence.py` (Regel, Rechnen, Beschreibung; Serien höchstens 100 Termine, höchstens 5 Jahre voraus, täglich nur mit Ende). Kalender: Serien werden als einzelne Termine mit `series`-Merker angelegt, Serien ohne Ende ein Jahr im Voraus und beim Lesen nachgelegt (`widgets.py`) |
| `GET_NEWS` | `get_news` | safe | `tools/news_tool.py` (über `net_fetch`, feste Feed-Liste `FEEDS`, je Quelle schaltbar) |
| `READ_PAGE` | `read_page` | safe für Artikel der letzten News-Liste, sonst **confirm** (Adresse wird gezeigt) | `tools/page_tool.py` (über `net_fetch` mit `ANY_PUBLIC_HOST`: nur öffentliche Adressen, Verbindung an die geprüfte Adresse gebunden gegen DNS-Rebinding) |
| `START_TIMER`, `LIST_TIMERS`, `CANCEL_TIMER` | gleichnamig | safe | `timer.py` |
| `ADD_CALENDAR_EVENT`, `LIST_CALENDAR_EVENTS` | gleichnamig | safe | `widgets.py` |
| `FIND_PROGRAM` | `find_program` | safe | `tools/program_tool.py` (nur `programs.json`) |
| `START_PROGRAM` | `find_program` + `open_program` | confirm | `tools/program_tool.py` |
| `OPEN_FILE` | `open_file` | confirm (verboten für `.exe` u. ä.) | `tools/file_tool.py` |

## Ein kleines Beispiel: Fähigkeit „Wie spät ist es in Edmonton?“ (Step 2.4, Plan)

1. Ein Satz: nennt die Uhrzeit in einer Zeitzone; ändert nichts. → `safe`.
2. Werkzeug `tools/timezone_tool.py`: `get_time_in(place)` mit fester Tabelle bekannter Orte → `ToolResult`.
   Kein Netz, daher kein `net_fetch`.
3. `tasks.py`: `GET_TIME_IN_PLACE`, Parameter `place` mit Beschreibung („Ort oder Zeitzone, z. B. Edmonton“).
4. `risk.py`: `"get_time_in": SAFE`.
5. `action_executor.py`: Zweig `get_time_in`.
6. Gastmodus: nein (nicht nötig).
7. Test: bekannter Ort, unbekannter Ort (verständliche Meldung), Sommerzeit-Wechsel.
8. „Was kannst du?“ zeigt sie von selbst; Abnahmezeile: „Wie spät ist es in Edmonton?“ / „What time is it in Tokyo?“.
