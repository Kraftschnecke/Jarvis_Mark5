"""Sprachausgabe ueber OpenAI (Step 6b).

Der Browser schickt nur den Text, der vorgelesen werden soll. Welche Stimme gilt,
entscheidet der Server aus den Einstellungen (nicht der Browser). Die Stimme
erkennt selbst, ob der Text deutsch oder englisch ist.

Hinweis zum Klang: Die Anweisung beschreibt nur eine Art zu sprechen (ruhiger,
eleganter, trocken-hoeflicher Butler). Es wird keine bestimmte reale Stimme
nachgebaut.
"""

import cost_guard
from config import TTS_MODEL

# Auswahl in den Einstellungen -> Name der Stimme bei OpenAI
VOICES = {
    "Onyx (male)": "onyx",
    "Echo (male)": "echo",
    "Ash (male)": "ash",
    "Nova (female)": "nova",
    "Shimmer (female)": "shimmer",
    "Coral (female)": "coral",
}
DEFAULT_VOICE = "Onyx (male)"

MAX_TEXT_CHARS = 1200          # mehr als ein paar Saetze pro Anfrage braucht niemand
MAX_AUDIO_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 25

INSTRUCTIONS = (
    "Voice: a calm, polished, understated AI butler. Precise diction, measured pace, "
    "warm but dry and slightly witty, never theatrical. Speak in the language of the "
    "text (German or English) and keep a natural accent for that language."
)


class SpeechError(Exception):
    """Fehler mit einer Meldung, die man dem Nutzer zeigen darf."""


def prepare_text(text):
    """Pruefter Text fuer die Sprachausgabe. Kein Text oder leer -> SpeechError."""
    if not isinstance(text, str):
        raise SpeechError("Kein Text zum Vorlesen.")

    cleaned = " ".join("".join(c if c >= " " and c != "\x7f" else " " for c in text).split())

    if not cleaned:
        raise SpeechError("Kein Text zum Vorlesen.")

    return cleaned[:MAX_TEXT_CHARS]


def synthesize(client, text, voice_label):
    """MP3-Daten fuer den Text. Fehler der Anfrage werden zu SpeechError."""
    text = prepare_text(text)
    voice = VOICES.get(voice_label, VOICES[DEFAULT_VOICE])

    if client is None:
        raise SpeechError("Die Sprachausgabe ist gerade nicht verfügbar.")

    try:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            instructions=INSTRUCTIONS,
            response_format="mp3",
            timeout=REQUEST_TIMEOUT,
        )
        audio = response.content
    except cost_guard.LimitReached as error:
        raise SpeechError(str(error)) from None
    except Exception as error:
        raise SpeechError(f"Die Sprachausgabe hat nicht geklappt ({type(error).__name__}).") from None

    if not isinstance(audio, (bytes, bytearray)) or not audio or len(audio) > MAX_AUDIO_BYTES:
        raise SpeechError("Die Sprachausgabe hat keine brauchbaren Daten geliefert.")

    return bytes(audio)
