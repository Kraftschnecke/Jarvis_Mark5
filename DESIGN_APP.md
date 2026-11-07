# DESIGN_APP: Jarvis als richtige App (Mark 5, Phase 4B)

Entscheidung aus Phase 3: **B, dann Remote über Tailscale**. Dieses Dokument beschreibt Phase 4B (die App am PC). Das Handy
(iPhone) kommt als eigener Schritt danach und bekommt ein eigenes Design (`DESIGN_REMOTE.md`).

## 1. Ziele (wie es sich anfühlen soll)

- Jarvis startet wie ein Programm: ein Klick (oder automatisch mit Windows), ein eigenes Fenster ohne Browserleiste, ein Icon im Tray.
- Ein globaler Hotkey (Vorschlag **Strg+Leertaste**) bringt Jarvis sofort nach vorn und setzt den Cursor ins Eingabefeld.
- Timer, Erinnerungen und Wecker melden sich als Windows-Benachrichtigung, auch wenn das Fenster zu ist.
- Ein eigener Look mit animiertem "Jarvis-Kern", der zeigt, ob Jarvis zuhört, nachdenkt oder spricht.
- Der Server bleibt auf `127.0.0.1`. Die App ändert nichts an der Sicherheit: nur dein PC, nur du.

## 2. Was bleibt, was kommt dazu

Der ganze Jarvis (Server, Fähigkeiten, Datenbank, Weboberfläche) bleibt unverändert. Die App ist eine **Hülle** um die bestehende
Weboberfläche. Das hat einen großen Vorteil: Jede Verbesserung der Weboberfläche steht sofort auch in der App, und alles, was
du im Browser nutzt, gibt es weiter.

## 3. Die Stufen

| Stufe | Was | Aufwand | Ergebnis |
|---|---|---|---|
| 4B.2 | **PWA**: Manifest, Icons, Service-Worker | klein | Im Browser "Installieren": eigenes Fenster, Icon im Startmenü, Vollbild ohne Adressleiste |
| 4B.3 | **Desktop-Hülle**: startet den Server selbst, ein Fenster, Tray, "in den Tray schließen", Start mit Windows | mittel | Ein Klick auf das Icon startet alles |
| 4B.4 | **Systemanbindung**: globaler Hotkey, Benachrichtigungen, Schnelleingabe | mittel | Strg+Leertaste, Meldungen bei Timern |
| 4B.5 | **Neuer Look**: Jarvis-Kern, weichere Übergänge, verschiebbare Widgets | mittel bis groß | "Wow"-Teil |
| 4B.6 | **Installer** und Versionsanzeige | mittel | Eine Datei zum Installieren und Aktualisieren |

### 4B.2 PWA (diese Stufe ist gebaut)

Eine PWA ist eine Webseite, die der Browser als App installieren lässt. Dafür braucht es drei Dinge, alle in `web/`:

- `manifest.webmanifest`: Name, Startadresse, "standalone" (ohne Browserleiste), Farben, Icons.
- Icons: `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (für runde/abgeschnittene Icons, Inhalt im sicheren Bereich),
  `apple-touch-icon.png` (180 Pixel, für das iPhone).
- `sw.js`, ein winziger **Service-Worker**. Chrome und Edge installieren eine Seite nur mit einem solchen. Unserer reicht jede Anfrage
  **unverändert an den Server durch** und speichert nichts: kein Zwischenspeicher, keine Offline-Kopie. Damit kann nie eine alte
  Oberfläche hängen bleiben, und Gespräche oder Daten liegen nirgends im Browser.

Installieren: in Chrome oder Edge `http://localhost:8000` öffnen, dann in der Adressleiste auf das Installieren-Symbol (oder
Menü, "Jarvis installieren"). `localhost` zählt für den Browser als sicher, deshalb braucht es dafür kein HTTPS.

Grenze der PWA: Sie ist nur ein Fenster. Sie startet den Server nicht selbst (das macht erst 4B.3), und ein Hotkey oder Tray
geht damit nicht.

### 4B.3 Desktop-Hülle: Technikwahl

Es gibt vier Wege. Wichtig ist eine Eigenheit von Jarvis: Die Spracherkennung (Wake Word, Mikrofon) nutzt die **Spracherkennung
des Browsers** (`webkitSpeechRecognition`). Die gibt es in Chrome und Edge, aber **nicht** in jeder eingebetteten Fensterhülle.

| Weg | Wie | Vorteile | Nachteile |
|---|---|---|---|
| **A: Edge/Chrome im App-Modus** | Python startet den Server und öffnet `msedge --app=http://127.0.0.1:8000`; Tray und Hotkey auch aus Python | Spracherkennung funktioniert wie im Browser; Rest bleibt in Python; klein | Fenster ist ein Edge-Fenster (sieht aber aus wie eine App) |
| B: pywebview | Python-Fenster mit eingebettetem Edge (WebView2) | alles in Python, sehr klein | Spracherkennung im Webview unsicher |
| C: Electron | Node.js-Hülle, Chromium eingebaut | viel Dokumentation, volle Kontrolle | 150 MB, zweite Sprache, Spracherkennung ohne Google-Schlüssel nicht verfügbar |
| D: Tauri | Rust-Hülle mit WebView2 | winzig | Rust nötig, gleiche Spracherkennungs-Frage wie B |

