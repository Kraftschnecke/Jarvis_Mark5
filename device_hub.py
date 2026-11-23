"""Warteschlange zwischen Server und Geraet (S6, DESIGN_GERAET.md).

Das Geraet (PC-Agent) fragt per Long-Polling "gibt es etwas fuer mich?" (``next_job``) und liefert das Ergebnis ab (``submit``).
Der Server stellt Auftraege mit ``request`` und wartet hoechstens ein paar Sekunden. Nichts hier startet etwas auf dem PC:
Auftraege kommen nur aus der festen Liste in device_commands.py, geprueft, bevor sie in die Warteschlange gehen.
"""
import secrets
import threading
import time

import device_commands

ONLINE_SECONDS = 45            # so lange gilt ein Geraet nach seiner letzten Anfrage als verbunden (Long-Poll dauert bis 25 s)
MAX_WAIT = 30                  # laengstes Warten eines Long-Polls
REQUEST_TIMEOUT = 8            # so lange wartet der Server auf ein Ergebnis
MAX_QUEUED = 20                # pro Geraet; mehr offene Auftraege lehnt der Hub ab


class DeviceError(Exception):
    """Gemeinsame Basis: Der Auftrag ging nicht durch (aus, zu langsam oder fehlgeschlagen)."""


class DeviceOffline(DeviceError):
    """Kein Geraet verbunden."""


class DeviceTimeout(DeviceError):
    """Das Geraet hat nicht rechtzeitig geantwortet."""


class DeviceFailed(DeviceError):
    """Das Geraet meldet einen Fehler oder ein ungueltiges Ergebnis."""


class DeviceHub:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._cond = threading.Condition()
        self._seen = {}            # Geraete-Id -> Zeitpunkt der letzten Anfrage
        self._queue = {}           # Geraete-Id -> Liste offener Auftraege
        self._jobs = {}            # Auftrags-Id -> {"device", "command", "done", "ok", "data"}

    # --- Geraeteseite -----------------------------------------------------
    def touch(self, device_id):
        with self._cond:
            self._seen[device_id] = self.clock()

    def forget(self, device_id):
        """Gesperrtes oder entferntes Geraet: nicht mehr verbunden, offene Auftraege scheitern."""
        with self._cond:
            self._seen.pop(device_id, None)
            for job in self._queue.pop(device_id, []):
                job["done"], job["ok"], job["data"] = True, False, "Gerät getrennt."
            self._cond.notify_all()

    def next_job(self, device_id, wait=25):
        """Der naechste Auftrag {"id", "command", "args"} fuer das Geraet; wartet bis ``wait`` Sekunden, sonst None."""
        wait = max(0, min(float(wait), MAX_WAIT))
        deadline = self.clock() + wait
        with self._cond:
            self._seen[device_id] = self.clock()
            while True:
                queue = self._queue.get(device_id)
                if queue:
                    job = queue.pop(0)
                    job["sent"] = True
                    return {"id": job["id"], "command": job["command"], "args": job["args"]}
                remaining = deadline - self.clock()
                if remaining <= 0:
                    return None
                self._cond.wait(min(remaining, 1.0))
                self._seen[device_id] = self.clock()

    def submit(self, device_id, job_id, ok, data):
        """Ergebnis eines Auftrags. Gibt True zurueck, wenn der Auftrag zu diesem Geraet gehoerte und noch offen war."""
        with self._cond:
            self._seen[device_id] = self.clock()
            job = self._jobs.get(job_id) if isinstance(job_id, str) else None
            if job is None or job["device"] != device_id or job["done"] or not job.get("sent"):
                return False
            if ok is True:
                try:
                    job["data"] = device_commands.check_result(job["command"], data)
                    job["ok"] = True
                except device_commands.CommandError as error:
                    job["ok"], job["data"] = False, str(error)
            else:
                job["ok"], job["data"] = False, "Das Gerät konnte den Auftrag nicht ausführen."     # Text des Geraets nie weitergeben
            job["done"] = True
            self._cond.notify_all()
            return True

    # --- Serverseite --------------------------------------------------------
    def online(self, device_id=None):
        """Ist das Geraet (oder irgendeines) verbunden?"""
        return self.online_device(device_id) is not None

    def online_device(self, device_id=None):
        """Die Id des verbundenen Geraets (bei None das zuletzt gesehene), sonst None."""
        now = self.clock()
        with self._cond:
            fresh = {d: t for d, t in self._seen.items() if now - t <= ONLINE_SECONDS}
            if device_id is not None:
                return device_id if device_id in fresh else None
            return max(fresh, key=fresh.get) if fresh else None

    def request(self, command, args=None, device_id=None, timeout=None):
        """Auftrag stellen und auf das Ergebnis warten. Wirft CommandError, DeviceOffline, DeviceTimeout oder DeviceFailed."""
        args = device_commands.check_args(command, args)
        timeout = device_commands.timeout_for(command) if timeout is None else timeout
        target = self.online_device(device_id)
        if target is None:
            raise DeviceOffline("Der PC ist gerade nicht erreichbar.")
        job = {"id": secrets.token_hex(8), "device": target, "command": command, "args": args,
               "done": False, "ok": False, "data": None, "sent": False}
        with self._cond:
            queue = self._queue.setdefault(target, [])
            if len(queue) >= MAX_QUEUED:
                raise DeviceFailed("Zu viele offene Aufträge.")
            queue.append(job)
            self._jobs[job["id"]] = job
            self._cond.notify_all()
            deadline = self.clock() + timeout
            try:
                while not job["done"]:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        if job in queue:
                            queue.remove(job)
                        raise DeviceTimeout("Der PC hat nicht rechtzeitig geantwortet.")
                    self._cond.wait(min(remaining, 1.0))
            finally:
                job["done"] = True
                self._jobs.pop(job["id"], None)
        if not job["ok"]:
            raise DeviceFailed(job["data"] if isinstance(job["data"], str) else "Fehler beim Gerät.")
        return job["data"]
