# DESIGN_CLIENT.md: Client-App, eigener Bereich für Tester, Abnahme zu zweit

Stand: 7. November 2026. Entwurf, nichts davon ist gebaut. Zeigt, was Mark 5 am Ende können soll und in welchen Schritten wir dorthin kommen.

## 1. Ziel

Ablauf, wie Moritz ihn beschrieben hat:

1. Moritz startet den Server (und `tailscale serve`).
2. Der Bruder lädt `JarvisGast-Setup.exe` herunter, installiert sie und startet die App.
3. Er meldet sich mit einem **Gastzugang** an (Koppelcode oder Link von Moritz).
4. Er bekommt einen **eigenen Bereich** mit eigener Unterhaltung, eigenen Erinnerungen, Listen, Zielen, Notizen und Kalender.
5. Seine Anfragen gehen an den Server auf Moritz' PC. **Dinge, die den Rechner verändern, sind nicht möglich.**
6. Er testet alles außer den Systemsachen. Das ist der zweite Durchlauf des Abnahmetests.
7. **Die iPhone-Web-App läuft unabhängig davon weiter**, wie sie ist.
8. **Moritz stellt die Limits des Gastes selbst ein**, damit der Bruder sauber durchtesten kann.

Der Zugang bleibt ausschließlich über Tailscale. Es kommt nichts ins offene Internet (kein Funnel).

Entscheidungen von Moritz (7. November):

| Frage | Entscheidung |
|---|---|
| Was darf der Bruder? | **Eigener Bereich zum Testen.** Eigene Unterhaltung, Notizen, Listen, Ziele, Kalender. Er sieht nichts von Moritz' Daten und nichts aus dem Gedächtnis. |
| „Anschau“-App | Gleiches Niveau wie das Handy, nur für Laptop/PC. Das ist **dieselbe Client-App** wie die des Bruders, kein eigenes Programm. |
| iPhone-App | **Bleibt die Web-App (PWA)** vom Home-Bildschirm. Keine native App. |
| Installer | **Windows, eine Setup-Datei.** |
| Administrator-App | Noch nicht entschieden, siehe Abschnitt 8. |

## 2. Was es heute schon gibt (Grundlage)

- Remote über Tailscale `serve` (HTTPS, nur im Tailnet), Geräte-Token, Koppel-Link, Sperren und Entsperren, Stufen, Limits (`DESIGN_REMOTE.md`).
- Eine PWA mit Manifest und Symbol (4B.2), `jarvis_app.py` für das Fenster am PC.
- Handy-Ansicht: eingeschränkte Seite, Handy-Einstellungen im Browser, Notizen allgemein oder pro Gerät.
- Gastmodus (`DESIGN_GUEST.md`) als Vorbild für einen Jarvis ohne Gedächtnis und ohne Aktionen.

Was fehlt: **Bereiche.** Heute teilen sich alle gekoppelten Geräte *eine* Unterhaltung, *eine* Notiz, *dieselben* Listen und dasselbe Gedächtnis. Genau das darf für den Bruder nicht gelten.

## 3. Bereiche (Profile)

Ein **Bereich** ist ein getrennter Satz Daten. Es gibt zwei Arten:

- **Besitzer** (Moritz): alles wie heute, auch alle seine Geräte (Handy, Laptop).
- **Tester** (Bruder, später weitere): eigener, abgeschlossener Bereich.

Jedes gekoppelte Gerät gehört zu genau einem Bereich. Der Bereich steht im Geräte-Eintrag in `remote_devices.json` und wird beim Koppeln festgelegt (der Koppel-Link bekommt dazu die Art „Besitzer“ oder „Tester“ mit Namen). Ein Gerät kann seinen Bereich nie selbst wechseln.

### Was ein Tester-Bereich enthält

