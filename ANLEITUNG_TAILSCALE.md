# ANLEITUNG: Jarvis vom iPhone aus (Tailscale)

Mark 5, Remote R6. Hintergrund und Sicherheitsüberlegungen stehen in `DESIGN_REMOTE.md`. Hier steht nur, **was du tust**, in der Reihenfolge,
in der du es tust. Plane etwa 30 Minuten ein. Du brauchst dafür den PC, auf dem Jarvis läuft, und dein iPhone.

Kurz, was am Ende passiert: Tailscale verbindet PC und iPhone zu einem **privaten Netz**. Ein einziger Befehl (`tailscale serve`) macht
Jarvis in diesem privaten Netz unter einer `https://…ts.net`-Adresse erreichbar. Von außen (Internet, fremdes WLAN) kommt niemand dran.
Jarvis selbst hört weiter nur auf deinem PC (127.0.0.1), es wird kein Port am Router geöffnet.

---

## Teil 1: Tailscale einrichten

1. **PC:** Tailscale für Windows von `tailscale.com/download` installieren und mit einem Konto anmelden (Google, Microsoft, Apple oder GitHub).
2. **iPhone:** App „Tailscale“ aus dem App Store installieren und **mit demselben Konto** anmelden. In iOS die VPN-Anfrage erlauben.
3. **Konto schützen:** Wer dein Tailscale-Konto übernimmt, kommt bis zur Kopplungsseite. Schalte beim Anbieter, mit dem du dich anmeldest
   (Google, Microsoft, Apple, GitHub), die **Zwei-Faktor-Anmeldung** ein.
4. Auf dem iPhone in der Tailscale-App prüfen: Dein PC steht in der Geräteliste und ist „Connected“.
5. Im Browser `login.tailscale.com/admin/dns` öffnen (Admin-Konsole):
   - **MagicDNS** muss an sein (ist bei neuen Konten Standard).
   - **HTTPS-Zertifikate** aktivieren („Enable HTTPS“). Ohne das kann Tailscale keine `https://`-Adresse für deinen PC ausstellen.
     Tailscale weist beim ersten `serve` ebenfalls darauf hin, falls es fehlt.

## Teil 2: Jarvis auf den Remote-Namen vorbereiten

1. Eingabeaufforderung (Windows-Taste, „cmd“) öffnen und Jarvis' Adresse im Tailnet ermitteln:
   ```
   tailscale serve --bg 8000
   tailscale serve status
   ```
   Der Befehl `tailscale serve --bg 8000` reicht `https://…` an Jarvis auf Port 8000 weiter und läuft danach dauerhaft im Hintergrund (auch nach
   einem Neustart). Die Ausgabe von `status` enthält eine Adresse wie `https://mein-pc.tail1a2b3.ts.net`. **Das ist dein Remote-Name:**
   nur der Teil ohne `https://` und ohne Schrägstrich am Ende.
   - Läuft Jarvis bei dir auf einem anderen Port (`JARVIS_PORT` in der `.env`), nimm statt `8000` diese Nummer.
2. In der Datei `.env` im Jarvis-Ordner (Notepad) **eine Zeile ergänzen**:
   ```
   JARVIS_REMOTE_HOST=mein-pc.tail1a2b3.ts.net
   ```
   Genau wie in der Ausgabe, ohne Leerzeichen, ohne `https://`. Speichern.
3. Jarvis neu starten (App beenden und wieder öffnen, oder `py server.py` neu starten). Beim Start steht in der Konsole:
   `Remote ist vorbereitet für https://mein-pc… (aktuell AUS, …)`. Steht das nicht da, ist der Name falsch geschrieben (er braucht einen Punkt).
4. In Jarvis: **Einstellungen → Remote**:
   - **Remote enabled** einschalten.
   - Stufen: **Auskunft** und **Alltag** an, **PC-Steuerung** aus (so ist es voreingestellt). Mehr geht auch später.
   - Limits: 0 lassen (unbegrenzt) oder zum Beispiel 30 Nachrichten pro 10 Minuten setzen. Sinnvoll, falls das Handy mal verloren geht.
   - Oben auf der Seite muss jetzt stehen: „Remote ist an: https://…“.

## Teil 3: Das iPhone koppeln

Jedes Handy wird einmal gekoppelt und bekommt dabei sein **eigenes Token** (ein langes Geheimnis, das nur auf dem Handy liegt).

