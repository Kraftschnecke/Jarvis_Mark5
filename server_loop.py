"""Hintergrund-Takt fuer den Server-Betrieb (Mark 5, Server S2/S3).

Am PC fragt die offene Seite jede Sekunde "gibt es etwas Neues?" und holt dabei faellige Erinnerungen, Wecker, Timer und
Hinweise ab. Auf einem Server ohne Fenster gibt es diese Seite nicht. Deshalb fragt hier ein Thread selbst nach:

  - alle FEED_SECONDS: neue Meldungen (Erinnerung, Wecker, Timer, Fokus) einsammeln und per Push schicken
  - alle HINTS_SECONDS: faellige Hinweise (Termine, Wetter) abholen, in die Meldungen legen und per Push schicken

Jede Meldung kommt aus demselben Topf wie die der Seite (BackgroundFeed): wer die Seite am Handy offen hat, sieht sie
auch dort, und nichts wird doppelt gemeldet. Wer die Hinweise abholt, bestimmt allein dieser Takt (Server-Betrieb).
Ein Fehler in einer Runde haelt den Takt nie an.
"""

import threading
import time

FEED_SECONDS = 2.0
HINTS_SECONDS = 60.0


class ServerLoop:
    def __init__(self, server, notifier, feed_seconds=FEED_SECONDS, hints_seconds=HINTS_SECONDS, clock=time.monotonic):
        self.server = server
        self.notifier = notifier
        self.feed_seconds = feed_seconds
        self.hints_seconds = hints_seconds
        self.clock = clock
        self._sent = server.feed.last          # alles Aeltere ist schon gesehen: beim Start kommt nichts nachtraeglich
        self._next_hints = 0.0
        self._stop = threading.Event()
        self._thread = None

    def tick_feed(self):
        """Neue Meldungen einsammeln und pushen. Gibt die Zahl der neuen Meldungen zurueck."""
        feed = self.server.feed
        feed.collect(self.server.jarvis)
        last, items = feed.since(self._sent)
        for item in items:
            self.notifier.send("Jarvis", item["text"], priority="high")
        self._sent = last
        return len(items)

    def tick_hints(self):
        """Faellige Hinweise abholen, in die Meldungen legen (Seite sieht sie) und pushen. Gibt die Zahl zurueck."""
        found = self.server.jarvis.proactive_hints()
        for hint in found:
            self.server.feed.add(hint["text"])
        return len(found)

    def tick(self):
        count = 0
        try:
            count += self.tick_feed()
        except Exception as error:
            print(f"[SERVER] Meldungen nicht geprueft: {type(error).__name__}")
        now = self.clock()
        if now >= self._next_hints:
            self._next_hints = now + self.hints_seconds
            try:
                self.tick_hints()
                count += self.tick_feed()           # frisch abgeholte Hinweise sofort weiterreichen
            except Exception as error:
                print(f"[SERVER] Hinweise nicht geprueft: {type(error).__name__}")
        return count

    def _run(self):
        while not self._stop.wait(self.feed_seconds):
            self.tick()

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self.server.hints_by_loop = True        # ab jetzt holt nur noch dieser Takt die Hinweise ab
            self._thread = threading.Thread(target=self._run, name="server-loop", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self.server.hints_by_loop = False
