# ANLEITUNG: Jarvis auf einem Server (Mark 5, Server S5)

Hintergrund steht in `DESIGN_SERVER.md`. Hier steht nur, **was du tust**, in der Reihenfolge. Plane 1 bis 1,5 Stunden ein, beim ersten Mal.
Du brauchst: deinen PC (Windows), das iPhone mit der ntfy-App (Push läuft schon), ein Konto beim Server-Anbieter (Beispiel hier: Hetzner Cloud)
und dein bestehendes Tailscale-Konto.

**Vorher am PC:** Alles, was neu ist (PC-Lage, Server-Dateien), committen und nach GitHub pushen. Der Server holt den Code von dort.

Kurz, was am Ende passiert: Ein kleiner Server in Deutschland oder Finnland führt Jarvis rund um die Uhr aus. Du erreichst ihn nur über Tailscale
(`https://…ts.net`), vom PC und vom Handy. Erinnerungen und Wecker kommen per Push. Kein Port ist offen außer SSH (für dich, nur mit Schlüssel).

---

## Teil 1: Schlüssel und Server bestellen

1. **SSH-Schlüssel am PC** (PowerShell): `ssh-keygen -t ed25519`. Dreimal Enter ist okay, besser mit Passwort für den Schlüssel.
   Den öffentlichen Teil anzeigen: `type $env:USERPROFILE\.ssh\id_ed25519.pub`. Die Zeile (beginnt mit `ssh-ed25519`) brauchst du gleich.
2. **Anbieter-Konto** anlegen (Hetzner Cloud: `hetzner.com/cloud`), ein neues Projekt „Jarvis" erstellen.
3. **Server erstellen:** Standort Falkenstein, Nürnberg oder Helsinki (EU). Image **Ubuntu 24.04**. Der kleinste Typ reicht (2 GB RAM genügen).
   Bei „SSH-Keys" deinen öffentlichen Schlüssel einfügen. Name z. B. `jarvis`. Erstellen.
4. Du bekommst eine **IP-Adresse**. Notiere sie.

## Teil 2: Erste Absicherung

1. Verbinden (PowerShell): `ssh root@DEINE-IP` (Frage nach dem Fingerabdruck mit `yes` beantworten).
2. Benutzer anlegen, Updates, Firewall:
   ```
   adduser jarvis
   usermod -aG sudo jarvis
   apt update && apt -y upgrade
   apt -y install python3-venv git ufw unattended-upgrades
   ufw allow OpenSSH
   ufw --force enable
   rsync --archive --chown=jarvis:jarvis ~/.ssh /home/jarvis
   timedatectl set-timezone Europe/Stockholm
   ```
   Die Zeitzone ist wichtig: Der Server läuft sonst in UTC, und „morgen um 8" wäre eine Stunde falsch.
3. **Neues Fenster** öffnen und prüfen, dass `ssh jarvis@DEINE-IP` klappt, **bevor** du weitermachst. Dann im alten Fenster (root) das Passwort-Login
   abschalten: `nano /etc/ssh/sshd_config`, dort `PermitRootLogin no` und `PasswordAuthentication no` setzen, speichern (Strg+O, Enter, Strg+X),
   `systemctl restart ssh`. Ab jetzt nur noch als `jarvis` mit Schlüssel.

## Teil 3: Tailscale auf dem Server

1. Als `jarvis`: `curl -fsSL https://tailscale.com/install.sh | sh`, dann `sudo tailscale up`. Den angezeigten Link am PC öffnen und mit **demselben
   Konto** anmelden wie am PC und am iPhone.
2. Name des Servers im Tailnet: `tailscale status`. Du brauchst den vollen Namen, z. B. `jarvis.tailabc.ts.net`. (MagicDNS und HTTPS-Zertifikate sind
   schon aktiv, siehe `ANLEITUNG_TAILSCALE.md`, Teil 1.)
3. `sudo tailscale serve --bg 8000` und prüfen mit `tailscale serve status`. **Nie `tailscale funnel`**, das stellt Jarvis ins öffentliche Internet.

## Teil 4: Jarvis installieren