| Teil | Tester | Wo es liegt |
|---|---|---|
| Unterhaltung | eigene, nur im Tester-Bereich | `profiles/<id>/conversation.json` |
| Notizen, Listen, Ziele, Kalender | eigene | `profiles/<id>/widgets.json` (eine eigene `WidgetStore`) |
| Gedächtnis (Memory) | **keins** (aus) | nichts, nie die Neon-Datenbank des Besitzers |
| Projekte | **keine** | nichts |
| Erinnerungen | eigene, kommen als Meldung in seiner App an (kein Alarmton am PC) | `profiles/<id>/reminders.json` |
| Einstellungen (Design, Schrift, Seitenleiste, Sprachausgabe) | eigene, im Browser des Geräts | wie die Handy-Einstellungen |
| Limits | eigene Zähler, von Moritz einstellbar | `profiles.json` (Werte), `profiles/<id>/usage.json` (Zähler) |

### Was der Tester kann

Nur Fähigkeiten, die keine Folgen außerhalb seines Bereichs haben:

- Plaudern.
- Auskunft: Wetter, Nachrichten, Rechner, Umrechnen, Uhrzeit/Zeitzonen, Wikipedia, Übersetzen, Webseite zusammenfassen.
- Eigene Listen, Ziele, Notizen, Kalender-Einträge (nur in seiner `WidgetStore`).
- **Eigene Erinnerungen** („Erinnere mich um 18 Uhr an …“). Sie liegen in seinem Bereich und erscheinen als Meldung in seiner App, wenn es soweit ist. Sie klingeln nie am PC von Moritz.
- **Nicht:** Wecker und Timer mit Alarmton und Fokus-Timer (sie klingeln am PC von Moritz), alles mit Programmen, Dateien, Mail, Zwischenablage, Bildschirm, Lautstärke. Nie Rückfragen, nie Pläne, nie Befehle (wie beim Handy).

### Technische Umsetzung

- Ein neuer `TesterJarvis` (ähnlich `GuestJarvis`): eigener Gesprächsverlauf, eigene Aufgabenliste, **kein** `Memory`, **kein** `Workspace`, **keine** Datenbank.
- Der Server wählt pro Anfrage den Bereich anhand des Geräte-Tokens: `jarvis`, `widget_store`, `sync_state` und die Einstellungsansicht kommen aus dem Bereich des Geräts.
- Aufgaben, die heute `widgets.default_store()` benutzen (Listen, Ziele), brauchen einen **pro-Anfrage-Speicher** (Thread-lokal, wie `_remote_scope` bei der Aufgabenliste). Dasselbe gilt für alles andere mit „Standard“-Speicher, das der Tester berühren kann. Prüfung per Test: kein Tester-Aufruf schreibt je in die Dateien des Besitzers.
- Live-Abgleich (`/api/sync`), Seitenleiste und Notizen liefern dem Tester nur seinen Bereich.
- Der PC von Moritz zeigt Tester-Bereiche nirgends an (anders als die Geräte-Notiz des Handys). Optional später: ein Schalter, um die Unterhaltung eines Testers anzusehen.

### Grenzen

- Kosten: Die KI-Aufrufe des Testers laufen über Moritz' OpenAI-Schlüssel. Deshalb hat jeder Bereich **eigene Limits, die Moritz auf der Remote-Seite einstellt**: KI-Aufrufe pro Tag (Voreinstellung 100), Nachrichten je 10 Minuten (Voreinstellung 20), 0 = unbegrenzt. Dazu zwei Knöpfe: „Zähler zurücksetzen“ (der Bruder kann sofort weitertesten) und „Bereich zurücksetzen“ (alle Daten des Bereichs weg, sauberer Neustart für den nächsten Testlauf).
- Der Tester kann keine Einstellungen von Moritz ändern und sieht sie nicht.
- Sperren/Entsperren/Entfernen eines Tester-Geräts wie bisher. Beim Entfernen des letzten Geräts bleibt der Bereich auf dem PC liegen, bis Moritz ihn löscht (Knopf „Bereich löschen“ in der Remote-Verwaltung).

## 4. Die Client-App

**Ziel:** Fenster ohne Adressleiste, Symbol im Startmenü, mit der eigenen Seite von Moritz' PC.

Zwei Wege, der zweite baut auf dem ersten auf:

1. **Sofort, ohne Installer: die Seite als App installieren.** Edge oder Chrome auf Windows können `https://<host>.ts.net` als App installieren („Als App installieren“). Das nutzt die schon vorhandene PWA. Das reicht, um den Bruder schon in Schritt C4 testen zu lassen.
2. **Setup-Datei (Inno Setup).** Eine `JarvisClient-Setup.exe`, gebaut aus einem Skript (`installer/jarvis_client.iss`). Sie
   - prüft, ob Tailscale installiert ist, und verweist sonst auf die Download-Seite,
   - fragt den Rechnernamen (`gott-desktop.taild3a628.ts.net`) ab, oder bekommt ihn fest eingebaut,
   - legt Startmenü- und Desktop-Verknüpfung an, die Edge im App-Modus mit eigenem Profilordner startet (`msedge --app=https://<host>/ --user-data-dir=%LOCALAPPDATA%\JarvisClient`),
   - hat einen Deinstaller und zeigt die Version.
   Sie enthält **keinen** Server und **keine** Zugangsdaten. Die Datei heißt `JarvisGast-Setup.exe`.
   **Anmelden:** Moritz erzeugt am PC einen Koppelcode für „Gast“. Die Koppelseite bekommt dazu ein Feld „Code eingeben“, damit der Bruder den Code nicht als Link öffnen muss (der Link mit `#code` bleibt für das Handy).

Der Installer wird auf Windows gebaut (Inno Setup ist kostenlos). Ich kann ihn hier nicht bauen oder starten. Ich liefere Skript und Anleitung, Moritz baut und meldet das Ergebnis.

**Die „Anschau“-App ist dieselbe Datei**, nur mit einem Bereich „Besitzer“ (Moritz am Laptop) statt „Tester“.

## 5. Zugang über Tailscale (offene Frage, zuerst prüfen)

Der Bruder muss Moritz' Rechner im Tailnet erreichen. Zwei Wege:

- **A: Als Nutzer ins Tailnet einladen** (Tailscale-Verwaltung → Nutzer einladen) und per **Zugriffsregel (ACL)** nur Port 443 auf Moritz' Rechner erlauben. Funktioniert sicher mit `tailscale serve`. Der kostenlose Tarif erlaubt eine kleine Zahl Nutzer (aktuell 3, bitte in der Verwaltung prüfen).
- **B: Gerät teilen** (Tailscale „Share“). Bei geteilten Geräten ist nicht sicher, ob `serve` und die HTTPS-Zertifikate für den Gast funktionieren: Ein Forenbeitrag nennt, dass geteilte Geräte Dienste verlieren können. Das ist unbestätigt.

**Schritt C0 (kein Code):** Moritz und sein Bruder probieren aus, ob der Bruder `https://gott-desktop.taild3a628.ts.net/pair` im Browser erreicht. Danach richtet sich, ob wir A oder B in der Anleitung beschreiben. Ohne dieses Ergebnis baue ich die Anleitung nicht fertig.

## 6. Sicherheit

- Alles, was Remote schon schützt, gilt unverändert: Host-Prüfung, Origin-Prüfung, Geräte-Token (nur als Hash gespeichert), Koppel-Link einmalig und 5 Minuten gültig, Sperre nach Fehlversuchen, keine Rückfragen, keine Befehle, keine Aktionen am PC.
- **Trennung der Bereiche ist die neue Hauptgefahr.** Ein Fehler hier würde Daten von Moritz an den Bruder geben. Deshalb: Tests, die für jede Adresse und jede Datenart prüfen, dass ein Tester-Gerät nie etwas aus dem Besitzer-Bereich sieht oder ändert (Unterhaltung, Notizen, Listen, Ziele, Kalender, Gedächtnis, Projekte, Einstellungen, Aktionsprotokoll, Geräteliste). Dazu eine Probe im Stabilitätstest: gemischte Last von Besitzer und Tester, danach Vergleich der Dateien.
- Das Tester-Gerät darf **keine** Remote-Verwaltung erreichen (wie jedes Remote-Gerät, 403).
- Prompt-Injection: Auch im Tester-Bereich gilt, dass Webseiten und Dokumente nur als Daten gelten (`DESIGN_INJECTION.md`).
- Tester-Bereiche und Geräte-Dateien gehören in `.gitignore` (`profiles/`).

