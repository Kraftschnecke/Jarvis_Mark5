# Rollen-Seiten (Mark 5, Schritt C5b)

Ziel: Nach der Kopplung bekommt jedes Gerät **seine** Seite. Das macht die HTML-Dateien kürzer und lesbar, und die Trennung
steht an einer Stelle im Server statt verstreut im Browser-Code.

## Ablauf

```
Gerät ruft  /  auf  (über den Remote-Namen)
  │
  ├─ nicht gekoppelt ......... pair.html (401): Code eintippen oder Link öffnen
  ├─ gekoppelt als Gast ...... guest.html  (nur Gast-Dateien, siehe unten)
  ├─ gekoppelt als Besitzer .. index.html  (wie bisher)
  └─ am PC (localhost) ....... index.html  (ohne Kopplung, wie bisher)
```

Später kommen weitere Rollen als eigene Seite dazu (z. B. `admin.html`): Eintrag in `remote_policy.py`, eine HTML-Datei, ein Test.

## Was wo steht

| Was | Wo |
|---|---|
| Welche Seite bekommt wer | `server.py`, `remote_get` (Gast-Zweig) und `remote_policy.guest_file()` |
| Welche Dateien darf ein Gast holen | `remote_policy.GUEST_STATIC` (alles andere unter `web/` ist für Gäste 404, auch `app_owner.js`) |
| Die Gast-Seite | `web/guest.html` |
| Abmelden | `POST /api/remote/logout` (`server.py`, `remote_post`), Cookie löschen: `remote_gate.clear_cookie_header()` |
| Wechsel mit neuem Code | `server.py`, öffentlicher Zweig von `remote_post`: der alte Zugang des Geräts wird entfernt |
| Kurzcode | `remote_auth.py`: `make_code()`, `normalize_code()` |

## Die Browser-Dateien (Stufe 2, erledigt)

`app.js` gibt es nicht mehr. Der Code ist in vier Dateien geteilt, die als normale Skripte nacheinander laden und sich die
globalen Namen teilen (so war es vorher auch, nur in einer Datei):

| Datei | Inhalt | Besitzer | Gast |
|---|---|---|---|
| `app_base.js` | Hilfen, Chat, Sprache, Widgets, Eingabe, Dialog, Menü, Seitenleiste | ja | ja |
| `app_state.js` | Einstellungs-Zustand, Aussehen, Remote-/Gast-Modus, Abmelden | ja | ja |
| `app_owner.js` | Einstellungs-Dialog, Aktionsprotokoll, Ordner, Remote-Verwaltung, Gedächtnis, „Alle Erinnerungen löschen“ | ja | **nie** |
| `app_start.js` | Handy-Einstellungen, Meldungen im Hintergrund (Timer, Klingeln), Start | ja | ja |

Reihenfolge: `app_base.js`, `app_state.js`, `app_owner.js` (nur Besitzer), `app_start.js`.
`index.html` lädt alle vier, `guest.html` nur drei. Der Server liefert einem Gast `app_owner.js` nicht aus (404), und der Test prüft,
dass in den drei Gast-Dateien keine Besitzer-Funktion steht.

Reines Zerschneiden nach Zeilen, keine Änderung der Logik. Neu ist nur, dass `el` und `smallButton` (Hilfsfunktionen) in
`app_base.js` stehen statt mitten in den Einstellungen.

## guest.html gegenüber index.html

Weg: „New Project“, der Einstellungs-Knopf und -Dialog, der Dialog „Alle Erinnerungen löschen“, `remote_admin.js`, `app_owner.js`.
Dazu: `<body class="tester remote">` von Anfang an (kein Aufblitzen der Besitzer-Oberfläche), eigener Titel.
Damit der gemeinsame Code auch ohne weggelassene Elemente läuft, holt er Elemente über `byId(id)`: fehlt eines, gibt es ein loses
Ersatz-Element, das nie angezeigt wird.

## Regeln (vom Test geprüft)

- Gast bekommt auf `/`, `/index.html`, `/guest.html` immer die Gast-Seite, nie `index.html`.
- Gast bekommt nur Dateien aus `GUEST_STATIC`; `remote_admin.js`, `server.py`, `.env`, `profiles.json`, Pfade mit `..` sind 404.
- Jede Datei, die `guest.html` lädt, steht in `GUEST_STATIC` (sonst wäre die Seite kaputt).
- Abmelden: nur POST, nur mit Origin, nur angemeldet; der Eintrag verschwindet, das Cookie wird gelöscht, das Token geht nicht mehr.
- Neuer Code auf einem gekoppelten Gerät: alter Zugang weg, neuer gilt; ein falscher Code lässt den Zugang bestehen.

## Noch offen

- `app_base.js` ist mit rund 1900 Zeilen die größte Datei (Chat, Widgets, Seitenleiste). Sie lässt sich bei Bedarf weiter teilen, ist aber für Besitzer und Gast gleich.
- Test-Helfer: `test/webapp.py` liest die Dateien in Ladereihenfolge als einen Text, damit „steht im Code“-Prüfungen weiter gelten.