1. **Zugang zu GitHub** (nur Lesen): `ssh-keygen -t ed25519 -f ~/.ssh/jarvis_deploy -N ""`, dann `cat ~/.ssh/jarvis_deploy.pub`. Die Zeile bei GitHub im
   Repository unter *Settings → Deploy keys → Add deploy key* einfügen (Haken „Allow write access" **nicht** setzen).
   Dann `nano ~/.ssh/config` mit dem Inhalt:
   ```
   Host github.com
     IdentityFile ~/.ssh/jarvis_deploy
     IdentitiesOnly yes
   ```
2. Code holen und installieren:
   ```
   git clone git@github.com:Kraftschnecke/Jarvis_Mark5.git
   cd Jarvis_Mark5
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
3. **`.env` vom PC kopieren** (am PC, PowerShell, im Jarvis-Ordner): `scp .env jarvis@DEINE-IP:Jarvis_Mark5/.env`. Dann auf dem Server `nano .env` und
   ergänzen bzw. prüfen:
   ```
   JARVIS_REMOTE_HOST=jarvis.tailabc.ts.net        (dein Name aus Teil 3)
   NTFY_TOPIC=dein-geheimer-name                    (derselbe wie am PC)
   ```
   Danach `chmod 600 .env`. Die Datei enthält deine Schlüssel und darf nirgends sonst liegen.
4. **Push testen:** `.venv/bin/python server_main.py --test-push`. Das Handy muss die Nachricht zeigen.

## Teil 5: Deine Daten mitnehmen (einmalig)

Erinnerungen, Notizen, Ziele, Termine und Einstellungen liegen in Dateien, nicht in Neon (Gedächtnis und Projekte schon). Diese Dateien kommen einmal auf den
Server. **Danach arbeitest du nur noch dort**, sonst laufen PC und Server auseinander.

1. Am PC Jarvis beenden.
2. Im Jarvis-Ordner am PC (PowerShell), alles in einer Zeile pro Datei:
   ```
   scp reminders.json widgets.json settings.json jarvis@DEINE-IP:Jarvis_Mark5/
   ```
   (Gibt es eine Datei nicht, ist das okay. Dann fehlt sie eben.)

## Teil 6: Als Dienst starten

1. `sudo nano /etc/systemd/system/jarvis.service` mit diesem Inhalt:
   ```
   [Unit]
   Description=J.A.R.V.I.S.
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=jarvis
   WorkingDirectory=/home/jarvis/Jarvis_Mark5
   ExecStart=/home/jarvis/Jarvis_Mark5/.venv/bin/python server_main.py
   Restart=on-failure
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1
   NoNewPrivileges=true
   PrivateTmp=true

   [Install]
   WantedBy=multi-user.target
   ```
2. `sudo systemctl daemon-reload && sudo systemctl enable --now jarvis`
3. Prüfen: `systemctl status jarvis` und `journalctl -u jarvis -n 30`. Du solltest „Push AN" und „Remote ist im Server-Betrieb eingeschaltet" lesen.

## Teil 7: Deinen PC koppeln (Vollzugriff)

1. Auf dem Server: `cd ~/Jarvis_Mark5 && .venv/bin/python server_main.py --pair-owner "PC Moritz"`. Es erscheint ein Link
   `https://jarvis.tailabc.ts.net/pair#XXXX-XXXX`. Er gilt 5 Minuten und nur einmal.
2. Öffne den Link **am PC im Browser** (Tailscale muss laufen). Danach ist dieser Browser als „PC Moritz" gekoppelt und zeigt Jarvis mit allen
   Einstellungen wie sonst. Lesezeichen setzen.
3. **Handy:** Dort Einstellungen → Remote → „Neues Gerät koppeln" (am PC-Browser), den Link ans iPhone schicken. Das Handy bleibt eingeschränkt, wie bisher.

Vollzugriff gibt es nur über diesen Befehl im Server-Terminal. Wer nur das Tailscale-Konto hat, kommt höchstens zur Kopplungsseite.
Verlorener PC: In der Geräteliste (Einstellungen → Remote) sperren.

## Teil 8: Betrieb

- **Update:** auf dem Server `cd ~/Jarvis_Mark5 && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart jarvis`.
- **Sicherung** (täglich 3 Uhr): `crontab -e`, Zeile anfügen:
  ```
  0 3 * * * cd /home/jarvis/Jarvis_Mark5 && mkdir -p ~/backups && tar czf ~/backups/daten-$(date +\%F).tgz *.json && find ~/backups -mtime +14 -delete
  ```
  Ab und zu eine Sicherung zum PC holen: `scp jarvis@DEINE-IP:backups/daten-DATUM.tgz .`
- **Logs:** `journalctl -u jarvis -f`.

## Das geht (noch) nicht auf dem Server

Alles, was auf deinen PC zugreift: Lautstärke, Musik, PC-Status, PC-Lage und Laufwerke (zeigen sonst den Server!), Programme öffnen, Dateien am PC.
Das kommt mit S6 (PC als Gerät anmelden). Bis dahin die PC-Fenster in der Fenster-Verwaltung ausgeschaltet lassen.

## Wenn etwas nicht klappt

| Problem | Prüfen |
|---|---|
| Link zeigt „nicht erlaubt" (403) | `JARVIS_REMOTE_HOST` in der `.env` genau wie in `tailscale status`; Dienst neu starten |
| Kopplungsseite sagt „ungültig" | Link ist älter als 5 Minuten oder schon benutzt: neuen Befehl ausführen |
| Kein Push | `.venv/bin/python server_main.py --test-push` |
| Erinnerung zur falschen Zeit | `timedatectl`: Zeitzone Europe/Stockholm? |
| Dienst startet nicht | `journalctl -u jarvis -n 50` (Fehlermeldung ohne Schlüssel kopieren und mir schicken) |
