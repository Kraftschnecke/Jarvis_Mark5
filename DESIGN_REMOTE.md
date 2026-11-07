# DESIGN_REMOTE: Jarvis vom iPhone aus (Mark 5, Phase 4B, Remote)

Entscheidung aus Phase 3: **B, dann Remote über Tailscale.** Dieses Dokument legt fest, *wie* das sicher geht. Gebaut wird erst
nach deinem OK (siehe Abschnitt 9).

## 1. Ziel

- Du startest Jarvis auf dem PC (jetzt auch automatisch mit Windows) und erreichst ihn **vom iPhone aus, auch in einem anderen Netz**.
- Das Handy ist nur eine Fernbedienung: **Handy → PC → KI.** Der OpenAI-Schlüssel, die Datenbank und alle Daten bleiben auf dem PC.
  Das Handy bekommt nur Text und Ergebnisse.
- Der Zugang ist **nur für dich**: niemand sonst, auch nicht im Internet oder im selben WLAN.
- Der PC muss an sein und Jarvis laufen. Ist er aus, geht nichts (gewollt: keine Cloud dazwischen).

## 2. Der Weg: Tailscale (privates Netz zwischen deinen Geräten)

- Tailscale verbindet deinen PC und dein iPhone zu einem **privaten Netz (Tailnet)**, verschlüsselt, ohne Port-Freigabe am Router.
- `tailscale serve` macht aus dem lokalen Jarvis (127.0.0.1:8000) eine **HTTPS-Adresse nur im Tailnet**, z. B.
  `https://mein-pc.tailabc.ts.net`. HTTPS ist nötig, weil iOS Mikrofon und "Zum Home-Bildschirm" nur damit sauber erlaubt.
- **Nie `tailscale funnel`.** Das würde Jarvis ins öffentliche Internet stellen. Die Anleitung und die Prüfung in Jarvis warnen davor.
- Der Jarvis-Server hört weiter **nur auf 127.0.0.1**. Tailscale reicht die Anfragen lokal an ihn durch. Es gibt keinen offenen Port.

## 3. Mehrere Schichten (jede Schicht allein soll schon schützen)

1. **Tailnet:** Nur Geräte in deinem Tailscale-Konto erreichen die Adresse. (Empfohlen: in den Tailscale-Regeln nur dein iPhone zulassen.)
2. **Aus per Voreinstellung:** Ohne `JARVIS_REMOTE_HOST` in der `.env` ist Remote vollständig aus. Der Server akzeptiert dann
   weiter nur localhost, wie heute. Zusätzlich gibt es einen Schalter "Remote" in den Einstellungen (am PC), der live ausschaltet.
3. **Host- und Origin-Prüfung bleibt streng:** erlaubt sind localhost **und genau der eine eingetragene Remote-Name**. Alles andere
   (auch fremde Namen, die auf dich zeigen) ist 403. Anfragen mit Remote-Namen akzeptiert der Server nur von der eigenen
   Maschine (Tailscale reicht lokal durch).
4. **Gerätetoken:** Jedes Handy bekommt **sein eigenes Token**. Ohne gültiges Token gibt es von außen nur die Kopplungsseite.
5. **Eingeschränkte Fähigkeiten:** Remote sieht nur eine feste Liste von Aufgaben (Abschnitt 5), alles andere gibt es dort *nicht*
   (wie im Gastmodus: nicht "verboten", sondern nicht vorhanden).
6. **Eigene Grenzen:** Rate-Limit pro Gerät, Tageslimit für KI-Aufrufe über Remote, Sperre bei falschen Kopplungsversuchen.
7. **Protokoll und Notaus:** Jede Remote-Aktion steht im Aktionsprotokoll mit Gerätename. Jedes Gerät lässt sich einzeln
   sperren, oder alle auf einmal ("Alle Geräte abmelden"), oder Remote komplett ausschalten. Alles nur **am PC**.

## 4. Kopplung und Token