1. In Jarvis am PC: Einstellungen → Remote. Bei „Name des Geräts“ z. B. `iPhone Moritz` eintragen und auf **Koppel-Link erzeugen** klicken.
2. Es erscheint ein Link wie `https://mein-pc.tail1a2b3.ts.net/pair#…` mit Restzeit. **Er gilt 5 Minuten und nur einmal.**
3. Den Link aufs iPhone bringen: **Kopieren** und per AirDrop, Nachrichten an dich selbst oder Notizen schicken. Nicht in ein Gruppen-Chat, nicht an andere.
4. Auf dem iPhone den Link in **Safari** öffnen (nicht in einer In-App-Vorschau). Die Seite sagt „Gekoppelt“ und führt zu Jarvis.
   Der Code steht im Teil nach dem `#` der Adresse und wird nie an einen Server geschickt; die Seite löscht ihn nach dem Einlösen aus der Adresszeile.
5. Zurück am PC: Das Gerät steht in der Liste, „aktiv · zuletzt gerade eben“.
6. Optional: In Safari **Teilen → Zum Home-Bildschirm**. Dann öffnet Jarvis wie eine App.

Klappt der Link nicht („ungültig, abgelaufen oder schon benutzt“): einfach am PC einen neuen erzeugen. Nach 5 falschen Versuchen sperrt die
Kopplung 15 Minuten lang; ein schon gekoppeltes Handy ist davon nicht betroffen.

## Teil 4: Testen (im Mobilfunk, nicht im WLAN)

Schalte auf dem iPhone **WLAN aus**, damit sicher nur das Tailnet dazwischen liegt. Tailscale-App muss „Connected“ zeigen.

| Was du tust | Das muss passieren |
|---|---|
| Jarvis (Home-Bildschirm-Symbol oder Safari) öffnen | Seite lädt, oben der Streifen „Remote (eingeschränkt) · Auskunft, Alltag · iPhone Moritz“ |
| „Wie spät ist es?“ | Antwort kommt |
| „Wie wird das Wetter?“ / „Stell einen Timer auf 5 Minuten“ | Antwort kommt, der Timer erscheint auch am PC |
| „Öffne den Notepad“ / „Schreibe eine Notiz“ / „Zeige meine Mails“ | **„Das geht nur am PC.“** |
| „Lösche alle Erinnerungen“ | „Das geht nur am PC.“ (Rückfragen gibt es nie am Handy) |
| Am PC etwas in derselben Unterhaltung schreiben | Erscheint nach ca. 2 Sekunden auf dem iPhone, und umgekehrt |
| Seitenleiste öffnen | Kein „Settings“, kein „New Project“, kein „⋯“-Menü |
| In den Einstellungen am PC: Gerät **Sperren** | Das iPhone bekommt sofort keine Antworten mehr (Seite zeigt „nicht angemeldet“ / Kopplungsseite) |

Im Aktionsprotokoll (Einstellungen → Activity) steht jede Handy-Nachricht mit dem Gerätenamen.

**Bekannte Grenzen:** Der PC muss an sein und Jarvis laufen (auch kein Standby). Das Weckwort geht auf dem iPhone nicht (iOS lässt das nicht zu), der
Mikrofon-Knopf der Seite ist in Safari weniger zuverlässig als am PC; die iOS-Tastatur hat ein Diktier-Symbol, das immer geht.
Timer und Wecker klingeln am PC, nicht am Handy (keine Push-Meldungen).

## Teil 5: Notaus (alles nur am PC)

Von schwach nach stark:

1. **Ein Gerät sperren:** Einstellungen → Remote → beim Gerät „Sperren“. Wirkt sofort. Danach „Entfernen“, wenn du die Zeile loswerden willst.
2. **Alle Geräte sperren:** „Alle Geräte sperren“ (zweimal klicken). Offene Koppel-Links werden auch ungültig.
3. **Remote ausschalten:** Schalter „Remote enabled“ aus. Der Remote-Name wird dann komplett abgelehnt, auch von gekoppelten Geräten. Nichts ist gelöscht,
   einschalten genügt.
4. **Tailscale-Weiterleitung abschalten:** in der Eingabeaufforderung
   ```
   tailscale serve reset
   ```
   Danach ist Jarvis im Tailnet gar nicht mehr erreichbar.
5. **Ganz hart:** `JARVIS_REMOTE_HOST` aus der `.env` löschen und Jarvis neu starten, oder Tailscale auf dem PC beenden.