**Empfehlung: Weg A.** Er behält alles, was heute funktioniert (auch das Wake Word), und bleibt in Python, also in dem, was du
verstehen willst. Ob B für dich gut genug ist, lässt sich in 4B.3 mit einem kleinen Test klären; die Entscheidung dazu fällt dann
mit dem Ergebnis. Tray-Symbol und Hotkey kommen aus Python (`pystray`, `keyboard` oder `pynput`), Benachrichtigungen über Windows
(`winotify` oder `plyer`). Das ist **die** Stelle, an der neue Pakete dazukommen (Eintrag in `requirements.txt`).

### 4B.4 Systemanbindung

- **Hotkey:** global (auch wenn ein anderes Programm vorn ist). Er bringt das Fenster nach vorn, er sendet nichts und führt nichts aus.
- **Benachrichtigungen:** nur für das, was Jarvis ohnehin meldet (Timer, Erinnerung, Wecker, ab 2.29 optional die Hinweise).
  Sie enthalten kurze Texte, nie Mail- oder Dateiinhalte.
- **Schnelleingabe:** kleines Eingabefeld per Hotkey, Antwort im Fenster. Es nutzt denselben Weg (`/api/message`) wie das Chatfenster,
  also dieselben Sicherheitsstufen und Rückfragen.

### 4B.5 Neuer Look

Erst Skizzen (Standbild des Jarvis-Kerns in drei Zuständen: hört zu, denkt, spricht), dann umsetzen. Der Kern ist eine kleine
Zeichnung (SVG/Canvas) mit Animation, die auf die vorhandenen Zustände der Seite reagiert (`ready`, `thinking`, `speaking`). Dazu
weichere Übergänge und Widgets, die man verschieben kann. Alles lässt sich in den Einstellungen abschalten (Bewegung reduzieren).

### 4B.6 Installer

Ein Programm als Installer (Python als Programm verpacken, z. B. PyInstaller, dazu ein Installationsprogramm wie Inno Setup).
Die `.env` mit dem OpenAI-Schlüssel kommt nie in den Installer; beim ersten Start fragt die App danach. Die Version steht unter
"About".

## 4. Sicherheit

- Server weiter nur `127.0.0.1`; Host- und Origin-Prüfung bleiben (der Test `test_pwa.py` prüft, dass auch Manifest und
  Service-Worker bei fremdem Host mit 403 abgewiesen werden).
- Der Service-Worker speichert nichts (Test: kein `caches`, kein `indexedDB`, keine Antwort wird verändert).
- Der Hotkey öffnet nur das Fenster. Alles, was Jarvis tut, läuft weiter durch Router, Risikostufen und Rückfragen.
- Der Tray-Eintrag "Beenden" stoppt auch den Server, damit kein unsichtbarer Jarvis weiterläuft.

## 5. Offene Punkte

- Weg A oder B für das Fenster (Test mit der Spracherkennung in 4B.3).
- Hotkey-Vorschlag Strg+Leertaste: Windows 11 nutzt ihn nicht, einige Programme (Texteditoren) schon; Taste soll einstellbar sein.
- Wie sich die installierte PWA mit dem Wake Word verhält, prüfst du bei der Abnahme von 4B.2 (siehe unten).

## 6. Abnahme 4B.2 (von Hand)

1. `py server.py`, in Edge oder Chrome `http://localhost:8000` öffnen.
2. Installieren-Symbol in der Adressleiste klicken (oder Menü: Apps, Jarvis installieren). Es erscheint ein eigenes Fenster ohne Adressleiste.
3. In dem Fenster: Chat, Einstellungen, Seitenleiste und Sprache wie im Browser. Wake Word ein: reagiert "Hey Jarvis"?
4. Server beenden und wieder starten, dann das App-Fenster neu laden: es zeigt den neuen Stand (nichts veraltet).
5. In den Browser-Entwicklertools (F12, Reiter "Application", "Service Workers") steht `sw.js` als aktiv; "Cache Storage" ist leer.

## 7. 4B.3 Desktop-Hülle (gebaut): Weg A

**Entscheidung:** Weg A. Das Fenster ist Edge (oder Chrome) im `--app`-Modus, also ohne Adressleiste, mit eigenem Profil
(`.jarvis_app_profile/`, nicht im Git). Grund: Spracherkennung und Wake-Word laufen weiter über die Browser-Funktion, die
ein eingebettetes Fenster oft nicht hat.

**Wie es läuft (`jarvis_app.py`):**
- Der Server läuft im selben Prozess in einem Thread (`server.main(..., on_ready=..., open_browser=False)`). So kann "Beenden"
  ihn mit `shutdown()` sauber anhalten und `main()` räumt wie immer auf (Erinnerungen, Wecker-Ton, Port frei).
  Es gibt bewusst keinen "Beenden"-Endpunkt im Server.