**Kopplung (einmal pro Gerät, am PC gestartet):**
1. Am PC: Einstellungen → Remote → "Neues Gerät koppeln" → Name eingeben (z. B. "iPhone Moritz").
2. Jarvis zeigt einen **Kopplungslink** (`https://mein-pc.tailabc.ts.net/pair#<Code>`), **5 Minuten gültig, nur einmal benutzbar**,
   Code zufällig und lang (32 Zeichen). Den Link schickst du dir selbst aufs iPhone (z. B. Notizen/AirDrop/Nachricht an dich selbst).
   Ein QR-Code kann später dazukommen.
3. Handy öffnet den Link in Safari: die Kopplungsseite tauscht den Code gegen ein **Token**. Der Code ist danach verbraucht.

**Token:**
- 256 Bit zufällig, **nur als Hash** in `remote_devices.json` gespeichert (kein Klartext, wie ein Passwort). In `.gitignore`.
- Im Handy als Cookie: `Secure`, `HttpOnly`, `SameSite=Strict`, Laufzeit lang (z. B. 90 Tage, wird bei Nutzung verlängert).
  Die Seite (JavaScript) kann das Token nie lesen, und andere Webseiten können es nicht mitschicken.
- Pro Gerät gespeichert: Name, erstellt am, zuletzt gesehen, gesperrt ja/nein. Die Liste siehst du am PC; "Sperren" wirkt sofort.
- Vergleich der Token mit konstanter Zeit; nach 5 falschen Codes/Token von derselben Quelle: 15 Minuten Pause für die Kopplung.

## 5. Was das Handy darf

Es gibt **drei Stufen**. Sie lassen sich am PC je einzeln an- und ausschalten ("Remote darf …"):

| Stufe | Inhalt | Voreinstellung |
|---|---|---|
| **Auskunft** | Uhrzeit, Datum, Rechnen, Websuche, Wetter, News, Übersetzer, Wikipedia, Weltuhr, Umrechnen | an |
| **Alltag** | Timer, Erinnerungen, Wecker, Tagesbriefing, Fokus, Kalender-Termine, Listen, Ziele | an |
| **PC-Steuerung (harmlos)** | Lautstärke, Musiksteuerung, Stumm/Helligkeit (nur die Aufgaben mit Stufe "safe") | **aus** |

**Nie über Remote (fest eingebaut, nicht einstellbar):**
- alles mit Stufe `confirm` oder `forbidden` in `risk.py`: Programme/Dateien öffnen, Notizen schreiben, Bildschirm ansehen,
  Zwischenablage, E-Mail, Kontakte, Webseiten im Browser öffnen, Dokumente lesen, frühere Gespräche durchsuchen.
  Rückfragen ("Soll ich …?") gibt es nur am PC. Fragt man so etwas am Handy, antwortet Jarvis ehrlich: "Das geht nur am PC."
- Pläne mit mehreren Schritten, Befehle wie "Reset", Projekt- oder Konversationsverwaltung.
- Einstellungen ändern, Gedächtnis ändern oder löschen, Ordner freigeben, Wecker/Timer-Töne am PC konfigurieren, Remote selbst verwalten.
- Das Aktionsprotokoll lesen.

**Welche Adressen (`/api/…`) Remote überhaupt kennt:** `message`, `background`, `timers`, `ringing` (+ stop/snooze), `alarms` (lesen),
`widgets` (lesen), `weather`, `speak` (mit eigenem Limit). Alles andere ist 403, auch mit gültigem Token. Ein Test prüft jede
Adresse einzeln (wie bei `DESIGN_GUEST.md`).

**Technisch:** Die Anfrage bekommt eine Herkunft ("remote"). Aufgaben außerhalb der erlaubten Stufen sind für diese Anfrage gar nicht
registriert und der Router bietet sie dem Sprachmodell nicht an. Zusätzlich prüft der Ausführer vor jeder Aktion noch einmal die
Herkunft und die Stufe (doppelte Absicherung wie im Gastmodus).