**Handy verloren oder gestohlen?** Sofort am PC „Alle Geräte sperren“ (oder das eine Gerät), dann im Tailscale-Admin (`login.tailscale.com/admin/machines`)
das iPhone entfernen.

---

## Sicherheits-Checkliste (vor dem ersten Einsatz einmal abhaken)

- [ ] **Nie `tailscale funnel` benutzen.** Funnel stellt Jarvis ins öffentliche Internet. Prüfen: `tailscale funnel status` zeigt, dass nichts freigegeben ist
      (oder den Befehl gar nicht kennt). Taucht in der Ausgabe von `tailscale serve status` irgendwo „Funnel on“ auf: sofort `tailscale serve reset`.
- [ ] Zwei-Faktor-Anmeldung für das Konto, mit dem du Tailscale benutzt, ist an.
- [ ] Im Tailscale-Admin (`login.tailscale.com/admin/machines`) stehen nur deine eigenen Geräte. Unbekannte entfernen.
- [ ] Optional, aber empfohlen: In den Tailscale-Regeln (`login.tailscale.com/admin/acls`) nur dein iPhone auf deinen PC zulassen.
- [ ] Jarvis hört nur lokal: In der Eingabeaufforderung `netstat -ano | findstr :8000` zeigt nur `127.0.0.1:8000` (nie `0.0.0.0:8000`).
- [ ] In `.gitignore` stehen `remote_devices.json` und `remote_devices.json.defekt` (dort liegen die Geräte als Hash, nie als Klartext), außerdem `.env`.
- [ ] Die `.env` und `remote_devices.json` hast du nie weitergegeben (nicht in Chats, nicht auf GitHub).
- [ ] Koppel-Links gehen nur an dich selbst. Jeder, der den Link in den 5 Minuten zuerst öffnet, bekommt Zugang.
- [ ] Stufe „PC-Steuerung“ bleibt aus, solange du sie nicht brauchst.
- [ ] Der Test aus Teil 4 hat „Das geht nur am PC.“ für Programme, Notizen und Mail gezeigt.
- [ ] „Sperren“ am PC wurde einmal ausprobiert und wirkt sofort am iPhone (danach neu koppeln).
- [ ] `py stabilitaetstest.py 120` endet mit `STABILITY TEST PASSED` (enthält jetzt auch Remote: falsche Token, verbotene Adressen, Limits, Sperren).
- [ ] Der PC ist mit Windows-Passwort/PIN gesperrt, wenn du nicht davor sitzt (Jarvis selbst läuft weiter).

## Wenn etwas nicht klappt

| Problem | Ursache und Lösung |
|---|---|
| Safari: Seite lädt nicht / Zeitüberschreitung | PC aus oder im Standby; Jarvis läuft nicht; `tailscale serve status` leer (Befehl aus Teil 2 noch einmal); Tailscale auf dem iPhone nicht „Connected“ |
| „Host nicht erlaubt“ (403) | `JARVIS_REMOTE_HOST` weicht vom Namen in `tailscale serve status` ab, oder „Remote enabled“ ist aus, oder Jarvis wurde nach dem Ändern der `.env` nicht neu gestartet |
| Zertifikat-Warnung / kein HTTPS | In der Admin-Konsole unter DNS „HTTPS-Zertifikate“ aktivieren (Teil 1, Punkt 5), dann `tailscale serve --bg 8000` erneut |
| Kopplungsseite: „ungültig, abgelaufen oder schon benutzt“ | Link nur 5 Minuten und nur einmal gültig, neuen erzeugen; Safari statt In-App-Vorschau |
| „Zu viele Versuche“ (429) bei der Kopplung | 15 Minuten warten (oder Jarvis neu starten); danach neuen Link |
| „Zu viele Anfragen“ (429) bei einer Nachricht | Dein Remote-Limit (Einstellungen → Remote) ist erreicht; auf 0 stellen oder kurz warten |
| Jarvis fragt am Handy „nicht angemeldet“ | Gerät wurde gesperrt oder das Cookie ist weg (Safari-Websitedaten gelöscht): neu koppeln |
| Mikrofon-Knopf tut nichts | Safari verlangt Erlaubnis für das Mikrofon (Einstellungen → Safari → Mikrofon) und HTTPS; sonst die Diktier-Taste der Tastatur nehmen |
| Antworten kommen nur am PC | Das Handy ist nicht im selben Tailnet-Konto, oder die Unterhaltung am PC ist eine andere (Seitenleiste prüfen) |