- Zweiter Start, während Jarvis läuft: Port belegt, also wird nur ein Fenster geöffnet, nichts doppelt gestartet.
- Fenster schließen: Jarvis läuft im Tray weiter. Tray-Menü: Jarvis öffnen (Doppelklick), Mit Windows starten (Haken), Beenden.
- Ohne pystray/Pillow: kein Tray, Fenster schließen beendet Jarvis (Hinweis in der Konsole).
- Ohne Edge/Chrome: Notausgang über den Standardbrowser.
- Autostart: Eintrag im Run-Schlüssel des Benutzers (HKCU, keine Adminrechte), Start mit `--background` (ohne Fenster, nur Tray).
- Der Server bleibt auf 127.0.0.1. Neu ist nichts von außen erreichbar.

**Start:** `start_jarvis_app.bat` (nutzt `pyw`, kein Konsolenfenster). `start_jarvis.bat` bleibt als Notweg mit Konsole.

**Abnahme von Hand (4B.3):**
1. `py -m pip install -r requirements.txt` (neu: pystray, Pillow), dann `start_jarvis_app.bat`: App-Fenster öffnet, Tray-Symbol erscheint.
2. Fenster schließen: Tray-Symbol bleibt. Doppelklick darauf öffnet das Fenster wieder (Verlauf noch da).
3. Zweites Mal `start_jarvis_app.bat` während es läuft: kein zweiter Server, nur das Fenster.
4. Mikrofon-Knopf im App-Fenster ausprobieren (Weg-A-Test). Beim ersten Mal Mikrofon erlauben.
5. Tray: "Mit Windows starten" anhaken, abmelden/anmelden: Jarvis ist im Tray, ohne Fenster. Danach wieder abhaken.
6. Tray: Beenden: Symbol weg, `http://localhost:8000` nicht mehr erreichbar.

## 8. 4B.4 Systemanbindung (gebaut)

**Hotkey (`desktop_system.py`):** Standard `Strg+Leertaste`, einstellbar mit `JARVIS_HOTKEY` in der `.env` (z. B. `alt+j`,
`ctrl+shift+f9`; `off` schaltet ihn aus). Erlaubt: Strg/Alt/Shift/Win plus Buchstabe, Ziffer, Leertaste oder F1-F12; mindestens ein
Modifier. Technik: `RegisterHotKey` von Windows. Windows meldet nur genau diese Kombination, es wird keine Taste mitgelesen
(kein Tastatur-Hook, kein Zusatzpaket). Ist die Kombination schon von einem anderen Programm belegt, steht ein Hinweis in der
Konsole und Jarvis läuft ohne Hotkey weiter.

**Was der Hotkey tut:** Er bringt das Jarvis-Fenster nach vorn (oder öffnet es, wenn keins da ist) und setzt den Cursor ins
Eingabefeld (`window focus` in `app.js`). Das ist die Schnelleingabe: Hotkey, tippen, Enter. Die Nachricht läuft wie immer über
`/api/message`, also mit denselben Risikostufen und Rückfragen. Der Hotkey sendet und führt nichts aus. Dieselbe Funktion holt auch
bei einem zweiten Start von `start_jarvis_app.bat` das vorhandene Fenster nach vorn, statt ein zweites zu öffnen.

**Benachrichtigungen:** Wenn ein Wecker oder Timer läutet und das Jarvis-Fenster nicht vorn ist, zeigt Windows eine Meldung über das
Tray-Symbol. Inhalt nur der kurze Name ("Timer abgelaufen: Pizza"), nie Mail- oder Dateiinhalte. Die App fragt dafür `/api/ringing`
ab, so wie die Seite es auch tut. Erinnerungen und die Hinweise aus 2.29 kommen später (sie laufen bisher nur im Seitenfenster).

**Abnahme 4B.4 (von Hand):**
1. `py jarvis_app.py`: In der Konsole steht "Hotkey Strg+Leertaste ist aktiv".
2. Ein anderes Programm vorn, `Strg+Leertaste`: Jarvis-Fenster kommt nach vorn, Cursor blinkt im Eingabefeld. Fenster minimiert: es wird wiederhergestellt.
3. Fenster ganz schließen (X), `Strg+Leertaste`: Fenster öffnet sich neu.
4. Kurzen Timer stellen ("Timer 1 Minute Test"), Fenster in den Hintergrund legen: Windows-Meldung "Timer abgelaufen: ...". Ist das Fenster vorn, kommt keine Meldung.
5. `start_jarvis_app.bat` bei laufender App erneut starten: das vorhandene Fenster kommt nach vorn, kein zweites.
6. `JARVIS_HOTKEY=alt+j` in die `.env`, neu starten: nur `Alt+J` geht. `JARVIS_HOTKEY=off`: kein Hotkey, Hinweis entfällt.
7. Beenden im Tray: Hotkey ist wieder frei.