## 6. Grenzen und Kosten

- **Erste Version: keine Mengen-Limits** (du bist das einzige Handy, und zum Testen stören sie nur). Der Mechanismus (Nachrichten
  pro Gerät und KI-Aufrufe pro Tag) wird trotzdem eingebaut und getestet, mit Voreinstellung **0 = unbegrenzt**. Wer später einen
  Wert einträgt, bekommt die Grenze, ohne dass etwas umgebaut werden muss (sinnvoll z. B. für ein verlorenes Handy).
- **Bleiben fest:** Sperre bei falschen Kopplungsversuchen, Begrenzung der Nachrichtenlänge.
- Fähigkeiten-Stufen und Limits lassen sich nur am PC ändern. Remote kann **keine** Einstellung ändern.

## 7. Das Handy-Erlebnis

- Dieselbe Seite wie am PC, mit Handy-Layout (Seitenleiste klappt ein, große Tippflächen, Eingabefeld über der Tastatur, Rand für
  die iPhone-Notch). Oben ein Hinweis "Remote (eingeschränkt)", damit man weiß, wo man ist.
- "Zum Home-Bildschirm" (PWA, kommt aus 4B.2) macht daraus eine App mit Jarvis-Symbol.
- **Sprache:** Eingabe per Tipp-Taste (Diktat der iOS-Tastatur geht immer). Der Mikrofon-Knopf der Seite nutzt die Spracherkennung
  von Safari; sie ist auf dem iPhone weniger zuverlässig als am PC. **Weckwort geht auf dem iPhone nicht zuverlässig** (iOS stoppt
  die Hintergrund-Erkennung) und bleibt dort aus. Vorlesen geht über die Sprachausgabe des Handys oder die Jarvis-Stimme (zählt
  zum Remote-Limit).
- **Keine Push-Meldungen** (Timer klingelt am PC, nicht am Handy). Das ginge später mit Web-Push, ist aber ein eigener Schritt.

## 8. Bekannte Grenzen

- Handy und PC teilen **dieselbe Unterhaltung** (Jarvis ist für eine offene Unterhaltung gebaut, Nachrichten laufen nacheinander).
  Was du am Handy schreibst, erscheint **auch am PC** in derselben Unterhaltung und umgekehrt, ohne Neuladen: Beide Seiten fragen
  kurz nach, ob sich die Unterhaltung geändert hat (Schritt R2b), und laden den Verlauf nach, sobald das so ist.
- Ist der PC im Standby, geht nichts. (Optional später: Energiesparen so einstellen, dass der PC wach bleibt.)
- Ein gestohlenes, entsperrtes Handy hat Zugriff auf die erlaubten Stufen, bis du das Gerät am PC sperrst. Deshalb sind die
  gefährlichen Dinge gar nicht erst über Remote erreichbar.
- Wer Zugriff auf dein Tailscale-Konto hat, kommt bis zur Kopplungsseite, braucht aber ein Token (Konto mit Zwei-Faktor schützen).

## 9. Bauplan (je Schritt: bauen, testen, abnehmen)

| Schritt | Inhalt | Du siehst |
|---|---|---|
| **R1** | `remote_auth.py`: Gerätespeicher (Hash, Kopplungscodes, Sperren, Limits), Stufen-Liste; reine Logik mit Tests | Tests grün |
| **R2** | Server: Remote-Erkennung, Host/Origin für den Remote-Namen, Cookie-Anmeldung, Kopplungsseite, Adressliste, Rate-Limit | Test mit gefälschtem Remote-Namen: jede Adresse einzeln |
| **R2b** | Live-Abgleich: `GET /api/sync` liefert einen Zähler, der bei jeder Änderung der Unterhaltung steigt; die Seite lädt den Verlauf nach, wenn er sich ändert (PC und Handy) | Am PC schreiben, im zweiten Browserfenster erscheint es |
| **R3** | Fähigkeiten nach Stufen einschränken (Herkunft "remote"), Rückfragen nie remote, Aktionsprotokoll mit Gerätename | `router_check` mit Remote-Beispielen |
| **R4** | Einstellungen am PC: Remote an/aus, Stufen, Geräteliste, Kopplungslink, Sperren | Du koppelst ein "Testgerät" am PC |
| **R5** | Handy-Layout und Hinweis "Remote" | Seite im schmalen Browserfenster prüfen |
| **R6** | Anleitung `ANLEITUNG_TAILSCALE.md` (Schritt für Schritt), Erweiterung `stabilitaetstest.py` (Remote-Anfragen, falsche Token, Limits), Sicherheits-Checkliste | Du koppelst dein iPhone und testest im Mobilfunk |

