"""Tageslimit fuer kostenpflichtige Aufrufe (Mark 5, Step 1.4).

Jeder Aufruf an OpenAI kostet Geld: KI-Antworten (``responses.create``) und die Stimme
(``audio.speech.create``). Dieser Waechter sitzt direkt um den OpenAI-Client:

- VOR jedem Aufruf wird geprueft, ob das Tageslimit erreicht ist. Wenn ja: ``LimitReached``,
  der Aufruf geht gar nicht erst raus.
- NACH einem erfolgreichen Aufruf wird gezaehlt. (Fehlgeschlagene Aufrufe kosten in der Regel nichts.)
- Der Zaehler liegt in ``usage.json`` (nicht in Git), gilt pro Kalendertag (Ortszeit) und
  ueberlebt einen Neustart. Neuer Tag = Zaehler wieder bei 0.
- Limit 0 bedeutet: kein Limit. Die Limits stehen in den Einstellungen (Limits).

Grenzen: Gezaehlt werden Aufrufe, nicht Euro. Das Limit ist eine Notbremse gegen Schleifen
und Missbrauch, keine Abrechnung. Laufen zwei Programme gleichzeitig (Jarvis und der
Gastmodus), nutzen sie getrennte Zaehler-Dateien.
Neue Arten von OpenAI-Aufrufen (Bilder, Embeddings) muessen hier eingetragen werden,
sonst werden sie nicht gezaehlt.
"""

import json
import os
import threading
from datetime import date
from pathlib import Path

KINDS = ("ai", "speech")

_LABELS = {"ai": "KI-Aufrufe", "speech": "Sprachausgabe"}


class LimitReached(Exception):
    """Das Tageslimit ist erreicht. Der Text darf dem Nutzer gezeigt werden."""

    def __init__(self, kind, limit):
        self.kind = kind
        self.limit = limit
        super().__init__(
            f"Das Tageslimit für {_LABELS.get(kind, kind)} ({limit}) ist erreicht. "
            "Es gilt bis Mitternacht; du kannst es in den Einstellungen unter Limits ändern."
        )


class UsageCounter:
    """Zaehlt Aufrufe pro Tag. ``limits`` ist eine Funktion, die {"ai": n, "speech": m} liefert."""

    def __init__(self, path, limits, today=date.today):
        self.path = Path(path)
        self.limits = limits
        self.today = today
        self._lock = threading.Lock()

    def _read(self):
        today = self.today().isoformat()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            counts = data["counts"]
            if data["date"] == today and isinstance(counts, dict):
                return today, {k: counts[k] if isinstance(counts.get(k), int) and counts[k] >= 0 else 0 for k in KINDS}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return today, {k: 0 for k in KINDS}

    def _write(self, today, counts):
        temp = self.path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps({"date": today, "counts": counts}), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            pass   # ohne Schreibrecht zaehlt nur der Speicher des Servers weiter nicht: lieber weiterarbeiten

    def snapshot(self):
        with self._lock:
            today, counts = self._read()
        limits = self.limits()
        return {"date": today, **{k: counts[k] for k in KINDS}, "limits": {k: limits.get(k, 0) for k in KINDS}}

    def check(self, kind):
        """Wirft LimitReached, wenn das Limit fuer ``kind`` heute erreicht ist."""
        limit = self.limits().get(kind, 0)
        if not limit:
            return
        with self._lock:
            _, counts = self._read()
        if counts[kind] >= limit:
            raise LimitReached(kind, limit)

    def count(self, kind):
        with self._lock:
            today, counts = self._read()
            counts[kind] += 1
            self._write(today, counts)


class _Guarded:
    """Pruefen, aufrufen, zaehlen."""

    def __init__(self, target, counter, kind):
        self._target = target
        self._counter = counter
        self._kind = kind

    def create(self, *args, **kwargs):
        self._counter.check(self._kind)
        result = self._target.create(*args, **kwargs)
        self._counter.count(self._kind)
        return result


class _GuardedAudio:
    def __init__(self, audio, counter):
        self._audio = audio
        self.speech = _Guarded(audio.speech, counter, "speech")

    def __getattr__(self, name):
        return getattr(self._audio, name)


class GuardedClient:
    """Huelle um den OpenAI-Client: zaehlt und begrenzt ``responses.create`` und ``audio.speech.create``."""

    def __init__(self, client, counter):
        self._client = client
        self.counter = counter
        self.responses = _Guarded(client.responses, counter, "ai")
        self.audio = _GuardedAudio(client.audio, counter)

    def __getattr__(self, name):
        return getattr(self._client, name)


def guard(client, counter):
    return GuardedClient(client, counter)
