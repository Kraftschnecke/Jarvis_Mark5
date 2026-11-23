# DESIGN_SERVER: Jarvis dauerhaft online (Mark 5, Server)

Ziel: Jarvis läuft auf einem Rechner, der immer an ist (kleiner Server im Netz, später zusätzlich ein Raspberry Pi als Zimmer-Gerät).
Erinnerungen, Wecker, Timer und Hinweise melden sich auch im Urlaub oder bei ausgeschaltetem PC, per Push aufs Handy.

## Aufbau

- **Kern** (Server): Chat, Erinnerungen, Wecker, Timer, Kalender, Listen, Notizen, Wetter, News. Läuft ohne Fenster (`server_main.py`).
- **Geräte** (später): PC (Lautstärke, Musik, PC-Lage, Dateien) und Raspberry Pi (Wecker-Lautsprecher, Smart Desk) melden sich beim Kern an.
  Ist ein Gerät aus, sagt Jarvis ehrlich: "Dafür muss dein PC an sein."
- **Push**: ntfy (`notify.py`). Jarvis schickt eine kleine Web-Anfrage an einen geheimen Themennamen; die ntfy-App auf dem Handy zeigt sie an.

## Schritte

| Schritt | Inhalt | Stand |
|---|---|---|
| S1 | Start ohne Fenster: `server_main.py`; Windows-Pakete (`pycaw`, `pystray`) nur unter Windows | fertig |
| S2 | Hintergrund-Takt `server_loop.py`: holt Meldungen und Hinweise ohne offene Seite ab | fertig |
| S3 | Push über ntfy (`notify.py`), Test mit `py server_main.py --test-push`; `.env`: `NTFY_TOPIC`, optional `NTFY_SERVER`, `NTFY_TOKEN` | fertig |
| S4 | **Besitzer-Zugang (Vollzugriff)**: Gerät mit `full`, Kopplung nur im Server-Terminal (`server_main.py --pair-owner`); Daten bleiben als Dateien auf dem Server, einmal kopiert | fertig |
| S5 | Server einrichten: `ANLEITUNG_SERVER.md` (Anbieter, Tailscale, Dienst, Updates, Sicherung) | Anleitung fertig, Einrichtung durch dich |
| S6 | PC als Gerät anmelden (PC-Aufgaben über den Server) | später |
| S7 | Raspberry Pi als Zimmer-Gerät (Wecker mit Lautsprecher) | später |

## Was im Code gefunden wurde (wichtig für S4)

1. **Daten liegen in lokalen Dateien**, nicht in Neon: `reminders.json`, `widgets.json` (Notizen, Ziele, Termine, Listen), `settings.json`,
   `hints_state.json`, `folders.json` u. a. Neon hält nur Gedächtnis und Projekte. Ein Server hätte deshalb zunächst eigene, leere Daten.
   Zwei Jarvis (PC und Server) mit getrennten Dateien würden auseinanderlaufen.
2. **Remote ist absichtlich eingeschränkt** (`DESIGN_REMOTE.md`): Einstellungen ändern, Notizen schreiben, Dateien usw. gehen nur am PC.
   Auf dem Server gibt es keinen "PC-Bildschirm". Der Besitzer braucht dort einen eigenen, sicheren Vollzugriff.

## Entscheidung für S4 (umgesetzt)

- Der **Server ist der einzige Besitzer der Daten** (die Dateien liegen dort, mit täglicher Sicherung). Der PC öffnet dieselbe Seite über Tailscale.
- **Besitzer-Zugang** über ein eigenes Gerätetoken mit Vollzugriff (nur für den PC, Kopplung nur im Server-Terminal, nie über die Weboberfläche);
  Handys behalten die eingeschränkten Stufen.
- **PC-Funktionen** laufen weiter lokal auf dem PC und werden vom Server nur angefragt, wenn der PC angemeldet ist (S6).
- Einmalig werden die vorhandenen Dateien auf den Server kopiert (Anleitung in S5).

## Sicherheit

- Der Server hört nur auf 127.0.0.1; Zugang nur über Tailscale (`tailscale serve`), nie `tailscale funnel`.
- Push: Themenname = Passwort (16–64 Zeichen), nur https, höchstens 30 Nachrichten pro Stunde, Fehler ohne Themenname im Terminal.
  Über ntfy.sh (öffentlich) laufen die Texte der Meldungen im Klartext. Wer das nicht will, betreibt später einen eigenen ntfy-Server (`NTFY_SERVER`).
- Schlüssel (OpenAI, Datenbank, ntfy) stehen nur in der `.env` auf dem Server, nie im Code oder in Git.

## Vollzugriff im Detail (S4)

- Ein gekoppeltes Gerät hat das Merkmal `full` (nur für Geräte des Besitzers, nie für Gast-Bereiche). Die Kopplung dafür gibt es nur mit
  `create_pairing(..., full=True)`, aufgerufen von `server_main.py --pair-owner`. Die Weboberfläche (`/api/remote/pair_link`) erzeugt nie so einen Code.
- Weil das Terminal ein eigener Prozess ist, liegt der Code zusätzlich (nur als Hash, 5 Minuten, einmal benutzbar, Dateirechte 600) in
  `remote_pending_full.json` neben `remote_devices.json`. Der Server liest die Datei beim Einlösen.
- Der Server prüft wie bei jedem Handy: Remote-Name, Cookie, Origin, nicht gesperrt. Danach behandelt `become_owner()` die Anfrage wie am PC
  (volle Einstellungen, Nachrichten ohne Remote-Einschränkung). Handys bleiben unverändert eingeschränkt.
- Im Server-Betrieb schaltet `server_main.py` Remote ein, wenn `JARVIS_REMOTE_HOST` gesetzt ist (sonst käme niemand an die Oberfläche).

## Bekannte Grenze bis S6

Auf dem Server zeigen PC-Status, PC-Lage und Laufwerke den **Server**, nicht deinen PC, und Lautstärke/Musik gehen nicht. Diese Fenster bleiben dort aus.
S6 verbindet den PC als Gerät, dann gehen diese Aufgaben wieder an deinen PC.