Alles bis R5 lässt sich **ohne Tailscale** am PC testen (mit dem Namen `localhost` als Test-Remote-Namen im Test). Tailscale brauchst du erst
bei R6.

## 10. Entschieden (7. November)

1. **Stufen wie in Abschnitt 5:** Auskunft und Alltag an, PC-Steuerung als einzige aus.
2. **Keine Rückfragen vom Handy** in der ersten Version (ein Notiz-Öffnen vom Handy aus ergibt aktuell keinen Sinn).
3. **Kopplung nur per Link** (QR-Code vielleicht später).
4. **Keine Limits** zum Start (Mechanismus vorhanden, Voreinstellung 0 = unbegrenzt).
5. **Gemeinsame Unterhaltung:** was am Handy geschrieben wird, erscheint am PC in derselben Unterhaltung (Schritt R2b).

## 11. Stand der Umsetzung

- **R1 gebaut:** `remote_auth.py` (Geräte, Kopplung, Token als Hash, Sperren, Grenzen), `remote_policy.py` (Stufen, Adressen).
- **R2 gebaut:** `remote_gate.py` und die Einbindung in `server.py`.
  - Einschalten braucht **zwei** Dinge: `JARVIS_REMOTE_HOST=mein-pc.tailabc.ts.net` in der `.env` **und** `remote.enabled = true` in den
    Einstellungen (Oberfläche dafür kommt in R4; bis dahin steht der Schalter in `settings.json`). Ohne beides lehnt der Server den Namen ab.
  - Anfragen mit dem Remote-Namen brauchen das Cookie eines gekoppelten Geräts. Ohne Cookie gibt es nur die Kopplungsseite
    (`/pair`, `web/pair.html`) und Dateien ohne Geheimnisse (Manifest, Icons).
  - Nachrichten vom Handy gehen in Jarvis nur über `process_remote_message(text, geraetename, stufen)`. **Das gibt es erst in R3.**
    Bis dahin antwortet der Server auf Nachrichten vom Handy mit 503, nie über den normalen Weg.
- **R2b gebaut:** Live-Abgleich, am PC und am Handy gleich.
  - `GET /api/sync?known=<version>` liefert `version` (Fingerabdruck aus aktiver Unterhaltung und allen Nachrichten) und `active`.
    Ist `known` anders als die aktuelle Version, kommen `messages` und `projects` mit. Gelesen wird ohne `message_lock`.
  - `web/sync.js` fragt alle 2 Sekunden. Es fragt nicht, wenn der Tab versteckt ist, Jarvis gerade antwortet oder eine Rückfrage offen ist
    (sonst würden die Ja/Nein-Knöpfe verschwinden). Beim Zurückkehren in den Tab wird sofort gefragt.
  - Eigene Aktionen (Nachricht, Rückfrage, Unterhaltung/Projekt wechseln) merkt sich die Seite nur, ohne neu zu zeichnen.
  - Grenze: Schreibt das andere Gerät genau in dem Moment, in dem die eigene Aktion endet, erscheint es erst bei der nächsten Änderung.