## 7. Schritte

Jeder Schritt wird einzeln gebaut, getestet, geliefert und von Moritz abgenommen.

| Schritt | Inhalt | Fertig, wenn |
|---|---|---|
| C0 | Tailscale-Zugang für den Bruder prüfen (kein Code) | Der Bruder erreicht die Koppelseite |
| C1 | Bereiche: Geräte gehören zu einem Bereich, Koppel-Link mit Art und Name, Ordner `profiles/<id>/`, Anzeige in der Remote-Verwaltung, „Bereich löschen“ | Tests: Zuordnung, Rechte, Löschen, alte Geräte bleiben Besitzer |
| C2 | `TesterJarvis` und pro-Anfrage-Speicher: eigene Unterhaltung, eigene `WidgetStore`, begrenzte Aufgaben, eigenes KI-Limit | Test: Tester schreibt nie in Dateien oder Datenbank des Besitzers, Aufgabenliste ist wie oben |
| C3 | Server verteilt pro Anfrage nach Bereich (Nachricht, Seitenleiste, Sync, Einstellungen), Isolationstests für jede Adresse | Probe: Besitzer und Tester gleichzeitig, nichts leckt |
| C3b | Erinnerungen und Hintergrundmeldungen pro Bereich (eigener Speicher und Zustellung in die eigene App) | Eine Erinnerung des Testers erscheint nur bei ihm, nie am PC |
| C4 | Oberfläche im Tester-Modus: Banner „Testbereich“, keine Projekte, eigene Einstellungen, eigene Notizen. Koppelseite mit Feld „Code eingeben“. Anleitung „Seite als App installieren“. Bruder kann testen | Moritz' Bruder nutzt es einen Abend lang |
| C5 | Setup-Datei (`installer/jarvis_client.iss`, Anleitung, Version unter About) | Moritz baut sie, der Bruder installiert und startet sie |
| C6 | `ABNAHMETEST_MARK5.md`: Teil A für Moritz am PC, Teil B für den Bruder (nur, was der Tester-Bereich kann). Stabilitätstest um Bereiche erweitert | Beide haben den Test durchlaufen, 0 Abweichungen |
| C7 | Status-Dokument, commit, Tag `mark5` | Tag gesetzt |

Reihenfolge: C0 jetzt, parallel C1. Der Installer (C5) kommt bewusst nach C4, weil der Bruder schon mit der PWA testen kann.

## 8. Offene Punkte

- **Administrator-App.** (Zurückgestellt, siehe unten.)

- **Administrator-App, Begründung.** Die Verwaltung (Geräte koppeln, sperren, Stufen, Limits, Bereiche) ist heute eine Seite in den Einstellungen am PC. Eine eigene „Administrator-App“ bringt nur dann etwas, wenn sie etwas anderes kann (zum Beispiel vom Laptop aus verwalten). Das widerspricht der Regel „Verwaltung nur am PC“. Vorschlag: vorerst bei der Seite bleiben, nach Mark 5 neu bewerten.
- **Was kann der Bruder wirklich prüfen?** Alles, was Aktionen am PC betrifft (Programme, Dateien, Lautstärke, Mail), geht per Remote nie. Diese Zeilen des Abnahmetests macht allein Moritz. Der Bruder prüft: Unterhaltung, Auskunft, Listen, Ziele, Notizen, Kalender, Seitenleiste, Einstellungen, Sperren und Entsperren (mit Moritz), Fehlermeldungen, Verhalten bei Ausfall.
- **KI-Kosten des Testers.** Voreinstellung 100 Aufrufe pro Tag, einstellbar. Moritz entscheidet, ob das reicht.
- **Konto des Bruders in Tailscale.** Ob er ein eigenes Konto braucht oder Moritz' Tailnet beitritt, steht nach C0 fest.
