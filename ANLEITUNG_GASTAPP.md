# ANLEITUNG_GASTAPP.md: Gast-App für den Bruder (Mark 5, Schritt C5)

Stand: 7. November 2026. Zwei Teile: **A** für Moritz (einmal: Setup bauen, Bruder ins Tailnet holen), **B** für den Bruder (installieren und anmelden). Danach gilt für jeden Testlauf der kurze Ablauf in **C**.

Was die App ist: ein eigenes Fenster (ohne Adressleiste, mit Symbol im Startmenü), das die Jarvis-Seite von Moritz' PC zeigt. Die App enthält **keinen Server, keine Schlüssel und keine Zugangsdaten**. Alles läuft auf Moritz' PC, nur über Tailscale. Der Bruder sieht nur seinen eigenen Bereich (eigene Unterhaltung, Listen, Ziele, Notizen, Kalender, Erinnerungen), nichts von Moritz.

---

## A. Für Moritz (einmalig)

### A1. Das Setup bauen (Windows)

Das Setup wird mit **Inno Setup 6** gebaut (kostenlos, nur Windows). Hier im Entwurf konnte es nicht gebaut werden, bitte bei dir:

1. Inno Setup 6 von `jrsoftware.org` laden und installieren.
2. Im Projektordner die Datei `installer\jarvis_client.iss` per Doppelklick öffnen (öffnet sich in Inno Setup).
3. Falls dein Rechnername im Tailnet nicht `gott-desktop.taild3a628.ts.net` ist: oben in der Datei die Zeile `#define DefaultHost "..."` ändern. (Der Bruder kann die Adresse bei der Installation auch selbst eintragen.)
4. Menü **Build → Compile** (oder Strg+F9).
5. Ergebnis: `installer\output\JarvisGast-Setup.exe`. Das ist die Datei für den Bruder.
6. Meldet Inno Setup beim Bauen einen Fehler, schick mir die Zeile mit der Fehlermeldung. Ich kann das Skript hier nicht ausführen, nur prüfen, was darin steht.

In `.gitignore` bitte ergänzen: `installer/output/` (die fertige .exe gehört nicht ins Git).

### A2. Den Bruder ins Tailnet holen (dieser Schritt ist noch nicht bestätigt)

Der Bruder muss deinen PC über Tailscale erreichen. Zwei Wege:

- **Weg 1 (empfohlen): Als Nutzer einladen.** Tailscale-Admin (`login.tailscale.com/admin/users`) → „Invite users“. Er legt mit seiner Mail ein Konto an und ist dann in **deinem** Tailnet. Danach in den Zugriffsregeln (`login.tailscale.com/admin/acls`) einschränken, sodass er nur deinen PC auf Port 443 erreicht (nicht deine anderen Geräte). Hinweis: Im kostenlosen Tarif ist die Zahl der Nutzer begrenzt. Die aktuelle Grenze bitte in der Admin-Konsole nachsehen, ich konnte sie nicht sicher bestätigen.
- **Weg 2: Gerät teilen** („Share“ im Admin, bei deinem PC). Der Bruder bleibt in seinem eigenen Tailnet. Ob dabei der HTTPS-Name von `tailscale serve` für ihn funktioniert, konnte ich nicht bestätigen. Wenn dieser Weg klappt, ist er der sauberere, wenn nicht, nimm Weg 1.

**Der Test, der entscheidet (kein Code nötig):** Der Bruder öffnet in seinem Browser `https://gott-desktop.taild3a628.ts.net/pair` (deine Adresse einsetzen), während Tailscale bei ihm an ist und dein Jarvis-Server läuft. Erscheint die dunkle Seite „J.A.R.V.I.S. koppeln“, funktioniert der Weg. Dann kann er mit B weitermachen. Bitte sag mir, welchen Weg du genommen hast und ob es ging.

---

## B. Für den Bruder (installieren und anmelden)

1. **Tailscale** installieren (`tailscale.com/download`) und anmelden, mit dem Konto, zu dem Moritz dich eingeladen hat. Tailscale muss laufen („Connected“), sonst erreicht die App den Server nicht.
2. **`JarvisGast-Setup.exe`** starten. Windows meldet eventuell „Der Computer wurde durch Windows geschützt“ (SmartScreen), weil die Datei nicht signiert ist. Das ist bei selbst gebauten Setups normal: **„Weitere Informationen“ → „Trotzdem ausführen“**. (Bekommst du die Datei nicht direkt von Moritz, starte sie nicht.)
3. Im Setup die **Adresse** prüfen (Moritz sagt dir, welche) und weiter. Fehlt Tailscale, fragt das Setup nach. Installiert wird nur in deinen Benutzerordner, es braucht keine Administratorrechte.
4. Am Ende „J.A.R.V.I.S. Gast jetzt starten“ anklicken (oder später im Startmenü „J.A.R.V.I.S. Gast“).
5. Die App zeigt „Dieses Gerät ist nicht gekoppelt“. **Den Code von Moritz eintippen** (Format `K7M2-QX9P`, Groß-/Kleinschreibung egal; ein Link geht auch) und auf „Koppeln“ klicken. Der Code gilt nur 5 Minuten und nur einmal. Die 5 Minuten betreffen nur den Code: Danach bleibt die App gekoppelt (90 Tage, verlängert sich bei jeder Benutzung). Danach öffnet sich Jarvis mit dem Streifen „Testbereich“.
6. Fertig. Beim nächsten Start ist die App sofort angemeldet. Mit „Abmelden“ unten links meldest du dich ab. Wenn Moritz das Gerät sperrt, musst du einen neuen Code holen. Für neue Rechte gibt er dir einen neuen Code: Auf der Koppelseite eintippen, der alte Zugang wird ersetzt.