- **R3 gebaut:** `Jarvis.process_remote_message(text, geraetename, stufen)` in `jarvis.py`.
  - Der Router und die Ausführung sehen nur die Aufgaben der freigegebenen Stufen (und nur, wenn sie in den Abilities an sind).
    Die Einschränkung gilt nur für den Thread der Handy-Nachricht, der PC sieht gleichzeitig weiter alles.
  - Nie Rückfragen, Pläne oder Befehle (Projekt wechseln, Beenden, Reset ...): dafür gibt es die feste Antwort „Das geht nur am PC.“
    Auch erlaubte Aufgaben, die am PC eine Rückfrage bräuchten (z. B. alle Erinnerungen löschen), werden am Handy abgelehnt.
  - „Ja“ vom Handy bestätigt nie etwas vom PC, und eine Handy-Nachricht räumt offene Rückfragen am PC nicht ab (auch nicht bei Fehlern oder Tageslimit).
  - Gleiche Unterhaltung wie am PC (siehe R2b). Keine Projekt-Prüfung mit Rückfrage, „Speichere das als Notiz“ gibt es am Handy nicht.
  - Jede Handy-Nachricht steht im Aktionsprotokoll (Aufgabe „REMOTE“, Gerätename, Text, Ergebnis TASK:…/CHAT/REFUSED).
  - „Was kannst du?“ nennt am Handy nur, was dort geht.
- **R4 gebaut:** Einstellungsseite „Remote“ (📱) am PC.
  - Schalter „Remote enabled“, die drei Stufen, die zwei Grenzen (0 = unbegrenzt) und darunter das Panel: Status, Geräteliste
    (aktiv / gesperrt / abgelaufen, zuletzt gesehen), „Sperren“, „Entfernen“, „Alle Geräte sperren“ (mit zweitem Klick zur Sicherheit).
  - **Koppel-Link:** Name eingeben, „Koppel-Link erzeugen“, der Link (`https://<name>/pair#<code>`) steht mit Restzeit auf der Seite,
    gilt 5 Minuten und einmal. Er wird nirgends gespeichert und steht nie in der Geräteliste.
  - Server (nur am PC, das Handy bekommt für alle diese Adressen 403): `GET /api/remote/state`, `POST /api/remote/pair_link`,
    `/revoke`, `/revoke_all`, `/forget`. Ohne Remote-Namen in der `.env` zeigt die Seite einen Hinweis und kein Koppel-Feld.
  - Ein echtes Koppeln braucht den Remote-Namen über Tailscale (R6). Bis dahin siehst du Link, Liste und Schalter, aber noch kein Handy.
- **R5 gebaut:** Handy-Ansicht (Remote-Modus der Seite, `web/remote_mode.js`).
  - Der Server meldet `"remote": true` in den Einstellungen, daran erkennt die Seite den Modus (nicht an der Adresse).
  - Streifen **„Remote (eingeschränkt)“** mit den freigegebenen Stufen und dem Gerätenamen (aus `/api/remote/whoami`).
  - Am Handy aus: Einstellungen, „New Project“, Umbenennen/Löschen, Weckwort, Tagesbriefing beim Start, Abendfrage, Hinweise, die Widgets
    PC Facts, Performance und Eishockey (die Adressen dafür gibt es über Remote nicht). Notizen sind am Handy nur lesbar.
  - Handy-Feinschliff: Eingabefelder mit 16 px (sonst zoomt iOS hinein), Abstand zu Notch und Home-Balken, `100dvh` gegen die springende Adressleiste.
  - Bekannte Grenze: Ziele, Listen und Kalender-Widget zeigen am Handy beim Bearbeiten eine Fehlermeldung statt zu speichern (der Server sperrt es). Ändern geht am PC.
  - Die Sperre steht immer im Server (R2), die Anzeige hier ist nur Komfort.
