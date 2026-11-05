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