**Ohne Setup, nur mit Edge oder Chrome:** Adresse `https://<Adresse von Moritz>/pair` öffnen, Code einfügen, koppeln. Dann in Edge: Menü „…“ → „Apps“ → „Diese Website als App installieren“. (Chrome: „Speichern und teilen“ → „Als App installieren“.) Das Ergebnis ist dasselbe Fenster, nur ohne Setup-Datei.

**Deinstallieren:** Windows-Einstellungen → Apps → „J.A.R.V.I.S. Gast“ → Deinstallieren. Das entfernt auch den App-Ordner mit der Anmeldung. Deine Daten im Testbereich liegen auf Moritz' PC und bleiben dort, bis er sie löscht oder zurücksetzt.

---

## C. Ablauf bei jedem Testlauf (für Moritz)

1. PC an, Jarvis-Server starten, `tailscale serve` läuft (wie für das iPhone, `ANLEITUNG_TAILSCALE.md`).
2. Einstellungen → Remote: Remote an. Unter „Gast-Bereiche“ den Bereich (zum Beispiel „Bruder“) anlegen. **Limits** einstellen:
   - KI-Anfragen pro Tag (Standard 100) und Nachrichten pro 10 Minuten (Standard 20). 0 heißt unbegrenzt.
   - Für einen langen Testabend: Limits hoch oder auf 0. Wenn er anstößt: „Zähler zurücksetzen“, er kann sofort weitertesten.
   - Für einen sauberen neuen Durchlauf: „Daten zurücksetzen“ (leert alles in seinem Bereich).
3. **Koppel-Code erzeugen**, Ziel „Gast: Bruder“ wählen, Namen des Geräts eintragen („Laptop Bruder“). Den großen Code (z. B. `K7M2-QX9P`) dem Bruder schicken, oder den Link darunter. Er muss ihn innerhalb von 5 Minuten einlösen.
4. Nach dem Test: Gerät **Sperren** oder Bereich **löschen**. Gesperrte Geräte kommen sofort nicht mehr herein.

Die Kosten tragen deine OpenAI-Anfragen. Die Limits in Schritt 2 sind die Bremse. Der Gast hat nie die bezahlte Stimme, nur die Browser-Stimme.

## Was der Bruder testen kann, und was nicht

| Kann er | Kann er nicht |
|---|---|
| Plaudern, Wetter, News, Übersetzen, Wikipedia, Weltuhr, Umrechnen, Uhrzeit, Rechnen | Programme, Dateien, Mail, Zwischenablage, Bildschirm, Lautstärke, Musik |
| Eigene Listen, Ziele, Notizen, Kalender-Einträge, Erinnerungen | Timer, Wecker, Fokus-Timer, Tagesbriefing (sie würden an deinem PC klingeln) |
| Eigene Handy-Einstellungen (Farbe, Schrift, Seitenleiste) | Deine Daten, dein Gedächtnis, deine Projekte, deine Einstellungen, die Remote-Verwaltung |

## Wenn etwas nicht klappt

| Problem | Ursache und Lösung |
|---|---|
| Setup meldet „Weder Microsoft Edge noch Google Chrome“ | Einen der beiden installieren und das Setup neu starten |
| App-Fenster bleibt leer oder zeigt einen Verbindungsfehler | Tailscale beim Bruder nicht „Connected“, dein PC aus, Jarvis läuft nicht, oder die Adresse im Setup ist falsch (Setup erneut starten, Adresse ändern) |
| Koppelseite: „ungültig, abgelaufen oder schon benutzt“ | Code nur 5 Minuten und einmal gültig: neuen Code erzeugen |
| „Zu viele Versuche“ (429) bei der Kopplung | 15 Minuten warten, dann neuer Code |
| Antwort „Höchstens N Nachrichten in 10 Minuten“ oder „Tageslimit erreicht“ | Deine Limits (siehe C2): erhöhen, oder „Zähler zurücksetzen“ |
| Er sieht plötzlich „nicht angemeldet“ | Gerät wurde gesperrt oder gelöscht: neuer Code |
| SmartScreen blockiert das Setup | „Weitere Informationen“ → „Trotzdem ausführen“. Das Setup ist nicht signiert (eine Signatur kostet Geld) |