- **R6 gebaut:** `ANLEITUNG_TAILSCALE.md` (Schritt für Schritt, Test, Notaus, Sicherheits-Checkliste, Fehlersuche) und die Erweiterung von
  `stabilitaetstest.py`.
  - Der Stabilitätstest koppelt echte „Handys“ und schickt 30 % der Last als Remote-Anfragen: Nachrichten, Lesen, Dateien, falsche/fehlende/zu lange Token,
    verbotene Adressen (GET und POST), falscher Origin und Host, ungültige und zu lange Nachrichten, falsche Kopplungscodes bis zur Sperre, Fehler in der KI.
  - Danach prüft er einzeln: Kopplungssperre (auch für richtige Codes, gekoppelte Geräte bleiben unberührt), Nachrichtenlimit je Gerät, Tageslimit für alle,
    Sperren eines Geräts, Remote aus (Handy 403, PC weiter ok), „Alle sperren“, keine Token im Klartext in `remote_devices.json`.
  - Ob das alles am echten iPhone über Mobilfunk klappt, zeigt erst dein Test nach der Anleitung (Teil 4).
- **Nachbesserung nach dem ersten iPhone-Test (R7a):** Gesperrte Geräte lassen sich am PC wieder **entsperren** (gleicher Token, Laufzeit beginnt neu, nur am PC).
  Aufgaben und Ablehnungen vom Handy werden jetzt ebenfalls in die gemeinsame Unterhaltung geschrieben (vorher nur Plauderei), damit der PC sie per Live-Abgleich sieht.
- **Handy-Einstellungen (R7b):** Knopf „Handy-Einstellungen“ in der Seitenleiste (nur am Handy) mit Design, Akzentfarbe und „Antworten vorlesen“.
  Die Werte stehen nur im Browser des Handys (`jarvis.remote.prefs`) und ueberdecken dort die Werte des PC (`remote_prefs.js`). Es gibt keine neue erlaubte Adresse,
  die PC-Einstellungen bleiben am Handy gesperrt.
- **Handy-Design (R7c):**
  - Ziele abhaken und Listen pflegen (Einkaufsliste abhaken, Einträge hinzufügen, löschen) gehen jetzt auch vom Handy. Erlaubt sind nur `POST /api/widgets/goals` und `/api/widgets/lists`, und nur mit der Stufe
    **Alltag** (`remote_policy.DAILY_POST_API`). Die strenge Prüfung des Servers gilt dort wie am PC. Notizen, Termine und Wecker bleiben am PC.
  - Die Handy-Einstellungen kennen zusätzlich Schriftgröße und die Felder der Seitenleiste (Uhr, Datum, Kalender, Notizen, Ziele, Listen), pro Gerät im Browser. „Alles wie am PC“ setzt zurück.
  - Nicht möglich: Wecker auf dem iPhone selbst stellen. Eine Webseite darf keine Wecker der iOS-Uhr anlegen. Möglich wäre später eine Kurzbefehl-Verknüpfung (Apple „Kurzbefehle“).
- **Notizen am Handy (R7d):** Mit der Stufe Alltag darf das Handy die **gemeinsame Notiz** (`/api/widgets/notes`, für alle Geräte) und seine **eigene Notiz**
  (`/api/widgets/device_note`) schreiben. Die eigene Notiz liegt pro Gerät in `widgets.json` (`device_notes`, höchstens 10 Geräte, 5000 Zeichen). Nur das Gerät selbst ändert sie,
  der PC zeigt sie schreibgeschützt an („Notiz von …“). Das Handy sieht nie die Notiz eines anderen Geräts. Notizen gesperrter Geräte blendet der PC aus.
  Am Handy wählt ein Schalter zwischen „Allgemein“ und „Nur dieses Gerät“. Änderungen anderer Geräte erscheinen bei der nächsten Aktualisierung, aber nie mitten in einer Eingabe.
- **Listen:** Der Name einer Liste im Auswahlfeld bleibt gleich; die Zahl der offenen Einträge steht daneben („2 offen“).
- Alle Schritte R1 bis R6 sind gebaut. Offen: dein Test mit dem iPhone (Anleitung), danach das Handy-Design.
